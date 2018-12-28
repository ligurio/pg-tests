import glob
import platform
import pytest
import os
import shutil
import subprocess

if platform.system() == 'Linux':
    dist = platform.linux_distribution()
elif platform.system() == 'Windows':
    dist = 'Windows'
else:
    print("Unknown Distro")


def pytest_addoption(parser):
    """This method needed for running pytest test with options
    Example: command "pytest --product_edition=std" will install
    postgrespro with standard edition

    :param parser pytest default param for command line args:
    :return:
    """
    parser.addoption(
        "--target", action="store", default='linux',
        help="Operating system")
    parser.addoption(
        "--product_version", action="store", default='9.6',
        help="Specify product version. Available values: 9.5, 9.6")
    parser.addoption(
        "--product_name", action="store", default='postgrespro',
        help="Specify product name. Available values: postgrespro, postresql")
    parser.addoption(
        "--product_edition", action="store", default='ent',
        help="Specify product edition. Available values: ent, std")
    parser.addoption(
        "--product_milestone", action="store",
        help="Specify product milestone. Available values: beta")
    parser.addoption(
        "--product_build", action="store",
        help="Specify product build.")
    parser.addoption(
        "--branch", action="store",
        help="Specify branch")
    parser.addoption("--skip_install", action="store_true")


@pytest.fixture(scope="session", autouse=True)
def setup(request):
    def finalize():
        if dist != 'Windows':
            test_script = r"""
if ps -o comm= -C systemd-coredump; then
    echo "The systemd-coredump process is running."
    for i in `seq 1 30`; do
        if ps -o comm= -C systemd-coredump >/dev/null; then
            sleep $i
        else
            break
        fi
    done
    if ps -o comm= -C systemd-coredump; then
        echo "The systemd-coredump process is not finished."
        exit 1
    fi
fi
if [ ! -z "`ls /var/coredumps`" ]; then
    echo "The /var/coredumps directory is not empty."
    for dump in /var/coredumps/*; do
        echo "Dump found: $dump"
        gdb --batch --eval-command=bt $dump
    done
    exit 1
fi
if [ -d /var/crash ] && [ ! -z "`ls /var/crash`" ]; then
    echo "The /var/crash directory is not empty."
    for dump in /var/crash/*; do
        echo "Dump found: $dump"
        gdb --batch --eval-command=bt $dump
    done
    exit 1
fi
if [ ! -z "`which coredumpctl 2>/dev/null`" ]; then
    if coredumpctl; then
        echo "Coredump found. Check coredumpctl."
        printf "set pagination off\nbt" | coredumpctl gdb
        exit 1
    fi
fi
if dmesg | grep ' segfault at '; then
    echo "A segfault recorded in dmesg."
    exit 1
fi
"""
            subprocess.check_call(test_script, shell=True)
        else:
            pass
    request.addfinalizer(finalize)
