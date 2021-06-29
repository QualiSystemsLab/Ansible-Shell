import os
from unittest import TestCase
from subprocess import PIPE
from cloudshell.cm.ansible.domain.connection_service import ConnectionService
from cloudshell.cm.ansible.domain.ansible_configuration import HostConfiguration
from mock import Mock, patch
from timeit import default_timer


TARGET_HOST_IP = "localhost"
TARGET_HOST_USER = "natti"
TARGET_HOST_PASSWORD = "ubuntu"


class TestConnectionService(TestCase):

    def setUp(self):
        self.connection_service = ConnectionService()
        self.logger = Mock()
        self._set_host_config()

    def _set_host_config(self):
        host_config = HostConfiguration()
        host_config.ip = TARGET_HOST_IP
        host_config.username = TARGET_HOST_USER
        host_config.password = TARGET_HOST_PASSWORD
        self.host_config = host_config

    def tearDown(self):
        pass

    def test_ssh_connection(self):
        self.host_config.connection_method = "SSH"
        self.connection_service.check_connection(logger=self.logger,
                                                 target_host=self.host_config,
                                                 ansible_port=22)

    def test_failed_ssh_connection_one_minute(self):
        self.host_config.connection_method = "SSH"
        start = default_timer()
        try:
            self.connection_service.check_connection(logger=self.logger,
                                                     target_host=self.host_config,
                                                     ansible_port=11,
                                                     timeout_minutes=1)
        except Exception as e:
            total_time = default_timer() - start
            print(total_time)
            assert(59 < total_time < 61)

