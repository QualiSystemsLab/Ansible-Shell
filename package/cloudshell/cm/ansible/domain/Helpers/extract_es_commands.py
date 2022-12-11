import json

from cloudshell.cm.ansible.domain.ansible_configuration import HostConfiguration
from cloudshell.cm.ansible.domain.Helpers.sandbox_reporter import SandboxReporter
from cloudshell.cm.ansible.domain.driver_globals import EsConnectivityCommandParams


def extract_es_commands_from_host_conf(host_conf_list, reporter):
    """
    replace the delimited router variable with the Address of the the matching app for ALL app params
    :param list[HostConfiguration] host_conf_list:
    :param SandboxReporter reporter:
    :return:
    """
    # search for params
    pre_commands = []
    post_commands = []
    for curr_host in host_conf_list:
        params = curr_host.parameters
        pre_command = params.get(EsConnectivityCommandParams.PRE_COMMAND_PARAM.value)
        post_command = params.get(EsConnectivityCommandParams.POST_COMMAND_PARAM.value)
        if pre_command:
            pre_commands.append(pre_command)
        if post_command:
            post_commands.append(post_command)

    return pre_commands, post_commands
