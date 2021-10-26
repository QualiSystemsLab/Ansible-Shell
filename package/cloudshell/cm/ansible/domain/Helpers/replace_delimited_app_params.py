import re
from cloudshell.cm.ansible.domain.ansible_configuration import HostConfiguration
from cloudshell.cm.ansible.domain.Helpers.sandbox_reporter import SandboxReporter
from cloudshell.api.cloudshell_api import ReservedResourceInfo


def _get_app_names_matching_delimiters(input_str):
    pattern = r"\<(.*?)\>"
    return re.findall(pattern, input_str)


def _replace_delimited_app_name_with_address(target_app_name, param_val_str, app_resource_address):
    pattern = r"(\<{}\>)".format(target_app_name)
    return re.sub(pattern, app_resource_address, param_val_str)


def replace_delimited_param_val_with_app_address(host_conf_list, resources, reporter):
    """
    replace the delimited router variable with the Address of the the matching app for ALL app params
    :param str ssh_param_key:
    :param list[HostConfiguration] host_conf_list:
    :param list[ReservedResourceInfo] resources:
    :param SandboxReporter reporter:
    :return:
    """
    for curr_host in host_conf_list:
        params = curr_host.parameters
        for param_name, param_value in params.items():
            if type(param_value) == list or type(param_value) == dict:
                # TODO - see where dict / list conversion of param is happening
                continue
            app_name_matches = _get_app_names_matching_delimiters(param_value)
            if not app_name_matches:
                continue
            replaced_param = param_value
            for curr_delimited_app_name in app_name_matches:
                matching_app_resource_search = [x for x in resources
                                                if x.AppDetails and x.AppDetails.AppName == curr_delimited_app_name]
                if not matching_app_resource_search:
                    warn_msg = "No match found for delimited app name '{}' in param '{}' for resource '{}'".format(
                        curr_delimited_app_name,
                        param_name,
                        curr_host.resource_name)
                    reporter.warn_out(warn_msg)
                    continue
                matching_resource_address = matching_app_resource_search[0].FullAddress
                replaced_param = _replace_delimited_app_name_with_address(curr_delimited_app_name,
                                                                          replaced_param,
                                                                          matching_resource_address)
            reporter.warn_out(
                "===App '{}' replacing delimited app names in param ===".format(curr_host.resource_name, param_name))
            reporter.info_out("Param Name: {}\n"
                              "New Param Value: {}\n"
                              "==========".format(param_name, replaced_param))
            curr_host.parameters[param_name] = replaced_param
