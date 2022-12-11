class AnsibleDriverException(Exception):
    """ the base exception class """
    pass


class CancellationException(AnsibleDriverException):
    pass


class PlaybookDownloadException(AnsibleDriverException):
    pass


class AnsibleFailedConnectivityException(AnsibleDriverException):
    pass


class AnsibleNotFoundException(AnsibleDriverException):
    pass


class AnsibleConfigNotFoundException(AnsibleDriverException):
    pass


class EsCommandException(AnsibleDriverException):
    pass