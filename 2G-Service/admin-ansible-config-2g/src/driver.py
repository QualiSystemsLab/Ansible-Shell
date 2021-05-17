import json
from cloudshell.api.cloudshell_api import CloudShellAPISession
from cloudshell.shell.core.resource_driver_interface import ResourceDriverInterface
from cloudshell.shell.core.driver_context import InitCommandContext, ResourceCommandContext, AutoLoadResource, \
    AutoLoadAttribute, AutoLoadDetails, CancellationContext
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
            ansible_config_json = self._get_ansible_config_json(context, api, reporter, playbook_path, script_params)
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
            ansible_config_json = self._get_ansible_config_json(context, api, reporter, playbook_path, script_params,
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
            raise Exception(exc_msg)

        api.SetServiceLiveStatus(reservationId=res_id, serviceAlias=service_name, liveStatusName="Online",
                                 additionalInfo="Playbook Flow Completed")
        completed_msg = "Ansible Flow Completed for '{}'.".format(service_name)
        reporter.warn_out(completed_msg, log_only=True)
        return completed_msg

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

    def _build_repo_url(self, resource, playbook_path_input, reporter):
        """
        build URL based on hierarchy of inputs.
        1. Command inputs take precedence over service values
        2. full url on service takes precedence over base path
        3. base path concatenation last
        4. if input is not full url, then tries to concatenate with base bath on service
        :param AnsibleConfig2G resource:
        :param str playbook_path:
        :param SandboxReporter reporter:
        :return:
        """
        service_full_url = resource.playbook_url_full
        gitlab_branch = resource.gitlab_branch if resource.gitlab_branch else "master"
        base_path = resource.playbook_base_path
        service_playbook_path = resource.playbook_script_path

        # if no playbook input look for fallback values on service
        if not playbook_path_input:

            # FALLBACK TO FULL URL
            if service_full_url:
                is_gitlab_api = is_base_path_gitlab_api(service_full_url)
                if is_gitlab_api:
                    return self._append_gitlab_url_suffix(service_full_url, gitlab_branch)
                return service_full_url

            # FALLBACK TO BASE PATH
            if not base_path or not service_playbook_path:
                err_msg = "Input Error - No valid playbook inputs found"
                reporter.err_out(err_msg)
                raise ValueError(err_msg)

            if base_path.endswith("/"):
                url = base_path + service_playbook_path
            else:
                url = base_path + "/" + service_playbook_path

            is_gitlab_api = is_base_path_gitlab_api(base_path)
            if is_gitlab_api:
                return self._append_gitlab_url_suffix(url, gitlab_branch)
            return url

        # COMMAND INPUT EXISTS

        # if playbook path input begins with a protocol then treat as full url
        if self._is_path_supported_protocol(playbook_path_input):
            is_gitlab_api = is_base_path_gitlab_api(playbook_path_input)
            if is_gitlab_api:
                return self._append_gitlab_url_suffix(playbook_path_input, gitlab_branch)
            return playbook_path_input

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

        is_gitlab_api = is_base_path_gitlab_api(url)
        if is_gitlab_api:
            return url + "/raw?ref={}".format(gitlab_branch)

        return url

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
                                 infrastructure_resources=None):
        """
        :param ResourceCommandContext context:
        :param SandboxReporter reporter:
        :param infrastructure_resources:
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

        # FIND LINKED HOSTS: CONNECTORS + ATTRIBUTES
        """
        Infrastructure resource command will ignore the connectors and linked attribute resources
        Connector and linked resources will be merged into a set and run together
        """

        # get host details from connectors
        connectors = context.connectors

        if infrastructure_resources:
            target_host_resources = infrastructure_resources
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

        # default host inputs
        # take command input, fallback to service values
        if script_params:
            default_script_params = build_params_list(script_params)
        elif service_script_parameters:
            default_script_params = build_params_list(service_script_parameters)
        else:
            default_script_params = []

        # repo details
        ansi_conf.repositoryDetails.url = self._build_repo_url(resource, playbook_path, reporter)
        ansi_conf.repositoryDetails.username = resource.repo_user
        password_val = api.DecryptPassword(resource.repo_password).Value
        ansi_conf.repositoryDetails.password = password_val if password_val else None
        enc_token = resource.repo_token
        ansi_conf.repositoryDetails.token = api.DecryptPassword(enc_token).Value

        # START POPULATING HOSTS
        missing_credential_hosts = []
        for curr_resource_obj in target_host_resources:
            curr_resource_name = curr_resource_obj.Name
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

            # INVENTORY GROUPS - NEEDS TO BE A LIST OR NULL/NONE
            resource_ansible_group_attr = get_resource_attribute_gen_agostic(INVENTORY_GROUP_PARAM, attrs)
            if resource_ansible_group_attr:
                if resource_ansible_group_attr.Value:
                    groups_str = resource_ansible_group_attr.Value
                else:
                    groups_str = service_inventory_groups
            else:
                groups_str = service_inventory_groups

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

            ansi_conf.hostsDetails.append(host_conf)

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
        curr_token = new_obj["repositoryDetails"]["token"]
        if curr_password:
            new_obj["repositoryDetails"]["password"] = "*******"
        if curr_token :
            new_obj["repositoryDetails"]["token"] = "*******"
        json_copy = json.dumps(new_obj, indent=4)
      #  reporter.info_out("=== Ansible Configuration JSON ===\n{}".format(json_copy), log_only=True)

        return ansi_conf_json

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
