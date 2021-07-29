class AnsibleDriverException(Exception):
    pass


class CancellationException(Exception):
    pass


class PlaybookDownloadException(Exception):
    pass


class AnsibleFailedConnectivityException(Exception):
    pass


class AnsibleNotFoundException(Exception):
    pass


class AnsibleConfigNotFoundException(Exception):
    pass