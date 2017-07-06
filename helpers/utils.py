import os
import paramiko
import platform
import random
import shlex
import shutil
import stat
import socket
import subprocess
import sys
import winrm

from time import sleep

REMOTE_LOGIN = 'test'
REMOTE_ROOT = 'root'
REMOTE_PASSWORD = 'TestPass1'
REMOTE_ROOT_PASSWORD = 'TestRoot1'
SSH_PORT = 22


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
                shlex.split(first_command), stdout=subprocess.PIPE)
            return subprocess.check_output(shlex.split(second_command), stdin=first_command_execute.stdout)
        else:
            if stdout:
                out = subprocess.Popen((shlex.split(cmd)), stdout=subprocess.PIPE)
                return out.stdout.readline().rstrip()
            else:
                if windows:
                    return subprocess.check_output(shlex.split(cmd), shell=True)
                else:
                    print(cmd)
                    return subprocess.check_call(shlex.split(cmd))


def get_virt_ip():
    """ Get host ip for virtual machine bridge interface

    :return: string ip address
    """
    out, err = subprocess.Popen('ifconfig virbr0|grep "inet addr"',
                                shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
    return out[20:33]


def copy_file(remote_path, local_path, hostname, dir=False, operating_system=None,
              product_name=None, product_version=None, product_edition=None, tests=None):
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


def copy_file_win(reportname, domipaddress):
    """ Copy reports

    :param reportname:
    :param domipaddress:
    :return:
    """

    cmd = r'net use f: "\\%s\reports" &&xcopy .\pg-tests\*.html f:\ /Y' % get_virt_ip()
    exec_command_win(cmd, domipaddress, REMOTE_LOGIN, REMOTE_PASSWORD)
    cmd = r'net use f: "\\%s\reports" &&xcopy .\pg-tests\*.xml f:\ /Y' % get_virt_ip()
    exec_command_win(cmd, domipaddress, REMOTE_LOGIN, REMOTE_PASSWORD)
    shutil.copy(r'/reports/%s.html' % reportname, r'reports')
    shutil.copy(r'/reports/%s.xml' % reportname, r'reports')


def exec_command(cmd, hostname, login, password, skip_ret_code_check= False):

    buff_size = 1024
    stdout = ""
    stderr = ""
    connect_retry_count = 3
    for _ in range(connect_retry_count):
        try:
            client = paramiko.SSHClient()
            client.load_system_host_keys()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(hostname=hostname, username=login, password=password, port=SSH_PORT, look_for_keys=False,
                           timeout=10)
        except (paramiko.AuthenticationException,
                paramiko.BadHostKeyException,
                paramiko.SSHException,
                socket.error,
                Exception) as e:
            print(e)
            sleep(10)

    chan = client.get_transport().open_session()
    print "Executing '%s' on '%s'" % (cmd, hostname)
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
            print("Return code for command  \'%s\' is not zero\n" % cmd)
            print("Stdout for command \'%s\'\n" % cmd)
            print(stdout)
            print("Stderror for command \'%s\'\n" % cmd)
            print(stderr)
            sys.exit(1)
        else:
            return retcode, stdout, stderr


def exec_command_win(cmd, hostname, user, password, skip_ret_code_check= False):
    """ Execute command on windows remote host

    :param cmd:
    :param hostname:
    :param user:
    :param password:
    :return:
    """

    p = winrm.Protocol(endpoint='http://' + hostname + ':5985/wsman', transport='plaintext',
                       username=user,
                       password=password)
    shell_id = p.open_shell()
    command_id = p.run_command(shell_id, cmd)
    stdout, stderr, retcode = p.get_command_output(shell_id, command_id)
    p.cleanup_command(shell_id, command_id)
    p.close_shell(shell_id)

    if skip_ret_code_check:
        return retcode, stdout, stderr
    else:
        if retcode != 0:
            print("Return code for command  \'%s\' is not zero\n" % cmd)
            print("Stdout for command \'%s\'\n" % cmd)
            print(stdout)
            print("Stderror for command \'%s\'\n" % cmd)
            print(stderr)
            sys.exit(1)
        else:
            return retcode, stdout, stderr


def gen_name(name):
    return name + '-' + str(random.getrandbits(15))


def write_file(file, text, remote=False, host=None):
    if remote:
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
    """ Get linux distribution and os version

    :param remote:
    :param ip:
    :return: tuple: linux distribution and os version
    """
    if remote:
        host_info = {}
        while len(host_info) == 0:
            host_info = get_os_type(ip)
        return host_info['NAME'].strip('"'), host_info['VERSION_ID'].strip('"')
    else:
        if "Linux" in platform.platform():
            return platform.linux_distribution()[0].strip('"'), platform.linux_distribution()[1]
        elif "Windows" in platform.platform():
            return platform.win32_ver()[0], platform.win32_ver()[1]
        else:
            print("Unknown distro")
            sys.exit(1)


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
