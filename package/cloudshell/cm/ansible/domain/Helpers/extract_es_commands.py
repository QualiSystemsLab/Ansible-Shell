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
    pre_commands_search = []
    post_commands_search = []
    for curr_host in host_conf_list:
        params = curr_host.parameters
        pre_command = params.get(EsConnectivityCommandParams.PRE_COMMAND_PARAM.value)
        post_command = params.get(EsConnectivityCommandParams.POST_COMMAND_PARAM.value)
        if pre_command:
            pre_commands_search.append(pre_command)
        if post_command:
            post_commands_search.append(post_command)

    # validate for duplicates and log warning if more than one found
    pre_command = None
    post_command = None
    if pre_commands_search:
        pre_command = pre_commands_search[0]

        if len(pre_commands_search) > 1:
            reporter.warn_out("More than one '{}' command found in params. Taking first.".format(
                EsConnectivityCommandParams.PRE_COMMAND_PARAM.value))
            reporter.info_out("Pre-connectivity params found:\n{}".format(json.dumps(pre_commands_search, indent=4)))

    if post_commands_search:
        post_command = post_commands_search[0]

        if len(post_commands_search) > 1:
            reporter.warn_out("More than one '{}' command found in params. Taking first.".format(
                EsConnectivityCommandParams.POST_COMMAND_PARAM.value))
            reporter.info_out("Post-connectivity params found:\n{}".format(json.dumps(post_commands_search, indent=4)))

    return pre_command, post_command
