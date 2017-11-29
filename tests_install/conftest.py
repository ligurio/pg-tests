import glob
import platform
import pytest
import os
import shutil
import subprocess


from helpers.os_helpers import delete_data_directory
from helpers.pginstall import delete_packages
from helpers.pginstall import delete_repo
from helpers.os_helpers import download_file

if platform.system() == 'Linux':
    dist = platform.linux_distribution()
elif platform.system() == 'Windows':
    dist = 'Windows'
else:
    print("Unknown Distro")


def pytest_addoption(parser):
    """This method needed for running pytest test with options
    Example: command "pytest --product_edition=standard" will install
    postgrespro with standard edition

    :param parser pytest default param for command line args:
    :return:
    """
    parser.addoption("--target", action="store", default='linux',
                     help="Operating system")
    parser.addoption("--product_version", action="store", default='9.6',
                     help="Specify product version. Available values: 9.5, 9.6")
    parser.addoption("--product_name", action="store", default='postgrespro',
                     help="Specify product name. Available values: postgrespro, postresql")
    parser.addoption("--product_edition", action="store", default='ee',
                     help="Specify product edition. Available values: ee, standard")
    parser.addoption("--product_milestone", action="store",
                     help="Specify product milestone. Available values: beta")
    parser.addoption("--product_build", action="store",
                     help="Specify product build.")
    parser.addoption("--branch", action="store",
                     help="Specify branch")
    parser.addoption("--skip_install", action="store_true")

