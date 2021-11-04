from cloudshell.cm.ansible.domain.ansible_configuration import HostConfiguration
from cloudshell.cm.ansible.domain.Helpers.replace_delimited_port import replace_delimited_port_with_random_port
from unittest import TestCase
from mock import Mock


TEST_PARAM_KEY = "PARAM1"
TEST_PARAM_VAL = "bla bla [PORT] bla bla [PORT]"


def generate_host_conf_list():
    host_conf = HostConfiguration()
    host_conf.parameters = {
        TEST_PARAM_KEY: TEST_PARAM_VAL,
        "Param2": "bla [PORT]",
        "Param3": "no replacement here [Port]"
    }
    return [host_conf]


class TestParamReplace(TestCase):
    def setUp(self):
        self.reporter = Mock()
        self.host_conf_list = generate_host_conf_list()

    def test_two_replacements(self):
        replace_delimited_port_with_random_port(self.host_conf_list, self.reporter)
        for key, value in self.host_conf_list[0].parameters.items():
            print("replaced param value: {}".format(value))