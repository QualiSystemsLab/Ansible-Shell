import os
from logging import Logger
from file_system_service import FileSystemService
from Helpers.build_ansible_list_var import params_list_to_yaml, build_simple_list_from_comma_separated


class HostVarsFile(object):
    FOLDER_NAME = 'host_vars'
    ANSIBLE_USER = 'ansible_user'
    ANSIBLE_PASSWORD = 'ansible_password'
    ANSIBLE_CONNECTION = 'ansible_connection'
    ANSIBLE_PORT = 'ansible_port'
    ANSIBLE_CONNECTION_FILE = 'ansible_ssh_private_key_file'
    ANSIBLE_WINRM_CERT_VALIDATION = 'ansible_winrm_server_cert_validation'
    ANSIBLE_SSH_COMMON_ARGS = 'ansible_ssh_common_args'

    def __init__(self, file_system, host_name, logger):
        """
        :type file_system: FileSystemService
        :type host_name: str
        :type logger: Logger
        """
        self.file_system = file_system
        self.logger = logger
        self.file_path = os.path.join(HostVarsFile.FOLDER_NAME, host_name)
        self.playbook_vars = {}

    def __enter__(self):
        self.logger.info('Creating \'%s\' vars file ...' % self.file_path)
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if not self.file_system.exists(HostVarsFile.FOLDER_NAME):
            self.file_system.create_folder(HostVarsFile.FOLDER_NAME)
        with self.file_system.create_file(self.file_path) as file_stream:
            lines = ['---']
            for key, value in sorted(self.playbook_vars.iteritems()):
                if type(value) == list or type(value) == dict:
                    lines.append(params_list_to_yaml(key, value))
                elif "," in value:
                    lines.append(build_simple_list_from_comma_separated(key, value))
                else:
                    lines.append(str(key) + ': ' + str(value))
            file_stream.write(os.linesep.join(lines))
            log_lines = self._mask_password_vars(lines)
            self.logger.info(os.linesep.join(log_lines))
        self.logger.info('Done.')

    @staticmethod
    def _mask_password_vars(lines):
        # mask password values
        log_lines = []
        for line in lines:
            if ":" in line:
                split = line.split(":")
                if len(split) < 3 and "pass" in split[0]:
                    split[1] = "******"
                new_line = "{}: {}".format(split[0], ":".join(split[1:]))
                log_lines.append(new_line)
            else:
                log_lines.append(line)
        return log_lines

    def add_vars(self, playbook_vars):
        self.playbook_vars.update(playbook_vars)

    def add_connection_type(self, connection_type):
        self.playbook_vars[HostVarsFile.ANSIBLE_CONNECTION] = connection_type

    def add_conn_file(self, file_path):
        self.playbook_vars[HostVarsFile.ANSIBLE_CONNECTION_FILE] = file_path

    def add_username(self, username):
        self.playbook_vars[HostVarsFile.ANSIBLE_USER] = username

    def add_password(self, password):
        self.playbook_vars[HostVarsFile.ANSIBLE_PASSWORD] = password

    def add_port(self, port):
        if HostVarsFile.ANSIBLE_PORT not in self.playbook_vars.keys() or \
                (self.playbook_vars[HostVarsFile.ANSIBLE_PORT] == '') or \
                self.playbook_vars[HostVarsFile.ANSIBLE_PORT] is None:
            self.playbook_vars[HostVarsFile.ANSIBLE_PORT] = port

    def add_ignore_winrm_cert_validation(self):
        self.playbook_vars[HostVarsFile.ANSIBLE_WINRM_CERT_VALIDATION] = 'ignore'
