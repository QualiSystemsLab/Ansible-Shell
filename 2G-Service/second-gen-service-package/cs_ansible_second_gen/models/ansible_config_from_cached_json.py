from cloudshell.cm.ansible.domain.ansible_configuration import PlaybookRepository
from cs_ansible_second_gen.service_globals import user_pb_params
import json


class CachedAnsibleConfiguration(object):
    def __init__(self, playbook_repo_decrypted_password=None, hosts_conf=None, additional_cmd_args=None, timeout_minutes=None):
        """
        :type playbook_repo_decrypted_password: CachedPlaybookRepoDecryptedPassword
        :type hosts_conf: list[CachedHostConfiguration]
        :type additional_cmd_args: str
        :type timeout_minutes: float
        """
        self.timeout_minutes = timeout_minutes or 0.0
        self.playbook_repo = playbook_repo_decrypted_password or CachedPlaybookRepoDecryptedPassword()
        self.hosts_conf = hosts_conf or []
        self.additional_cmd_args = additional_cmd_args
        self.is_second_gen_service = True


class CachedPlaybookRepoDecryptedPassword(object):
    """ the cached sandbox data object has password already decrypted """
    def __init__(self, url=None, username=None, decrypted_password=None):
        self.url = url
        self.username = username
        self.decrypted_password = decrypted_password


class CachedHostConfiguration(object):
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


def get_cached_ansible_config_from_json(input_json):
    ansi_conf = CachedAnsibleConfiguration()
    playbook_repo = CachedPlaybookRepoDecryptedPassword()

    my_obj = json.loads(input_json)

    # REPO
    my_obj_repo = my_obj["playbook_repo"]
    playbook_repo.url = my_obj_repo["url"]
    playbook_repo.username = my_obj_repo["username"]
    playbook_repo.decrypted_password = my_obj_repo["password"]
    ansi_conf.playbook_repo = playbook_repo

    # HOSTS - SHOULD ONLY BE ONE
    my_obj_hosts = my_obj["hosts_conf"]

    if not my_obj_hosts:
        raise Exception("No hosts configuration data stored.")

    if len(my_obj_hosts) > 1:
        raise Exception("hosts data list greater than 1:\n{}".format(json.dumps(my_obj_hosts, indent=4)))

    host_obj = my_obj_hosts[0]
    host_conf = CachedHostConfiguration()
    host_conf.username = host_obj["username"]
    host_conf.password = host_obj["password"]
    host_conf.ip = host_obj["ip"]
    host_conf.resource_name = host_obj["resource_name"]
    host_conf.parameters = host_obj["parameters"]
    host_conf.groups = host_obj["groups"]
    host_conf.access_key = host_obj["access_key"]
    host_conf.connection_method = host_obj["connection_method"]
    host_conf.connection_secured = host_obj["connection_secured"]
    ansi_conf.hosts_conf.append(host_conf)
    return ansi_conf


# USER PLAYBOOKS
def get_cached_user_pb_repo_data(cached_ansible_conf):
    """
    stored as extra user parameters
    :param CachedAnsibleConfiguration cached_ansible_conf:
    :return:
    """
    params_dict = cached_ansible_conf.hosts_conf[0].parameters
    repo = CachedPlaybookRepoDecryptedPassword()
    repo.url = params_dict.get(user_pb_params.REPO_URL_PARAM)
    repo.username = params_dict.get(user_pb_params.REPO_USERNAME_PARAM)
    repo.decrypted_password = params_dict.get(user_pb_params.REPO_PASSWORD_PARAM)
    return repo


def get_cached_user_pb_inventory_groups_str(cached_ansible_conf):
    """
    stored as extra user parameters
    :param CachedAnsibleConfiguration cached_ansible_conf:
    :return:
    """
    params_dict = cached_ansible_conf.hosts_conf[0].parameters
    return params_dict.get(user_pb_params.INVENTORY_GROUPS_PARAM)


# MGMT PLAYBOOKS
def get_cached_mgmt_pb_inventory_groups_list(cached_ansible_conf):
    """
    stored as extra user parameters
    :param CachedAnsibleConfiguration cached_ansible_conf:
    :return:
    """
    groups_list = cached_ansible_conf.hosts_conf[0].groups
    return groups_list
