import json
from cloudshell.core.logger.qs_logger import get_qs_logger
from cs_ansible_second_gen.commands.utility.gitlab_api_url_validator import is_base_path_gitlab_api
from cs_ansible_second_gen.commands.utility.parse_script_params import build_params_list
from cs_ansible_second_gen.commands.utility.resource_helpers import get_resource_attribute_gen_agostic
from cs_ansible_second_gen.commands.utility.sandbox_reporter import SandboxReporter
from cs_ansible_second_gen.commands.utility.shell_connector_helpers import get_connector_endpoints
from cs_ansible_second_gen.commands.utility.validate_protocols import is_path_supported_protocol
from cs_ansible_second_gen.exceptions.exceptions import AnsibleSecondGenServiceException
from cs_ansible_second_gen.models.ansible_config_from_cached_json import get_cached_ansible_config_from_json, \
    get_cached_mgmt_pb_inventory_groups_list, get_cached_user_pb_inventory_groups_str, CachedPlaybookRepoDecryptedPassword
from cs_ansible_second_gen.models.ansible_configuration_request import AnsibleConfigurationRequest2G, \
    GenericAnsibleServiceData, HostConfigurationRequest2G
from cs_ansible_second_gen.service_globals import user_pb_params, override_attributes


class AnsibleSecondGenLogic(object):
    def __init__(self):
        pass

    def get_linked_resources(self, api, service_name, res_id, connectors, config_selector, reporter):
        """
        find resources connected by connector or linked by matching selector attribute and combine
        :param api:
        :param service_name:
        :param res_id:
        :param connectors:
        :param config_selector:
        :param reporter:
        :return:
        """
        connector_resources = self._get_resources_from_connectors(api, service_name, connectors, reporter)
        connector_resource_names = [x.Name for x in connector_resources]
        selector_linked_resource_names = self._get_selector_linked_resource_names(api, res_id, config_selector)
        all_linked_resources = connector_resource_names + selector_linked_resource_names

        if not all_linked_resources:
            exc_msg = "No target hosts linked to Service '{}'.".format(service_name)
            reporter.err_out(exc_msg)
            raise AnsibleSecondGenServiceException(exc_msg)

        target_host_resource_names = list(set(all_linked_resources))
        target_host_resources = [api.GetResourceDetails(x) for x in target_host_resource_names]
        return target_host_resources

    @staticmethod
    def get_canvas_resources(api, res_id, service_name, service_inventory_groups, reporter):
        """
        find resources for "global" playbook execution. run against all resources without connections
        inventory_only boolean targets only the resources with "inventory groups" populated.
        This can come from resource attribute, or custom param value on cached user playbook data
        :param CloudShellAPISession api:
        :param SandboxReporter reporter:
        :param str res_id:
        :param str service_name:
        :param str service_inventory_groups:
        :return:
        :rtype list[ResourceInfo]:
        """
        res_details = api.GetReservationDetails(res_id, True).ReservationDescription
        all_resources = res_details.Resources
        root_resources = [x for x in all_resources if "/" not in x.Name]

        sandbox_data = api.GetSandboxData(res_id).SandboxDataKeyValues

        if not service_inventory_groups:
            reporter.info_out("{} running against ALL canvas resources..".format(service_name))
        else:
            reporter.info_out("{} running against matching inventory groups '{}'..".format(service_name,
                                                                                           service_inventory_groups))

        target_resources = []
        for curr_resource in root_resources:
            details = api.GetResourceDetails(curr_resource.Name)

            # IF SERVICE INVENTORY GROUPS ATTR NOT POPULATED THEN COLLECT ALL RESOURCES
            if not service_inventory_groups:
                target_resources.append(details)
                continue

            # OTHERWISE LOOK ONLY FOR RESOURCES WITH MATCHING INVENTORY GROUPS VALUE
            # CHECK THE LOGICAL RESOURCE FIRST AND THEN CACHED USER DATA
            attrs = details.ResourceAttributes
            inventory_groups_attr_search = [x for x in attrs
                                            if x.Name.lower() == user_pb_params.INVENTORY_GROUPS_PARAM.lower()]
            if inventory_groups_attr_search:
                inventory_group_val = inventory_groups_attr_search[0].Value
                if service_inventory_groups in inventory_group_val:
                    target_resources.append(details)
                    continue

            matching_sb_data_key = [x for x in sandbox_data if x.Key == "ansible_{}".format(curr_resource.Name)]
            if matching_sb_data_key:
                cached_data_json = matching_sb_data_key[0].Value
                cached_ansi_config = get_cached_ansible_config_from_json(cached_data_json)
                cached_params = cached_ansi_config.hosts_conf[0].parameters
                cached_inventory_groups = cached_params.get("INVENTORY_GROUPS")
                if service_inventory_groups in cached_inventory_groups:
                    target_resources.append(details)

        return target_resources

    @staticmethod
    def get_infrastructure_resources(comma_separated_input, service_name, api, reporter):
        """

        :param CloudShellAPISession api:
        :param str comma_separated_input:
        :param str service_name:
        :param SandboxReporter reporter:
        :return:
        """
        if not comma_separated_input:
            raise AnsibleSecondGenServiceException("infrastructure_resources argument must be passed")

        resource_names = [x.strip() for x in comma_separated_input.split(",")]

        resources = []
        for name in resource_names:
            try:
                resource_details = api.GetResourceDetails(name)
            except Exception as e:
                exc_msg = "'{}' Input Error. '{}' is not a resource. Must connect to root resource: {}".format(
                    service_name,
                    name,
                    str(e))
                reporter.err_out(exc_msg)
                raise AnsibleSecondGenServiceException(exc_msg)
            resources.append(resource_details)
        return resources

    @staticmethod
    def get_user_pb_target_resource_from_alias(service_name, api, reporter):
        """

        :param CloudShellAPISession api:
        :param str service_name:
        :param SandboxReporter reporter:
        :return:
        """
        if not service_name:
            raise AnsibleSecondGenServiceException("User Playbook Alias is not populated")

        if not service_name.startswith("PB_"):
            raise AnsibleSecondGenServiceException(
                "User Playbook alias does not start wit PB. Current Alias: {}".format(service_name))

        resource_name = service_name.split("PB_")[1]

        # validate that resource name is real
        try:
            resource_details = api.GetResourceDetails(resource_name)
        except Exception as e:
            exc_msg = "Failed API Call. '{}' is not a real resource: {}".format(resource_name,
                                                                                str(e))
            reporter.err_out(exc_msg)
            raise AnsibleSecondGenServiceException(exc_msg)

        return resource_details

    @staticmethod
    def get_cached_ansi_conf_from_resource_name(resource_name, sandbox_data):
        """
        :param str resource_name:
        :param list[SandboxDataKeyValueInfo] sandbox_data:
        :return:
        """
        matching_sb_data = [x for x in sandbox_data
                            if "ansible_{}".format(resource_name) == x.Key]
        if matching_sb_data:
            cached_resource_data_json = matching_sb_data[0].Value
            cached_ansible_conf = get_cached_ansible_config_from_json(cached_resource_data_json)
            return cached_ansible_conf
        return None

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

    def build_repo_url(self, service_full_url, service_url_base_path, service_pb_relative_path, input_playbook_path,
                       supported_protocols, reporter, gitlab_branch="master"):
        """
        build URL based on hierarchy of inputs.
        1. Command inputs take precedence over service values
        2. full url on service takes precedence over base path
        3. base path concatenation last
        4. if input is not full url, then tries to concatenate with base bath on service
        :param str service_full_url:
        :param str service_url_base_path: base path of repo
        :param str service_pb_relative_path: path to script from base path, simple concatenation
        :param str input_playbook_path: from user input on command, override service attribute
        :param list[str] supported_protocols:
        :param SandboxReporter reporter:
        :param str gitlab_branch: concatenates
        :return:
        """
        # if no playbook input look for fallback values on service
        if not input_playbook_path:

            # FALLBACK TO FULL URL
            if service_full_url:
                is_gitlab_api = is_base_path_gitlab_api(service_full_url.strip())
                if is_gitlab_api:
                    return self._append_gitlab_url_suffix(service_full_url, gitlab_branch)
                return service_full_url

            # FALLBACK TO BASE PATH
            if not service_url_base_path or not service_pb_relative_path:
                err_msg = "Input Error - No valid playbook inputs found"
                reporter.err_out(err_msg)
                raise AnsibleSecondGenServiceException(err_msg)

            if service_url_base_path.endswith("/"):
                url = service_url_base_path + service_pb_relative_path
            else:
                url = service_url_base_path + "/" + service_pb_relative_path

            is_gitlab_api = is_base_path_gitlab_api(service_url_base_path.strip())
            if is_gitlab_api:
                return self._append_gitlab_url_suffix(url, gitlab_branch)
            return url

        # === COMMAND INPUT EXISTS ===

        # if playbook path input begins with a protocol then treat as full url
        if is_path_supported_protocol(input_playbook_path, supported_protocols):
            is_gitlab_api = is_base_path_gitlab_api(input_playbook_path.strip())
            if is_gitlab_api:
                return self._append_gitlab_url_suffix(input_playbook_path, gitlab_branch)
            return input_playbook_path

        # check that base path is populated
        if not service_url_base_path:
            err_msg = "Input Error - Repo Base Path not populated when using short path input"
            reporter.err_out(err_msg)
            raise ValueError(err_msg)

        # validate base path includes protocol
        if not is_path_supported_protocol(service_url_base_path, supported_protocols):
            err_msg = "Input Error - Base Path does not begin with valid protocol. Supported: {}".format(
                supported_protocols)
            reporter.err_out(err_msg)
            raise ValueError(err_msg)

        if service_url_base_path.endswith("/"):
            url = service_url_base_path + input_playbook_path
        else:
            url = service_url_base_path + "/" + input_playbook_path

        is_gitlab_api = is_base_path_gitlab_api(url.strip())
        if is_gitlab_api:
            return url + "/raw?ref={}".format(gitlab_branch)

        return url

    def get_repo_details(self, api, playbook_path, reporter, service_data, supported_protocols):
        """
        :param api:
        :param playbook_path:
        :param reporter:
        :param service_data:
        :param list[str] supported_protocols:
        :return:
        """
        repo_user = service_data.repo_user
        repo_password = api.DecryptPassword(service_data.repo_password).Value
        repo_url = self.build_repo_url(service_full_url=service_data.repo_url,
                                       service_url_base_path=service_data.repo_base_path,
                                       service_pb_relative_path=service_data.repo_script_path,
                                       input_playbook_path=playbook_path,
                                       supported_protocols=supported_protocols,
                                       reporter=reporter,
                                       gitlab_branch=service_data.gitlab_branch)
        repo_details = CachedPlaybookRepoDecryptedPassword(repo_url, repo_user, repo_password)
        return repo_details

    @staticmethod
    def _get_resources_from_connectors(api, service_name, connectors, reporter):
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
    def _get_selector_linked_resource_names(api, res_id, selector_value):
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

    def get_ansible_config_json(self, service_data, api, reporter, target_host_resources, repo_details,
                                sandbox_data, script_params=None, is_global_playbook=False, is_mgmt_playbook=False):
        """
        Bulk of control flow logic in this method. The different playbook commands expect their correct json from here.
        :param GenericAnsibleServiceData service_data:
        :param CloudShellAPISession api:
        :param SandboxReporter reporter:
        :param list[ResourceInfo] target_host_resources: resources to run playbook against
        :param CachedPlaybookRepoDecryptedPassword repo_details:
        :param list[SandboxDataKeyValueInfo] sandbox_data:
        :param str script_params:
        :param bool is_global_playbook:
        :param bool is_mgmt_playbook:
        :return:
        """
        # unpack service data
        service_name = service_data.service_name
        service_connection_method = service_data.connection_method
        service_inventory_groups = service_data.inventory_groups
        service_script_parameters = service_data.script_parameters
        service_additional_args = service_data.additional_args
        service_timeout_minutes = service_data.timeout_minutes

        # REPORT TARGET RESOURCES
        resource_names = [x.Name for x in target_host_resources]
        start_msg = "'{}' Target Hosts :\n{}".format(service_name, json.dumps(resource_names, indent=4))
        reporter.info_out(start_msg)

        # INITIALIZE CONFIG REQUEST DATA MODEL AND START POPULATING
        ansi_conf = AnsibleConfigurationRequest2G()
        ansi_conf.additionalArgs = service_additional_args if service_additional_args else None
        ansi_conf.timeoutMinutes = int(service_timeout_minutes) if service_timeout_minutes else 0

        # REPO DETAILS - REPO PASSWORD EXPECTED AS PLAIN TEXT DECRYPTED STRING
        ansi_conf.repositoryDetails.url = repo_details.url
        ansi_conf.repositoryDetails.username = repo_details.username
        ansi_conf.repositoryDetails.password = repo_details.decrypted_password

        # TAKE COMMAND INPUT AS PRIORITY, FALLBACK TO SERVICE ATTR VALUE
        # THIS WILL BE MERGED WITH CACHED VARS IN LOOP FOR EACH RESOURCE
        if script_params:
            script_params_2g = build_params_list(script_params)
        elif service_script_parameters:
            script_params_2g = build_params_list(service_script_parameters)
        else:
            script_params_2g = []

        """ START POPULATING HOSTS IN LOOP """
        missing_credential_hosts = []
        for curr_resource_obj in target_host_resources:
            curr_resource_name = curr_resource_obj.Name

            # the goal here was to read "user" playbook data stored to sandbox during management playbook run
            cached_ansible_conf = self.get_cached_ansi_conf_from_resource_name(curr_resource_name, sandbox_data)

            # START BUILDING REQUEST
            host_conf = HostConfigurationRequest2G()
            host_conf.ip = curr_resource_obj.Address
            host_conf.resource_name = curr_resource_name

            # USER ATTR FROM LOGICAL RESOURCE
            attrs = curr_resource_obj.ResourceAttributes
            user_attr = get_resource_attribute_gen_agostic("User", attrs)
            user_attr_val = user_attr.Value if user_attr else ""
            host_conf.username = user_attr_val

            # HOST PASSWORD EXPECTED AS ENCRYPTED VALUE
            password_attr = get_resource_attribute_gen_agostic("Password", attrs)
            encrypted_password_val = password_attr.Value
            host_conf.password = encrypted_password_val

            # ACCESS KEY - THIS ATTRIBUTE HAS TO BE CREATED ON LOGICAL RESOURCE - SHOULD BE ENCRYPTED PASSWORD ATTR
            access_key_attr = get_resource_attribute_gen_agostic(override_attributes.ACCESS_KEY_ATTR, attrs)
            encrypted_access_key_val = access_key_attr.Value if access_key_attr else None
            host_conf.accessKey = encrypted_access_key_val

            # VALIDATE HOST CREDENTIALS - NEED USER AND PASSWORD/ACCESS KEY
            if user_attr_val:
                decrypted_password = api.DecryptPassword(encrypted_password_val).Value
                if encrypted_access_key_val:
                    decrypted_access_key = api.DecryptPassword(encrypted_access_key_val).Value
                else:
                    decrypted_access_key = None

                if not decrypted_password and not decrypted_access_key:
                    missing_credential_hosts.append((curr_resource_name, "Missing Credentials Attribute"))
            else:
                missing_credential_hosts.append((curr_resource_name, "Empty User Attribute on Resource"))

            # INVENTORY GROUPS
            """ 
            PRIORITY: 
            1. populated resource attribute 
            2. cached user playbook inventory groups
            3. for 'global' playbook leave empty 
            4. linked playbook service will broadcast default value
            """
            cached_user_pb_inventory_groups_str = get_cached_user_pb_inventory_groups_str(cached_ansible_conf) \
                if cached_ansible_conf else None
            resource_ansible_group_attr = get_resource_attribute_gen_agostic(override_attributes.INVENTORY_GROUP_ATTR,
                                                                             attrs)
            if resource_ansible_group_attr and resource_ansible_group_attr.Value:
                groups_str = resource_ansible_group_attr.Value
            elif cached_user_pb_inventory_groups_str:
                groups_str = cached_user_pb_inventory_groups_str
            elif is_global_playbook:
                groups_str = None
            else:
                groups_str = service_inventory_groups

            # INVENTORY GROUPS NEEDS TO BE A LIST OR NULL/NONE TO FULFILL CONTRACT WITH PACKAGE DRIVER
            if groups_str:
                inventory_groups_list = groups_str.strip().split(",")
            else:
                inventory_groups_list = None

            # RERUN WITH MGMT PLAYBOOK GROUPS VALUE
            if is_mgmt_playbook:
                cached_mgmt_pb_inventory_groups_list = get_cached_mgmt_pb_inventory_groups_list(cached_ansible_conf) \
                    if cached_ansible_conf else None
                if cached_mgmt_pb_inventory_groups_list:
                    host_conf.groups = cached_mgmt_pb_inventory_groups_list
            else:
                host_conf.groups = inventory_groups_list

            # CONNECTION METHOD
            """ 
            PRIORITY: 
            1. populated resource attribute 
            2. cached user playbook connection method 
            3. default mgmt playbook connection method 
            4. 2G service value as fallback
            only way to override cached app value is with resource attribute 
            """
            resource_attr_connection_method = None
            connection_method_attr = get_resource_attribute_gen_agostic(override_attributes.CONNECTION_METHOD_ATTR,
                                                                        attrs)
            if connection_method_attr:
                connection_val = connection_method_attr.Value
                if connection_val:
                    if connection_val.lower() not in ["na", "n/a"]:
                        resource_attr_connection_method = connection_val

            if resource_attr_connection_method:
                host_conf.connectionMethod = resource_attr_connection_method
            elif cached_ansible_conf:
                cached_mgmt_pb_connection_method = cached_ansible_conf.hosts_conf[0].connection_method
                cached_params_dict = cached_ansible_conf.hosts_conf[0].parameters
                cached_user_pb_connection_method = cached_params_dict.get(user_pb_params.CONNECTION_METHOD_PARAM)
                if cached_user_pb_connection_method:
                    host_conf.connectionMethod = cached_user_pb_connection_method
                else:
                    host_conf.connectionMethod = cached_mgmt_pb_connection_method
            else:
                host_conf.connectionMethod = service_connection_method

            # CONNECTION SECURED
            connection_secured_attr = get_resource_attribute_gen_agostic(override_attributes.CONNECTION_SECURED_ATTR,
                                                                         attrs)
            if connection_secured_attr:
                host_conf.connectionSecured = True if connection_secured_attr.Value.lower() == "true" else False
            else:
                host_conf.connectionSecured = False

            # SCRIPT PARAMS
            script_params_attr = get_resource_attribute_gen_agostic(override_attributes.SCRIPT_PARAMS_ATTR, attrs)
            if script_params_attr:
                if script_params_attr.Value:
                    host_conf.parameters = build_params_list(script_params_attr.Value)
                else:
                    host_conf.parameters = script_params_2g
            else:
                host_conf.parameters = script_params_2g

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

        """ EXITING THE BIG FOR LOOP """

        # VALIDATE MISSING CREDENTIALS ON HOSTS
        if missing_credential_hosts:
            missing_json = json.dumps(missing_credential_hosts, indent=4)
            warning_msg = "=== '{}' Connected Hosts Missing Credentials ===\n{}".format(service_name, missing_json)
            reporter.info_out(warning_msg)
            err_msg = "Missing credentials on target hosts. See console / logs for info."
            raise Exception(err_msg)

        ansi_conf_json = ansi_conf.get_pretty_json()

        # hide repo password in json printout
        new_obj = json.loads(ansi_conf_json)
        curr_password = new_obj["repositoryDetails"]["password"]
        if curr_password:
            new_obj["repositoryDetails"]["password"] = "*******"
        json_copy = json.dumps(new_obj, indent=4)
        reporter.info_out("=== Ansible Configuration JSON ===\n{}".format(json_copy), log_only=True)

        return ansi_conf_json

    @staticmethod
    def get_sandbox_reporter(context, api):
        """
        helper method to get sandbox reporter instance
        :param ResourceCommandContext context:
        :param CloudShellAPISession api:
        :return:
        """
        res_id = context.reservation.reservation_id
        model = context.resource.model
        service_name = context.resource.name
        # Logic for prefixing log files with SVC for services
        log_name_prefix = "SVC_" if "PB" not in service_name else ""
        logger = get_qs_logger(log_group=res_id, log_category=model, log_file_prefix=log_name_prefix + service_name)
        reporter = SandboxReporter(api, res_id, logger)
        return reporter
