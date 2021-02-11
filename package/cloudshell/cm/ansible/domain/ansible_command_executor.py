from subprocess import Popen, PIPE
import time
import os
from logging import Logger
from cloudshell.api.cloudshell_api import CloudShellAPISession
import re

from cloudshell.cm.ansible.domain.cancellation_sampler import CancellationSampler
from cloudshell.cm.ansible.domain.output.unixToHtmlConverter import UnixToHtmlColorConverter
from cloudshell.cm.ansible.domain.output.ansible_result import AnsibleResult
from cloudshell.shell.core.context import ResourceCommandContext
from cloudshell.cm.ansible.domain.stdout_accumulator import StdoutAccumulator, StderrAccumulator
from Helpers.html_print_wrappers import warn_span


class AnsibleCommandExecutor(object):
    def __init__(self):
        pass

    def execute_playbook(self, playbook_file, inventory_file, args, output_writer, logger, cancel_sampler):
        """
        :type playbook_file: str
        :type inventory_file: str
        :type args: str
        :type logger: Logger
        :type output_writer: OutputWriter
        :type cancel_sampler: CancellationSampler
        :rtype: AnsibleResult
        """
        shell_command = self._create_shell_command(playbook_file, inventory_file, args)
        converter = UnixToHtmlColorConverter()

        logger.info('Running cmd \'%s\' ...' % shell_command)
        start_time = time.time()
        curr_minutes_counter = 0
        output_writer.write("Running Playbook '{}'...".format(playbook_file))

        process = Popen(shell_command, shell=True, stdout=PIPE, stderr=PIPE)
        all_txt_err = ''
        all_txt_out = ''

        with StdoutAccumulator(process.stdout) as stdout:
            with StderrAccumulator(process.stderr) as stderr:
                txt_lines = []
                while True:
                    txt_err = stderr.read_all_txt()
                    txt_out = stdout.read_all_txt()
                    if txt_err:
                        all_txt_err += txt_err
                        txt_lines.append(txt_err)
                    if txt_out:
                        all_txt_out += txt_out
                        txt_lines.append(txt_out)

                    elapsed = time.time() - start_time
                    elapsed_minutes = int(elapsed / 60)

                    # INCREMENT COUNTER EVERY MINUTE
                    if elapsed_minutes > curr_minutes_counter:
                        curr_minutes_counter += 1
                        # DUMP OUTPUT EVERY FIVE MINUTES TO CONSOLE
                        if curr_minutes_counter % 2 == 0:
                            msg = "Playbook '{}' has been running for: {} minutes".format(playbook_file,
                                                                                          curr_minutes_counter)
                            output_writer.write(msg)
                            logger.info(msg)

                        # DUMP OUTPUT EVERY FIVE MINUTES TO CONSOLE
                        if curr_minutes_counter % 5 == 0:
                            playbook_output = self._convert_text(playbook_file, txt_lines, converter, output_writer,
                                                                 logger)
                            header = warn_span("===== Playbook '{}' output after {} minutes =====".format(playbook_file,
                                                                                                          curr_minutes_counter))
                            separator = warn_span("============================================================")
                            output_msg = "\n{}\n{}{}".format(header,
                                                             playbook_output,
                                                             separator)
                            output_writer.write(output_msg)

                    if process.poll() is not None:
                        break
                    if cancel_sampler.is_cancelled():
                        process.kill()
                        cancel_sampler.throw()
                    time.sleep(2)

                try:
                    full_output = converter.convert(os.linesep.join(txt_lines))
                    full_output = converter.remove_strike(full_output)
                    output_writer.write(full_output)
                    logger.error(full_output)
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

    def _create_shell_command(self, playbook_file, inventory_file, args):
        command = "ansible"

        if playbook_file:
            command += "-playbook " + playbook_file
        if inventory_file:
            command += " -i " + inventory_file
        if args:
            command += " " + args
        return command

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
