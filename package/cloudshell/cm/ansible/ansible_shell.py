import json
import os
import time

from cloudshell.cm.ansible.domain.Helpers.replace_delimited_app_params import replace_delimited_param_val_with_app_address
from cloudshell.cm.ansible.domain.Helpers.ansible_connection_helper import AnsibleConnectionHelper
from cloudshell.cm.ansible.domain.Helpers.sandbox_reporter import SandboxReporter
from cloudshell.cm.ansible.domain.cancellation_sampler import CancellationSampler
from cloudshell.cm.ansible.domain.connection_service import ConnectionService
from cloudshell.cm.ansible.domain.exceptions import PlaybookDownloadException, \
    AnsibleFailedConnectivityException, AnsibleDriverException
from cloudshell.cm.ansible.domain.ansible_command_executor import AnsibleCommandExecutor, ReservationOutputWriter
from cloudshell.cm.ansible.domain.ansible_config_file import AnsibleConfigFile, get_user_ansible_cfg_config_keys
from cloudshell.cm.ansible.domain.ansible_configuration import AnsibleConfigurationParser, AnsibleConfiguration, \
    HostConfiguration, AnsibleServiceNameParser
from cloudshell.cm.ansible.domain.file_system_service import FileSystemService
from cloudshell.cm.ansible.domain.filename_extractor import FilenameExtractor
from cloudshell.cm.ansible.domain.host_vars_file import HostVarsFile
from cloudshell.cm.ansible.domain.http_request_service import HttpRequestService
from cloudshell.cm.ansible.domain.inventory_file import InventoryFile
from cloudshell.cm.ansible.domain.output.ansible_result import AnsibleResult, HostResult
from cloudshell.cm.ansible.domain.playbook_downloader import PlaybookDownloader
from cloudshell.cm.ansible.domain.temp_folder_scope import TempFolderScope
from cloudshell.cm.ansible.domain.zip_service import ZipService
from cloudshell.core.context.error_handling_context import ErrorHandlingContext
from cloudshell.shell.core.session.cloudshell_session import CloudShellSessionContext
from cloudshell.shell.core.session.logging_session import LoggingSessionContext
from domain.models import HttpAuth
from cloudshell.shell.core.driver_context import ResourceCommandContext
from cloudshell.cm.ansible.domain import sandbox_data_caching as sb_data_helper
from cloudshell.api.cloudshell_api import CloudShellAPISession, ReservedResourceInfo
from cloudshell.cm.ansible.domain.Helpers.execution_server_info import get_first_nic_ip
import cloudshell.cm.ansible.domain.driver_globals as constants
from timeit import default_timer
from cloudshell.cm.ansible.domain.Helpers.extract_es_commands import extract_es_commands_from_host_conf


