import json
import os
import re

from cloudshell.cm.ansible.domain.output.unixToHtmlConverter import UnixToHtmlColorConverter
from cloudshell.cm.ansible.domain.ansible_configuration import HostConfiguration

DUPLICATE_IP_ISSUE_MSG = "No resource name found for resource, playbook did not run."
FAILED_CONNECTIVITY_CHECK_MSG = "Failed connectivity check, playbook did not run."


class AnsibleResult(object):
    START = '\033\[\d+\;\d+m'
    END = '\033\[0m'
    DID_NOT_RUN_ERROR = 'Did not run / no information for this host.'

    def __init__(self, output, error, hosts_conf_list):
        """

        :param str output:
        :param str error:
        :param list[HostConfiguration] hosts_conf_list:
        """
        self.output = output
        self.error = str(error)
        self.hosts_conf_list = hosts_conf_list
        self.host_results = self._load()
        self.failed_hosts = [h for h in self.host_results if not h.success]
        self.success = not self.failed_hosts

    def to_json(self):
        return self._to_json(self.host_results)

    def failed_hosts_to_json(self):
        return self._to_json(self.failed_hosts)

    @staticmethod
    def _to_json(host_results):
        """
        :param list[HostResult] host_results:
        :return:
        """
        arr = [{'host': h.ip,
                'resource_name': h.resource_name,
                'success': h.success,
                'error': h.error}
               for h in host_results]
        return json.dumps(arr, indent=4)

    def _load(self):
        host_results = []
        recap_table = self._get_final_table()
        error_by_host = self._get_failing_hosts_errors()
        general_error = self._get_parsed_error()
        for host in self.hosts_conf_list:
            # sort the hosts that failed before playbook run
            if not host.resource_name:
                host_results.append(HostResult(host.ip, "", False, DUPLICATE_IP_ISSUE_MSG))
            elif not host.health_check_passed:
                host_results.append(HostResult(host.ip, host.resource_name, False, FAILED_CONNECTIVITY_CHECK_MSG))
            # Success
            elif recap_table.get(host.ip):
                host_results.append(HostResult(host.ip, host.resource_name, True, "", True))
            # Failed with error
            elif error_by_host.get(host.ip):
                host_results.append(HostResult(host.ip, host.resource_name, False, error_by_host.get(host.ip), True))
            # Failed without error
            elif not recap_table.get(host.ip):
                host_results.append(HostResult(host.ip, host.resource_name, False, self.error, True))
            # Didn't run at all (no information for this ip)
            else:
                err_msg = self.DID_NOT_RUN_ERROR + os.linesep + general_error
                host_results.append(HostResult(host.ip, host.resource_name, False, err_msg, True))
        return host_results

    def _get_final_table(self):
        table = {}
        pattern = '^(' + self.START + ')?(?P<ip>\d+\.\d+\.\d+\.\d+)(' + self.END + ')?\s*\\t*\:.+unreachable=(?P<unreachable>\d+).+failed=(?P<failed>\d+)'
        matches = self._scan_for_groups(pattern)
        for m in matches:
            table[m['ip']] = True if int(m['unreachable']) + int(m['failed']) == 0 else False
        return table

    def _get_failing_hosts_errors(self):
        pattern = '^(' + self.START + ')?fatal: \[(?P<ip>\d+\.\d+\.\d+\.\d+)\]\:.*=>\s*(?P<details>\{.*\})\s*(' + self.END + ')?$'
        matches = self._scan_for_groups(pattern)
        ip_to_error = dict([(m['ip'], UnixToHtmlColorConverter().remove_strike(m['details'])) for m in matches])
        return ip_to_error

    def _scan_for_groups(self, pattern):
        matches = list(re.finditer(pattern, self.output, re.MULTILINE))
        matches = [m.groupdict() for m in matches]
        return matches

    def _get_parsed_error(self):
        pattern = '^(' + self.START + ')(\[ERROR\]\:|ERROR\!)\s*(?P<txt>.*)\s*(' + self.END + ')\s*'
        minimized_error = self.error.replace(os.linesep + os.linesep, os.linesep)
        matches = list(re.finditer(pattern, minimized_error, re.MULTILINE | re.DOTALL))
        if (matches):
            return '\n'.join([m.groupdict()['txt'] for m in matches])
        else:
            return self.error


class HostResult(object):
    def __init__(self, ip, resource_name, success, err_msg="", health_check_passed=False):
        """
        reduced result object
        :param str ip:
        :param str resource_name:
        :param bool success:
        :param str err_msg:
        :param bool health_check_passed:
        """
        self.ip = ip
        self.resource_name = resource_name
        self.success = success
        self.error = err_msg
        self.health_check_passed = health_check_passed
