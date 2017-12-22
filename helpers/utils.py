import ConfigParser
import os
import platform
import random
import shlex
import shutil
import socket
import subprocess
import sys

from enum import Enum
from time import sleep

REMOTE_LOGIN = 'test'
REMOTE_ROOT = 'root'
REMOTE_PASSWORD = 'TestPass1'
REMOTE_ROOT_PASSWORD = 'TestRoot1'
SSH_PORT = 22
CONNECT_RETRY_DELAY = 10


class MySuites(Enum):
    def __str__(self):
        return self.value

    PARENT_SUITE = 'parentSuite'
    EPIC = 'epic'


def command_executor(cmd, remote=False, host=None, login=None, password=None, stdout=False, windows=False):
    """ Command executor for local commands and remote commands. For local command using subprocess
    for remote command paramiko or winrm (for windows)

    :param cmd: st: commands with options, separator for each option whitespace
    :param remote:  bool, local or remote command
    :param login: str: only for remote command ssh/winrm login
    :param password: str: only for remote command ssh/winrm  password
    :return: result
    """
    if remote:
        return exec_command(cmd, host, login, password)
    elif remote and windows:
        return exec_command_win(cmd, host, login, password)
    else:
        if '|' in cmd:
            first_command = cmd[:cmd.index("|")]
            second_command = cmd[cmd.index("|") + 1:]
            first_command_execute = subprocess.Popen(
                shlex.split(first_command, posix=not(windows)), stdout=subprocess.PIPE)
            return subprocess.check_output(shlex.split(second_command, posix=not(windows)),
                                           stdin=first_command_execute.stdout)
        else:
            if stdout:
                out = subprocess.Popen((shlex.split(cmd, posix=not(windows))), stdout=subprocess.PIPE)
                return out.stdout.readline().rstrip()
            else:
                if windows:
                    return subprocess.check_call(shlex.split(cmd, posix=False), shell=True)
                else:
                    print(cmd)
                    return subprocess.check_call(shlex.split(cmd))


def get_virt_ip():
    """ Get host ip for virtual machine bridge interface

    :return: string ip address
    """
    return subprocess.check_output('ip addr show virbr0', shell=True).split("inet ")[1].split("/")[0]


def copy_file(remote_path, local_path, hostname, dir=False, operating_system=None,
              product_name=None, product_version=None, product_edition=None, tests=None):
    import paramiko

    transport = paramiko.Transport((hostname, SSH_PORT))
    transport.connect(username=REMOTE_LOGIN, password=REMOTE_PASSWORD)
    sftp = paramiko.SFTPClient.from_transport(transport)
    if dir:
        print(sftp.listdir(remote_path))
        for file in sftp.listdir(remote_path):
            print "Copying file '%s', remote host is '%s'" % (file, hostname)
            sftp.get(os.path.join(remote_path, file), os.path.join(local_path, file))
            # if '.xml' in file and 'environment' not in file:
            #     new_file_name = "{}_{}_{}_{}_{}-testsuite.xml".format(operating_system, product_name,
            #                                                           product_version, product_edition, tests)
            #     print "Copying file '%s', remote host is '%s'" % (file, hostname)
            #     sftp.get(os.path.join(remote_path, file), os.path.join(local_path, new_file_name))
            # elif '.txt' in file:
            #     print "Copying file '%s', remote host is '%s'" % (file, hostname)
            #     sftp.get(os.path.join(remote_path, file), os.path.join(local_path, file))
            # elif '.xml' in file and 'environment' in file:
            #     print "Copying file '%s', remote host is '%s'" % (file, hostname)
            #     sftp.get(os.path.join(remote_path, file), os.path.join(local_path, file))
            # else:
            #     continue
    else:
        print "Copying file '%s', remote host is '%s'" % (remote_path, hostname)
        sftp.get(remote_path, local_path)
    sftp.close()
    transport.close()
    return 0


