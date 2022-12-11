from enum import Enum


DRIVER_SERVICE_NAME_PREFIX = "MPB"
ANSIBLE_MGMT_FAILED_PREFIX = "failed_execution_"

# family app attributes
MGMT_ANSIBLE_LOG_ATTR = "MGMT Ansible Log"
USER_ANSIBLE_LOG_ATTR = "User Ansible Log"
SANDBOX_DATA_EXTRA_ANSIBLE_PARAMS_KEY = "EXTRA_ANSIBLE_PARAMS"


# app param to disable preflight health check
class ConnectivityCheckAppParam(Enum):
    PARAM_NAME = "CONNECTIVITY_CHECK"
    DISABLED_VALUES = ["off", "false", "no", "n"]
    ENABLED_VALUES = ["on", "true", "yes", "y"]


class EsConnectivityCommandParams(Enum):
    PRE_COMMAND_PARAM = "CONNECTIVITY_PRE_COMMAND"
    POST_COMMAND_PARAM = "CONNECTIVITY_POST_COMMAND"


ANSIBLE_PARAM_SSH_COMMON_ARGS = "ansible_ssh_common_args"