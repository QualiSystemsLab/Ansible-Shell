import json

"""
These data model keys are what is expected by package driver when parsing
These are same keys that Quali server sends with it's request
Note the camelCase of attributes, these are dumped directly to json
"""


class AnsibleConfigurationRequest2G(object):
    """ build, convert to json, and send to cm-ansible package command """
    def __init__(self, playbook_repo=None, hosts_conf=None, additional_cmd_args=None, timeout_minutes=None):
        """
        :type playbook_repo: PlaybookRepository
        :type hosts_conf: list[HostConfigurationRequest2G]
        :type additional_cmd_args: str
        :type timeout_minutes: float
        """
        self.timeoutMinutes = timeout_minutes or 0.0
        self.repositoryDetails = playbook_repo or PlaybookRepository()
        self.hostsDetails = hosts_conf or []
        self.additionalArgs = additional_cmd_args
        self.isSecondGenService = True
        self.printOutput = True

    def get_pretty_json(self):
        return json.dumps(self, default=lambda o: getattr(o, '__dict__', str(o)), indent=4)


class PlaybookRepository(object):
    def __init__(self, url=None, username=None, password=None):
        self.url = url
        self.username = username
        self.password = password


class HostConfigurationRequest2G(object):
    """ camelCase attributes are reserved JSON keys, snake_case is extra added member """

    def __init__(self):
        self.ip = None
        self.connectionMethod = None
        self.connectionSecured = None
        self.username = None
        self.password = None
        self.accessKey = None
        self.groups = None
        self.parameters = None
        self.resource_name = None


class GenericAnsibleServiceData(object):
    """ generic data structure to be populated from the admin and regular service attributes """

    def __init__(self, service_name, connection_method, inventory_groups, script_parameters, additional_args,
                 timeout_minutes, config_selector, repo_user, repo_password, repo_url, repo_base_path,
                 repo_script_path, gitlab_branch):
        self.service_name = service_name
        self.connection_method = connection_method
        self.inventory_groups = inventory_groups
        self.script_parameters = script_parameters
        self.additional_args = additional_args
        self.timeout_minutes = timeout_minutes
        self.config_selector = config_selector
        self.repo_user = repo_user
        self.repo_password = repo_password
        self.repo_url = repo_url
        self.repo_base_path = repo_base_path
        self.repo_script_path = repo_script_path
        self.gitlab_branch = gitlab_branch
