from cloudshell.api.cloudshell_api import CloudShellAPISession, SandboxDataKeyValue
from ansible_configuration import AnsibleConfiguration
from cloudshell.shell.core.driver_context import ResourceCommandContext


def _get_resource_name_from_ip(resources, ansi_conf_ip):
    """
    :param CloudShellAPISessionapi:
    :param str res_id:
    :param str ip:
    :return:
    """
    matching_resource_search = [x for x in resources if x.FullAddress == ansi_conf_ip]
    if len(matching_resource_search) > 1:
        matching_resource_names = [x.Name for x in matching_resource_search]
        raise Exception("Multiple resources have IP {}: {}".format(ansi_conf_ip, matching_resource_names))
    if not matching_resource_search:
        return None
    return matching_resource_search[0].Name


def _cache_host_data_to_sandbox(api, res_id, sandbox_resources, ansi_conf, logger):
    """
    cache params in sandbox data, if key exists then return
    :param CloudShellAPISession api:
    :param ResourceCommandContext context:
    :param AnsibleConfiguration ansi_conf:
    :param logging.Logger logger:
    :return same config object:
    :rtype AnsibleConfiguration
    """
    hosts_list = ansi_conf.hosts_conf
    sandbox_data = api.GetSandboxData(res_id).SandboxDataKeyValues
    for host in hosts_list:
        ansi_conf_ip = host.ip
        resource_name = _get_resource_name_from_ip(sandbox_resources, ansi_conf_ip)
        if not resource_name:
            raise Exception("No resource name found for IP: {}".format(ansi_conf_ip))
        matching_sb_data = [x for x in sandbox_data if x.Key == "ansible_{}".format(resource_name)]
        if matching_sb_data:
            return
        ansi_conf_json = ansi_conf.get_pretty_json()
        sb_data_key = "ansible_" + resource_name
        sb_data_value = ansi_conf_json
        sb_data = [SandboxDataKeyValue(sb_data_key, sb_data_value)]
        api.SetSandboxData(res_id, sb_data)
        logger.info("set sandbox data key: {}\n{}".format(sb_data_key, sb_data_value))


def cache_data_and_merge_global_inputs(api, context, ansi_conf, logger):
    """
    this method will cache host data to sandbox then merge global inputs to host vars list
    :param CloudShellAPISession api:
    :param ResourceCommandContext context:
    :param AnsibleConfiguration ansi_conf:
    :return same config object:
    :rtype AnsibleConfiguration
    """
    res_id = context.reservation.reservation_id
    sandbox_details = api.GetReservationDetails(res_id, True).ReservationDescription
    sb_resources = sandbox_details.Resources

    _cache_host_data_to_sandbox(api, res_id, sb_resources, ansi_conf, logger)

    sb_global_inputs = api.GetReservationInputs(res_id).GlobalInputs

    # MERGE GLOBAL INPUTS IF THEY DONT HAVE A VALUE
    hosts_list = ansi_conf.hosts_conf
    for host in hosts_list:
        host_params_dict = host.parameters
        for global_input in sb_global_inputs:
            if not host_params_dict.get(global_input.ParamName):
                host_params_dict[global_input.ParamName] = global_input.Value

    return ansi_conf
