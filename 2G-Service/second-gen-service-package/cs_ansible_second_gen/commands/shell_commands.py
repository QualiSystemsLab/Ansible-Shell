import json
from cloudshell.shell.core.session.cloudshell_session import CloudShellSessionContext
from cs_ansible_second_gen.commands.shell_logic import AnsibleSecondGenLogic
from cs_ansible_second_gen.models.ansible_config_from_cached_json import get_cached_user_pb_repo_data
from cs_ansible_second_gen.models.ansible_configuration_request import GenericAnsibleServiceData
from cs_ansible_second_gen.exceptions.exceptions import AnsibleSecondGenServiceException
from cs_ansible_second_gen.commands.utility.sandbox_reporter import SandboxReporter
from cloudshell.cm.ansible.ansible_shell import AnsibleShell
from cloudshell.shell.core.driver_context import ResourceCommandContext, CancellationContext
from cloudshell.api.cloudshell_api import CloudShellAPISession


class AnsibleSecondGenCommands(object):
    def __init__(self):
        self._logic = AnsibleSecondGenLogic()
        self._first_gen_ansible_shell = AnsibleShell()
        self._supported_protocols = ["http", "https"]

    def execute_playbook(self, service_data, context, cancellation_context, playbook_path, script_params):
        """
        :param GenericAnsibleServiceData service_data:
        :param ResourceCommandContext context:
        :param CancellationContext cancellation_context:
        :param str playbook_path:
        :param str script_params:
        :return:
        """
        api = CloudShellSessionContext(context).get_api()
        res_id = context.reservation.reservation_id
        reporter = self._logic.get_sandbox_reporter(context, api)
        service_name = context.resource.name
        config_selector = service_data.config_selector

        target_host_resources = self._logic.get_playbook_target_resources(api, reporter, res_id, context,
                                                                          config_selector,
                                                                          service_name, service_data)

        repo_details = self._logic.get_repo_details(api, playbook_path, reporter, service_data,
                                                    self._supported_protocols)

        try:
            ansible_config_json = self._logic.get_ansible_config_json(service_data,
                                                                      target_host_resources,
                                                                      repo_details,
                                                                      reporter,
                                                                      script_params)
        except Exception as e:
            custom_msg = "Issue building ansible JSON request"
            exc_msg = self._build_exc_msg(service_name, custom_msg, e)
            self._log_and_status(exc_msg, reporter, api, res_id, service_name)
            raise AnsibleSecondGenServiceException(exc_msg)

        completed_msg = self._run_and_validate_playbook(api, res_id, reporter, context, cancellation_context,
                                                        ansible_config_json,
                                                        service_name)
        return completed_msg

    def execute_infrastructure_playbook(self, service_data, context, cancellation_context, infrastructure_resources,
                                        playbook_path,
                                        script_params):
        """
        :param GenericAnsibleServiceData service_data:
        :param ResourceCommandContext context:
        :param CancellationContext cancellation_context:
        :param str infrastructure_resources:
        :param str playbook_path:
        :param str script_params:
        :return:
        """
        api = CloudShellSessionContext(context).get_api()
        res_id = context.reservation.reservation_id
        reporter = self._logic.get_sandbox_reporter(context, api)
        service_name = context.resource.name

        target_host_resources = self._logic.get_infrastructure_resources(infrastructure_resources, service_name, api,
                                                                         reporter)

        repo_details = self._logic.get_repo_details(api, playbook_path, reporter, service_data,
                                                    self._supported_protocols)

        try:
            ansible_config_json = self._logic.get_ansible_config_json(service_data,
                                                                      target_host_resources,
                                                                      repo_details,
                                                                      reporter,
                                                                      script_params)
        except Exception as e:
            custom_msg = "Issue building ansible JSON request"
            exc_msg = self._build_exc_msg(service_name, custom_msg, e)
            self._log_and_status(exc_msg, reporter, api, res_id, service_name)
            raise AnsibleSecondGenServiceException(exc_msg)

        completed_msg = self._run_and_validate_playbook(api, res_id, reporter, context, cancellation_context,
                                                        ansible_config_json,
                                                        service_name, "Infra Playbook")
        return completed_msg

    def execute_cached_user_playbook(self, service_data, context, cancellation_context):
        """
        :param GenericAnsibleServiceData service_data:
        :param ResourceCommandContext context:
        :param CancellationContext cancellation_context:
        :return:
        """
        api = CloudShellSessionContext(context).get_api()
        res_id = context.reservation.reservation_id
        reporter = self._logic.get_sandbox_reporter(context, api)
        service_name = service_data.service_name

        sandbox_data = api.GetSandboxData(res_id).SandboxDataKeyValues
        target_host_resources = self._logic.get_user_playbook_target_resources(api, context, reporter, res_id,
                                                                               service_data,
                                                                               service_name)
        self._validate_cached_playbook_target_hosts_count(reporter, service_name, target_host_resources)
        target_resource = target_host_resources[0]

        try:
            cached_config = self._logic.get_cached_ansi_conf_from_resource_name(target_resource.Name, sandbox_data)
        except Exception as e:
            err_msg = "Issue getting cached config for user playbook. {}: {}".format(type(e).__name__, str(e))
            reporter.err_out(err_msg)
            raise AnsibleSecondGenServiceException(err_msg)

        repo_details = get_cached_user_pb_repo_data(cached_config)
        if not repo_details.url:
            err_msg = "No user playbook defined on app. 'REPO_URL' param must be populated"
            reporter.err_out(err_msg)
            raise AnsibleSecondGenServiceException(err_msg)

        try:
            ansible_config_json = self._logic.get_cached_ansible_user_pb_config_json(api,
                                                                                     target_resource,
                                                                                     repo_details,
                                                                                     cached_config,
                                                                                     reporter)
        except Exception as e:
            custom_msg = "Issue building ansible JSON request for User Playbook."
            exc_msg = self._build_exc_msg(service_name, custom_msg, e)
            self._log_and_status(exc_msg, reporter, api, res_id, service_name)
            raise AnsibleSecondGenServiceException(exc_msg)

        completed_msg = self._run_and_validate_playbook(api, res_id, reporter, context, cancellation_context,
                                                        ansible_config_json,
                                                        service_name, "User Playbook")
        return completed_msg

    def execute_cached_mgmt_playbook(self, service_data, context, cancellation_context):
        """
        :param GenericAnsibleServiceData service_data:
        :param ResourceCommandContext context:
        :param CancellationContext cancellation_context:
        :return:
        """
        api = CloudShellSessionContext(context).get_api()
        res_id = context.reservation.reservation_id
        reporter = self._logic.get_sandbox_reporter(context, api)
        service_name = service_data.service_name

        sandbox_data = api.GetSandboxData(res_id).SandboxDataKeyValues

        target_host_resources = self._logic.get_linked_resources(api, service_name, res_id, context.connectors,
                                                                 service_data.config_selector, reporter)

        self._validate_cached_playbook_target_hosts_count(reporter, service_name, target_host_resources)

        target_resource = target_host_resources[0]
        cached_config = self._logic.get_cached_ansi_conf_from_resource_name(target_resource.Name, sandbox_data)

        if not cached_config:
            err_msg = "No cached data for MGMT playbook '{}'".format(target_resource.Name)
            reporter.err_out(err_msg)
            raise AnsibleSecondGenServiceException(err_msg)

        try:
            ansible_config_json = self._logic.get_cached_ansible_mgmt_config_json(service_data,
                                                                                  target_resource,
                                                                                  cached_config,
                                                                                  reporter)
        except Exception as e:
            custom_msg = "Issue building ansible JSON request"
            exc_msg = self._build_exc_msg(service_name, custom_msg, e)
            self._log_and_status(exc_msg, reporter, api, res_id, service_name)
            raise AnsibleSecondGenServiceException(exc_msg)

        completed_msg = self._run_and_validate_playbook(api, res_id, reporter, context, cancellation_context,
                                                        ansible_config_json,
                                                        service_name, "Management Playbook")
        return completed_msg

    def _run_and_validate_playbook(self, api, res_id, reporter, context, cancellation_context, ansible_config_json,
                                   service_name, playbook_type="playbook"):
        reporter.info_out("'{}' running {}...".format(context.resource.name, playbook_type))
        try:
            result_msg = self._first_gen_ansible_shell.execute_playbook(context, ansible_config_json,
                                                                        cancellation_context)
        except Exception as e:
            custom_msg = "Issue executing playbook driver"
            exc_msg = self._build_exc_msg(service_name, custom_msg, e)
            self._log_and_status(exc_msg, reporter, api, res_id, service_name)
            raise AnsibleSecondGenServiceException(exc_msg)
        if "failed" in result_msg:
            custom_msg = "Failed playbook result"
            exc_msg = self._build_exc_msg(service_name, custom_msg)
            self._log_and_status(exc_msg, reporter, api, res_id, service_name)
            raise AnsibleSecondGenServiceException(exc_msg)
        api.SetServiceLiveStatus(reservationId=res_id, serviceAlias=service_name, liveStatusName="Online",
                                 additionalInfo="Playbook Flow Completed")
        completed_msg = "Ansible service '{}' completed SUCCESSFULLY.".format(context.resource.name)
        reporter.info_out(completed_msg, log_only=True)
        return completed_msg

    @staticmethod
    def _validate_cached_playbook_target_hosts_count(reporter, service_name, target_host_resources):
        if not target_host_resources:
            exc_msg = "{} can't run USER playbook. No target host".format(service_name)
            reporter.err_out(exc_msg)
            raise AnsibleSecondGenServiceException(exc_msg)
        if len(target_host_resources) > 1:
            target_host_names = [x.Name for x in target_host_resources]
            json_output = json.dumps(target_host_names, indent=4)
            exc_msg = "Can't run USER playbook against multiple hosts. Current targets:\n{}".format(json_output)
            reporter.err_out(exc_msg)
            raise AnsibleSecondGenServiceException(exc_msg)

    @staticmethod
    def _log_and_status(exc_msg, reporter, api, res_id, service_name):
        """
        log and print message and set live status on service
        :param CloudShellAPISession api:
        :param SandboxReporter reporter:
        :param str res_id:
        :param str service_name:
        :return:
        """
        reporter.exc_out(exc_msg)
        api.SetServiceLiveStatus(reservationId=res_id, serviceAlias=service_name, liveStatusName="Error",
                                 additionalInfo=exc_msg)

    @staticmethod
    def _build_exc_msg(service_name, custom_message="", inner_exc=None):
        exc_msg = "Service '{}' Error.".format(service_name)

        if custom_message:
            exc_msg += "{}.".format(custom_message)

        if inner_exc:
            exc_msg += "Inner Exception '{}': {}".format(type(inner_exc).__name__, str(inner_exc))
        else:
            exc_msg += "See Logs / Activity Feed for more details."
        return exc_msg