def copy_reports_win(reportname, reportsdir, destreports, domipaddress):
    """ Copy reports

    :param reportname:
    :param reportsdir:
    :param destreports:
    :param domipaddress:
    :return:
    """

    subprocess.call('net usershare list | grep pg-tests-reports && '
                    'net usershare delete pg-tests-reports', shell=True)
    subprocess.check_call('net usershare add pg-tests-reports %s '
                          '"pg-tests reports" everyone:F guest_ok=y' %
                          os.path.abspath(destreports), shell=True)

    share = r'\\%s\pg-tests-reports' % get_virt_ip()
    cmd = r'xcopy /Y /F .\pg-tests\{0}.* {1}\\'.format(reportname, share)
    exec_command_win(cmd, domipaddress, REMOTE_LOGIN, REMOTE_PASSWORD)
    cmd = r'xcopy /Y /F .\pg-tests\reports {0}\\{1}\\'.format(
        share, reportsdir.replace('/', '\\'))
    exec_command_win(cmd, domipaddress, REMOTE_LOGIN, REMOTE_PASSWORD)
    subprocess.check_call('net usershare delete pg-tests-reports', shell=True)


def exec_command(cmd, hostname, login, password, skip_ret_code_check=False, connect_retry_count=3):

    import paramiko

    buff_size = 1024
    stdout = ""
    stderr = ""
    for trc in range(connect_retry_count):
        try:
            client = paramiko.SSHClient()
            client.load_system_host_keys()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(hostname=hostname, username=login, password=password, port=SSH_PORT, look_for_keys=False,
                           timeout=CONNECT_RETRY_DELAY)
            chan = client.get_transport().open_session()
            break
        except (paramiko.AuthenticationException,
                paramiko.BadHostKeyException,
                paramiko.SSHException,
                socket.error,
                Exception) as e:
            if trc >= connect_retry_count - 1:
                raise e
            sleep(CONNECT_RETRY_DELAY)

    if cmd is None:
        chan.close()
        client.close()
        return

    print "Executing '%s' on %s..." % (cmd, hostname)
    chan.exec_command(cmd)
    retcode = chan.recv_exit_status()
    while chan.recv_ready():
        stdout += chan.recv(buff_size)

    while chan.recv_stderr_ready():
        stderr += chan.recv_stderr(buff_size)

    client.close()
    if skip_ret_code_check:
        return retcode, stdout, stderr
    else:
        if retcode != 0:
            print("Return code for command  \'%s\' is %d.\n" % (cmd, retcode))
            print("The command stdout:\n%s" % stdout)
            print("The command stderr:\n%s" % stder)
            raise Exception('Command "%s" failed.'  % cmd)
        else:
            return retcode, stdout, stderr


def exec_command_win(cmd, hostname, user, password, skip_ret_code_check=False, connect_retry_count=3):
    """ Execute command on windows remote host

    :param cmd:
    :param hostname:
    :param user:
    :param password:
    :return:
    """

    import winrm

    for trc in range(connect_retry_count):
        try:
            p = winrm.Protocol(endpoint='http://' + hostname + ':5985/wsman', transport='plaintext',
                            username=user,
                            password=password)
            shell_id = p.open_shell()
            break
        except (winrm.exceptions.WinRMOperationTimeoutError,
                winrm.exceptions.WinRMTransportError,
                socket.error,
                ) as e:
            if trc == connect_retry_count:
                raise e
            sleep(CONNECT_RETRY_DELAY)

    if cmd is None:
        p.close_shell(shell_id)
        return

    print "Executing '%s' on %s..." % (cmd, hostname)
    command_id = p.run_command(shell_id, cmd)
    stdout, stderr, retcode = p.get_command_output(shell_id, command_id)
    p.cleanup_command(shell_id, command_id)
    p.close_shell(shell_id)

    if skip_ret_code_check:
        return retcode, stdout, stderr
    else:
        if retcode != 0:
            print("Return code for command  \'%s\' is %d.\n" % (cmd, retcode))
            print("The command stdout:\n%s" % stdout)
            print("The command stderr:\n%s" % stder)
            raise Exception('Command "%s" failed.'  % cmd)
        else:
            return retcode, stdout, stderr

