from cloudshell.shell.core.resource_driver_interface import ResourceDriverInterface
from cloudshell.shell.core.driver_context import InitCommandContext, ResourceCommandContext, CancellationContext
from cs_ansible_second_gen.models.ansible_configuration_request import GenericAnsibleServiceData
from cs_ansible_second_gen.commands.shell_commands import AnsibleSecondGenCommands
from data_model import AdminAnsibleConfig2G


class AdminAnsibleConfig2GDriver(ResourceDriverInterface):

    def __init__(self):
        """
        ctor must be without arguments, it is created with reflection at run time
        """
        self._commands = AnsibleSecondGenCommands()
        pass

    def initialize(self, context):
        """
        Initialize the driver session, this function is called everytime a new instance of the driver is created
        This is a good place to load and cache the driver configuration, initiate sessions etc.
        :param InitCommandContext context: the context the command runs on
        """
        pass

    def execute_playbook(self, context, cancellation_context, playbook_path, script_params):
        """
        :param ResourceCommandContext context:
        :param CancellationContext cancellation_context:
        :param str playbook_path:
        :param str script_params:
        :return:
        """
        service_data = self._get_service_data_from_resource(context)
        return self._commands.execute_playbook(service_data, context, cancellation_context, playbook_path,
                                               script_params)

    def execute_infrastructure_playbook(self, context, cancellation_context, infrastructure_resources, playbook_path,
                                        script_params):
        """
        :param ResourceCommandContext context:
        :param CancellationContext cancellation_context:
        :param str infrastructure_resources:
        :param str playbook_path:
        :param str script_params:
        :return:
        """
        service_data = self._get_service_data_from_resource(context)
        self._commands.execute_infrastructure_playbook(service_data, context, cancellation_context,
                                                       infrastructure_resources, playbook_path, script_params)

    def execute_cached_user_playbook(self, context, cancellation_context):
        """
        :param ResourceCommandContext context:
        :param CancellationContext cancellation_context:
        :return:
        """
        service_data = self._get_service_data_from_resource(context)
        self._commands.execute_cached_user_playbook(service_data, context, cancellation_context)

    def execute_cached_mgmt_playbook(self, context, cancellation_context):
        """
        :param ResourceCommandContext context:
        :param CancellationContext cancellation_context:
        :return:
        """
        service_data = self._get_service_data_from_resource(context)
        self._commands.execute_cached_mgmt_playbook(service_data, context, cancellation_context)

    @staticmethod
    def _get_service_data_from_resource(context):
        resource = AdminAnsibleConfig2G.create_from_context(context)
        return GenericAnsibleServiceData(service_name=resource.name,
                                         connection_method=resource.connection_method,
                                         inventory_groups=resource.inventory_groups,
                                         script_parameters=resource.script_parameters,
                                         additional_args=resource.ansible_cmd_args,
                                         timeout_minutes=resource.timeout_minutes,
                                         config_selector=resource.ansible_config_selector,
                                         repo_user=resource.repo_user,
                                         repo_password=resource.repo_password,
                                         repo_url=resource.playbook_url_full,
                                         repo_base_path=resource.playbook_base_path,
                                         repo_script_path=resource.playbook_script_path,
                                         gitlab_branch=resource.gitlab_branch)

    def cleanup(self):
        """
        Destroy the driver session, this function is called everytime a driver instance is destroyed
        This is a good place to close any open sessions, finish writing to log files
        """
        pass