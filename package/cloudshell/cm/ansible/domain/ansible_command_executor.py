from subprocess import Popen, PIPE, check_output
import time
import os
from logging import Logger
from cloudshell.api.cloudshell_api import CloudShellAPISession

from cloudshell.cm.ansible.domain.cancellation_sampler import CancellationSampler
from cloudshell.cm.ansible.domain.output.unixToHtmlConverter import UnixToHtmlColorConverter
from cloudshell.cm.ansible.domain.output.ansible_result import AnsibleResult
from cloudshell.shell.core.context import ResourceCommandContext
from cloudshell.cm.ansible.domain.stdout_accumulator import StdoutAccumulator, StderrAccumulator
from Helpers.html_print_wrappers import warn_span
from exceptions import AnsibleNotFoundException, EsCommandException


class AnsibleCommandExecutor(object):
    POLLING_INTERVAL_SECONDS = 2
    MINIMUM_CHUNKED_OUTPUT_LINE_SIZE = 20

    def __init__(self):
        pass

    def execute_playbook(self, playbook_file, inventory_file, args, output_writer, logger, cancel_sampler,
                         service_name):
        """
        :type playbook_file: str
        :type inventory_file: str
        :type args: str
        :type logger: Logger
        :type output_writer: ReservationOutputWriter
        :type cancel_sampler: CancellationSampler
        :type service_name: str
        :rtype: AnsibleResult
        """
        shell_command = self._create_shell_command(playbook_file, inventory_file, args)
        converter = UnixToHtmlColorConverter()

        logger.info('Running cmd \'%s\' ...' % shell_command)
        output_writer.write("Running Playbook '{}'...".format(playbook_file))

        process = Popen(shell_command, shell=True, stdout=PIPE, stderr=PIPE)
        all_txt_err = ''
        all_txt_out = ''

        start_time = time.time()
        curr_minutes_counter = 0
        chop_start_index = 0

        with StdoutAccumulator(process.stdout) as stdout:
            with StderrAccumulator(process.stderr) as stderr:
                all_txt_lines = []
                while True:
                    curr_txt_lines_out = stdout.read_all_txt()
                    curr_txt_err_lines_out = stderr.read_all_txt()
                    curr_txt_out = os.linesep.join(curr_txt_lines_out)
                    curr_txt_err = os.linesep.join(curr_txt_err_lines_out)

                    # now merging lists of real lines instead of chunked text
                    # will be easier to analyze content of lines and determine output triggers
                    if curr_txt_lines_out:
                        all_txt_lines += curr_txt_lines_out
                    if curr_txt_err_lines_out:
                        all_txt_lines += curr_txt_err_lines_out

                    # collect the full output and err_output in separate string variable as before
                    if curr_txt_err:
                        all_txt_err += curr_txt_err
                    if curr_txt_out:
                        all_txt_out += curr_txt_out

                    # get elapsed time info
                    elapsed = time.time() - start_time
                    elapsed_minutes = int(elapsed / 60)
                    elapsed_seconds = int(elapsed)

                    # Increment minute counter every minute
                    if elapsed_minutes > curr_minutes_counter:
                        curr_minutes_counter += 1

                    chop_end_index = None

                    # need minimum amount of lines before chopping and printing (Let's say 10)
                    starting_iteration_index = chop_start_index + self.MINIMUM_CHUNKED_OUTPUT_LINE_SIZE
                    if len(all_txt_lines) > starting_iteration_index:
                        chop_end_index = self.get_target_chopping_index(all_txt_lines, starting_iteration_index)

                    if chop_end_index:
                        target_lines = all_txt_lines[chop_start_index:chop_end_index]
                        elapsed_run_time = self._format_elapsed_run_time_string(curr_minutes_counter,
                                                                                elapsed_seconds)
                        self._write_to_console_and_log_target_lines(service_name, target_lines, converter,
                                                                    elapsed_run_time,
                                                                    output_writer, logger)
                        # move pointer along
                        chop_start_index = chop_end_index

                    if process.poll() is not None:
                        break
                    if cancel_sampler.is_cancelled():
                        process.kill()
                        cancel_sampler.throw()
                    time.sleep(self.POLLING_INTERVAL_SECONDS)

                try:
                    # PRINT REMAINING OUTPUT IN BUFFER
                    elapsed = time.time() - start_time
                    total_elapsed_seconds = int(elapsed)
                    elapsed_total_minutes = int(elapsed / 60)
                    target_lines = all_txt_lines[chop_start_index:len(all_txt_lines) - 1]
                    elapsed_run_time = self._format_elapsed_run_time_string(elapsed_total_minutes,
                                                                            total_elapsed_seconds)
                    self._write_to_console_and_log_target_lines(service_name, target_lines, converter,
                                                                elapsed_run_time,
                                                                output_writer, logger, True)
                except Exception as e:
                    logger.error("failed to write remaining ansible buffer. {}: {}".format(type(e).__name__, str(e)))

        elapsed = time.time() - start_time
        err_line_count = len(all_txt_err.split(os.linesep))
        out_line_count = len(all_txt_out.split(os.linesep))
        logger.info('Done (after \'%s\' sec, with %s lines of output, with %s lines of error).' % (
            elapsed, out_line_count, err_line_count))
        logger.debug('Err: ' + all_txt_err)
        logger.debug('Out: ' + all_txt_out)
        logger.debug('Code: ' + str(process.returncode))

        return all_txt_out, all_txt_err

    @staticmethod
    def get_target_chopping_index(all_txt_lines, starting_iteration_index):
        """
        loop through designated starting point to end of array looking for chopping point
        :param list[str] all_txt_lines:
        :param int starting_iteration_index:
        :return:
        """
        target_chopping_index = None
        for i in range(starting_iteration_index, len(all_txt_lines)):
            curr_line = all_txt_lines[i]
            if "PLAY RECAP" in curr_line:
                # end of playbook - full output will be on the way shortly - don't need incremental dump
                break
            if "TASK [debug]" in curr_line:
                # Don't want to chop on debug tasks - keep going until the play
                break
            if "PLAY [" in curr_line or "TASK [" in curr_line:
                target_chopping_index = i
        return target_chopping_index

    @staticmethod
    def _create_shell_command(playbook_file, inventory_file, args):
        command = "ansible"

        if playbook_file:
            command += "-playbook " + playbook_file
        if inventory_file:
            command += " -i " + inventory_file
        if args:
            command += " " + args
        return command

    @staticmethod
    def get_ansible_version_data(execution_server_ip):
        command = "ansible --version"
        process = Popen(command, shell=True, stdout=PIPE, stderr=PIPE)
        outp, err_outp = process.communicate()
        if "command not found" in err_outp:
            exc_msg = "Ansible not found on ES '{}'.\nCheck version output: {}".format(execution_server_ip,
                                                                                       err_outp)
            raise AnsibleNotFoundException(exc_msg)
        return outp

    @staticmethod
    def send_es_command_non_blocking(command):
        process = Popen(command, shell=True, stdout=PIPE, stderr=PIPE)
        return process

    @staticmethod
    def send_es_command_blocking(command):
        process = Popen(command, shell=True, stdout=PIPE, stderr=PIPE)
        std_out, std_err = process.communicate()
        if std_err:
            raise EsCommandException("Error running ES command.\n"
                                     "Command: {}\n"
                                     "Error Output: {}".format(command, std_err))
        return std_out

    @staticmethod
    def _convert_text(txt_lines, converter):
        output = converter.convert(os.linesep.join(txt_lines))
        output = converter.remove_strike(output)
        return output

    @staticmethod
    def _format_elapsed_run_time_string(curr_minutes_counter, elapsed_seconds):
        if curr_minutes_counter == 1:
            elapsed_run_time = "{} minute".format(curr_minutes_counter)
        elif curr_minutes_counter > 1:
            elapsed_run_time = "{} minutes".format(curr_minutes_counter)
        else:
            elapsed_run_time = "{} seconds".format(elapsed_seconds)
        return elapsed_run_time

    def _write_to_console_and_log_target_lines(self, service_name, txt_lines, converter, elapsed_run_time_msg,
                                               output_writer,
                                               logger, final_output=False):
        """
        helper method wrapping up the convert action and adding line break sandwich
        :param str service_name:
        :param list[str] txt_lines:
        :param UnixToHtmlColorConverter converter:
        :param str elapsed_run_time_msg: Integer and unit. Example - 1 minute, 2 minutes, 35 seconds etc.
        :param ReservationOutputWriter output_writer:
        :param logger:
        :return:
        """
        playbook_output = self._convert_text(txt_lines, converter)

        context_msg = "COMPLETED" if final_output else "output"
        header = warn_span("===== '{}' {} after {} =====".format(service_name,
                                                                 context_msg,
                                                                 elapsed_run_time_msg))
        separator = warn_span("============================================================")
        output_msg = "\n{}\n{}{}".format(header,
                                         playbook_output,
                                         separator)
        output_writer.write(output_msg)
        logger.info(playbook_output)


class OutputWriter(object):
    def write(self, msg):
        """
        :type msg: str
        """
        raise NotImplementedError()


class ReservationOutputWriter(OutputWriter):
    def __init__(self, session, command_context):
        """
        :type session: CloudShellAPISession
        :type command_context: ResourceCommandContext
        """
        self.session = session
        self.reservation_id = command_context.reservation.reservation_id

    def write(self, msg):
        self.session.WriteMessageToReservationOutput(self.reservation_id, msg)
