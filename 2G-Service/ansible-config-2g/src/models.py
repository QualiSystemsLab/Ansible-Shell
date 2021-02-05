class CachedAnsibleConfiguration(object):
    def __init__(self, playbook_repo=None, hosts_conf=None, additional_cmd_args=None, timeout_minutes=None):
        """
        :type playbook_repo: PlaybookRepoDetails
        :type hosts_conf: list[HostConfiguration]
        :type additional_cmd_args: str
        :type timeout_minutes: float
        """
        self.timeout_minutes = timeout_minutes or 0.0
        self.playbook_repo = playbook_repo or PlaybookRepoDetails()
        self.hosts_conf = hosts_conf or []
        self.additional_cmd_args = additional_cmd_args
        self.is_second_gen_service = False


class PlaybookRepoDetails(object):
    def __init__(self, url=None, username=None, decrypted_password=None):
        self.url = url
        self.username = username
        self.decrypted_password = decrypted_password


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
