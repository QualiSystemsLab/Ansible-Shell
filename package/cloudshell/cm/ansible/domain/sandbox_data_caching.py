from cloudshell.api.cloudshell_api import CloudShellAPISession, SandboxDataKeyValue, ReservedResourceInfo, ReservedTopologyGlobalInputsInfo
from ansible_configuration import AnsibleConfiguration
from cloudshell.shell.core.driver_context import ResourceCommandContext
import copy
from cloudshell.cm.ansible.domain.Helpers.sandbox_reporter import SandboxReporter
from cloudshell.cm.ansible.domain.driver_globals import ANSIBLE_MGMT_FAILED_PREFIX


class AnsibleDuplicateAddressException(Exception):
    pass


class AnsibleMatchingAddressNotFoundException(Exception):
    pass


def _get_resource_name_from_ip(sandbox_resources, ansi_conf_host_ip, api, reporter):
    """
    :param list[ReservedResourceInfo] sandbox_resources:
    :param str ansi_conf_host_ip:
    :param CloudShellAPISession api:
    :param SandboxReporter reporter:
    :return:
    """
    matching_resource_search = [x for x in sandbox_resources if x.FullAddress == ansi_conf_host_ip]
    if len(matching_resource_search) > 1:
        matching_resource_names = [x.Name for x in matching_resource_search]
        err_msg = "Multiple resources have IP {}: {}".format(ansi_conf_host_ip, matching_resource_names)
        reporter.err_out(err_msg)
        for curr_resource_name in matching_resource_names:
            api.SetResourceLiveStatus(resourceFullName=curr_resource_name,
                                      liveStatusName="Error",
                                      additionalInfo=err_msg)
        raise AnsibleDuplicateAddressException(err_msg)
    if not matching_resource_search:
        err_msg = "No resource on canvas matching IP: {}".format(ansi_conf_host_ip)
        reporter.err_out(err_msg)
        raise AnsibleMatchingAddressNotFoundException(err_msg)
    return matching_resource_search[0].Name


def find_resources_matching_addresses(sandbox_resources, ansi_conf, api, reporter):
    """
    iterate over ansi_conf object and add resource names by matching the IP
    :param list[ReservedResourceInfo] sandbox_resources:
    :param AnsibleConfiguration ansi_conf:
    :param logging.Logger logger:
    :return same config object:
    :rtype AnsibleConfiguration
    """
    for curr_host in ansi_conf.hosts_conf:
        # skip this on setup reruns
        if curr_host.resource_name:
            continue

        # do the lookup, if duplicate or not found, leave as None
        try:
            matching_resource_name = _get_resource_name_from_ip(sandbox_resources, curr_host.ip, api, reporter)
        except Exception as e:
            pass
        else:
            curr_host.resource_name = matching_resource_name
    return ansi_conf


def cache_host_data_to_sandbox(ansi_conf, api, res_id, reporter):
    """
    cache params in sandbox data, if key exists then return (to make re-run of setup idempotent)
    store each host separately with the resource name as sandbox data key
    :param AnsibleConfiguration ansi_conf:
    :param CloudShellAPISession api:
    :param str res_id:
    :param SandboxReporter reporter:
    :return same config object:
    :rtype AnsibleConfiguration
    """
    sandbox_data = api.GetSandboxData(res_id).SandboxDataKeyValues
    for curr_host in ansi_conf.hosts_conf:
        curr_ansi_conf_ip = curr_host.ip
        resource_name = curr_host.resource_name

        # resource name is populated on object earlier in custom flow by lookup action. If not found it will be None.
        if not resource_name:
            err_msg = "No resource name found for IP: {}. Skipping sandbox data save for this host".format(curr_ansi_conf_ip)
            reporter.err_out(err_msg, log_only=True)
            continue

        # skip cacheing step for existing keys when rerunning setup
        matching_sb_data = [x for x in sandbox_data if x.Key == "ansible_{}".format(resource_name)]
        if matching_sb_data:
            reporter.info_out("Sandbox data already exists for resource '{}'. Skipping.".format(resource_name),
                              log_only=True)
            continue

        # copy ansi_conf and add host list of only the matching host, cache that to sandbox data
        ansi_conf_copy = copy.deepcopy(ansi_conf)
        target_filtered_host_conf = [host_data for host_data in ansi_conf.hosts_conf
                                     if host_data.ip == curr_ansi_conf_ip]

        # set ONLY the target host to cached host list
        ansi_conf_copy.hosts_conf = target_filtered_host_conf

        # convert to json and write to sandbox data with namespaced ansible key
        ansi_conf_json = ansi_conf_copy.get_pretty_json()
        sb_data_key = "ansible_" + resource_name
        sb_data_value = ansi_conf_json
        sb_data = [SandboxDataKeyValue(sb_data_key, sb_data_value)]
        try:
            api.SetSandboxData(res_id, sb_data)
        except Exception as e:
            err_msg = "Issue setting sandbox data for resource '{}'".format(resource_name)
            reporter.err_out(err_msg, log_only=True)
            raise Exception(err_msg)
        reporter.info_out("set ansible sandbox data key: {}".format(sb_data_key), log_only=True)


def merge_global_inputs_to_app_params(ansi_conf, sb_global_inputs):
    """
    Merge all global inputs to app params
    POPULATED App level params that already exist will take precedence over the globals
    :param AnsibleConfiguration ansi_conf:
    :param list[ReservedTopologyGlobalInputsInfo] sb_global_inputs:
    :return same config object:
    :rtype AnsibleConfiguration
    """
    for host in ansi_conf.hosts_conf:
        host_params_dict = host.parameters
        for global_input in sb_global_inputs:
            if not host_params_dict.get(global_input.ParamName):
                host_params_dict[global_input.ParamName] = global_input.Value
    return ansi_conf


def set_failed_hosts_to_sandbox_data(service_name, failed_host_json, api, res_id, logger):
    """
    workaround to throwing error in driver which sets live status on all resources
    :param str service_name:
    :param str failed_host_json:
    :param CloudShellAPISession api:
    :param str res_id:
    :param logging.Logger logger:
    :return:
    """
    logger.info("Setting sandbox data for failed hosts in service '{}'".format(service_name))
    sb_data_key = ANSIBLE_MGMT_FAILED_PREFIX + service_name
    sb_data_value = failed_host_json
    sb_data = [SandboxDataKeyValue(sb_data_key, sb_data_value)]
    api.SetSandboxData(res_id, sb_data)