def wait_for_boot(host, time=300, linux=True):
    print("Waiting for control protocol availability.")
    if linux:
        exec_command(None, host, REMOTE_LOGIN, REMOTE_PASSWORD,
                     connect_retry_count=time/CONNECT_RETRY_DELAY)
    else:
        exec_command_win(None, host, REMOTE_LOGIN, REMOTE_PASSWORD,
                         connect_retry_count=time/CONNECT_RETRY_DELAY)


def gen_name(name):
    return name + '-' + str(random.getrandbits(15))


def write_file(file, text, remote=False, host=None):
    if remote:
        import paramiko

        transport = paramiko.Transport((host, 22))
        transport.connect(username=REMOTE_ROOT, password=REMOTE_ROOT_PASSWORD)
        sftp = paramiko.SFTPClient.from_transport(transport)
        f = sftp.open(file, "w+")
        f.write(text)
        f.close
        transport.close()
    else:
        with open(file, "w+") as f:
            f.write(text)


def get_distro(remote=False, ip=None):
    """ Get os distribution, version, and architecture

    :param remote:
    :param ip:
    :return: tuple: os distribution, version, and architecture
    """
    if remote:
        host_info = {}
        while len(host_info) == 0:
            host_info = get_os_type(ip)
        return host_info['NAME'].strip('"'), host_info['VERSION_ID'].strip('"'), None
    else:
        os = platform.platform()
        if "Linux" in os:
            return platform.linux_distribution()[0].strip('"'), platform.linux_distribution()[1], platform.machine()
        elif "Windows" in os:
            return platform.win32_ver()[0], platform.win32_ver()[1], platform.machine()
        else:
            raise Exception("Unknown OS platform (%s)." % os)


def get_os_type(ip):
    """ Get os type on remote linux machine

    :param ip:
    :return:
    """
    cmd = 'cat /etc/*-release'
    retcode, stdout, stderr = exec_command(cmd, ip, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
    if retcode == 0:
        return dict(
            v.split("=") for v in stdout.replace(
                '\t', ' ').strip().split('\n') if v.strip() and "=" in v)
    else:
        return None


def parse_config_runner(config):
    """Parse config file

    :param config: string path to config
    :return:
    """
    pass


def create_env_info_from_config(env_name, config):
    """Create environment information from config file

    :param env_name: string with env name
    :param config: string path to config file
    :return: dict with config
    """
    env_info = {env_name: {}}
    env_info[env_name]['nodes'] = []
    config_file = ConfigParser.ConfigParser()
    config_file.read(config)
    for node in config_file.sections():
        for value in config_file.items(node):
            if value[0] == 'ip_address':
                env_info[env_name]['nodes'].append({"domname": node, "ip": value[1]})
    return env_info


def refresh_env_win():
    if sys.hexversion > 0x03000000:
        import winreg
    else:
        import _winreg as winreg

    regkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
            r"System\CurrentControlSet\Control\Session Manager\Environment",
            0, winreg.KEY_READ)
    i = 0
    while True:
        try:
            envvar, envval, valtype = winreg.EnumValue(regkey, i)
        # pylint: disable=undefined-variable
        except WindowsError as e:
            break
        i += 1
        if envvar.upper() == 'PATH' or envvar.upper().startswith('PG'):
            os.environ[envvar] = envval


# def check_systemd(remote=False, host=None):
#     """Check systemd or not in system
#
#     :return:
#     """
#     cmd = "ps -p 1"
#     result = command_executor(cmd, remote=remote, host=host, stdout=True)
#     if remote:
#         if "systemd" in result[1]:
#             return True
#     else:
#         if "systemd" in result:
#             return True
