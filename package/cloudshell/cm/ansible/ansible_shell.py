import os

from cloudshell.cm.ansible.domain.Helpers.ansible_connection_helper import AnsibleConnectionHelper
from cloudshell.cm.ansible.domain.Helpers.sandbox_reporter import SandboxReporter
from cloudshell.cm.ansible.domain.cancellation_sampler import CancellationSampler
from cloudshell.cm.ansible.domain.connection_service import ConnectionService
from cloudshell.cm.ansible.domain.exceptions import AnsibleDriverException, PlaybookDownloadException, \
    AnsibleFailedConnectivityException
from cloudshell.cm.ansible.domain.ansible_command_executor import AnsibleCommandExecutor, ReservationOutputWriter
from cloudshell.cm.ansible.domain.ansible_config_file import AnsibleConfigFile, get_user_ansible_cfg_config_keys
from cloudshell.cm.ansible.domain.ansible_configuration import AnsibleConfigurationParser, AnsibleConfiguration, \
    HostConfiguration, AnsibleServiceNameParser
from cloudshell.cm.ansible.domain.file_system_service import FileSystemService
from cloudshell.cm.ansible.domain.filename_extractor import FilenameExtractor
from cloudshell.cm.ansible.domain.host_vars_file import HostVarsFile
from cloudshell.cm.ansible.domain.http_request_service import HttpRequestService
from cloudshell.cm.ansible.domain.inventory_file import InventoryFile
from cloudshell.cm.ansible.domain.output.ansible_result import AnsibleResult, HostResult, FAILED_CONNECTIVITY_CHECK_MSG, \
    DUPLICATE_IP_ISSUE_MSG
from cloudshell.cm.ansible.domain.playbook_downloader import PlaybookDownloader
from cloudshell.cm.ansible.domain.temp_folder_scope import TempFolderScope
from cloudshell.cm.ansible.domain.zip_service import ZipService
from cloudshell.core.context.error_handling_context import ErrorHandlingContext
from cloudshell.shell.core.session.cloudshell_session import CloudShellSessionContext
from cloudshell.shell.core.session.logging_session import LoggingSessionContext
from domain.models import HttpAuth
from cloudshell.shell.core.driver_context import ResourceCommandContext
from domain.sandbox_data_caching import find_resources_matching_addresses, cache_host_data_to_sandbox, \
    merge_global_inputs_to_app_params, set_failed_hosts_to_sandbox_data
