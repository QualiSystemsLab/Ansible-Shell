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
    DISABLED_VALUES = ["off", "false", "no"]
