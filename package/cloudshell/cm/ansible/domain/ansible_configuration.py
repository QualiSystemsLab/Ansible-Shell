import json
from cloudshell.api.cloudshell_api import CloudShellAPISession
from cloudshell.cm.ansible.domain.Helpers.parse_script_path_from_repo_url import parse_script_path_from_url, get_net_loc_from_url
from cloudshell.cm.ansible.domain.driver_globals import DRIVER_SERVICE_NAME_PREFIX


# OPTIONAL SCRIPT PARAMETERS, IF PRESENT WILL OVERRIDE THE DEFAULT READ-ONLY VALUES
# THESE SHOULD BE CUSTOM PARAMS DEFINED ON APP
CONNECTION_METHOD_PARAM = "CONNECTION_METHOD"
ACCESS_KEY_PARAM = "ACCESS_KEY"


class AnsibleConfiguration(object):
    def __init__(self, playbook_repo=None, hosts_conf=None, additional_cmd_args=None, timeout_minutes=None):
        """
        :type playbook_repo: PlaybookRepository
        :type hosts_conf: list[HostConfiguration]
        :type additional_cmd_args: str
        :type timeout_minutes: float
        """
        self.timeout_minutes = timeout_minutes or 0.0
        self.playbook_repo = playbook_repo or PlaybookRepository()
        self.hosts_conf = hosts_conf or []
        self.additional_cmd_args = additional_cmd_args
        self.is_second_gen_service = False

    def get_pretty_json(self):
        return json.dumps(self, default=lambda o: getattr(o, '__dict__', str(o)), indent=4)


class PlaybookRepository(object):
    def __init__(self):
        self.url = None
        self.username = None
        self.password = None
        self.url_netloc = None


class HostConfiguration(object):
    def __init__(self):
        self.ip = None
        self.connection_method = None
        self.connection_secured = None
        self.username = None
        self.password = None
        self.access_key = None
        self.groups = []
        self.parameters = {}
        self.resource_name = None
        self.health_check_passed = False


def over_ride_defaults(ansi_conf, params_dict, host_index):
    """
    go over custom params and over-ride values for HOSTS only
    :param AnsibleConfiguration ansi_conf:
    :param dict params_dict:
    :return same config:
    :rtype AnsibleConfiguration
    """

    if params_dict.get(CONNECTION_METHOD_PARAM):
        ansi_conf.hosts_conf[host_index].connection_method = params_dict[CONNECTION_METHOD_PARAM].lower()

    if params_dict.get(ACCESS_KEY_PARAM):
        ansi_conf.hosts_conf[host_index].connection_method = params_dict[CONNECTION_METHOD_PARAM].lower()

    return ansi_conf


