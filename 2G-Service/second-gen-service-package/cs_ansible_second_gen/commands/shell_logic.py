import json
from cloudshell.core.logger.qs_logger import get_qs_logger
from cs_ansible_second_gen.commands.utility.gitlab_api_url_validator import is_base_path_gitlab_api
from cs_ansible_second_gen.commands.utility.parse_script_params import build_params_list
from cs_ansible_second_gen.commands.utility.sandbox_reporter import SandboxReporter
from cs_ansible_second_gen.commands.utility.shell_connector_helpers import get_connector_endpoints
from cs_ansible_second_gen.commands.utility.validate_protocols import is_path_supported_protocol
from cs_ansible_second_gen.exceptions.exceptions import AnsibleSecondGenServiceException
from cs_ansible_second_gen.models.ansible_config_from_cached_json import get_cached_ansible_config_from_json, \
    CachedPlaybookRepoDecryptedPassword, CachedAnsibleConfiguration
from cs_ansible_second_gen.models.ansible_configuration_request import AnsibleConfigurationRequest2G, \
    GenericAnsibleServiceData, HostConfigurationRequest2G, PlaybookRepository
from cs_ansible_second_gen.service_globals import user_pb_params, override_attributes, utility_globals
from cloudshell.api.cloudshell_api import CloudShellAPISession, ResourceInfo
from cs_ansible_second_gen.commands.utility.resource_helpers import get_normalized_attrs_dict
from cs_ansible_second_gen.commands.utility.common_helpers import get_list_of_param_dicts


