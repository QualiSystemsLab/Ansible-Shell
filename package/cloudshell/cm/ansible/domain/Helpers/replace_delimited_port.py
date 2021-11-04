import re
from cloudshell.cm.ansible.domain.ansible_configuration import HostConfiguration
from cloudshell.cm.ansible.domain.Helpers.sandbox_reporter import SandboxReporter
from cloudshell.api.cloudshell_api import ReservedResourceInfo
from cloudshell.cm.ansible.domain.Helpers.find_open_es_port import get_open_es_port

DELIMITED_PORT_PATTERN = r"\[PORT\]"


def _get_ports_matching_delimiters(input_str):
    return re.findall(DELIMITED_PORT_PATTERN, input_str)


def _regex_replace_delimited_port_with_random_port(random_port, param_val_str):
    """
    :param str random_port:
    :param str param_val_str:
    :return:
    """
    return re.sub(DELIMITED_PORT_PATTERN, random_port, param_val_str)


def replace_delimited_port_with_random_port(host_conf_list, reporter):
    """
    replace the delimited router variable with the Address of the the matching app for ALL app params
    :param str ssh_param_key:
    :param list[HostConfiguration] host_conf_list:
    :param SandboxReporter reporter:
    :return:
    """
    collected_ports = []
    for curr_host in host_conf_list:
        params = curr_host.parameters
        random_port = None
        for param_name, param_value in params.items():
            if type(param_value) == list or type(param_value) == dict:
                # TODO - when changing handling of json params behavior, can remove this guard
                continue
            matching_delimited_ports = _get_ports_matching_delimiters(param_value)
            if matching_delimited_ports:
                if not random_port:
                    random_port = get_open_es_port(collected_ports)
                    collected_ports.append(random_port)
                replaced_param_value = _regex_replace_delimited_port_with_random_port(str(random_port), param_value)
                reporter.warn_out("=== Replacing Delimited Port in '{}' ===".format(curr_host.resource_name))
                reporter.info_out("Param Name: {}\nNew Param Value: {}".format(param_name, replaced_param_value))
                curr_host.parameters[param_name] = replaced_param_value
