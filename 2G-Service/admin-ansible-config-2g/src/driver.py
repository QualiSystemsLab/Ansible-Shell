import json
from cloudshell.api.cloudshell_api import CloudShellAPISession, ResourceInfo
from cloudshell.shell.core.resource_driver_interface import ResourceDriverInterface
from cloudshell.shell.core.driver_context import InitCommandContext, ResourceCommandContext, AutoLoadResource, \
    AutoLoadAttribute, AutoLoadDetails, CancellationContext

from ansible_config_from_cached_json import get_cached_ansible_config_from_json, get_cached_repo_data, \
    get_cached_inventory_groups, PlaybookRepository
from data_model import *  # run 'shellfoundry generate' to generate data model classes
from cloudshell.shell.core.session.cloudshell_session import CloudShellSessionContext
from cloudshell.shell.core.driver_context import Connector
from cloudshell.cm.ansible.ansible_shell import AnsibleShell
from helper_code.sandbox_reporter import SandboxReporter
from helper_code.shell_connector_helpers import get_connector_endpoints
from helper_code.resource_helpers import get_resource_attribute_gen_agostic
from helper_code.parse_script_params import build_params_list
from helper_code.gitlab_api_url_validator import is_base_path_gitlab_api
from helper_code.validate_protocols import is_path_supported_protocol
from cloudshell.core.logger.qs_logger import get_qs_logger
from ansible_configuration import AnsibleConfiguration, HostConfiguration
from get_resource_from_context import get_resource_from_context


# HOST OVERRIDE PARAMS - IF PRESENT ON RESOURCE THEY WILL OVERRIDE THE SERVICE DEFAULT
# TO BE CREATED IN SYSTEM AS GLOBAL ATTRIBUTE
ACCESS_KEY_PARAM = "Access Key"
CONNECTION_METHOD_PARAM = "Connection Method"
SCRIPT_PARAMS_PARAM = "Script Parameters"
INVENTORY_GROUP_PARAM = "Inventory Groups"
CONNECTION_SECURED_PARAM = "Connection Secured"


