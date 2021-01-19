"""
Will run "shellfoundry install" on all shell subdirectories of current folder
"""

import os
import subprocess


def install_shell(dir_name):
    my_path = os.path.abspath(__file__)
    mydir = os.path.dirname(my_path)
    shell_dir_path = os.path.join(mydir, dir_name)
    subprocess.call(["shellfoundry", "install"], cwd=shell_dir_path)
    print("===========================")


directories_in_curdir = [d for d in os.listdir(os.curdir) if os.path.isdir(d)]
if not directories_in_curdir:
    raise Exception("No subdirectories in this folder")

for shell_dir in directories_in_curdir:
    install_shell(shell_dir)
