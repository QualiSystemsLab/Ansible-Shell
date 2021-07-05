from itertools import groupby


class PlaybookTaskListParsingException(Exception):
    pass


class PlaybookData(object):
    def __init__(self, task_list_input):
        """
        :param str task_list_input:
        """
        self.task_list_input = task_list_input
        self.playbook_name = None
        self.plays = []
        try:
            self._parse_task_list()
        except Exception as e:
            raise PlaybookTaskListParsingException("Issue parsing playbook data: {}. Exception: {}".format(self.task_list_input,
                                                                                                           str(e)))

    def _parse_task_list(self):
        lines = self.task_list_input.splitlines()

        # clean lines - any multispace lines will be reduced and filtered out in groupby sort
        lines = [x.strip() for x in lines]

        grouped_lines = self._get_grouped_lines(lines)

        playbook_name_string = grouped_lines[0][0]  # list of lists

        # Sample Playbook line: 'playbook: run_tasks.yaml'
        self.playbook_name = playbook_name_string.split(":")[1].strip()

        chunked_plays = grouped_lines[1:]
        for curr_play_chunk in chunked_plays:
            new_play = PlaybookPlay()
            # Sample play name string: 'play #1 (all): run serial tasks       TAGS: []'
            new_play.play_name = curr_play_chunk[0].split(":")[1].split("TAGS")[0].strip()
            task_lines = curr_play_chunk[2:]
            for curr_line in task_lines:
                # Sample task line name: '  task 1    TAGS: []'
                task_name = curr_line.split("TAGS")[0].strip()
                new_task = PlaybookTask(task_name)
                new_play.tasks.append(new_task)
            self.plays.append(new_play)

            pass

    @staticmethod
    def _get_grouped_lines(lines):
        """
        split input lines into groups based on empty strings
        itertools.groupby can group based on consecutive occurences
         based on this example - https: // stackoverflow.com / a / 52943659
         sample lines input from ansible-playbook --tasks-list command
        [
        "",
        "playbook: my_playbook.yaml",
        "",
        "play #1 (all): my play     TAGS: []"
        "tasks:",
        "task 1:    TAGS: []",
        "",
        "play #2 (all): my second play  TAGS: []"
        "tasks:",
        "task 1:    TAGS: []",
        ""
        ]
        :param list[str] lines:
        :return:
        """
        grouped_lines = [list(g) for k, g in groupby(lines, key=bool) if k]
        return grouped_lines


class PlaybookPlay(object):
    def __init__(self):
        self.play_name = None
        self.tasks = []


class PlaybookTask(object):
    def __init__(self, task_name):
        self.task_name = task_name


if __name__ == "__main__":
    SAMPLE_TASK_LIST = """
playbook: run_tasks.yaml

play #1 (all): run serial tasks       TAGS: []
tasks:
  task 1    TAGS: []
  task 2    TAGS: []
  debug     TAGS: []

play #2 (all): second play    TAGS: []
tasks:
  task 1    TAGS: []
  task 2    TAGS: []
  debug     TAGS: []
    """
    playbook_data = PlaybookData(SAMPLE_TASK_LIST)
    pass
