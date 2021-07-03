class AnsibleConnectionHelper(object):
    CONNECTION_METHOD_WIN_RM = 'winrm'
    WIN_RM_SECURED_PORT = '5986'
    WIN_RM_PORT = '5985'
    CONNECTION_METHOD_SSH = 'ssh'
    CONNECTION_METHOD_NETWORK_CLI = "network_cli"
    CONNECTION_METHOD_VM_WARE = "vmware_tools"
    SSH_PORT = '22'
    VM_WARE_PORT = '443'

    def __init__(self):
        pass

    def get_ansible_port(self, host):
        if host.connection_method == self.CONNECTION_METHOD_WIN_RM:
            if host.connection_secured:
                return self.WIN_RM_SECURED_PORT
            else:
                return self.WIN_RM_PORT
        if host.connection_method == self.CONNECTION_METHOD_SSH:
            return self.SSH_PORT
        if host.connection_method == self.CONNECTION_METHOD_VM_WARE:
            return self.VM_WARE_PORT
        if host.connection_method == self.CONNECTION_METHOD_NETWORK_CLI:
            return self.SSH_PORT

