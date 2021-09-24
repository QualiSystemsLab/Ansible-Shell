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
from exceptions import AnsibleNotFoundException


class AnsibleCommandExecutor(object):
    POLLING_INTERVAL_SECONDS = 2
    CHUNKED_OUTPUT_LINE_SIZE = 10

    def __init__(self):
        pass

    def execute_playbook(self, playbook_file, inventory_file, args, output_writer, logger, cancel_sampler):
        """
        :type playbook_file: str
        :type inventory_file: str
        :type args: str
        :type logger: Logger
        :type output_writer: ReservationOutputWriter
        :type cancel_sampler: CancellationSampler
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
        all_txt_lines_pointer = 0

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

                    # TODO - wrap incremental output logic into function
                    # Increment minute counter every minute
                    if elapsed_minutes > curr_minutes_counter:
                        curr_minutes_counter += 1

                    # when minimum chunk size of lines are reached, print output at next task or play that finishes
                    if len(all_txt_lines) > all_txt_lines_pointer + self.CHUNKED_OUTPUT_LINE_SIZE:
                        starting_iteration_index = all_txt_lines_pointer + self.CHUNKED_OUTPUT_LINE_SIZE
                        target_chopping_index = None
                        for i in range(starting_iteration_index, len(all_txt_lines)):
                            curr_line = all_txt_lines[i]
                            if "PLAY RECAP" in curr_line:
                                # end of playbook - full output will be on the way shortly - don't need incremental dump
                                break
                            if "TASK [debug]" in curr_line:
                                # Don't want to chop on debug tasks - keep going until the play
                                continue
                            if "PLAY [" in curr_line or "TASK [" in curr_line:
                                # when we hit the line, slice up to that point
                                logger.debug("playbook / task line: " + curr_line)
                                if len(all_txt_lines) > i:
                                    logger.debug("playbook / task next line: " + all_txt_lines[i + 1])
                                target_chopping_index = i
                                break

                        if target_chopping_index:
                            target_lines = all_txt_lines[all_txt_lines_pointer:target_chopping_index]
                            elapsed_run_time = self._format_elapsed_run_time_string(curr_minutes_counter,
                                                                                    elapsed_seconds)
                            self._write_out_target_lines(playbook_file, target_lines, converter,
                                                         elapsed_run_time,
                                                         output_writer, logger)
                            # move pointer along
                            all_txt_lines_pointer = target_chopping_index

                    if process.poll() is not None:
                        break
                    if cancel_sampler.is_cancelled():
                        process.kill()
                        cancel_sampler.throw()
                    time.sleep(self.POLLING_INTERVAL_SECONDS)

                try:
                    elapsed = time.time() - start_time
                    total_elapsed_seconds = int(elapsed)
                    elapsed_total_minutes = int(elapsed / 60)
                    full_output = converter.convert(os.linesep.join(all_txt_lines))
                    full_output = converter.remove_strike(full_output)
                    elapsed_run_time = self._format_elapsed_run_time_string(elapsed_total_minutes,
                                                                            total_elapsed_seconds)
                    header_msg = warn_span("===== Playbook '{}' DONE after {} =====".format(playbook_file,
                                                                                            elapsed_run_time))
                    separator = warn_span("============================================================")
                    output_writer.write("{}\n{}\n{}".format(header_msg, full_output, separator))
                    logger.debug(full_output)
                except Exception as e:
                    output_writer.write('failed to write text of %s characters (%s)' % (len(full_output), e))
                    logger.debug("failed to write:" + full_output)
                    logger.debug("failed to write.")

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
    def _convert_text(playbook_name, txt_lines, converter, output_writer, logger):
        try:
            full_output = converter.convert(os.linesep.join(txt_lines))
            full_output = converter.remove_strike(full_output)
            return full_output
        except:
            exc_msg = '=== failed to convert playbook output for {} ==='.format(playbook_name)
            output_writer.write(exc_msg)
            logger.info(exc_msg)

    @staticmethod
    def _format_elapsed_run_time_string(curr_minutes_counter, elapsed_seconds):
        if curr_minutes_counter == 1:
            elapsed_run_time = "{} minute".format(curr_minutes_counter)
        elif curr_minutes_counter > 1:
            elapsed_run_time = "{} minutes".format(curr_minutes_counter)
        else:
            elapsed_run_time = "{} seconds".format(elapsed_seconds)
        return elapsed_run_time

    def _write_out_target_lines(self, playbook_file, txt_lines, converter, elapsed_run_time_msg,
                                output_writer,
                                logger):
        """
        helper method wrapping up the convert action and adding line break sandwich
        :param str playbook_file:
        :param list[str] txt_lines:
        :param UnixToHtmlColorConverter converter:
        :param str elapsed_run_time_msg: Integer and unit. Example - 1 minute, 2 minutes, 35 seconds etc.
        :param ReservationOutputWriter output_writer:
        :param logger:
        :return:
        """
        playbook_output = self._convert_text(playbook_file, txt_lines, converter, output_writer, logger)
        header = warn_span("===== Playbook '{}' output after {} =====".format(playbook_file,
                                                                              elapsed_run_time_msg))
        separator = warn_span("============================================================")
        output_msg = "\n{}\n{}{}".format(header,
                                         playbook_output,
                                         separator)
        output_writer.write(output_msg)


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
