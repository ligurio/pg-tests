import os
import platform
import distro
import shlex
import socket
import subprocess
import sys
import re
import difflib
import math
import gc
import locale
import random
import time
import functools

from enum import Enum
from time import sleep

try:
    import configparser
except ImportError:  # py2compat
    import ConfigParser as configparser
try:
    import urllib.request as urlrequest
except ImportError:  # py2compat
    import urllib as urlrequest

REMOTE_LOGIN = 'test'
REMOTE_ROOT = 'root'
REMOTE_PASSWORD = 'TestPass1'
REMOTE_ROOT_PASSWORD = 'TestRoot1'
SSH_PORT = 22
CONNECT_RETRY_DELAY = 10
ConsoleEncoding = locale.getdefaultlocale()[1]
if not ConsoleEncoding:
    ConsoleEncoding = 'UTF-8'


class MySuites(Enum):
    def __str__(self):
        return self.value

    PARENT_SUITE = 'parentSuite'
    EPIC = 'epic'


def retry(exc_type=Exception, action='processing', arg=None):
    def decorator(func):
        @functools.wraps(func)
        def result(*args, **kwargs):
            timeout = 0
            count = 5
            act = action
            if 'retry_cnt' in kwargs:
                count = kwargs['retry_cnt']
                kwargs.pop('retry_cnt')
            if '%s' in action and arg is not None:
                act = action % args[arg - 1]
            for attempt in range(count - 1):
                try:
                    return func(*args, **kwargs)
                except exc_type as ex:
                    print('Exception occured while %s' % act)
                    print(ex)
                    print('========')
                    timeout += 5
                    print(
                        'Retrying (attempt %d with delay for %d seconds)...' %
                        (attempt + 2, timeout))
                    time.sleep(timeout)
            if count > 1:
                print('Last attempt to perform %s\n' % act)
            return func(*args, **kwargs)
        return result
    return decorator


def urlopen(url):
    return urlrequest.urlopen(url)


def updated_image_detected(url, file_name):
    try:
        req = urlopen(url)
    except Exception as e:
        return False
    return int(req.info()['Content-Length']) != \
        int(os.stat(file_name).st_size)


@retry(action='getting content from %s', arg=1)
def urlcontent(url, retry_cnt=5):
    return urlopen(url).read().decode()


def urlretrieve(url, target, retry_cnt=5):
    timeout = 0
    attempt = 1
    while attempt < retry_cnt:
        try:
            if retry_cnt == attempt + 1:
                print('Last attempt to retrieve url...\n')
            elif attempt > 1:
                print('Retrying (attempt %d with delay for %d seconds)...' %
                      (attempt, timeout))
            if os.path.exists(target):
                os.remove(target)
            req = urlopen(url)
            if req.getcode() >= 400:
                raise Exception("HTTP Error %s" % req.getcode())
            return urlrequest.urlretrieve(url, target)
        except Exception as ex:
            print('Exception occured while retrieving url "%s":' % url)
            print(ex)
            print('========')
            attempt += 1
            timeout += 1
            if attempt + 1 > retry_cnt:
                raise ex
            time.sleep(timeout)


