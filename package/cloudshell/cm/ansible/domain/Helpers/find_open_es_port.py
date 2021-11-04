import random
import socket
from contextlib import closing

# dynamic ephemeral range standard
ES_PORT_RANGE = "49152-65535"
MAX_PORT_RETRIES = 100


def is_socket_taken(host, port):
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        connect_status_no = sock.connect_ex((host, port))
        if connect_status_no == 0:
            return True
        else:
            return False


def _get_open_es_port(excluded_list=None, attempts=0):
    """
    Recursively check for open port
    :param excluded_list:
    :param attempts:
    :return:
    """
    excluded_list = excluded_list if excluded_list else []
    # get random number in range
    range_bounds = ES_PORT_RANGE.split("-")
    if not len(range_bounds) == 2:
        raise ValueError("Incorrectly set port range: {}".format(ES_PORT_RANGE))
    range_bounds = [int(curr_num) for curr_num in range_bounds]
    random_port = random.randint(range_bounds[0], range_bounds[1])

    if attempts > MAX_PORT_RETRIES:
        raise Exception("Could not find open port after {} attempts".format(MAX_PORT_RETRIES))

    # check that is not already used by other app in playbook
    if random_port in excluded_list:
        _get_open_es_port(excluded_list, attempts+1)

    # check that its open
    if not is_socket_taken("127.0.0.1", random_port):
        return random_port
    else:
        _get_open_es_port(excluded_list, attempts+1)


def get_open_es_port(excluded_list):
    return _get_open_es_port(excluded_list)


if __name__ == "__main__":
    print(get_open_es_port(None))