class AnsibleShell(object):
    INVENTORY_FILE_NAME = 'hosts'

    def __init__(self, file_system=None, playbook_downloader=None, playbook_executor=None, session_provider=None,
                 http_request_service=None, zip_service=None):
        """
        :type file_system: FileSystemService
        :type playbook_downloader: PlaybookDownloader
        :type playbook_executor: AnsibleCommandExecutor
        :type session_provider: CloudShellSessionProvider
        """
        http_request_service = http_request_service or HttpRequestService()
        zip_service = zip_service or ZipService()
        self.file_system = file_system or FileSystemService()
        filename_extractor = FilenameExtractor()
        self.downloader = playbook_downloader or PlaybookDownloader(self.file_system, zip_service, http_request_service,
                                                                    filename_extractor)
        self.executor = playbook_executor or AnsibleCommandExecutor()
        self.connection_service = ConnectionService()
        self.ansible_connection_helper = AnsibleConnectionHelper()
        self.execution_server_ip = get_first_nic_ip()

    def execute_playbook(self, command_context, ansi_conf_json, cancellation_context):
        """
        :type command_context: ResourceCommandContext
        :type ansi_conf_json: str
        :type cancellation_context: CancellationContext
        :rtype str
        """
        service_name_parser = AnsibleServiceNameParser(ansi_conf_json)

        # for default management playbooks need to change service name for logging purposes
        if not service_name_parser.is_second_gen_service:
            command_context.resource.name = service_name_parser.rename_first_gen_service_name(
                command_context.resource.name)

        with LoggingSessionContext(command_context) as logger:
            with ErrorHandlingContext(logger):
                with CloudShellSessionContext(command_context) as api:
                    logger.info('\'execute_playbook\' is called with the configuration json: \n' + ansi_conf_json)

                    res_id = command_context.reservation.reservation_id
                    reporter = SandboxReporter(api, res_id, logger)
                    service_name = command_context.resource.name
                    command_start_msg = "'{}' started on ES '{}'".format(service_name,
                                                                         self.execution_server_ip)
                    reporter.info_out(command_start_msg)

                    self.ansible_sanity_check(reporter, service_name)
                    try:
                        playbook_result = self._execute_playbook(command_context, ansi_conf_json, cancellation_context,
                                                                 api, res_id, service_name, logger, reporter)
                    except Exception as e:
                        err_msg = "Ansible Service '{}' execution error. {}: {}".format(service_name,
                                                                                        type(e).__name__,
                                                                                        str(e))
                        reporter.exc_out(err_msg)
                        raise AnsibleDriverException(err_msg)
                    return playbook_result

    def ansible_sanity_check(self, reporter, service_name):
        """
        run ansible version check to see that ansible is installed on ES
        :param SandboxReporter reporter:
        :param str service_name:
        :return:
        """
        # log ansible version info - will also function as ansible sanity check
        try:
            ansible_version_info = self.executor.get_ansible_version_data(
                execution_server_ip=self.execution_server_ip)
        except Exception as e:
            err_msg = "Issue getting Ansible Version Info. Stopping Execution '{}'\nException '{}': {}".format(
                service_name,
                type(e).__name__,
                str(e))
            reporter.err_out(err_msg)
            raise
        reporter.info_out("Ansible version info:\n" + ansible_version_info, log_only=True)

    def _execute_playbook(self, command_context, ansi_conf_json, cancellation_context, api, res_id, service_name,
                          logger, reporter):
        """
        internal wrapper for execute action
        :param ResourceCommandContext command_context:
        :param str ansi_conf_json:
        :param CancellationContext cancellation_context:
        :param CloudShellAPISession api:
        :param str res_id:
        :param str service_name:
        :param logging.Logger logger:
        :param SandboxReporter reporter:
        :return:
        """
        ansi_conf = AnsibleConfigurationParser(api).json_to_object(ansi_conf_json)

        # sandbox details needed to find resource names not provided by server - needed to set live status
        sandbox_details = api.GetReservationDetails(res_id, True).ReservationDescription
        sb_resources = sandbox_details.Resources
        sb_global_inputs = api.GetReservationInputs(res_id).GlobalInputs

        if not ansi_conf.is_second_gen_service:
            # lookup for resource names from IP given by server request
            # 2G service sends the resource name in the json request, so no need for lookup
            ansi_conf = sb_data_helper.find_resources_matching_addresses(sb_resources, ansi_conf, api, reporter)

        # populate log path attribute
        if not ansi_conf.is_second_gen_service:
            self._populate_log_path_attr_value(constants.MGMT_ANSIBLE_LOG_ATTR,
                                               service_name,
                                               api,
                                               ansi_conf.hosts_conf,
                                               reporter)

        else:
            self._populate_log_path_attr_value(constants.USER_ANSIBLE_LOG_ATTR,
                                               service_name,
                                               api,
                                               ansi_conf.hosts_conf,
                                               reporter)

        # 2G service needs to read config data stored on app and no api exists to read this currently
        if not ansi_conf.is_second_gen_service:
            sb_data_helper.cache_host_data_to_sandbox(ansi_conf, api, res_id, reporter)

        # this step merges all global inputs to app params. App level params take precedence
        sb_data_helper.merge_global_inputs_to_app_params(ansi_conf, sb_global_inputs)
        sb_data_helper.merge_sandbox_context_params(sandbox_details, ansi_conf, reporter)
        sb_data_helper.merge_extra_params_from_sandbox_data(api, res_id, ansi_conf, reporter)

        # dynamically updating delimited <APP_NAME> value in params with IP of deployed app
        replace_delimited_param_val_with_app_address(ansi_conf.hosts_conf, sb_resources, reporter)
        es_pre_command, es_post_command = extract_es_commands_from_host_conf(ansi_conf.hosts_conf, reporter)

        output_writer = ReservationOutputWriter(api, command_context)
        log_msg = "Ansible Config Object after manipulations:\n{}".format(ansi_conf.get_pretty_json())
        logger.debug(log_msg)

        # FOR DEBUGGING PURPOSES TO CUT FLOW SHORT AND JUST INSPECT THE MANIPULATED ANSI_CONF JSON
        # output_writer.write(log_msg)
        # return

        cancellation_sampler = CancellationSampler(cancellation_context)
        with TempFolderScope(self.file_system, logger, True):
            # playbook download is primary dependency, get that first before polling the target hosts
            playbook_name = self._download_playbook(ansi_conf, service_name, cancellation_sampler, logger,
                                                    reporter)

            # check that at least one host from list is reachable
            self._wait_for_all_hosts_to_be_deployed(ansi_conf, service_name, api, logger, reporter)

            # if all hosts failed health check throw exception and exit
            self._validate_host_connectivity(ansi_conf.hosts_conf, service_name, reporter)

            # build ansible auxiliary file dependencies for playbook
            self._add_ansible_config_file(logger)
            self._add_inventory_file(ansi_conf, logger)
            self._add_host_vars_files(ansi_conf, logger)

            pre_command_process = None
            if es_pre_command:
                reporter.warn_out("Running non-blocking Pre-Connectivity Command")
                reporter.info_out(es_pre_command)
                pre_command_process = self.executor.send_es_command_non_blocking(es_pre_command)

            # run the downloaded playbook against all hosts that passed connectivity check
            ansible_result, run_time_seconds = self._run_playbook(ansi_conf, playbook_name, output_writer,
                                                                  cancellation_sampler,
                                                                  logger, reporter, service_name)
            if pre_command_process:
                pre_command_process.kill()
            if es_post_command:
                reporter.warn_out("Running non-blocking Post-connectivity Command")
                reporter.info_out(es_post_command)
                post_command_process = self.executor.send_es_command_non_blocking(es_post_command)
                time.sleep(3)
                post_command_process.kill()

            # if failed set live error status, if passed set green with run time info
            try:
                self._set_live_status_for_playbook_hosts(ansible_result.host_results, service_name,
                                                         run_time_seconds, api)
            except Exception as e:
                err_msg = "'{}' had issue setting live status for apps. {}: {}".format(service_name, type(e).__name__, str(e))
                reporter.err_out(err_msg)
                reporter.info_out("Failed hosts: {}".format(ansible_result.to_json()))

            # when re-running playbooks from setup need to clear the error key
            sb_data_helper.reset_failed_sandbox_data(service_name, api, res_id, logger)
            # on fail, store failed hosts json to sandbox data and return failed string without exception
            if ansible_result.failed_hosts:
                failed_hosts_json = ansible_result.failed_hosts_to_json()
                reporter.err_out("FAILED hosts in Ansible Service Execution")
                reporter.info_out("Failed hosts:\n{}".format(failed_hosts_json))

                # if triggered from 2G service no need to store sandbox data
                if not ansi_conf.is_second_gen_service:
                    sb_data_helper.set_failed_hosts_to_sandbox_data(service_name, failed_hosts_json, api, res_id,
                                                                    logger)

                failed_msg = "'{}' completed with failed hosts. See logs for details".format(service_name)
                return failed_msg

            success_msg = "'{}' completed SUCCESSFULLY for all hosts.".format(service_name)
            logger.info(success_msg)
            return success_msg

    def _add_ansible_config_file(self, logger):
        """
        :type logger: Logger
        """
        user_ansible_config_keys = get_user_ansible_cfg_config_keys(logger)
        with AnsibleConfigFile(self.file_system, logger, user_ansible_config_keys) as cfg_file:
            cfg_file.ignore_ssh_key_checking()
            cfg_file.force_color()
            cfg_file.set_retry_path("." + os.pathsep)

    def _add_inventory_file(self, ansi_conf, logger):
        """
        :type ansi_conf: AnsibleConfiguration
        :type logger: logging.Logger
        """
        with InventoryFile(self.file_system, self.INVENTORY_FILE_NAME, logger) as inventory:
            for host_conf in ansi_conf.hosts_conf:
                if not self._is_host_valid(host_conf, logger, "Ansible Hosts List"):
                    continue
                inventory.add_host_and_groups(host_conf.ip, host_conf.groups)

    def _add_host_vars_files(self, ansi_conf, logger):
        """
        :type ansi_conf: AnsibleConfiguration
        :type logger: logging.Logger
        """
        for host_conf in ansi_conf.hosts_conf:
            if not self._is_host_valid(host_conf, logger, "Ansible Vars File"):
                continue

            with HostVarsFile(self.file_system, host_conf.ip, logger) as vars_file:
                vars_file.add_connection_type(host_conf.connection_method)
                ansible_port = self.ansible_connection_helper.get_ansible_port(host_conf)
                vars_file.add_port(ansible_port)
                vars_file.add_vars(host_conf.parameters)

                if host_conf.connection_method == AnsibleConnectionHelper.CONNECTION_METHOD_WIN_RM:
                    if host_conf.connection_secured:
                        vars_file.add_ignore_winrm_cert_validation()

                vars_file.add_username(host_conf.username)
                if host_conf.password:
                    vars_file.add_password(host_conf.password)
                else:
                    file_name = host_conf.ip + '_access_key.pem'
                    with self.file_system.create_file(file_name, 0400) as file_stream:
                        file_stream.write(host_conf.access_key)
                    vars_file.add_conn_file(file_name)

    @staticmethod
    def _is_host_valid(host_conf, logger, file_type):
        """
        validate whether host should be added to hosts list and vars file for playbook execution
        :param HostConfiguration host_conf:
        :param logging.Logger logger:
        :param str file_type: "Hosts List" / "Vars File" - for logging purposes
        :return:
        """
        if not host_conf.resource_name:
            logger.warn("skipping {} for '{}' - missing resource name".format(file_type, host_conf.ip))
            return False
        if not host_conf.health_check_passed:
            logger.warn("skipping {} for '{}' - failed connectivity check".format(file_type,
                                                                                  host_conf.resource_name))
            return False
        if not host_conf.password and not host_conf.access_key:
            logger.warn("skipping {} for '{}' - missing Password / Access Key.".format(file_type,
                                                                                       host_conf.resource_name))
            return False
        return True

    def _download_playbook(self, ansi_conf, service_name, cancellation_sampler, logger, reporter):
        """
        :type ansi_conf: AnsibleConfiguration
        :type service_name: str
        :type cancellation_sampler: CancellationSampler
        :type logger: Logger
        :type reporter: SandboxReporter
        :rtype str
        """
        repo = ansi_conf.playbook_repo
        # we need password field to be passed for gitlab auth tokens (which require token and not user)
        auth = HttpAuth(repo.username, repo.password) if repo.password else None
        reporter.info_out(
            "'{}' Playbook DOWNLOADING from '{}' to ES '{}'..".format(service_name, repo.url_netloc,
                                                                      self.execution_server_ip))
        start_time = default_timer()
        try:
            playbook_name = self.downloader.get(ansi_conf.playbook_repo.url, auth, logger, cancellation_sampler)
        except Exception as e:
            exc_msg = "Error downloading playbook from '{}' to ES '{}'. Exception {}: {}".format(
                repo.url_netloc,
                self.execution_server_ip,
                type(e).__name__,
                str(e))
            reporter.err_out(exc_msg)
            raise PlaybookDownloadException(exc_msg)
        download_seconds = default_timer() - start_time
        completed_msg = "'{}' playbook download finished after '{:.2f}' seconds".format(service_name, download_seconds)
        reporter.info_out(completed_msg)
        return playbook_name

    def _run_playbook(self, ansi_conf, playbook_name, output_writer, cancellation_sampler, logger, reporter,
                      service_name):
        """
        :type ansi_conf: AnsibleConfiguration
        :type playbook_name: str
        :type output_writer: OutputWriter
        :type cancellation_sampler: CancellationSampler
        :type logger: Logger
        :type reporter: SandboxReporter
        :type str service_name:
        """
        start_time = default_timer()
        output, error = self.executor.execute_playbook(
            playbook_name, self.INVENTORY_FILE_NAME, ansi_conf.additional_cmd_args, output_writer, logger,
            cancellation_sampler, service_name)
        total_run_time = default_timer() - start_time
        reporter.info_out("'{}' finished EXECUTING after '{:.2f}' seconds".format(service_name, total_run_time))

        ansible_result = AnsibleResult(output, error, ansi_conf.hosts_conf)

        # STOPPING error here from going to server and failing all hosts
        # if not ansible_result.success:
        #     raise AnsibleException(ansible_result.to_json())

        # pass result object back up to main flow
        return ansible_result, total_run_time

    def _wait_for_all_hosts_to_be_deployed(self, ansi_conf, service_name, api, logger, reporter):
        """
        Pre-flight health check to resources before playbook starts
        :param AnsibleConfiguration ansi_conf:
        :param str service_name:
        :param CloudShellAPISession api:
        :param logging.Logger logger:
        :param SandboxReporter reporter:
        :return:
        """
        wait_for_deploy_msg = "'{}' checking CONNECTIVITY to all hosts...".format(service_name)

        # timeout_minutes = ansi_conf.timeout_minutes

        # since package update does not set value on service setting default hardcoded value to 1
        # this int is how long to poll the device before determining failed health check
        timeout_minutes = 1

        reporter.info_out(wait_for_deploy_msg)
        for host in ansi_conf.hosts_conf:

            # disable pre-flight health check by default - CONNECTIVITY_CHECK must be passed and set to ON to run
            health_check_input = host.parameters.get(constants.ConnectivityCheckAppParam.PARAM_NAME.value, "")
            if health_check_input.lower() in constants.ConnectivityCheckAppParam.DISABLED_VALUES.value:
                reporter.info_out("Skipping pre-flight ansible health check for '{}'".format(host.resource_name))
                host.health_check_passed = True
                continue

            if not host.resource_name:
                err_msg = "Skipping health check for '{}' due to missing resource name".format(host.ip)
                reporter.err_out(err_msg)  # can't set live status without resource name :/
                continue

            if not host.password and not host.access_key:
                err_msg = "Missing credentials on '{}'. Skipping Health Check".format(host.resource_name)
                self._error_log_and_status(api, host.resource_name, err_msg, reporter)
                continue

            ansible_port = self.ansible_connection_helper.get_ansible_port(host)

            # user can overwrite ansible port by passing in custom 'ansible_port' param on app
            custom_ansible_port = host.parameters.get(HostVarsFile.ANSIBLE_PORT)
            if custom_ansible_port:
                ansible_port = custom_ansible_port

            reporter.info_out("Connecting to '{}', IP: {}, Port: {}, Timeout Minutes: {}".format(host.resource_name,
                                                                                                 host.ip,
                                                                                                 ansible_port,
                                                                                                 timeout_minutes))
            try:
                self.connection_service.check_connection(logger, host, ansible_port=ansible_port,
                                                         timeout_minutes=timeout_minutes)
            except Exception as e:
                err_msg = "Connectivity Check FAILED to '{}', IP '{}'. Exception '{}': {}".format(host.ip,
                                                                                                  host.resource_name,
                                                                                                  type(e).__name__,
                                                                                                  str(e))
                self._error_log_and_status(api, host.resource_name, err_msg, reporter)
            else:
                # Set status of health check to passed. Will be added to ansible hosts list
                host.health_check_passed = True

        reporter.info_out("Communication check completed to all hosts.")

    @staticmethod
    def _error_log_and_status(api, resource_name, err_msg, reporter):
        """
        utility function
        :param CloudShellAPISession api:
        :param str resource_name:
        :param str err_msg:
        :param SandboxReporter reporter:
        :return:
        """
        reporter.err_out(err_msg)
        api.SetResourceLiveStatus(resourceFullName=resource_name,
                                  liveStatusName="Error",
                                  additionalInfo=err_msg)

    @staticmethod
    def _set_live_status_for_playbook_hosts(host_results, service_name, run_time_seconds, api):
        """
        :param list[HostResult] host_results:
        :param CloudShellAPISession api:
        :return:
        """
        for host in host_results:
            if not host.resource_name:
                # can't set resource live status without a resource name...
                continue
            # set status for failed playbook results
            if not host.success:
                if not host.health_check_passed:
                    # these errors already had their live status set in real time earlier
                    continue

                live_status_msg = "FAILED playbook service '{}'. Error: {}".format(service_name, host.error)
                api.SetResourceLiveStatus(resourceFullName=host.resource_name,
                                          liveStatusName="Error",
                                          additionalInfo=live_status_msg)
            else:
                live_status_msg = "SUCCESSFUL playbook service '{}'. Runtime: {:.2f} seconds".format(service_name,
                                                                                                     run_time_seconds)
                api.SetResourceLiveStatus(resourceFullName=host.resource_name,
                                          liveStatusName="Online",
                                          additionalInfo=live_status_msg)

    @staticmethod
    def _populate_log_path_attr_value(target_log_attr, service_name, api, hosts_conf, reporter):
        """
        :param str target_log_attr:
        :param str service_name:
        :param CloudShellAPISession api:
        :param list[HostConfiguration] hosts_conf:
        :param SandboxReporter reporter:
        :return:
        """
        reporter.info_out("Setting log path attribute for '{}'".format(target_log_attr))
        for curr_host in hosts_conf:
            resource_name = curr_host.resource_name
            try:
                api.SetAttributeValue(resourceFullPath=resource_name,
                                      attributeName=target_log_attr,
                                      attributeValue=service_name)
            except Exception as e:
                err_msg = "Error setting '{}' attribute for resource '{}'. {}: {}".format(target_log_attr,
                                                                                          curr_host.resource_name,
                                                                                          type(e).__name__,
                                                                                          str(e))
                reporter.err_out(err_msg, log_only=True)
            else:
                reporter.info_out("Log path attributes set successfully", log_only=True)

    def _validate_host_connectivity(self, ansi_conf_list, service_name, reporter):
        """
        :param list[HostConfiguration] ansi_conf_list:
        :param str service_name:
        :param SandboxReporter reporter:
        :return:
        """
        passed_health_check_hosts = [h for h in ansi_conf_list if h.health_check_passed]
        if not passed_health_check_hosts:
            exc_msg = "ALL hosts failed connectivity check for service '{}'. Execution Server IP '{}'".format(
                service_name,
                self.execution_server_ip)
            reporter.err_out(exc_msg)
            raise AnsibleFailedConnectivityException(exc_msg)

    def _run_es_command_non_blocking(self, command, reporter):
        """

        :param str command:
        :param SandboxReporter reporter:
        :return:
        """
        if not command:
            return

        reporter.warn_out("Running non blocking ES command: {}".format(command))
        try:
            process = self.executor.send_es_command_non_blocking(command)
        except Exception as e:
            reporter.err_out("Error running ES command. {}: {}".format(type(e).__name__, str(e)))
