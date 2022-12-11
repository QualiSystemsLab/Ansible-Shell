from cloudshell.cm.ansible.domain.ansible_configuration import HostConfiguration
from cloudshell.cm.ansible.domain.Helpers.replace_delimited_app_params import replace_delimited_param_val_with_app_address
from unittest import TestCase
from mock import Mock

APP_NAME = "APP1"
APP_NAME2 = "APP2"
TEST_PARAM_KEY = "PARAM1"
TEST_PARAM_VAL = "configure first IP <{}>, second IP <{}>".format(APP_NAME, APP_NAME2)


def generate_app_resource_data(resource_count):
    resources = []
    for i in range(resource_count):
        ip = "{0}.{0}.{0}.{0}".format(i + 1)
        app_name = "APP{}".format(i + 1)
        resource = Mock()
        resource.AppDetails.AppName = app_name
        resource.FullAddress = ip
        resources.append(resource)
    return resources


def generate_host_conf_list():
    host_conf = HostConfiguration()
    host_conf.parameters = {TEST_PARAM_KEY: TEST_PARAM_VAL}
    return [host_conf]


class TestParamReplace(TestCase):
    def setUp(self):
        self.reporter = Mock()
        self.host_conf_list = generate_host_conf_list()

    def test_two_replacements(self):
        resources = generate_app_resource_data(2)
        replace_delimited_param_val_with_app_address(self.host_conf_list, resources, self.reporter)
        print("input: {}".format(TEST_PARAM_VAL))
        print("output: {}".format(self.host_conf_list[0].parameters[TEST_PARAM_KEY]))