from cloudshell.api.cloudshell_api import CloudShellAPISession
from cloudshell.cm.ansible.domain.Helpers.execution_server_info import get_first_nic_ip
from timeit import default_timer


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
        if service_name_parser.is_second_gen_service:
            command_context.resource.name = service_name_parser.parse_service_name_from_repo_url()

        with LoggingSessionContext(command_context) as logger:
            with ErrorHandlingContext(logger):
                with CloudShellSessionContext(command_context) as api:
                    logger.info('\'execute_playbook\' is called with the configuration json: \n' + ansi_conf_json)
                    ansi_conf = AnsibleConfigurationParser(api).json_to_object(ansi_conf_json)

                    res_id = command_context.reservation.reservation_id
                    reporter = SandboxReporter(api, res_id, logger)
                    service_name = command_context.resource.name
                    msg = "Ansible service '{}' started on Execution Server '{}'".format(service_name,
                                                                                         self.execution_server_ip)
                    reporter.info_out(msg)

                    # sandbox details needed to find resource names not provided by server - needed to set live status
                    sandbox_details = api.GetReservationDetails(res_id, True).ReservationDescription
                    sb_resources = sandbox_details.Resources
                    sb_global_inputs = api.GetReservationInputs(res_id).GlobalInputs

                    # this step does the IP lookup for resource names and populates data to conf host list
                    ansi_conf = find_resources_matching_addresses(sb_resources, ansi_conf, api, reporter)

                    # 2G service needs to read some config data stored on app and no api exists to read this currently
                    if not ansi_conf.is_second_gen_service:
                        cache_host_data_to_sandbox(ansi_conf, api, res_id, reporter)

                    # this step merges all global inputs to app params. App level params take precedence
                    ansi_conf = merge_global_inputs_to_app_params(ansi_conf, sb_global_inputs)

                    output_writer = ReservationOutputWriter(api, command_context)
                    log_msg = "Ansible Config Object after manipulations:\n{}".format(ansi_conf.get_pretty_json())
                    logger.debug(log_msg)

                    # FOR DEBUGGING PURPOSES TO CUT FLOW SHORT AND JUST INSPECT THE MANIPULATED ANSI_CONF JSON
                    # output_writer.write(log_msg)
                    # return

                    cancellation_sampler = CancellationSampler(cancellation_context)

                    with TempFolderScope(self.file_system, logger):
                        # playbook is ultimate dependency, so let's get that first before polling the target hosts
                        playbook_name = self._download_playbook(ansi_conf, service_name, cancellation_sampler, logger,
                                                                reporter)

                        # check that at least one host from list is reachable
                        self._wait_for_all_hosts_to_be_deployed(ansi_conf, service_name, api, logger, reporter)
                        self._validate_host_connectivity(ansi_conf.hosts_conf, service_name, reporter)

                        # build auxiliary file dependencies
                        self._add_ansible_config_file(logger)
                        self._add_host_vars_files(ansi_conf, logger)
                        self._add_inventory_file(ansi_conf, logger)

                        # run the downloaded playbook against all hosts that passed connectivity check
                        ansible_result, run_time_seconds = self._run_playbook(ansi_conf, playbook_name, output_writer,
                                                                              cancellation_sampler,
                                                                              logger, reporter, service_name)

                        self._set_live_status_for_playbook_hosts(ansible_result.host_results, service_name,
                                                                 run_time_seconds, api)

                        if ansible_result.failed_hosts:
                            failed_hosts_json = ansible_result.failed_hosts_to_json()
                            reporter.err_out("FAILED hosts in Ansible Service Execution")
                            reporter.info_out("Failed hosts:\n{}".format(failed_hosts_json))

                            # for default playbooks store failed hosts to sandbox data so that exception can be thrown later
                            if not ansi_conf.is_second_gen_service:
                                set_failed_hosts_to_sandbox_data(service_name, failed_hosts_json, api, res_id, logger)

                            failed_msg = "Ansible driver '{}' FAILED. See logs for details".format(service_name)
                            return failed_msg

                        success_msg = "Ansible driver '{}' PASSED with no errors".format(service_name)
                        logger.info(success_msg)
                        return success_msg

    def _add_ansible_config_file(self, logger):
        """
        :type logger: Logger
        """
        user_ansible_config_keys = get_user_ansible_cfg_config_keys(logger)
        with AnsibleConfigFile(self.file_system, logger, user_ansible_config_keys) as file:
            file.ignore_ssh_key_checking()
            file.force_color()
            file.set_retry_path("." + os.pathsep)

    def _add_inventory_file(self, ansi_conf, logger):
        """
        :type ansi_conf: AnsibleConfiguration
        :type logger: Logger
        """
        with InventoryFile(self.file_system, self.INVENTORY_FILE_NAME, logger) as inventory:
            for host_conf in ansi_conf.hosts_conf:
                if not host_conf.resource_name:
                    logger.info(
                        "skipping adding host to inventory file for '{}' due to Duplicate IP / missing resource name")
                    continue
                if not host_conf.health_check_passed:
                    logger.info("skipping adding host to inventory file for '{}' due to failed connectivity check")
                    continue
                inventory.add_host_and_groups(host_conf.ip, host_conf.groups)

    def _add_host_vars_files(self, ansi_conf, logger):
        """
        :type ansi_conf: AnsibleConfiguration
        :type logger: Logger
        """
        for host_conf in ansi_conf.hosts_conf:
            if not host_conf.resource_name:
                logger.info("skipping host vars file for '{}' due to Duplicate IP / missing resource name")
                continue
            if not host_conf.health_check_passed:
                logger.info("skipping host vars file for '{}' due to failed connectivity check")
                continue

            with HostVarsFile(self.file_system, host_conf.ip, logger) as file:
                file.add_vars(host_conf.parameters)
                file.add_connection_type(host_conf.connection_method)
                ansible_port = self.ansible_connection_helper.get_ansible_port(host_conf)
                file.add_port(ansible_port)

                if host_conf.connection_method == AnsibleConnectionHelper.CONNECTION_METHOD_WIN_RM:
                    if host_conf.connection_secured:
                        file.add_ignore_winrm_cert_validation()

                file.add_username(host_conf.username)
                if host_conf.password:
                    file.add_password(host_conf.password)
                else:
                    file_name = host_conf.ip + '_access_key.pem'
                    with self.file_system.create_file(file_name, 0400) as file_stream:
                        file_stream.write(host_conf.access_key)
                    file.add_conn_file(file_name)

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
            "Starting Playbook download from '{}' to Execution Server '{}'".format(repo.url, self.execution_server_ip))
        start_time = default_timer()
        try:
            playbook_name = self.downloader.get(ansi_conf.playbook_repo.url, auth, logger, cancellation_sampler)
        except Exception as e:
            exc_msg = "Issue downloading playbook from '{}' to Execution Server '{}'. Exception: {}".format(repo.url,
                                                                                                            self.execution_server_ip,
                                                                                                            str(e))
            reporter.err_out(exc_msg)
            raise PlaybookDownloadException(exc_msg)
        download_seconds = default_timer() - start_time
        completed_msg = "Service '{}' finished playbook download from '{}' after '{}' seconds".format(service_name,
                                                                                                      repo.url,
                                                                                                      download_seconds)
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
        reporter.info_out("Ansible Service '{}' executing the playbook '{}'...".format(service_name, playbook_name))

        start_time = default_timer()
        output, error = self.executor.execute_playbook(
            playbook_name, self.INVENTORY_FILE_NAME, ansi_conf.additional_cmd_args, output_writer, logger,
            cancellation_sampler)
        total_run_time = default_timer() - start_time
        reporter.info_out("Ansible Service '{}' done executing after '{}' seconds".format(service_name, total_run_time))

        ansible_result = AnsibleResult(output, error, ansi_conf.hosts_conf)

        # swallowing error here from going to server and failing all hosts
        # if not ansible_result.success:
        #     raise AnsibleException(ansible_result.to_json())

        # pass result object back up to main flow
        return ansible_result, total_run_time

    def _wait_for_all_hosts_to_be_deployed(self, ansi_conf, service_name, api, logger, reporter):
        """

        :param AnsibleConfiguration ansi_conf:
        :param str service_name:
        :param CloudShellAPISession api:
        :param logging.Logger logger:
        :param SandboxReporter reporter:
        :return:
        """
        wait_for_deploy_msg = "Waiting for all hosts to deploy for service '{}'...".format(service_name)

        # timeout_minutes = ansi_conf.timeout_minutes

        # since package update does not set value on service setting default hardcoded value to 1
        timeout_minutes = 1

        reporter.info_out(wait_for_deploy_msg)
        for host in ansi_conf.hosts_conf:
            if not host.resource_name:
                skip_message = "Skipping health check for host '{}' due to duplicate IP error".format(host.ip)
                reporter.warn_out(skip_message)
                continue

            ansible_port = self.ansible_connection_helper.get_ansible_port(host)

            if HostVarsFile.ANSIBLE_PORT in host.parameters.keys() and (
                    host.parameters[HostVarsFile.ANSIBLE_PORT] != '' and
                    host.parameters[HostVarsFile.ANSIBLE_PORT] is not None):
                ansible_port = host.parameters[HostVarsFile.ANSIBLE_PORT]

            port_ansible_port = "Connectivity Timeout: {} minutes, Ansible port: {}".format(timeout_minutes,
                                                                                            ansible_port)

            reporter.info_out("Trying to connect to host:" + host.ip)
            reporter.info_out(port_ansible_port)

            try:
                self.connection_service.check_connection(logger, host, ansible_port=ansible_port,
                                                         timeout_minutes=timeout_minutes)
            except Exception as e:
                err_msg = "Connectivity Check FAILED to Resource '{}', IP '{}'. Message: '{}'".format(host.ip,
                                                                                                      host.resource_name,
                                                                                                      str(e))
                reporter.err_out(err_msg)
                api.SetResourceLiveStatus(resourceFullName=host.resource_name,
                                          liveStatusName="Error",
                                          additionalInfo=err_msg)
            else:
                # Set status of health check to passed. Will be added to ansible hosts list
                host.health_check_passed = True

        reporter.info_out("Communication check completed to all hosts.")

    @staticmethod
    def _set_live_status_for_playbook_hosts(host_results, service_name, run_time_seconds, api):
        """
        :param list[HostResult] host_results:
        :param CloudShellAPISession api:
        :return:
        """
        for host in host_results:
            # these errors already had their live status set in real time earlier
            if DUPLICATE_IP_ISSUE_MSG in host.error:
                continue
            if FAILED_CONNECTIVITY_CHECK_MSG in host.error:
                continue

            # set status for failed playbook results
            if not host.success:
                live_status_msg = "FAILED playbook service '{}'. Error: {}".format(service_name, host.error)
                api.SetResourceLiveStatus(resourceFullName=host.resource_name,
                                          liveStatusName="Error",
                                          additionalInfo=live_status_msg)
            else:
                live_status_msg = "SUCCESSFUL playbook service '{}'. Runtime: {} seconds".format(service_name,
                                                                                                 run_time_seconds)
                api.SetResourceLiveStatus(resourceFullName=host.resource_name,
                                          liveStatusName="Online",
                                          additionalInfo=live_status_msg)

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
