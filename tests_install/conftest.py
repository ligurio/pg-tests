import distro
import platform
import pytest
import os
import sys
import subprocess
from helpers.os_helpers import OsHelper
from helpers.utils import get_distro

dist = []
if platform.system() == 'Linux':
    dist = get_distro()
elif platform.system() == 'Windows':
    dist = 'Windows'
else:
    print("Unknown Distro")

# sysctl.conf ubuntu bug
if dist[0] == 'Ubuntu' and dist[1] == '20.04':
    subprocess.check_call('sysctl fs.protected_regular=0', shell=True)

# py2compat
if not sys.version_info > (3, 0):
    # pylint: disable = undefined-variable
    reload(sys)
    # pylint: disable = no-member
    sys.setdefaultencoding('utf8')


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
        help="Specify product version. Available values: 9.6, 10, 11, ...")
    parser.addoption(
        "--product_name", action="store", default='postgrespro',
        help="Specify product name. Available values: postgrespro, postresql")
    parser.addoption(
        "--product_edition", action="store", default='ent',
        help="Specify product edition. Available values: ent, std")
    parser.addoption(
        "--product_milestone", action="store",
        help="Specify product milestone. Available values: alpha, beta")
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
            script = r"""#!/bin/bash
if ps -o comm= -C systemd-coredump; then
    echo "The systemd-coredump process is running."
    for i in {1..30}; do
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
if [ ! -z "`which coredumpctl 2>/dev/null`" ]; then
    if coredumpctl; then
        echo "Coredump found. Check coredumpctl."
        printf "set pagination off\nbt" | coredumpctl gdb
        exit 1
    fi
fi
result=0
if [ ! -z "`ls /var/coredumps`" ]; then
    for dump in /var/coredumps/*; do
        case $dump in
            *":!usr!bin!qemu-ga")
                # The qemu-ga coredump encountered on SLES 15 SP2
                continue
                ;;
            *":!bin!cp")
                The cp coredump on SIGQUIT encountered on AltLinux 8
                continue
                ;;
        esac
        result=1
        echo "Coredump found: $dump"
        exepath="${dump##*-EXE:}"
        if [ X"$dump" = X"$exepath" ]; then
            gdb --batch --eval-command=bt $dump;
        else
            exepath="${exepath//\!//}"
            echo "exepath: $exepath"
            gdb --batch --eval-command=bt $exepath --core="$dump";
        fi
    done
fi
if [ -d /var/crash ] && [ ! -z "`ls /var/crash`" ]; then
    for dump in /var/crash/*; do
        case $dump in
            *"/_usr_bin_do-release-upgrade."*".crash")
                # The do-release-upgrade coredump encountered on Ubuntu 18.04
                continue
                ;;
        esac
        result=1
        echo "Coredump found: $dump"
    done
fi
if dmesg | grep ' segfault at '; then
    echo "A segfault recorded in dmesg."
    result=1
fi
exit $result
"""
            script_file = '/tmp/check-coredumps.sh'
            with open(script_file, 'w') as scrf:
                scrf.write(script)
            os.chmod(script_file, 0o0755)
            subprocess.check_call(script_file, shell=True)
        else:
            pass
    request.addfinalizer(finalize)
    target_ssh = "@ssh" in request.config.getoption('--target')
    if target_ssh:
        print('Starting up prepare')
        oh = OsHelper()
        packages = sorted(oh.get_all_installed_packages())
        orig_pack_list = '/etc/pgt-initial-packages.list'
        if os.path.isfile(orig_pack_list):
            with open(orig_pack_list, 'r') as pack_list:
                orig_packages = [line.rstrip() for line in pack_list]
            to_remove = list(set(packages) - set(orig_packages))
            if len(to_remove) > 0:
                oh.remove_package(' '.join(to_remove), True)
        else:
            if len(packages) <= 0:
                raise Exception('Zero packages was returned')
            with open(orig_pack_list, 'w') as pack_list:
                pack_list.write('\n'.join(packages))


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    if exitstatus == 0 and hasattr(session, 'customexitstatus'):
        session.exitstatus = session.customexitstatus