def command_executor(cmd, remote=False, host=None,
                     login=None, password=None,
                     stdout=False, windows=False):
    """ Command executor for local commands and remote commands.
        For local command using subprocess
        for remote command paramiko or winrm (for windows)

    :param cmd: commands with options, separator for each option whitespace
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
                shlex.split(first_command, posix=not(windows)),
                stdout=subprocess.PIPE)
            return subprocess.check_output(
                shlex.split(second_command, posix=not(windows)),
                stdin=first_command_execute.stdout)
        else:
            if stdout:
                out = subprocess.Popen(
                    shlex.split(cmd, posix=not(windows)),
                    stdout=subprocess.PIPE)
                return out.stdout.read().decode(ConsoleEncoding)
            else:
                if windows:
                    return subprocess.check_call(
                        shlex.split(cmd, posix=False), shell=True)
                else:
                    print(cmd)
                    return subprocess.check_call(shlex.split(cmd))


def exec_retry(cmd, cwd='.', description='', retry_cnt=10):
    attempt = 1
    timeout = 0
    if not description:
        description = cmd
    print(description + '...')
    while attempt < retry_cnt:
        try:
            return subprocess.check_output(cmd, cwd=cwd, shell=True)
        except Exception as ex:
            print('Exception occured while running "%s":' % cmd)
            print(ex)
            print('========')
            attempt += 1
            timeout += random.randint(1, 8)
            print('Retrying (attempt %d with delay for %d seconds)...' %
                  (attempt, timeout))
            time.sleep(timeout)
    if retry_cnt > 1:
        print('Last attempt to execute the command...\n')
    return subprocess.check_output(cmd, cwd=cwd, shell=True)


def get_virt_ip():
    """ Get host ip for virtual machine bridge interface

    :return: string ip address
    """
    return subprocess.check_output(
        'ip addr show virbr0', shell=True).decode(ConsoleEncoding).\
        split("inet ")[1].split("/")[0]


def copy_file(remote_path, local_path, hostname, dir=False,
              operating_system=None,
              product_name=None, product_version=None, product_edition=None,
              tests=None):
    import paramiko
    connect_retry_count = 3

    for trc in range(connect_retry_count):
        try:
            transport = paramiko.Transport((hostname, SSH_PORT))
            transport.connect(username=REMOTE_LOGIN, password=REMOTE_PASSWORD)
            sftp = paramiko.SFTPClient.from_transport(transport)
            break
        except (paramiko.AuthenticationException,
                paramiko.BadHostKeyException,
                paramiko.SSHException,
                socket.error,
                Exception) as e:
            if trc >= connect_retry_count - 1:
                raise e
            sleep(CONNECT_RETRY_DELAY)

    if dir:
        print(sftp.listdir(remote_path))
        for file in sftp.listdir(remote_path):
            print("Copying file '%s', remote host is '%s'" % (
                file, hostname))
            sftp.get(os.path.join(remote_path, file),
                     os.path.join(local_path, file))
    else:
        print("Copying file '%s', remote host is '%s'" % (
            remote_path, hostname))
        sftp.get(remote_path, local_path)
    sftp.close()
    transport.close()


def copy_reports_win(reportname, reportsdir, destreports, domipaddress):
    """ Copy reports

    :param reportname:
    :param reportsdir:
    :param destreports:
    :param domipaddress:
    :return:
    """

    sharename = 'pg-tests-reports-%s' % domipaddress
    subprocess.call(
        'net usershare list | grep %s && net usershare delete %s' %
        (sharename, sharename), shell=True)
    subprocess.check_call(
        'net usershare add %s %s "pg-tests reports" everyone:F guest_ok=y' %
        (sharename, os.path.abspath(destreports)), shell=True)

    share = r'\\%s\%s' % (get_virt_ip(), sharename)
    cmd = r'net use {0} /user:localhost\test test & ' \
          r'xcopy /Y /F .\pg-tests\{1}.* {0}\ & ' \
          r'xcopy /Y /F .\pg-tests\reports {0}\{2}\ '. \
          format(share, reportname, reportsdir.replace('/', '\\'))
    exec_command_win(cmd, domipaddress, REMOTE_LOGIN, REMOTE_PASSWORD)
    subprocess.check_call(
        'net usershare delete %s' % sharename, shell=True)


def exec_command(cmd, hostname, login, password,
                 skip_ret_code_check=False, connect_retry_count=3):

    import paramiko

    for trc in range(connect_retry_count):
        try:
            client = paramiko.SSHClient()
            client.load_system_host_keys()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(hostname=hostname,
                           username=login, password=password,
                           port=SSH_PORT, look_for_keys=True,
                           timeout=CONNECT_RETRY_DELAY)
            chan = client.get_transport().open_session()
            break
        except (paramiko.AuthenticationException,
                paramiko.BadHostKeyException,
                paramiko.SSHException,
                socket.error,
                Exception) as e:
            print("Try %s of %s" % (trc + 1, connect_retry_count))
            if trc >= connect_retry_count - 1:
                raise e
            sleep(CONNECT_RETRY_DELAY)

    if cmd is None:
        chan.close()
        client.close()
        return

    print("Executing '%s' on %s..." % (cmd, hostname))
    chan.get_pty()
    chan.exec_command(cmd)
    stdout_stream = chan.makefile("r", -1)
    stderr_stream = chan.makefile_stderr("r", -1)
    stdout = stdout_stream.read()
    stderr = stderr_stream.read()
    retcode = chan.recv_exit_status()

    chan.close()
    client.close()
    stdout = stdout.decode(ConsoleEncoding)
    stderr = stderr.decode(ConsoleEncoding)
    if skip_ret_code_check:
        return retcode, stdout, stderr
    else:
        if retcode != 0:
            print("Return code for command  \'%s\' is %d.\n" % (cmd, retcode))
            print("The command stdout:\n%s" % stdout)
            print("The command stderr:\n%s" % stderr)
            raise Exception('Command "%s" failed.' % cmd)
        else:
            return retcode, stdout, stderr


def exec_command_win(cmd, hostname,
                     user, password,
                     skip_ret_code_check=False, connect_retry_count=3):
    """ Execute command on windows remote host

    :param cmd:
    :param hostname:
    :param user:
    :param password:
    :return:
    """

    import winrm
    import requests

    for trc in range(connect_retry_count):
        try:
            p = winrm.Protocol(
                endpoint='http://' + hostname + ':5985/wsman',
                transport='plaintext',
                read_timeout_sec=360,
                operation_timeout_sec=300,
                username=user,
                password=password)
            shell_id = p.open_shell()
            break
        except (winrm.exceptions.WinRMOperationTimeoutError,
                winrm.exceptions.WinRMTransportError,
                winrm.exceptions.WinRMError,
                requests.exceptions.ConnectionError,
                socket.error) as e:
            if trc == connect_retry_count:
                raise e
            sleep(CONNECT_RETRY_DELAY)

    if cmd is None:
        p.close_shell(shell_id)
        return

    print("Executing '%s' on %s..." % (cmd, hostname))
    command_id = p.run_command(shell_id, cmd)
    stdout, stderr, retcode = p.get_command_output(shell_id, command_id)
    stdout = stdout.decode(ConsoleEncoding)
    stderr = stderr.decode(ConsoleEncoding)

    if not (skip_ret_code_check) and retcode != 0:
        print("Return code for command  \'%s\' is %d.\n" % (cmd, retcode))
        print("The command stdout:\n%s" % stdout)
        print("The command stderr:\n%s" % stderr)
        raise Exception('Command "%s" failed.' % cmd)

    # These operations fail when the current user excluded from
    # the Administrators group, so just ignore the error.
    try:
        p.cleanup_command(shell_id, command_id)
    except winrm.exceptions.WinRMError:
        pass
    try:
        p.close_shell(shell_id)
    except winrm.exceptions.WinRMError:
        print("Trying to reconnect to WinRM after a failure on "
              "winrm.close_shell()")
        exec_command_win(None, hostname, user, password, connect_retry_count=5)
    return retcode, stdout, stderr


def gen_name(name, prefix="pgt"):
    return prefix + '--' + name + '-' + str(random.getrandbits(15))


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
        return host_info['NAME'].strip('"'), \
            host_info['VERSION_ID'].strip('"'), None
    else:
        os = platform.platform()
        if "Linux" in os:
            # Workaround for lsb_release returning "n/a" in MSVSphere 6.3
            if distro.name(True) == "MSVSphere 6.3":
                return "\xd0\x9c\xd0\xa1\xd0\x92\xd0\xa1\xd1\x84\xd0\xb5" \
                    "\xd1\x80\xd0\xb0 \xd0\xa1\xd0\xb5\xd1\x80\xd0\xb2" \
                    "\xd0\xb5\xd1\x80", \
                    "6.3", \
                    platform.machine()
            return distro.linux_distribution()[0].strip('"'), \
                distro.linux_distribution()[1], \
                platform.machine()
        elif "Windows" in os:
            return 'Windows-' + platform.win32_ver()[0], \
                '.'.join(platform.win32_ver()[1].split('.')[:-1]), \
                platform.machine()
        else:
            raise Exception("Unknown OS platform (%s)." % os)


def get_os_type(ip):
    """ Get os type on remote linux machine

    :param ip:
    :return:
    """
    cmd = 'cat /etc/*-release'
    retcode, stdout, stderr = exec_command(cmd, ip,
                                           REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
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
    config_file = configparser.ConfigParser()
    config_file.read(config)
    for node in config_file.sections():
        for value in config_file.items(node):
            if value[0] == 'ip_address':
                env_info[env_name]['nodes'].append(
                    {"domname": node, "ip": value[1]})
    return env_info


def refresh_env_win():
    if sys.hexversion > 0x03000000:
        import winreg  # pylint: disable=import-error
    else:
        import _winreg as winreg  # pylint: disable=import-error

    regkey = winreg.OpenKey(
        winreg.HKEY_LOCAL_MACHINE,
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
        if envvar.upper() == 'PATH':
            os.environ[envvar] = os.path.expandvars(envval)
        elif (envvar.upper().startswith('PG') or
              envvar.upper().startswith('PYTHON')):
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


def read_dump(file):

    numre = re.compile(r"\b[-+]?[0-9]*\.?[0-9]+([e][-+]?[0-9]+)?")
    exre = re.compile(r"EXECUTE\s+\w+")
    alterrolere = re.compile(r"(ALTER ROLE.*)PASSWORD\s'[^']+'")
    createdatabaselocalere = re.compile(
        r"(CREATE DATABASE.*)LOCALE\s*=\s*'([^']+)'(.*)")
    createdatabasere = re.compile(
        r"(CREATE DATABASE.*)LC_COLLATE\s*=\s*'([^@]+)@[^']+'(.*)")
    ddl_procre = re.compile(r"\s?(CREATE|ALTER|GRANT\s+(ALL)?\s?ON|"
                            r"REVOKE\s+(ALL)?\s?ON)\s+(PROCEDURE|FUNCTION)")

    def normalize_numbers(line):
        def norma(match):
            number = match.group()
            if not ('.' in number or 'e' in number):
                return number
            try:
                f = float(number)
            except ValueError:
                return number
            (m, e) = math.frexp(f)
            m = round(m, 3)
            nf = math.ldexp(m, e)
            if abs(nf) < 0.000001:
                return '0'
            return str(nf)

        newstr = numre.sub(norma, line)
        return newstr

    def preprocess(str):
        if str.strip() == 'SET default_table_access_method = heap;':
            return ''
        ustr = str.upper()
        result = str
        if '--' in result:
            result = re.sub(r"\s?--.*", "", result)
        if 'ALTER ROLE' in ustr:
            result = alterrolere.sub(r"\1PASSWORD ''", result)
        elif ddl_procre.match(ustr):
            result = re.sub(r"IN\s+", "", result)
        elif 'CREATE DATABASE' in ustr:
            result = createdatabaselocalere.sub(
                r"\1LC_COLLATE = '\2' LC_CTYPE = '\2'\3", result)
            result = createdatabasere.sub(r"\1LC_COLLATE = '\2'\3", result)
        elif 'EXECUTE' in ustr:
            result = exre.sub(r"EXECUTE ***", result)
        result = normalize_numbers(result)
        return result

    lines = []
    lines_to_sort = []
    copy_line = ''
    sort_patterns = [
        re.compile(r"\s?CREATE\s+(UNIQUE\s+)?INDEX\s.*"),
        re.compile(r"\s?CREATE\s+OPERATOR\s.*"),
        re.compile(r"\s?ALTER\s+OPERATOR\s.*"),
        re.compile(r"\s?ALTER\s+TABLE\s+(ONLY\s+)?.*(ADD\sCONSTRAINT\s)?.*")
    ]
    copy_pattern = re.compile(r"\s?COPY\s+.*FROM\sstdin.*")
    rt_pattern = re.compile(r"\s?CREATE\s+TYPE.*AS\s+RANGE\s.*")
    remove_mr_tn_pattern = re.compile(
        r"([^(^,]?)(,?\s+multirange_type_name\s?=\s?[^\s^)^,]+)(,?\)?.*)"
    )
    alter_op_family_pattern = re.compile(
        r"\s?ALTER\s+OPERATOR\s+FAMILY\s+([^\s]+)\s+USING\s+[^\s]+\s+ADD.*"
    )
    sort_item = []
    sort_body = []
    sort_items = []
    rt_items = []
    aof = None
    op_families = {}
    operator = False
    with open(file, 'rb') as f:
        for line in f:
            line = preprocess(line.decode()).strip()
            if line:
                # In 14th+ common objects for OPERATOR CLASSES were
                # moved to FAMILY
                # For example:
                # ALTER OPERATOR FAMILY public.custom_opclass USING hash ADD
                # FUNCTION 2(integer, integer) \
                # public.dummy_hashint4(integer, bigint)
                # and FUNCTION 2.. is absent in CREATE OPERATOR CLASS:
                # CREATE OPERATOR CLASS public.custom_opclass
                # FOR TYPE integer USING hash FAMILY public.custom_opclass A
                # OPERATOR 1 =(integer,integer)
                # but in 13th- public.custom_opclass defined as
                # CREATE OPERATOR CLASS public.custom_opclass
                # FOR TYPE integer USING hash FAMILY public.custom_opclass A
                # FUNCTION 2 (integer, integer) \
                # public.dummy_hashint4(integer,bigint)
                # OPERATOR 1 =(integer,integer)
                # -----
                # We search for "ALTER OPERATOR FAMILY schema.name ADD"
                # and collect FUNCTIONS AND OPERATORS "FUNCTION num ..."
                aof_search = alter_op_family_pattern.search(line)
                if aof_search:
                    aof = aof_search.group(1)
                    op_families[aof] = []
                    continue
                if aof:
                    op_families[aof].append(line.rstrip(';'))
                    if line.endswith(';'):
                        aof = None
                    continue
                for pattern in sort_patterns:
                    if pattern.match(line):
                        sort_item.append('')
                        sort_body = []
                        if 'OPERATOR' in pattern.pattern:
                            operator = True
                        break
                if sort_item:
                    if operator:
                        # Determine FAMILY for OPERATOR
                        search = re.search(
                            r"\s?FOR\s+TYPE\s+[^\s]+\s+USING"
                            r"\s+[^\s]+\s+FAMILY\s+([^\s]+)\s+.*", line)
                        # And substitute all objects from FAMILY
                        if search and search.group(1) in op_families:
                            sort_body.extend(op_families[search.group(1)])
                            operator = False
                    if len(sort_item) > 1:
                        sort_body.append(line[:-1].strip())
                    else:
                        sort_item.append(line)
                    if line.endswith(';'):
                        sort_body.sort()
                        sort_item.extend(sort_body)
                        sort_items.append("\n".join(sort_item))
                        sort_item = []
                        operator = False
                    continue

                if rt_items or rt_pattern.match(line):
                    rt_items.append(line)
                    if line.endswith(';'):
                        rt_line = " ".join(rt_items)
                        lines.append(re.sub(r"\(,", "(",
                                            remove_mr_tn_pattern.
                                            sub(r"\1\3", rt_line)))
                        rt_items = []
                    continue

                if copy_pattern.match(line):
                    copy_line = line
                    continue
                if line == "\\.":
                    lines.append(copy_line)
                    copy_line = ''
                    lines_to_sort.sort()
                    lines.extend(lines_to_sort)
                    lines_to_sort = []
                if not copy_line:
                    lines.append(line)
                else:
                    lines_to_sort.append(line)
    sort_items.sort()
    lines.extend(sort_items)
    return [line + '\n' for line in lines]


def diff_dbs(file1, file2, diff_file):
    import time
    start_time = time.time()
    lines1 = read_dump(file1)
    print("%s read in %s sec" % (file1, time.time()-start_time))
    start_time = time.time()
    lines2 = read_dump(file2)
    print("%s read in %s sec" % (file2, time.time()-start_time))
    difference = difflib.unified_diff(
        lines1,
        lines2,
        fromfile=file1,
        tofile=file2
    )
    with open(diff_file, "w") as file:
        file.writelines(difference)
        pos = file.tell()
    if pos > 0:
        with open(diff_file, "rb") as file:
            lines = file.readlines()
            i = 1
            for line in lines:
                print(line)
                if i > 20:
                    print("...")
                    break
                i = i + 1
        raise Exception("Difference found. See file " + diff_file)
    gc.collect()


def download_dump(product, edition, version, dir, custom_dump=None):
    if custom_dump:
        dump_file_name = custom_dump
    else:
        dump_file_name = "dump-%s.sql" % "-".join([product, edition, version])
    dump_url = "http://dist.l.postgrespro.ru/pgdatas/xregress/%s" % \
               dump_file_name
    dump_file_name = os.path.join(dir, dump_file_name)
    urlretrieve(dump_url, dump_file_name)
    return dump_file_name


def extend_ver(ver):
    return '.'.join([d.rjust(4) for d in ver.split('.')])


def compare_versions(ver1, ver2):
    v1 = extend_ver(ver1)
    v2 = extend_ver(ver2)
    return -1 if v1 < v2 else (0 if v1 == v2 else 1)


@retry(action='getting soup from %s', arg=1)
def get_soup(url):
    try:
        from bs4 import BeautifulSoup
    except ImportError:  # py2compat
        from BeautifulSoup import BeautifulSoup

    if (sys.version_info > (3, 0)):
        soup = BeautifulSoup(urlopen(url), 'html.parser')
    else:
        soup = BeautifulSoup(urlopen(url))
    return soup


def revoke_admin_right(domipaddress, remote_login, remote_password,
                       windows=False):
    if windows:
        cmd = "powershell -Command \"$group=(New-Object System.Security."\
            "Principal.SecurityIdentifier (\'S-1-5-32-544\')).Translate"\
            "([System.Security.Principal.NTAccount]).Value.Split(\'\\\\\')"\
            "[1]; net localgroup $group %s /delete\"" % remote_login
        exec_command_win(cmd, domipaddress, remote_login, remote_password)
    else:
        raise("Not implemented.")