class AdminAnsibleConfig2GDriver(ResourceDriverInterface):

    def __init__(self):
        """
        ctor must be without arguments, it is created with reflection at run time
        """
        self.first_gen_ansible_shell = AnsibleShell()
        self.supported_protocols = ["http", "https"]
        pass

    def initialize(self, context):
        """
        Initialize the driver session, this function is called everytime a new instance of the driver is created
        This is a good place to load and cache the driver configuration, initiate sessions etc.
        :param InitCommandContext context: the context the command runs on
        """
        pass

    def execute_playbook(self, context, cancellation_context, playbook_path, script_params):
        """
        :param ResourceCommandContext context:
        :param CancellationContext cancellation_context:
        :return:
        """
        api = CloudShellSessionContext(context).get_api()
        res_id = context.reservation.reservation_id
        reporter = self._get_sandbox_reporter(context, api)
        service_name = context.resource.name

        try:
            ansible_config_json, resource_names = self._get_ansible_config_json(context, api, reporter, playbook_path,
                                                                                script_params)
        except Exception as e:
            exc_msg = "Error building playbook request on '{}': {}".format(service_name, str(e))
            reporter.exc_out(exc_msg)
            api.SetServiceLiveStatus(reservationId=res_id, serviceAlias=service_name, liveStatusName="Error",
                                     additionalInfo=str(e))
            raise Exception(exc_msg)

        reporter.info_out("'{}' is Executing Ansible Playbook...".format(context.resource.name))
        try:
            self.first_gen_ansible_shell.execute_playbook(context, ansible_config_json, cancellation_context)
        except Exception as e:
            exc_msg = "Error running playbook on '{}': {}".format(service_name, str(e))
            reporter.exc_out(exc_msg)
            api.SetServiceLiveStatus(reservationId=res_id, serviceAlias=service_name, liveStatusName="Error",
                                     additionalInfo=str(e))
            for name in resource_names:
                api.SetResourceLiveStatus(resourceFullName=name, liveStatusName="Error",
                                          additionalInfo=str(e))
            raise Exception(exc_msg)

        api.SetServiceLiveStatus(reservationId=res_id, serviceAlias=service_name, liveStatusName="Online",
                                 additionalInfo="Playbook Flow Completed")
        completed_msg = "Ansible Flow Completed for '{}'.".format(context.resource.name)
        reporter.warn_out(completed_msg, log_only=True)
        return completed_msg

    @staticmethod
    def _get_infrastructure_resources(comma_separated_input, service_name, api, reporter):
        """

        :param CloudShellAPISession api:
        :param str comma_separated_input:
        :return:
        """
        if not comma_separated_input:
            raise Exception("infrastructure_resources argument must be passed")

        resource_names = [x.strip() for x in comma_separated_input.split(",")]

        resources = []
        for name in resource_names:
            try:
                resource_details = api.GetResourceDetails(name)
            except Exception as e:
                exc_msg = "'{}' Input Error. '{}' is not a resource. Must connect to root resource".format(service_name,
                                                                                                           name)
                reporter.err_out(exc_msg)
                raise Exception(exc_msg)
            resources.append(resource_details)
        return resources

    def execute_infrastructure_playbook(self, context, cancellation_context, infrastructure_resources, playbook_path,
                                        script_params):
        """
        :param ResourceCommandContext context:
        :param CancellationContext cancellation_context:
        :return:
        """
        api = CloudShellSessionContext(context).get_api()
        res_id = context.reservation.reservation_id
        reporter = self._get_sandbox_reporter(context, api)
        service_name = context.resource.name
        resources = self._get_infrastructure_resources(infrastructure_resources, service_name, api, reporter)

        reporter.info_out("'{}' is Executing Ansible Playbook...".format(context.resource.name))
        try:
            ansible_config_json, resource_names = self._get_ansible_config_json(context, api, reporter, playbook_path,
                                                                                script_params,
                                                                                resources)
        except Exception as e:
            exc_msg = "Error building playbook request on '{}': {}".format(service_name, str(e))
            reporter.exc_out(exc_msg)
            api.SetServiceLiveStatus(reservationId=res_id, serviceAlias=service_name, liveStatusName="Error",
                                     additionalInfo=str(e))
            raise Exception(exc_msg)

        try:
            self.first_gen_ansible_shell.execute_playbook(context, ansible_config_json, cancellation_context)
        except Exception as e:
            exc_msg = "Error running playbook on '{}': {}".format(service_name, str(e))
            reporter.err_out(exc_msg)
            api.SetServiceLiveStatus(reservationId=res_id, serviceAlias=service_name, liveStatusName="Error",
                                     additionalInfo=str(e))
            for name in resource_names:
                api.SetResourceLiveStatus(resourceFullName=name, liveStatusName="Error",
                                          additionalInfo=str(e))
            raise Exception(exc_msg)

        api.SetServiceLiveStatus(reservationId=res_id, serviceAlias=service_name, liveStatusName="Online",
                                 additionalInfo="Playbook Flow Completed")
        completed_msg = "Ansible Flow Completed for '{}'.".format(service_name)
        reporter.warn_out(completed_msg, log_only=True)
        return completed_msg

    @staticmethod
    def _get_inventory_resources(api, res_id, inventory_only_bool):
        """

        :param CloudShellAPISession api:
        :param str res_id:
        :param bool inventory_only_bool:
        :return:
        :rtype list[ResourceInfo]:
        """
        res_details = api.GetReservationDetails(res_id, True).ReservationDescription
        all_resources = res_details.Resources
        root_resources = [x for x in all_resources if "/" not in x.Name]
        sandbox_data = api.GetSandboxData(res_id).SandboxDataKeyValues

        target_resources = []
        for curr_resource in root_resources:
            details = api.GetResourceDetails(curr_resource.Name)
            if not inventory_only_bool:
                target_resources.append(details)
                continue
            attrs = details.ResourceAttributes
            inventory_groups_attr_search = [x for x in attrs if x.Name.lower() == INVENTORY_GROUP_PARAM.lower()]
            if inventory_groups_attr_search:
                inventory_group_val = inventory_groups_attr_search[0].Value
                if inventory_group_val:
                    target_resources.append(details)
                    continue
            matching_sb_data_key = [x for x in sandbox_data if x.Key == "ansible_{}".format(curr_resource.Name)]
            if matching_sb_data_key:
                cached_data_json = matching_sb_data_key[0].Value
                cached_ansi_config = get_cached_ansible_config_from_json(cached_data_json)
                cached_params = cached_ansi_config.hosts_conf[0].parameters
                cached_inventory_groups = cached_params.get("INVENTORY_GROUPS")
                if cached_inventory_groups:
                    target_resources.append(details)

        return target_resources

    def _is_path_supported_protocol(self, path):
        return is_path_supported_protocol(path, self.supported_protocols)

    @staticmethod
    def _append_gitlab_url_suffix(url, branch):
        """
        :param str url:
        :param str branch:
        :return:
        """
        raw_url_suffix = "/raw?"
        if raw_url_suffix not in url.lower():
            url += "/raw?ref={}".format(branch)
        return url

    def _build_repo_url(self, resource, playbook_path_input, cached_repo_data, reporter):
        """
        build URL based on hierarchy of inputs.
        1. Command inputs take precedence over service values
        2. full url on service takes precedence over base path
        3. base path concatenation last
        4. if input is not full url, then tries to concatenate with base bath on service
        :param AnsibleConfig2G resource:
        :param PlaybookRepository cached_repo_data:
        :param str playbook_path_input:
        :param SandboxReporter reporter:
        :return:
        """
        service_full_url = resource.playbook_url_full
        gitlab_branch = resource.gitlab_branch if resource.gitlab_branch else "master"
        base_path = resource.playbook_base_path
        service_playbook_path = resource.playbook_script_path
        cached_playbook_path = cached_repo_data.url if cached_repo_data else None

        # if no playbook input look for fallback values on service
        if not playbook_path_input:

            # FALLBACK TO FULL URL
            if service_full_url:
                is_gitlab_api = is_base_path_gitlab_api(service_full_url.strip())
                if is_gitlab_api:
                    return self._append_gitlab_url_suffix(service_full_url, gitlab_branch), False
                return service_full_url, False

            # FALLBACK TO BASE PATH
            if not base_path or not service_playbook_path:
                if cached_playbook_path:
                    return cached_playbook_path, True
                err_msg = "Input Error - No valid playbook inputs found"
                reporter.err_out(err_msg)
                raise ValueError(err_msg)

            if base_path.endswith("/"):
                url = base_path + service_playbook_path
            else:
                url = base_path + "/" + service_playbook_path

            is_gitlab_api = is_base_path_gitlab_api(base_path.strip())
            if is_gitlab_api:
                return self._append_gitlab_url_suffix(url, gitlab_branch), False
            return url, False

        # COMMAND INPUT EXISTS

        # if playbook path input begins with a protocol then treat as full url
        if self._is_path_supported_protocol(playbook_path_input):
            is_gitlab_api = is_base_path_gitlab_api(playbook_path_input.strip())
            if is_gitlab_api:
                return self._append_gitlab_url_suffix(playbook_path_input, gitlab_branch), False
            return playbook_path_input, False

        # check that base path is populated
        if not base_path:
            err_msg = "Input Error - Repo Base Path not populated when using short path input"
            reporter.err_out(err_msg)
            raise ValueError(err_msg)

        # validate base path includes protocol
        if not self._is_path_supported_protocol(base_path):
            err_msg = "Input Error - Base Path does not begin with valid protocol. Supported: {}".format(
                self.supported_protocols)
            reporter.err_out(err_msg)
            raise ValueError(err_msg)

        if base_path.endswith("/"):
            url = base_path + playbook_path_input
        else:
            url = base_path + "/" + playbook_path_input

        is_gitlab_api = is_base_path_gitlab_api(url.strip())
        if is_gitlab_api:
            return url + "/raw?ref={}".format(gitlab_branch), False

        return url, False

    @staticmethod
    def _get_resources_from_connectors(connectors, service_name, api, reporter):
        """
        :param list[Connector] connectors:
        :param str service_name:
        :param CloudShellAPISession api:
        :param SandboxReporter reporter:
        :return:
        """
        connector_endpoints = get_connector_endpoints(service_name, connectors)

        # get connected resource names
        resource_detail_objects = []
        for resource_name in connector_endpoints:
            try:
                resource_details = api.GetResourceDetails(resource_name)
            except Exception as e:
                warn_msg = "Connected component '{}' is not a resource: {}".format(resource_name, str(e))
                reporter.warn_out(warn_msg)
            else:
                resource_detail_objects.append(resource_details)
        return resource_detail_objects

    @staticmethod
    def _get_selector_linked_resources(selector_value, api, res_id):
        """
        scan sandbox and find resources with matching selector value
        :param str selector_value:
        :param CloudShellAPISession api:
        :param res_id:
        :return:
        """
        if not selector_value:
            return []

        all_resources = api.GetReservationDetails(reservationId=res_id).ReservationDescription.Resources
        selector_linked_resources = []
        for resource in all_resources:
            details = api.GetResourceDetails(resource.Name)
            attrs = details.ResourceAttributes
            attr_search = [x for x in attrs if x.Name == "Ansible Config Selector"]
            if attr_search:
                attr_val = attr_search[0].Value
                if attr_val and attr_val.lower() == selector_value.lower():
                    selector_linked_resources.append(resource.Name)
        return selector_linked_resources

    def _get_ansible_config_json(self, context, api, reporter, playbook_path, script_params,
                                 supplied_resources=None, is_global_inventory_cmd=False):
        """
        :param ResourceCommandContext context:
        :param SandboxReporter reporter:
        :param list[ResourceInfo] supplied_resources: resources obtained from method other than connectors logic
        :param CloudShellAPISession api:
        :return:
        """
        resource = get_resource_from_context(context)
        service_name = context.resource.name
        service_connection_method = resource.connection_method
        service_inventory_groups = resource.inventory_groups
        service_script_parameters = resource.script_parameters
        service_additional_args = resource.ansible_cmd_args
        service_timeout_minutes = resource.timeout_minutes
        res_id = context.reservation.reservation_id
        config_selector = resource.ansible_config_selector
        inventory_only_bool = True if resource.only_inventory_groups == "True" else False


        # FIND LINKED HOSTS: CONNECTORS + ATTRIBUTES
        """
        Infrastructure resource command + Inventory Command will ignore the connectors and linked attribute resources
        They pass in their own 'supplied_resources'
        Connector + attribute linked resources will be merged into a set and run together
        """

        # get host details from connectors
        connectors = context.connectors

        if supplied_resources:
            # INFRASTRUCTURE COMMAND RESOURCES
            target_host_resources = supplied_resources
        elif not connectors and not config_selector:
            # INVENTORY COMMAND FLOW
            if inventory_only_bool:
                reporter.info_out("{} Inventory Playbook against resources with 'Inventory Groups' populated.".format(service_name))
            else:
                reporter.info_out("{} Inventory Playbook against ALL resources on canvas".format(service_name))
            target_host_resources = self._get_inventory_resources(api, res_id, inventory_only_bool)
        else:
            connector_resources = self._get_resources_from_connectors(connectors, resource.name, api, reporter)
            connector_resource_names = [x.Name for x in connector_resources]
            selector_linked_resources = self._get_selector_linked_resources(config_selector, api, res_id)
            all_linked_resources = connector_resource_names + selector_linked_resources
            if not all_linked_resources:
                exc_msg = "No target hosts linked to Service '{}'!".format(service_name)
                reporter.err_out(exc_msg)
                raise Exception(exc_msg)
            target_host_resource_names = list(set(all_linked_resources))
            target_host_resources = [api.GetResourceDetails(x) for x in target_host_resource_names]

        # INITIALIZE DATA MODEL AND START POPULATING
        ansi_conf = AnsibleConfiguration()
        ansi_conf.additionalArgs = service_additional_args if service_additional_args else None
        ansi_conf.timeoutMinutes = int(service_timeout_minutes) if service_timeout_minutes else 0

        # TAKE COMMAND ARGS AS PRIORITY, FALLBACK TO SERVICE VALUES
        if script_params:
            default_script_params = build_params_list(script_params)
        elif service_script_parameters:
            default_script_params = build_params_list(service_script_parameters)
        else:
            default_script_params = []

        # NO URL SUPPLIED + MULTIPLE TARGET HOSTS NOT SUPPORTED
        if not playbook_path and not resource.playbook_url_full and not resource.playbook_base_path:
            if len(target_host_resources) > 1:
                raise Exception("Can not run 'cached' playbook against multiple hosts. Not supported.")

        cached_repo_data = None

        # START POPULATING HOSTS
        missing_credential_hosts = []
        for curr_resource_obj in target_host_resources:
            curr_resource_name = curr_resource_obj.Name

            # GET CACHED SANDBOX DATA
            sandbox_data = api.GetSandboxData(res_id).SandboxDataKeyValues
            matching_sb_data = [x for x in sandbox_data
                                if "ansible_{}".format(curr_resource_name) == x.Key]
            if matching_sb_data:
                cached_resource_data_json = matching_sb_data[0].Value
                cached_ansible_conf = get_cached_ansible_config_from_json(cached_resource_data_json)
            else:
                reporter.warn_out("No cached data for '{}'".format(curr_resource_name))
                cached_ansible_conf = None

            if cached_ansible_conf and len(target_host_resources) == 1:
                cached_repo_data = get_cached_repo_data(cached_ansible_conf)

            # START BUILDING REQUEST
            host_conf = HostConfiguration()
            host_conf.ip = curr_resource_obj.Address
            attrs = curr_resource_obj.ResourceAttributes

            user_attr = get_resource_attribute_gen_agostic("User", attrs)
            user_attr_val = user_attr.Value if user_attr else ""
            host_conf.username = user_attr_val

            password_attr = get_resource_attribute_gen_agostic("Password", attrs)
            encrypted_password_val = password_attr.Value
            host_conf.password = encrypted_password_val

            # OVERRIDE SERVICE ATTRIBUTES IF ATTRIBUTES EXIST ON RESOURCE
            # ACCESS KEY
            access_key_attr = get_resource_attribute_gen_agostic(ACCESS_KEY_PARAM, attrs)
            encrypted_acces_key_val = access_key_attr.Value if access_key_attr else None
            host_conf.accessKey = encrypted_acces_key_val

            # VALIDATE HOST CREDENTIALS - NEED USER AND PASSWORD/ACCESS KEY
            if user_attr_val:
                decrypted_password = api.DecryptPassword(encrypted_password_val).Value
                if encrypted_acces_key_val:
                    decrypted_access_key = api.DecryptPassword(encrypted_acces_key_val).Value
                else:
                    decrypted_access_key = None
                if not decrypted_password and not decrypted_access_key:
                    missing_credential_hosts.append((curr_resource_name, "Empty Credentials Attribute on Resource"))
            else:
                missing_credential_hosts.append((curr_resource_name, "Empty User Attribute on Resource"))

            # INVENTORY GROUPS
            cached_inventory_groups_str = get_cached_inventory_groups(cached_ansible_conf) if cached_ansible_conf else None

            # FOR CONNNECTORS FLOW SERVICE VALUE BROADCASTS, FOR 'GLOBAL' INVENTORY COMMAND NOT DESIRED BEHAVIOR
            resource_ansible_group_attr = get_resource_attribute_gen_agostic(INVENTORY_GROUP_PARAM, attrs)
            if resource_ansible_group_attr:
                if resource_ansible_group_attr.Value:
                    groups_str = resource_ansible_group_attr.Value
                else:
                    if is_global_inventory_cmd:
                        groups_str = None
                    else:
                        groups_str = service_inventory_groups
            else:
                if cached_inventory_groups_str:
                    groups_str = cached_inventory_groups_str
                else:
                    if is_global_inventory_cmd:
                        groups_str = None
                    else:
                        groups_str = service_inventory_groups

            # INVENTORY GROUPS - NEEDS TO BE A LIST OR NULL/NONE TO FULFILL JSON STRUCTURE CONTRACT WITH PACKAGE
            if groups_str:
                inventory_groups_list = groups_str.strip().split(",")
            else:
                inventory_groups_list = None
            host_conf.groups = inventory_groups_list

            # CONNECTION METHOD
            resource_connection_method = None
            connection_method_attr = get_resource_attribute_gen_agostic(CONNECTION_METHOD_PARAM, attrs)
            if connection_method_attr:
                connection_val = connection_method_attr.Value
                if connection_val:
                    if connection_val.lower() not in ["na", "n/a"]:
                        resource_connection_method = connection_val

            if resource_connection_method:
                host_conf.connectionMethod = resource_connection_method
            else:
                host_conf.connectionMethod = service_connection_method

            # CONNECTION SECURED
            connection_secured_attr = get_resource_attribute_gen_agostic(CONNECTION_SECURED_PARAM, attrs)
            if connection_secured_attr:
                host_conf.connectionSecured = True if connection_secured_attr.Value.lower() == "true" else False
            else:
                host_conf.connectionSecured = False

            # SCRIPT PARAMS
            script_params_attr = get_resource_attribute_gen_agostic(SCRIPT_PARAMS_PARAM, attrs)
            if script_params_attr:
                if script_params_attr.Value:
                    host_conf.parameters = build_params_list(script_params_attr.Value)
                else:
                    host_conf.parameters = default_script_params
            else:
                host_conf.parameters = default_script_params

            # MERGE CACHED APP PARAMS - SERVICE LEVEL PARAMS WIN IN CASE OF CONFLICT
            if cached_ansible_conf:
                cached_params_dict = cached_ansible_conf.hosts_conf[0].parameters
                cached_params_list = []
                service_params_copy = host_conf.parameters[:]
                for cached_key, cached_val in cached_params_dict.iteritems():
                    if cached_val:
                        for service_param in service_params_copy:
                            service_key = service_param["name"]
                            service_val = service_param["value"]
                            if service_key == cached_key:
                                if not service_val:
                                    cached_params_list.append({"name": cached_key, "value": cached_val})
                                    continue
                                else:
                                    continue
                        cached_params_list.append({"name": cached_key, "value": cached_val})
                host_conf.parameters.extend(cached_params_list)

            ansi_conf.hostsDetails.append(host_conf)

        # REPO DETAILS
        repo_url, is_cached_url = self._build_repo_url(resource, playbook_path, cached_repo_data, reporter)
        ansi_conf.repositoryDetails.url = repo_url
        if is_cached_url:
            ansi_conf.repositoryDetails.username = cached_repo_data.username
            ansi_conf.repositoryDetails.password = cached_repo_data.password
        else:
            ansi_conf.repositoryDetails.username = resource.repo_user
            password_val = api.DecryptPassword(resource.repo_password).Value
            ansi_conf.repositoryDetails.password = password_val if password_val else None

        if missing_credential_hosts:
            missing_json = json.dumps(missing_credential_hosts, indent=4)
            warning_msg = "=== '{}' Connected Hosts Missing Credentials ===\n{}".format(service_name, missing_json)
            reporter.info_out(warning_msg)
            err_msg = "Missing credentials on target hosts. See console / logs for info."
            raise Exception(err_msg)

        # REPORT TARGET RESOURCES
        resource_names = [x.Name for x in target_host_resources]
        start_msg = "'{}' Target Hosts :\n{}".format(service_name, json.dumps(resource_names, indent=4))
        reporter.info_out(start_msg)

        ansi_conf_json = ansi_conf.get_pretty_json()

        # hide repo password in json printout
        new_obj = json.loads(ansi_conf_json)
        curr_password = new_obj["repositoryDetails"]["password"]
        if curr_password:
            new_obj["repositoryDetails"]["password"] = "*******"
        json_copy = json.dumps(new_obj, indent=4)
        reporter.info_out("=== Ansible Configuration JSON ===\n{}".format(json_copy), log_only=True)

        return ansi_conf_json, resource_names

    @staticmethod
    def _get_sandbox_reporter(context, api):
        """
        helper method to get sandbox reporter instance
        :param ResourceCommandContext context:
        :param CloudShellAPISession api:
        :return:
        """
        res_id = context.reservation.reservation_id
        model = context.resource.model
        service_name = context.resource.name
        logger = get_qs_logger(log_group=res_id, log_category=model, log_file_prefix=service_name)
        reporter = SandboxReporter(api, res_id, logger)
        return reporter

    def cleanup(self):
        """
        Destroy the driver session, this function is called everytime a driver instance is destroyed
        This is a good place to close any open sessions, finish writing to log files
        """
        pass
