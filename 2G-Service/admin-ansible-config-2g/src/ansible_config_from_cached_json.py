import json

"""
These are same data models that package uses after parsing json request
It is also what is being cached in sandbox data
These are same keys that server sends with it's request
Note: Only one host data is cached
"""


REPO_URL_PARAM = "REPO_URL"
REPO_USERNAME_PARAM = "REPO_USERNAME"
REPO_PASSWORD_PARAM = "REPO_PASSWORD"
INVENTORY_GROUPS_PARAM = "INVENTORY_GROUPS"


class CachedAnsibleConfiguration(object):
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


class PlaybookRepository(object):
    def __init__(self):
        self.url = None
        self.username = None
        self.password = None


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


def get_cached_ansible_config_from_json(input_json):
    ansi_conf = CachedAnsibleConfiguration()
    playbook_repo = PlaybookRepository()

    my_obj = json.loads(input_json)

    my_obj_repo = my_obj["playbook_repo"]
    playbook_repo.url = my_obj_repo["url"]
    playbook_repo.username = my_obj_repo["username"]
    playbook_repo.password = my_obj_repo["password"]
    ansi_conf.playbook_repo = playbook_repo

    my_obj_hosts = my_obj["hosts_conf"]
    for host_obj in my_obj_hosts:
        host_conf = HostConfiguration()
        host_conf.username = host_obj["username"]
        host_conf.password = host_obj["password"]
        host_conf.ip = host_obj["ip"]
        host_conf.parameters = host_obj["parameters"]
        host_conf.groups = host_obj["groups"]
        host_conf.access_key = host_obj["access_key"]
        host_conf.connection_method = host_obj["connection_method"]
        host_conf.connection_secured = host_obj["connection_secured"]
        ansi_conf.hosts_conf.append(host_conf)

    return ansi_conf


class CachedRepoData(object):
    def __init__(self, playbook_repo, inventory_groups):
        self.playbook_repo = playbook_repo
        self.inventory_groups = inventory_groups


def get_cached_repo_data(cached_ansible_conf):
    """

    :param CachedAnsibleConfiguration cached_ansible_conf:
    :return:
    """
    params_dict = cached_ansible_conf.hosts_conf[0].parameters

    repo = PlaybookRepository()
    repo.url = params_dict.get(REPO_URL_PARAM)
    repo.username = params_dict.get(REPO_USERNAME_PARAM)
    repo.password = params_dict.get(REPO_PASSWORD_PARAM)
    return repo


def get_cached_inventory_groups(cached_ansible_conf):
    """

    :param CachedAnsibleConfiguration cached_ansible_conf:
    :return:
    """
    params_dict = cached_ansible_conf.hosts_conf[0].parameters
    return params_dict.get(INVENTORY_GROUPS_PARAM)
