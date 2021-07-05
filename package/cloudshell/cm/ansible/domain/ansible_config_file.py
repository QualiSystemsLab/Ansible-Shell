from subprocess import Popen, PIPE
from file_system_service import FileSystemService
from logging import Logger
import os
from collections import OrderedDict
import re
from cloudshell.cm.ansible.domain.exceptions import AnsibleDriverException


class AnsibleConfigFile(object):
    FILE_NAME = 'ansible.cfg'
    DEFAULTS_STANZA = '[defaults]'

    def __init__(self, file_system, logger, config_keys=None):
        """
        :type file_system: FileSystemService
        :type logger: Logger
        """
        self.file_system = file_system
        self.logger = logger
        self.config_keys = config_keys if config_keys else OrderedDict([(self.DEFAULTS_STANZA, OrderedDict())])

    def __enter__(self):
        self.logger.info('Creating \'%s\' configuration file ...'%AnsibleConfigFile.FILE_NAME)
        return self

    def __exit__(self, type, value, traceback):
        with self.file_system.create_file(AnsibleConfigFile.FILE_NAME) as file_stream:
            cfg_lines_list = _cfg_config_keys_to_lines_list(self.config_keys)

            # write merged cfg to file system
            file_stream.write(os.linesep.join(cfg_lines_list))

            # mask passwords and log cfg file contents
            password_masked_lines = _cfg_lines_to_password_masked_lines(cfg_lines_list)
            self.logger.info(os.linesep.join(password_masked_lines))
        self.logger.info('Done.')

    def ignore_ssh_key_checking(self):
        self.config_keys[self.DEFAULTS_STANZA]['host_key_checking'] = 'False'

    def force_color(self):
        self.config_keys[self.DEFAULTS_STANZA]['force_color'] = '1'

    def set_retry_path(self, save_path):
        self.config_keys[self.DEFAULTS_STANZA]['retry_files_save_path'] = str(save_path)


# ANSIBLE CFG MERGE HELPERS
def _read_user_ansible_cfg():
    """
    read in users cfg data from file system
    :return:
    """
    process = Popen("ansible-config view", shell=True, stdout=PIPE, stderr=PIPE)
    outp = process.stdout.read()
    return outp


def _build_config_keys_from_user_cfg(input_cfg_text):
    """
    convert user cfg string into data structure
    return ordered dict of ordered dicts
    {
        '[defaults]': {key1: val1, key2: val2},
        '[paramiko_connection]': {key1: val1, key2: val2},
        '[ssh_connection]': {key1: val1, key2: val2}
    }
    :param str input_cfg_text:
    :return:
    """
    config_keys = OrderedDict()
    lines = input_cfg_text.splitlines()
    cleaned_lines = [x.strip() for x in lines]
    curr_cfg_stanza = None
    for line in cleaned_lines:

        # skip comments
        if line.startswith("#") or not line:
            continue

        # match the stanza headers - example '[defaults]', '[paramiko_connection]'
        if re.match('\[\w+\]', line):
            config_keys[line] = OrderedDict()
            curr_cfg_stanza = line
            continue

        if curr_cfg_stanza:
            key, value = [x.strip() for x in line.split("=")]
            config_keys[curr_cfg_stanza][key] = value

    return config_keys


def _cfg_config_keys_to_lines_list(config_keys):
    lines = []
    for stanza, curr_settings in config_keys.items():
        lines.append(stanza)
        for key, value in curr_settings.items():
            lines.append(key + ' = ' + value)
        lines.append("")  # extra line as buffer between stanzas
    lines.pop()  # remove last empty space
    return lines


def _cfg_lines_to_password_masked_lines(cfg_lines_list):
    """
    masking passwords for logging ansible.cfg
    :param list[str] cfg_lines_list:
    """
    result = []
    for curr_line in cfg_lines_list:
        if "=" in curr_line:
            key, value = [x.strip() for x in curr_line.split("=")]
            if "pass" in key:
                value = "********"
            curr_line = key + " = " + value
        result.append(curr_line)
    return result


def get_user_ansible_cfg_config_keys(logger):
    """
    main function putting together steps to read in data and get data structure
    :param logging.Logger logger:
    :return:
    """
    try:
        ansible_cfg_output = _read_user_ansible_cfg()
    except Exception as e:
        exc_msg = "Issue READING user ansible.cfg"
        logger.error(exc_msg)
        raise AnsibleDriverException(exc_msg)

    try:
        config_keys = _build_config_keys_from_user_cfg(ansible_cfg_output)
    except Exception as e:
        exc_msg = "Issue PROCESSING user ansible.cfg"
        logger.error(exc_msg)
        raise AnsibleDriverException(exc_msg)

    return config_keys


if __name__ == "__main__":
    sample_config = """
[DEPRECATION WARNING]: Ansible will require Python 3.8 or newer on the controller starting
with Ansible 2.12. Current version: 3.7.2 (default, May 23 2021, 05:14:11) [GCC 4.8.5
20150623 (Red Hat 4.8.5-44)]. This feature will be removed from ansible-core in version
2.12. Deprecation warnings can be disabled by setting deprecation_warnings=False in ansible.cfg.

[defaults]
host_key_checking = True
random_key=true
ansible_ssh_pass = super_secret_password
# third_key=false

[paramiko_connections]
key_1=val_1
key_2 = val_2

[ssh_connections]
key_1 = val_1
key_3 = val_3
    """
    my_config_keys = _build_config_keys_from_user_cfg(sample_config)
    lines = _cfg_config_keys_to_lines_list(my_config_keys)
    password_masked_lines = _cfg_lines_to_password_masked_lines(lines)
    x = os.linesep.join(password_masked_lines)
    pass
