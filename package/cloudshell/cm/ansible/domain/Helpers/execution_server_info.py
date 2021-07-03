from subprocess import check_output

HOSTNAME_COMMAND = "hostname -I"


def get_first_nic_ip():
    output = check_output(HOSTNAME_COMMAND, shell=True)
    split = output.split(" ")
    if split:
        return split[0]
    return None

