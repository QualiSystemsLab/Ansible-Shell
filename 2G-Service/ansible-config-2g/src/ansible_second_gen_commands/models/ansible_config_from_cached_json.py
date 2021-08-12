from models import CachedAnsibleConfiguration, PlaybookRepoDetails, HostConfiguration
import json

# USER PLAYBOOK PARAMS - DEFINED AS PARAMETERS ON APPS
REPO_URL_PARAM = "REPO_URL"
REPO_USERNAME_PARAM = "REPO_USERNAME"
REPO_PASSWORD_PARAM = "REPO_PASSWORD"
INVENTORY_GROUPS_PARAM = "INVENTORY_GROUPS"


def get_cached_ansible_config_from_json(input_json):
    ansi_conf = CachedAnsibleConfiguration()
    playbook_repo = PlaybookRepoDetails()

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


def get_cached_user_pb_repo_data(cached_ansible_conf):
    """
    stored as extra user parameters
    :param CachedAnsibleConfiguration cached_ansible_conf:
    :return:
    """
    params_dict = cached_ansible_conf.hosts_conf[0].parameters

    repo = PlaybookRepoDetails()
    repo.url = params_dict.get(REPO_URL_PARAM)
    repo.username = params_dict.get(REPO_USERNAME_PARAM)
    repo.decrypted_password = params_dict.get(REPO_PASSWORD_PARAM)
    return repo


def get_cached_user_pb_inventory_groups_str(cached_ansible_conf):
    """
    stored as extra user parameters
    :param CachedAnsibleConfiguration cached_ansible_conf:
    :return:
    """
    params_dict = cached_ansible_conf.hosts_conf[0].parameters
    return params_dict.get(INVENTORY_GROUPS_PARAM)


def get_cached_mgmt_pb_inventory_groups_list(cached_ansible_conf):
    """
    stored as extra user parameters
    :param CachedAnsibleConfiguration cached_ansible_conf:
    :return:
    """
    groups_list = cached_ansible_conf.hosts_conf[0].groups
    return groups_list
