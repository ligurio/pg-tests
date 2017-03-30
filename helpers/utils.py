import os
import paramiko
import platform
import random
import shlex
import socket
import subprocess
import sys

from time import sleep

SSH_LOGIN = 'test'
SSH_ROOT = 'root'
SSH_PASSWORD = 'TestPass1'
SSH_ROOT_PASSWORD = 'TestRoot1'
SSH_PORT = 22


def command_executor(cmd, remote=False, host=None, login=None, password=None, stdout=False):
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
                return subprocess.check_output(shlex.split(cmd))


def copy_file(local_path, remote_path, hostname):

    transport = paramiko.Transport((hostname, SSH_PORT))
    transport.connect(username=SSH_LOGIN, password=SSH_PASSWORD)
    sftp = paramiko.SFTPClient.from_transport(transport)
    print "Copying file '%s', remote host is '%s'" % (remote_path, hostname)
    sftp.get(remote_path, local_path)
    sftp.close()
    transport.close()

    # TODO: return exit code


def exec_command(cmd, hostname, login, password):

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

    return retcode, stdout, stderr


def gen_name(name):
    return name + '-' + str(random.getrandbits(15))


def write_file(file, text, remote=False, host=None):
    if remote:
        transport = paramiko.Transport((host, 22))
        transport.connect(username=SSH_ROOT, password=SSH_ROOT_PASSWORD)
        sftp = paramiko.SFTPClient.from_transport(transport)
        f = sftp.open(file, "w+")
        f.write(text)
        f.close
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
        return platform.linux_distribution()[0], platform.linux_distribution()[1]


def get_os_type(ip):
    cmd = 'cat /etc/*-release'
    retcode, stdout, stderr = exec_command(cmd, ip, SSH_ROOT, SSH_ROOT_PASSWORD)
    if retcode == 0:
        return dict(
            v.split("=") for v in stdout.replace(
                '\t', ' ').strip().split('\n') if v.strip() and "=" in v)
    else:
        return None