class AnsibleSecondGenLogic(object):
    def __init__(self):
        pass

    def get_linked_resources(self, api, service_name, res_id, connectors, config_selector, reporter):
        """
        find resources connected by connector or linked by matching selector attribute and combine
        :param CloudShellAPISession api:
        :param str service_name:
        :param str res_id:
        :param connectors:
        :param str config_selector:
        :param SandboxReporter reporter:
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
    def get_all_canvas_resources(api, res_id):
        """
        find resources for "global" playbook execution. run against all resources without connections
        inventory_only boolean targets only the resources with "inventory groups" populated.
        This can come from resource attribute, or custom param value on cached user playbook data
        :param CloudShellAPISession api:
        :param str res_id:
        :return:
        :rtype list[ResourceInfo]:
        """
        root_resources = AnsibleSecondGenLogic._get_root_canvas_resources(api, res_id)
        target_resources = []
        for curr_resource in root_resources:
            details = api.GetResourceDetails(curr_resource.Name)
            target_resources.append(details)
        return target_resources

    @staticmethod
    def get_matching_inventory_group_resources(api, res_id, service_inventory_groups):
        """
        find resources for "global" playbook execution. run against all resources without connections
        inventory_only boolean targets only the resources with "inventory groups" populated.
        This can come from resource attribute, or custom param value on cached user playbook data
        :param CloudShellAPISession api:
        :param str res_id:
        :param str service_inventory_groups:
        :return:
        :rtype list[ResourceInfo]:
        """
        root_resources = AnsibleSecondGenLogic._get_root_canvas_resources(api, res_id)

        target_resources = []
        for curr_resource in root_resources:
            details = api.GetResourceDetails(curr_resource.Name)
            attrs = details.ResourceAttributes
            inventory_groups_attr_search = [x for x in attrs
                                            if x.Name.lower() == user_pb_params.INVENTORY_GROUPS_PARAM.lower()]
            if inventory_groups_attr_search:
                inventory_group_val = inventory_groups_attr_search[0].Value
                if service_inventory_groups.lower() == inventory_group_val.lower():
                    target_resources.append(details)
        return target_resources

    @staticmethod
    def _get_root_canvas_resources(api, res_id):
        res_details = api.GetReservationDetails(res_id, True).ReservationDescription
        all_resources = res_details.Resources
        root_resources = [x for x in all_resources if "/" not in x.Name]
        return root_resources

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
                exc_msg = "'{}' Input Error. '{}' is not a valid resource. Exception: {}: {}".format(
                    service_name,
                    name,
                    type(e).__name__,
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
                "User Playbook alias does not start with PB. Current Alias: {}".format(service_name))

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
        :param CloudShellAPISession api:
        :param playbook_path:
        :param reporter:
        :param service_data:
        :param list[str] supported_protocols:
        :return:
        """
        repo_user = service_data.repo_user
        repo_password = service_data.repo_password
        repo_url = self.build_repo_url(service_full_url=service_data.repo_url,
                                       service_url_base_path=service_data.repo_base_path,
                                       service_pb_relative_path=service_data.repo_script_path,
                                       input_playbook_path=playbook_path,
                                       supported_protocols=supported_protocols,
                                       reporter=reporter,
                                       gitlab_branch=service_data.gitlab_branch)
        repo_details = PlaybookRepository(repo_url, repo_user, repo_password)
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

    def get_ansible_config_json(self, service_data, target_host_resources, repo_details, reporter,
                                cmd_input_params=""):
        """
        Bulk of control flow logic in this method. The different playbook commands expect their correct json from here.
        :param GenericAnsibleServiceData service_data:
        :param list[ResourceInfo] target_host_resources: resources to run playbook against
        :param PlaybookRepository repo_details:
        :param SandboxReporter reporter:
        :param str cmd_input_params:
        :return:
        """
        # REPORT TARGET RESOURCES
        self._log_resource_names(reporter, service_data, target_host_resources)

        # BUILD CONFIG REQUEST OBJECT
        ansi_conf = AnsibleConfigurationRequest2G()
        self._populate_top_level_ansi_conf(ansi_conf, repo_details, service_data)

        # TODO:
        # add logic into separate function for cached playbook actions
        for curr_resource_obj in target_host_resources:
            # START BUILDING REQUEST
            host_conf = HostConfigurationRequest2G()
            host_conf = self._populate_host_conf(host_conf, curr_resource_obj, service_data, cmd_input_params)
            ansi_conf.hostsDetails.append(host_conf)

        ansi_conf_json = ansi_conf.get_pretty_json()
        self._log_ansi_conf_with_masked_password(ansi_conf_json, reporter)
        return ansi_conf_json

    def get_cached_ansible_mgmt_config_json(self, service_data, target_resource, cached_config, reporter):
        """
        Bulk of control flow logic in this method. The different playbook commands expect their correct json from here.
        :param GenericAnsibleServiceData service_data:
        :param ResourceInfo target_resource:
        :param CachedAnsibleConfiguration cached_config:
        :param SandboxReporter reporter:
        :return:
        """
        # BUILD CONFIG REQUEST OBJECT
        ansi_conf = AnsibleConfigurationRequest2G()
        self._populate_top_level_mgmt_ansi_conf(ansi_conf, cached_config)

        # START BUILDING REQUEST FOR SINGLE HOST
        host_conf = HostConfigurationRequest2G()

        host_conf = self._populate_mgmt_pb_host_conf(host_conf, target_resource, cached_config)
        ansi_conf.hostsDetails.append(host_conf)

        ansi_conf_json = ansi_conf.get_pretty_json()
        self._log_ansi_conf_with_masked_password(ansi_conf_json, reporter)
        return ansi_conf_json

    def get_cached_ansible_user_pb_config_json(self, service_data, target_resource, repo_details, cached_config,
                                               reporter):
        """
        Bulk of control flow logic in this method. The different playbook commands expect their correct json from here.
        :param GenericAnsibleServiceData service_data:
        :param ResourceInfo target_resource:
        :param CachedPlaybookRepoDecryptedPassword repo_details:
        :param CachedAnsibleConfiguration cached_config:
        :param SandboxReporter reporter:
        :return:
        """
        # BUILD CONFIG REQUEST OBJECT
        ansi_conf = AnsibleConfigurationRequest2G()
        self._populate_top_level_user_pb_ansi_conf(ansi_conf, repo_details, service_data, cached_config)

        # START BUILDING REQUEST FOR SINGLE HOST
        host_conf = HostConfigurationRequest2G()
        host_conf = self._populate_user_pb_host_conf(host_conf, target_resource, service_data, cached_config)
        ansi_conf.hostsDetails.append(host_conf)

        ansi_conf_json = ansi_conf.get_pretty_json()
        self._log_ansi_conf_with_masked_password(ansi_conf_json, reporter)
        return ansi_conf_json

    def _log_resource_names(self, reporter, service_data, target_host_resources):
        resource_names = [x.Name for x in target_host_resources]
        reporter.info_out("'{}' Target Hosts :\n{}".format(service_data.service_name,
                                                           json.dumps(resource_names, indent=4)))

    def _log_ansi_conf_with_masked_password(self, ansi_conf_json, reporter):
        """
        HIDE REPO PASSWORDS IN JSON OUTPUT
        :param str ansi_conf_json:
        :param SandboxReporter reporter:
        :return:
        """
        new_obj = json.loads(ansi_conf_json)
        curr_password = new_obj["repositoryDetails"]["password"]
        if curr_password:
            new_obj["repositoryDetails"]["password"] = "*******"
        json_copy = json.dumps(new_obj, indent=4)
        reporter.info_out("=== Ansible Configuration JSON ===\n{}".format(json_copy), log_only=True)

    # TODO - Create flow for physical resources / apps / cached mgmt / user pb
    def _populate_host_conf(self, host_conf, curr_resource_obj, service_data, cmd_input_params):
        """
        for apps and physical resources
        general priority is resource level value with fallback to service level
        :param HostConfigurationRequest2G host_conf:
        :param ResourceInfo curr_resource_obj:
        :param GenericAnsibleServiceData service_data:
        :param str cmd_input_params:
        :return:
        """
        # USER ATTR FROM LOGICAL RESOURCE
        attrs = curr_resource_obj.ResourceAttributes

        # attrs_dict = {attr.Name: attr.Value for attr in attrs}
        attrs_dict = get_normalized_attrs_dict(attrs)

        curr_resource_name = curr_resource_obj.Name

        host_conf.ip = curr_resource_obj.Address
        host_conf.resourceName = curr_resource_name

        user_val = attrs_dict.get("User", "")
        host_conf.username = user_val

        # HOST PASSWORD + ACCESS KEY EXPECTED IN ENCRYPTED FORM IN REQUEST
        encrypted_password_val = attrs_dict.get("Password", utility_globals.ENCRYPTED_EMPTY_STRING)
        host_conf.password = encrypted_password_val

        # ACCESS KEY - THIS ATTRIBUTE HAS TO BE CREATED ON LOGICAL RESOURCE - SHOULD BE ENCRYPTED PASSWORD ATTR
        # TODO - how will access key / pem attr get populated for deployed apps on public cloud like AWS?
        # Is there an api call maybe to get pem from DB?
        encrypted_access_key_val = attrs_dict.get(override_attributes.ACCESS_KEY_ATTR,
                                                  utility_globals.ENCRYPTED_EMPTY_STRING)
        host_conf.accessKey = encrypted_access_key_val

        # INVENTORY GROUPS
        groups_str = attrs_dict.get(override_attributes.INVENTORY_GROUP_ATTR, "")
        if groups_str:
            inventory_groups_list = groups_str.strip().split(",")
        else:
            inventory_groups_list = None
        host_conf.groups = inventory_groups_list

        # CONNECTION METHOD
        resource_attr_connection_method = attrs_dict.get(override_attributes.CONNECTION_METHOD_ATTR, "")

        # connection method may be a lookup attribute with "NA" option which we want falsy
        if resource_attr_connection_method.lower() in ["na", "n/a"]:
            resource_attr_connection_method = ""

        # host level value takes priority, fall back to service value
        if resource_attr_connection_method:
            host_conf.connectionMethod = resource_attr_connection_method
        else:
            host_conf.connectionMethod = service_data.connection_method

        # CONNECTION SECURED
        connection_secured_attr = attrs_dict.get(override_attributes.CONNECTION_SECURED_ATTR, "False")
        is_connection_secured = True if connection_secured_attr.lower() == "true" else False
        host_conf.connectionSecured = is_connection_secured

        # SCRIPT PARAMS
        script_params_resource_attr = attrs_dict.get(override_attributes.SCRIPT_PARAMS_ATTR, "")
        self._populate_host_conf_params(host_conf, cmd_input_params, script_params_resource_attr, service_data)

        return host_conf

    @staticmethod
    def _populate_user_pb_host_conf(host_conf, curr_resource_obj, service_data, cached_config):
        """
        user pb - get details from cached params of app - reserved keywords
        :param HostConfigurationRequest2G host_conf:
        :param ResourceInfo curr_resource_obj:
        :param GenericAnsibleServiceData service_data:
        :param CachedAnsibleConfiguration cached_config:
        :return:
        """
        # USER ATTR FROM LOGICAL RESOURCE
        attrs = curr_resource_obj.ResourceAttributes
        attrs_dict = {attr.Name: attr.Value for attr in attrs}
        attrs_dict = get_normalized_attrs_dict(attrs)

        host_conf.ip = curr_resource_obj.Address
        host_conf.resourceName = curr_resource_obj.Name
        user_val = attrs_dict.get("User", "")
        host_conf.username = user_val

        # HOST PASSWORD + ACCESS KEY EXPECTED IN ENCRYPTED FORM IN REQUEST
        encrypted_password_val = attrs_dict.get("Password", utility_globals.ENCRYPTED_EMPTY_STRING)
        host_conf.password = encrypted_password_val

        # the cached config will only have the one target host
        host_conf.accessKey = cached_config.hosts_conf[0].access_key

        # dig into the cached params dictionary for reserved keywords that define user playbooks
        cached_params_dict = cached_config.hosts_conf[0].parameters

        # INVENTORY GROUPS - app param first, fall back to resource attr
        app_level_inventory_groups = cached_params_dict.get(user_pb_params.INVENTORY_GROUPS_PARAM)
        resource_level_inventory_groups = attrs_dict.get(override_attributes.INVENTORY_GROUP_ATTR)
        if app_level_inventory_groups:
            inventory_groups_list = app_level_inventory_groups.strip().split(",")
        elif resource_level_inventory_groups:
            inventory_groups_list = resource_level_inventory_groups.strip().split(",")
        else:
            inventory_groups_list = None
        host_conf.groups = inventory_groups_list

        # CONNECTION METHOD
        app_level_connection_method = cached_params_dict.get(user_pb_params.CONNECTION_METHOD_PARAM)
        resource_attr_connection_method = attrs_dict.get(override_attributes.CONNECTION_METHOD_ATTR, "")

        # connection method may be a lookup attribute with "NA" option which we want falsy
        if resource_attr_connection_method.lower() in ["na", "n/a"]:
            resource_attr_connection_method = ""

        # app level takes priority, fall back resource attr, then to 2G service value
        if app_level_connection_method:
            host_conf.connectionMethod = app_level_connection_method
        elif resource_attr_connection_method:
            host_conf.connectionMethod = resource_attr_connection_method
        else:
            host_conf.connectionMethod = service_data.connection_method

        # CONNECTION SECURED
        app_level_connection_secured = cached_params_dict.get(user_pb_params.CONNECTION_SECURED_PARAM, "")
        resource_attr_connection_secured = attrs_dict.get(override_attributes.CONNECTION_SECURED_ATTR, "")
        if app_level_connection_secured:
            host_conf.connectionSecured = True if app_level_connection_secured.lower() == "true" else False
        else:
            host_conf.connectionSecured = True if resource_attr_connection_secured.lower() == "true" else False

        # SCRIPT PARAMS
        host_conf.parameters = get_list_of_param_dicts(cached_config.hosts_conf[0].parameters)

        return host_conf

    @staticmethod
    def _populate_mgmt_pb_host_conf(host_conf, curr_resource_obj, cached_config):
        """
        rerun the mgmt playbook
        :param HostConfigurationRequest2G host_conf:
        :param ResourceInfo curr_resource_obj:
        :param CachedAnsibleConfiguration cached_config:
        :return:
        """
        # ==== RESOURCE ATTRIBUTES ====
        # USER ATTR FROM LOGICAL RESOURCE
        attrs = curr_resource_obj.ResourceAttributes
        attrs_dict = {attr.Name: attr.Value for attr in attrs}
        attrs_dict = get_normalized_attrs_dict(attrs)

        host_conf.ip = curr_resource_obj.Address
        host_conf.resourceName = curr_resource_obj.Name
        user_val = attrs_dict.get("User", "")
        host_conf.username = user_val

        # HOST PASSWORD + ACCESS KEY EXPECTED IN ENCRYPTED FORM
        encrypted_password_val = attrs_dict.get("Password", utility_globals.ENCRYPTED_EMPTY_STRING)
        host_conf.password = encrypted_password_val

        # the cached config will only have the one target host
        host_conf.accessKey = cached_config.hosts_conf[0].access_key

        # dig into the cached params dictionary for reserved keywords that define user playbooks
        cached_params_dict = cached_config.hosts_conf[0].parameters

        # INVENTORY GROUPS - cached management value on host
        inventory_groups_str = cached_config.hosts_conf[0].groups
        if inventory_groups_str:
            inventory_groups_list = inventory_groups_str.strip().split(",")
            host_conf.groups = inventory_groups_list
        else:
            host_conf.groups = None

        # CONNECTION METHOD
        host_conf.connectionMethod = cached_config.hosts_conf[0].connection_method

        # CONNECTION SECURED - NOT actually exposed in config UI - default to False and set true if attribute or param exist
        app_level_connection_secured = cached_params_dict.get(user_pb_params.CONNECTION_SECURED_PARAM, "")
        resource_attr_connection_secured = attrs_dict.get(override_attributes.CONNECTION_SECURED_ATTR, "")
        if app_level_connection_secured:
            host_conf.connectionSecured = True if app_level_connection_secured.lower() == "true" else False
        else:
            host_conf.connectionSecured = True if resource_attr_connection_secured.lower() == "true" else False

        # SCRIPT PARAMS
        host_conf.parameters = get_list_of_param_dicts(cached_config.hosts_conf[0].parameters)

        return host_conf

    @staticmethod
    def _populate_host_conf_params(host_conf, cmd_input_params, script_params_resource_attr, service_data):
        """
        priority list - NOT cumulative list, they override
        1. service command input
        2. resource attribute if populated
        3. Fallback to service attribute value
        :param str cmd_input_params:
        :param HostConfigurationRequest2G host_conf:
        :param str script_params_resource_attr:
        :param GenericServiceData service_data:
        :return:
        """
        if cmd_input_params:
            host_conf.parameters = build_params_list(cmd_input_params)
        elif script_params_resource_attr:
            host_conf.parameters = build_params_list(script_params_resource_attr)
        else:
            host_conf.parameters = build_params_list(service_data.script_parameters)

    @staticmethod
    def _populate_top_level_ansi_conf(ansi_conf, repo_details, service_data):
        """
        populate all top level data outside of the hosts list
        no return value - side effect helper to populate ansi_conf object
        :param AnsibleConfigurationRequest2G ansi_conf:
        :param PlaybookRepository repo_details:
        :param GenericServiceData service_data:
        :return:
        """
        # START POPULATING REQUEST OBJECT
        ansi_conf.additionalArgs = service_data.additional_args if service_data.additional_args else None
        ansi_conf.timeoutMinutes = int(service_data.timeout_minutes) if service_data.timeout_minutes else 0

        # REPO DETAILS - REPO PASSWORD EXPECTED AS PLAIN TEXT DECRYPTED STRING
        ansi_conf.repositoryDetails.url = repo_details.url
        ansi_conf.repositoryDetails.username = repo_details.username
        ansi_conf.repositoryDetails.password = repo_details.password

    @staticmethod
    def _populate_top_level_mgmt_ansi_conf(ansi_conf, cached_config):
        """
        populate all top level data outside of the hosts list
        no return value - side effect helper to populate ansi_conf object
        :param AnsibleConfigurationRequest2G ansi_conf:
        :param CachedAnsibleConfiguration cached_config:
        :return:
        """
        # START POPULATING REQUEST OBJECT
        ansi_conf.additionalArgs = cached_config.additional_cmd_args
        ansi_conf.timeoutMinutes = cached_config.timeout_minutes

        # REPO DETAILS - REPO PASSWORD EXPECTED AS PLAIN TEXT DECRYPTED STRING
        ansi_conf.repositoryDetails.url =  cached_config.playbook_repo.url
        ansi_conf.repositoryDetails.username = cached_config.playbook_repo.username
        ansi_conf.repositoryDetails.password = cached_config.playbook_repo.decrypted_password

    @staticmethod
    def _populate_top_level_user_pb_ansi_conf(ansi_conf, repo_details, service_data, cached_config):
        """
        populate all top level data outside of the hosts list
        no return value - side effect helper to populate ansi_conf object
        :param AnsibleConfigurationRequest2G ansi_conf:
        :param CachedPlaybookRepoDecryptedPassword repo_details:
        :param GenericServiceData service_data:
        :param CachedAnsibleConfiguration cached_config:
        :return:
        """
        # START POPULATING REQUEST OBJECT
        ansi_conf.additionalArgs = cached_config.additional_cmd_args
        ansi_conf.timeoutMinutes = cached_config.timeout_minutes

        # REPO DETAILS
        ansi_conf.repositoryDetails.url = repo_details.url
        ansi_conf.repositoryDetails.username = repo_details.username
        ansi_conf.repositoryDetails.password = repo_details.decrypted_password

    @staticmethod
    def _get_script_params_list(script_params, service_data):
        """
        user input takes priority over service attribute value
        if both empty fallback to empty list
        :param str script_params:
        :param GenericServiceData service_data:
        :return:
        """
        if script_params:
            script_params_2g = build_params_list(script_params)
        elif service_data.script_parameters:
            script_params_2g = build_params_list(service_data.script_parameters)
        else:
            script_params_2g = []
        return script_params_2g

    def get_playbook_target_resources(self, api, reporter, res_id, context, config_selector, service_name,
                                      service_data):
        if context.connectors or config_selector:
            # GET CONNECTED RESOURCES / MATCHING CONFIG SELECTOR RESOURCES
            target_host_resources = self.get_linked_resources(api, service_name, res_id, context.connectors,
                                                              service_data.config_selector, reporter)
        elif service_data.inventory_groups:
            # RESOURCES WITH MATCHING INVENTORY GROUP VALUE
            target_host_resources = self.get_matching_inventory_group_resources(api, res_id,
                                                                                service_data.inventory_groups)
        else:
            # FALL BACK TO ALL CANVAS RESOURCES
            target_host_resources = self.get_all_canvas_resources(api, res_id)
        return target_host_resources

    def get_user_playbook_target_resources(self, api, context, reporter, res_id, service_data, service_name):
        if context.connectors:
            target_host_resources = self.get_linked_resources(api, service_name, res_id, context.connectors,
                                                              service_data.config_selector, reporter)
        else:
            target_resource = self.get_user_pb_target_resource_from_alias(service_name, api, reporter)
            target_host_resources = [target_resource]
        return target_host_resources

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