class AnsibleConfigurationParser(object):

    def __init__(self, api):
        """
        :type api: CloudShellAPISession
        """
        self.api = api

    def json_to_object(self, json_str):
        """
        Decodes a json string to an AnsibleConfiguration instance.
        :type json_str: str
        :rtype AnsibleConfiguration
        """
        ansi_conf_dict = json.loads(json_str)
        AnsibleConfigurationParser._validate(ansi_conf_dict)

        ansi_conf = AnsibleConfiguration()
        ansi_conf.additional_cmd_args = ansi_conf_dict.get('additionalArgs')
        ansi_conf.timeout_minutes = ansi_conf_dict.get('timeoutMinutes', 0.0)

        # if using 2G wrapper service then skip the param override replacement step - all params come from service
        is_second_gen_service = ansi_conf_dict.get('isSecondGenService', False)
        ansi_conf.is_second_gen_service = is_second_gen_service

        if ansi_conf_dict.get('repositoryDetails'):
            ansi_conf.playbook_repo.url = ansi_conf_dict['repositoryDetails'].get('url')
            ansi_conf.playbook_repo.username = ansi_conf_dict['repositoryDetails'].get('username')
            ansi_conf.playbook_repo.password = self._get_repo_password(ansi_conf_dict)
            ansi_conf.playbook_repo.url_netloc = get_net_loc_from_url(ansi_conf.playbook_repo.url)

        for host_index, json_host in enumerate(ansi_conf_dict.get('hostsDetails', [])):
            host_conf = HostConfiguration()
            host_conf.ip = json_host.get('ip')
            host_conf.resource_name = json_host.get('resourceName')
            host_conf.connection_method = json_host.get('connectionMethod').lower()
            host_conf.connection_secured = bool_parse(json_host.get('connectionSecured'))
            host_conf.username = json_host.get('username')
            host_conf.password = self._get_password(json_host)
            host_conf.access_key = self._get_access_key(json_host)
            host_conf.groups = json_host.get('groups')
            if json_host.get('parameters'):
                all_params_dict = dict((i['name'], i['value']) for i in json_host['parameters'])
                host_conf.parameters = all_params_dict

                # CONSIDERING TO DEPRECATE THIS OVERRIDE FEATURE COMPLETELY AS IT OPENS POTENTIAL FOR BUGS
                # PLAYBOOKS WITH MULTIPLE HOSTS CAN'T LOGICALLY OVERRIDE THE SINGLETON SCRIPT URL PARAMS
                # if not is_second_gen_service:
                    # 2G service doesn't need override logic, this is only relevant for default flow
                    # ansi_conf = over_ride_defaults(ansi_conf, all_params_dict, host_index)
            ansi_conf.hosts_conf.append(host_conf)

        return ansi_conf

    # catching decrpyt errors to use plain text passwords coming from 2G service
    def _get_password(self, json_host):
        pw = json_host.get('password')
        if pw:
            try:
                return self.api.DecryptPassword(pw).Value
            except Exception as e:
                pass
        return pw

    def _get_repo_password(self, ansi_conf_dict):
        pw = ansi_conf_dict['repositoryDetails'].get('password')
        if pw:
            try:
                return self.api.DecryptPassword(pw).Value
            except Exception as e:
                pass
        return pw

    def _get_access_key(self, json_host):
        key = json_host.get('accessKey')
        if key:
            try:
                return self.api.DecryptPassword(key).Value
            except Exception as e:
                pass
        return key

    @staticmethod
    def _validate(json_obj):
        """
        :type json_obj: dict
        :rtype bool
        """
        basic_msg = 'Failed to parse ansible configuration input json: '

        if json_obj.get('repositoryDetails') is None:
            raise SyntaxError(basic_msg + 'Missing "repositoryDetails" node.')

        if json_obj['repositoryDetails'].get('url') is None:
            raise SyntaxError(basic_msg + 'Missing "repositoryDetails.url" node.')

        if not json_obj['repositoryDetails'].get('url'):
            raise SyntaxError(basic_msg + '"repositoryDetails.url" node cannot be empty.')

        if json_obj.get('hostsDetails') is None:
            raise SyntaxError(basic_msg + 'Missing "hostsDetails" node.')

        if len(json_obj['hostsDetails']) == 0:
            raise SyntaxError(basic_msg + '"hostsDetails" node cannot be empty.')

        hosts_without_ip = [h for h in json_obj['hostsDetails'] if not h.get('ip')]
        if hosts_without_ip:
            raise SyntaxError(basic_msg + 'Missing "ip" node in ' + str(len(hosts_without_ip)) + ' hosts.')

        hosts_without_conn = [h for h in json_obj['hostsDetails'] if not h.get('connectionMethod')]
        if hosts_without_conn:
            raise SyntaxError(basic_msg + 'Missing "connectionMethod" node in ' + str(len(hosts_without_conn)) + ' hosts.')


def bool_parse(b):
    if b is None:
        return False
    else:
        return str(b).lower() == 'true'


class AnsibleServiceNameParser(object):

    def __init__(self, ansible_json):
        """
        :type api: CloudShellAPISession
        """
        self._ansible_json = ansible_json
        self.is_second_gen_service = False
        self.repo_url = None
        self._load_json()

    def _load_json(self):
        """
        Decodes a json string to an AnsibleConfiguration instance.
        :type json_str: str
        :rtype AnsibleConfiguration
        """
        json_obj = json.loads(self._ansible_json)
        self.is_second_gen_service = json_obj.get('isSecondGenService', False)
        self.repo_url = json_obj['repositoryDetails'].get('url')

    def rename_first_gen_service_name(self, current_first_gen_name):
        """
        :param str current_first_gen_name:
        :return:
        """
        first_gen_server_id = current_first_gen_name.split("_")[1].split("--")[0].strip()
        script_path = parse_script_path_from_url(self.repo_url)
        service_name = "{}_{}__{}".format(DRIVER_SERVICE_NAME_PREFIX, first_gen_server_id, script_path)
        return service_name



