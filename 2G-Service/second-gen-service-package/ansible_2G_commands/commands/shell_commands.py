class AnsibleSecondGenCommands(object):

    def execute_playbook(self, context, cancellation_context, playbook_path, script_params):
        """
        :param ResourceCommandContext context:
        :param CancellationContext cancellation_context:
        :param str playbook_path:
        :param str script_params:
        :return:
        """
        resource = get_resource_from_context(context)
        api = CloudShellSessionContext(context).get_api()
        res_id = context.reservation.reservation_id
        reporter = self._get_sandbox_reporter(context, api)
        service_name = context.resource.name
        config_selector = resource.ansible_config_selector

        # PACK UP REPO DETAILS
        repo_user = resource.repo_user
        repo_password = api.DecryptPassword(resource.repo_password).Value
        repo_url = self._build_repo_url(resource, playbook_path, reporter)
        repo_details = PlaybookRepoDetails(repo_url, repo_user, repo_password)

        # GET LINKED OR CANVAS RESOURCES
        if context.connectors or config_selector:
            target_host_resources = self._get_linked_resources(context, api, reporter)
            is_global_playbook = False
        else:
            target_host_resources = self._get_canvas_resources(context, api, reporter)
            is_global_playbook = True

        sandbox_data = api.GetSandboxData(res_id).SandboxDataKeyValues

        try:
            ansible_config_json = self._get_ansible_config_json(context, api, reporter,
                                                                target_host_resources,
                                                                repo_details,
                                                                sandbox_data,
                                                                script_params,
                                                                is_global_playbook)
        except Exception as e:
            exc_msg = "Error building playbook request on '{}': {}".format(service_name, str(e))
            reporter.exc_out(exc_msg)
            api.SetServiceLiveStatus(reservationId=res_id, serviceAlias=service_name, liveStatusName="Error",
                                     additionalInfo=str(e))
            raise Exception(exc_msg)

        reporter.info_out("'{}' is Executing Ansible Playbook...".format(context.resource.name))
        try:
            self.first_gen_ansible_shell.execute_playbook(context, ansible_config_json, cancellation_context)
        except Exception as e:
            exc_msg = "Error running playbook on '{}': {}".format(service_name, str(e))
            reporter.exc_out(exc_msg)
            api.SetServiceLiveStatus(reservationId=res_id, serviceAlias=service_name, liveStatusName="Error",
                                     additionalInfo=str(e))
            if len(target_host_resources) == 1:
                resource_name = target_host_resources[0].Name
                api.SetResourceLiveStatus(resourceFullName=resource_name, liveStatusName="Error",
                                          additionalInfo=str(e))
            raise Exception(exc_msg)

        api.SetServiceLiveStatus(reservationId=res_id, serviceAlias=service_name, liveStatusName="Online",
                                 additionalInfo="Playbook Flow Completed")
        if len(target_host_resources) == 1:
            resource_name = target_host_resources[0].Name
            api.SetResourceLiveStatus(resourceFullName=resource_name, liveStatusName="Online",
                                      additionalInfo="Playbook Flow Completed")
        completed_msg = "Ansible Flow Completed for '{}'.".format(context.resource.name)
        reporter.warn_out(completed_msg, log_only=True)
        return completed_msg

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
        api = CloudShellSessionContext(context).get_api()
        res_id = context.reservation.reservation_id
        reporter = self._get_sandbox_reporter(context, api)
        resource = get_resource_from_context(context)
        service_name = context.resource.name

        # PACK UP REPO DETAILS
        repo_user = resource.repo_user
        repo_password = api.DecryptPassword(resource.repo_password).Value
        repo_url = self._build_repo_url(resource, playbook_path, reporter)
        repo_details = PlaybookRepoDetails(repo_url, repo_user, repo_password)

        target_host_resources = self._get_infrastructure_resources(infrastructure_resources, service_name, api,
                                                                   reporter)

        reporter.info_out("'{}' Executing Ansible INFRA Playbook...".format(context.resource.name))
        sandbox_data = api.GetSandboxData(res_id).SandboxDataKeyValues

        try:
            ansible_config_json = self._get_ansible_config_json(context, api, reporter,
                                                                target_host_resources,
                                                                repo_details,
                                                                sandbox_data,
                                                                script_params)
        except Exception as e:
            exc_msg = "Error building playbook request on '{}': {}".format(service_name, str(e))
            reporter.exc_out(exc_msg)
            api.SetServiceLiveStatus(reservationId=res_id, serviceAlias=service_name, liveStatusName="Error",
                                     additionalInfo=str(e))
            raise Exception(exc_msg)

        try:
            self.first_gen_ansible_shell.execute_playbook(context, ansible_config_json, cancellation_context)
        except Exception as e:
            exc_msg = "Error running playbook on '{}': {}".format(service_name, str(e))
            reporter.err_out(exc_msg)
            api.SetServiceLiveStatus(reservationId=res_id, serviceAlias=service_name, liveStatusName="Error",
                                     additionalInfo=str(e))
            if len(target_host_resources) == 1:
                resource_name = target_host_resources[0].Name
                api.SetResourceLiveStatus(resourceFullName=resource_name, liveStatusName="Error",
                                          additionalInfo=str(e))
            raise Exception(exc_msg)

        api.SetServiceLiveStatus(reservationId=res_id, serviceAlias=service_name, liveStatusName="Online",
                                 additionalInfo="Playbook Flow Completed")
        if len(target_host_resources) == 1:
            resource_name = target_host_resources[0].Name
            api.SetResourceLiveStatus(resourceFullName=resource_name, liveStatusName="Online",
                                      additionalInfo="Playbook Flow Completed")
        completed_msg = "Ansible INFRA Flow Completed for '{}'.".format(service_name)
        reporter.warn_out(completed_msg, log_only=True)
        return completed_msg

    def execute_cached_user_playbook(self, context, cancellation_context):
        """
        :param ResourceCommandContext context:
        :param CancellationContext cancellation_context:
        :return:
        """
        api = CloudShellSessionContext(context).get_api()
        res_id = context.reservation.reservation_id
        reporter = self._get_sandbox_reporter(context, api)
        resource = get_resource_from_context(context)
        service_name = resource.name

        sandbox_data = api.GetSandboxData(res_id).SandboxDataKeyValues

        if context.connectors:
            target_host_resources = self._get_linked_resources(context, api, reporter)
        else:
            target_resource = self._get_user_pb_target_resource_from_alias(service_name, api, reporter)
            target_host_resources = [target_resource]

        if not target_host_resources:
            exc_msg = "{} can't run USER playbook. No target host".format(service_name)
            reporter.err_out(exc_msg)
            raise Exception(exc_msg)

        if len(target_host_resources) > 1:
            target_host_names = [x.Name for x in target_host_resources]
            json_outp = json.dumps(target_host_names, indent=4)
            exc_msg = "Can't run USER playbook against multiple hosts. Current targets:\n{}".format(json_outp)
            reporter.err_out(exc_msg)
            raise Exception(exc_msg)

        target_resource_name = target_host_resources[0].Name
        cached_config = self._get_cached_ansi_conf_from_resource_name(target_resource_name, sandbox_data)

        if not cached_config:
            stop_msg = "No cached USER playbook for '{}'. Stopping command.".format(target_resource_name)
            reporter.warn_out(stop_msg, log_only=True)
            return stop_msg

        repo_details = get_cached_user_pb_repo_data(cached_config)

        reporter.info_out("'{}' is Executing USER Ansible Playbook...".format(context.resource.name))
        try:
            ansible_config_json = self._get_ansible_config_json(context, api, reporter,
                                                                target_host_resources,
                                                                repo_details,
                                                                sandbox_data)
        except Exception as e:
            exc_msg = "Error building playbook request on '{}': {}".format(service_name, str(e))
            reporter.exc_out(exc_msg)
            api.SetServiceLiveStatus(reservationId=res_id, serviceAlias=service_name, liveStatusName="Error",
                                     additionalInfo=str(e))
            raise Exception(exc_msg)

        try:
            self.first_gen_ansible_shell.execute_playbook(context, ansible_config_json, cancellation_context)
        except Exception as e:
            exc_msg = "Error running playbook on '{}': {}".format(service_name, str(e))
            reporter.err_out(exc_msg)
            api.SetServiceLiveStatus(reservationId=res_id, serviceAlias=service_name, liveStatusName="Error",
                                     additionalInfo=str(e))
            api.SetResourceLiveStatus(resourceFullName=target_resource_name, liveStatusName="Error",
                                      additionalInfo=str(e))
            raise Exception(exc_msg)

        api.SetServiceLiveStatus(reservationId=res_id, serviceAlias=service_name, liveStatusName="Online",
                                 additionalInfo="USER Playbook Flow Completed")
        if len(target_host_resources) == 1:
            resource_name = target_host_resources[0].Name
            api.SetResourceLiveStatus(resourceFullName=resource_name, liveStatusName="Online",
                                      additionalInfo="Playbook Flow Completed")
        completed_msg = "'{}' USER playbook flow completed.".format(service_name)
        reporter.warn_out(completed_msg, log_only=True)
        return completed_msg

    def execute_cached_mgmt_playbook(self, context, cancellation_context):
        """
        :param ResourceCommandContext context:
        :param CancellationContext cancellation_context:
        :return:
        """
        api = CloudShellSessionContext(context).get_api()
        res_id = context.reservation.reservation_id
        reporter = self._get_sandbox_reporter(context, api)
        resource = get_resource_from_context(context)
        service_name = resource.name

        sandbox_data = api.GetSandboxData(res_id).SandboxDataKeyValues

        target_host_resources = self._get_linked_resources(context, api, reporter)
        if not target_host_resources:
            exc_msg = "{} can't run MGMT playbook. No target host".format(service_name)
            reporter.err_out(exc_msg)
            raise Exception(exc_msg)

        if len(target_host_resources) > 1:
            target_host_names = [x.Name for x in target_host_resources]
            json_outp = json.dumps(target_host_names, indent=4)
            exc_msg = "Can't run MGMT playbook against multiple hosts. Current targets:\n{}".format(json_outp)
            reporter.err_out(exc_msg)
            raise Exception(exc_msg)

        target_resource_name = target_host_resources[0].Name
        cached_config = self._get_cached_ansi_conf_from_resource_name(target_resource_name, sandbox_data)

        if not cached_config:
            stop_msg = "No cached MGMT playbook for '{}'. Stopping command.".format(target_resource_name)
            reporter.warn_out(stop_msg, log_only=True)
            return stop_msg

        repo_details = get_cached_user_pb_repo_data(cached_config)

        reporter.info_out("'{}' is Executing MGMT Ansible Playbook...".format(context.resource.name))
        try:
            ansible_config_json = self._get_ansible_config_json(context=context, api=api, reporter=reporter,
                                                                target_host_resources=target_host_resources,
                                                                repo_details=repo_details,
                                                                sandbox_data=sandbox_data,
                                                                is_mgmt_playbook=True)
        except Exception as e:
            exc_msg = "Error building playbook request on '{}': {}".format(service_name, str(e))
            reporter.exc_out(exc_msg)
            api.SetServiceLiveStatus(reservationId=res_id, serviceAlias=service_name, liveStatusName="Error",
                                     additionalInfo=str(e))
            raise Exception(exc_msg)

        try:
            self.first_gen_ansible_shell.execute_playbook(context, ansible_config_json, cancellation_context)
        except Exception as e:
            exc_msg = "Error running playbook on '{}': {}".format(service_name, str(e))
            reporter.err_out(exc_msg)
            api.SetServiceLiveStatus(reservationId=res_id, serviceAlias=service_name, liveStatusName="Error",
                                     additionalInfo=str(e))
            api.SetResourceLiveStatus(resourceFullName=target_resource_name, liveStatusName="Error",
                                      additionalInfo=str(e))
            raise Exception(exc_msg)

        api.SetServiceLiveStatus(reservationId=res_id, serviceAlias=service_name, liveStatusName="Online",
                                 additionalInfo="MGMT Playbook Flow Completed")
        if len(target_host_resources) == 1:
            resource_name = target_host_resources[0].Name
            api.SetResourceLiveStatus(resourceFullName=resource_name, liveStatusName="Online",
                                      additionalInfo="MGMT Playbook Flow Completed")
        completed_msg = "'{}' MGMT playbook flow completed.".format(service_name)
        reporter.warn_out(completed_msg, log_only=True)
        return completed_msg
