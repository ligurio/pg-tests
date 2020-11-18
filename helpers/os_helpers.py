import os
import psutil
import random
import re
import time
import subprocess
from helpers.utils import command_executor, get_distro, REMOTE_ROOT, \
    REMOTE_ROOT_PASSWORD, write_file, refresh_env_win, \
    urlretrieve, ConsoleEncoding

REDHAT_BASED = ['CentOS Linux', 'CentOS',
                'Red Hat Enterprise Linux Server', 'Red Hat Enterprise Linux',
                'Oracle Linux Server',
                'ROSA Enterprise Linux Server',
                'ROSA Enterprise Linux Cobalt', 'GosLinux',
                "\xd0\x9c\xd0\xa1\xd0\x92\xd0\xa1\xd1\x84\xd0\xb5"
                "\xd1\x80\xd0\xb0 \xd0\xa1\xd0\xb5\xd1\x80\xd0\xb2"
                "\xd0\xb5\xd1\x80",
                'RED OS', 'AlterOS']
YUM_BASED = ['CentOS Linux', 'CentOS',
             'Red Hat Enterprise Linux Server', 'Red Hat Enterprise Linux',
             'Oracle Linux Server',
             'ROSA Enterprise Linux Server',
             'ROSA Enterprise Linux Cobalt', 'GosLinux',
             "\xd0\x9c\xd0\xa1\xd0\x92\xd0\xa1\xd1\x84\xd0\xb5\xd1\x80\xd0\xb0"
             " \xd0\xa1\xd0\xb5\xd1\x80\xd0\xb2\xd0\xb5\xd1\x80",
             'RED OS', 'AlterOS']
DEBIAN_BASED = ['debian', 'Ubuntu', 'Debian GNU/Linux',
                'Astra Linux (Smolensk)', 'Astra Linux (Orel)',
                'OSNova Linux (Onyx)']
APT_BASED = ['debian', 'Ubuntu', 'Debian GNU/Linux',
             'Astra Linux (Smolensk)', 'Astra Linux (Orel)',
             'ALT Linux', 'ALT Server', 'ALT SPServer', 'starter kit',
             'OSNova Linux (Onyx)']
ASTRA_BASED = ['Astra Linux (Smolensk)', 'Astra Linux (Orel)']
ALT_BASED = ['ALT Linux', 'ALT Server', 'ALT SPServer', 'starter kit']
SUSE_BASED = ['SLES']
ZYPPER_BASED = ['SLES']
WIN_BASED = ['Windows-2012ServerR2', 'Windows-10', 'Windows-8.1', 'Windows-7']

dist = {"Oracle Linux Server": 'oraclelinux',
        "CentOS Linux": 'centos',
        "CentOS": 'centos',
        "RHEL": 'rhel',
        "Red Hat Enterprise Linux Server": 'rhel',
        "Red Hat Enterprise Linux": 'rhel',
        "debian": 'debian',
        "Debian GNU/Linux": 'debian',
        "Ubuntu": 'ubuntu',
        "OSNova Linux (Onyx)": "osnova",
        "ROSA Enterprise Linux Server": 'rosa-el',
        "ROSA Enterprise Linux Cobalt": 'rosa-sx',
        "SLES": 'sles',
        "ALT Linux": 'altlinux',
        "ALT Server": 'altlinux',
        "starter kit": 'altlinux',
        "GosLinux": 'goslinux',
        "RED OS": 'redos',
        "AlterOS": 'alteros'}


class OsHelper:
    def __init__(self, remote=False, host=None):
        self.remote = remote
        self.host = host
        self.dist_info = get_distro(remote, host)
        self.os_name = self.dist_info[0]
        self.os_version = self.dist_info[1]
        self.os_arch = self.dist_info[2]

    def get_package_version(self, package_name):
        cmd = ''
        if self.is_pm_yum():
            cmd = "sh -c \"LANG=C yum info %s\"" % package_name
        elif self.is_pm_apt():
            cmd = "sh -c \"LANG=C apt-cache show %s\"" % package_name
        elif self.is_pm_zypper():
            cmd = "sh -c \"LANG=C zypper info %s\"" % package_name

        if cmd:
            out = command_executor(cmd, self.remote, self.host,
                                   REMOTE_ROOT, REMOTE_ROOT_PASSWORD,
                                   stdout=True).split('\n')
            for line in out:
                # Find "Version : 9.6.15.2-alt1" or "Version: 2:9.6.15.2-alt1"
                # or "Version: 10.10.2"
                # or "Version: 13beta1"
                vere = re.search(r'Version\s*:.*[:\s]([0-9.a-z]+)', line)
                if (vere):
                    return vere.group(1)
        return None

    def get_packages_in_repo(self, reponame, version):
        result = []
        if self.is_windows():
            return result
        if self.is_pm_yum():
            cmd = "script -q -c \"stty cols 150; " \
                  "LANG=C yum -q --disablerepo='*' " \
                  "--enablerepo='%s' list available\"" % reponame
            ysout = command_executor(cmd, self.remote, self.host,
                                     REMOTE_ROOT, REMOTE_ROOT_PASSWORD,
                                     stdout=True).split('\n')
            for line in ysout:
                line = line.strip()
                if line == 'Available Packages' or line == '':
                    continue
                pkginfo = line.split()
                if len(pkginfo) != 3:
                    print("Invalid line in yum list output:", line)
                    raise Exception('Invalid line in yum list output')
                pkgname = re.sub(r'\.(x86_64|noarch)$', '', pkginfo[0])
                result.append(pkgname)
            if version == '9.6':
                if 'pgbadger' in result and 'pgpro-pgbadger' in result:
                    result.remove('pgbadger')
        elif self.is_altlinux():
            # Parsing binary package info in lists/ is unfeasible,
            # so the only way to find packages from the repository is
            # to parse `apt-cache showpkg` output
            # Use only relevant lists in separate directory to optimize parsing
            cmd = "sh -c \"rm -rf /tmp/t_r 2>/dev/null; mkdir /tmp/t_r;" \
                  "cp /var/lib/apt/lists/%s* /tmp/t_r/;" \
                "echo 'Dir::State::Lists \\\"/tmp/t_r\\\";'>/tmp/t_apt.conf;" \
                  "APT_CONFIG=/tmp/t_apt.conf " \
                  "apt-cache --names-only search .\"" % reponame
            acout = command_executor(cmd, self.remote, self.host,
                                     REMOTE_ROOT, REMOTE_ROOT_PASSWORD,
                                     stdout=True).split('\n')
            ipkgs = []
            for line in acout:
                if line.strip() != '':
                    ipkgs.append(line[:line.index(' - ')])

            cmd = "sh -c \"APT_CONFIG=/tmp/t_apt.conf " \
                  "apt-cache showpkg %s \"" % (" ".join(ipkgs))
            acout = command_executor(cmd, self.remote, self.host,
                                     REMOTE_ROOT, REMOTE_ROOT_PASSWORD,
                                     stdout=True).split('\n')
            state = 0
            pkgname = None
            for line in acout:
                if line.strip() == '':
                    state = 0
                    pkgname = None
                    continue
                if state == 0:
                    if line.startswith('Package:'):
                        pkgname = re.sub(r'^Package:\s+', '', line)
                        state = 1
                elif state == 1:
                    if line.strip() == 'Versions:':
                        state = 2
                elif state == 2:
                    if ('(/tmp/t_r/' + reponame) in line:
                        result.append(pkgname)
        elif self.is_pm_apt():
            cmd = "sh -c \"grep -h -e 'Package:\\s\\+' " \
                  "/var/lib/apt/lists/%s*\"" % reponame
            gsout = command_executor(cmd, self.remote, self.host,
                                     REMOTE_ROOT, REMOTE_ROOT_PASSWORD,
                                     stdout=True).split('\n')
            for line in gsout:
                if line == '':
                    continue
                pkgname = line.replace('Package: ', '')
                if pkgname == 'Auto-Built-debug-symbols':
                    continue
                if pkgname not in result:
                    result.append(pkgname)
            if version == '9.6':
                # PGPRO-2286
                exclude = []
                for pkgname in result:
                    if pkgname.startswith('lib'):
                        if ('postgrespro-' + pkgname) in result:
                            exclude.append(pkgname)
                for pkgname in exclude:
                    result.remove(pkgname)
        elif self.is_pm_zypper():
            cmd = "sh -c \"LANG=C zypper search --repo %s\"" % reponame
            zsout = command_executor(cmd, self.remote, self.host,
                                     REMOTE_ROOT, REMOTE_ROOT_PASSWORD,
                                     stdout=True).split('\n')
            for line in zsout:
                pkginfo = line.split('|')
                if len(pkginfo) != 4:
                    continue
                pkgname = pkginfo[1].strip()
                if (pkgname == 'Name'):
                    continue
                result.append(pkgname)
        return result

    def get_files_in_package(self, pkgname):
        if self.is_debian_based():
            cmd = "sh -c \"LANG=C dpkg --listfiles %s\"" % pkgname
        else:
            cmd = "sh -c \"LANG=C rpm -q --list %s 2>&1\"" % pkgname
        result = command_executor(cmd, self.remote, self.host,
                                  REMOTE_ROOT, REMOTE_ROOT_PASSWORD,
                                  stdout=True).strip().split('\n')
        if result and result[0] == '(contains no files)':
            return []
        return result

    def is_redhat_based(self):
        return self.os_name in REDHAT_BASED

    def is_debian_based(self):
        return self.os_name in DEBIAN_BASED

    def is_astra(self):
        return self.os_name in ASTRA_BASED

    def is_altlinux(self):
        return self.os_name in ALT_BASED

    def is_suse(self):
        return self.os_name in SUSE_BASED

    def is_debian(self):
        return self.os_name == 'Debian GNU/Linux'

    def is_windows(self):
        return self.os_name in WIN_BASED

    def is_pm_apt(self):
        return self.os_name in APT_BASED

    def is_pm_zypper(self):
        return self.os_name in ZYPPER_BASED

    def is_pm_yum(self):
        return self.os_name in YUM_BASED

    def install_package(self, pkg_name):
        """
        :param pkg_name
        :return:
        """
        if self.is_pm_yum():
            cmd = "yum install -y %s" % pkg_name
            self.exec_cmd_retry(cmd)
        elif self.is_pm_apt():
            if self.is_altlinux():
                cmd = "sh -c \"apt-get install -y %s\"" % \
                      pkg_name.replace('*', '.*')
            else:
                cmd = "sh -c \"DEBIAN_FRONTEND='noninteractive' " \
                      "apt-get -y -o " \
                      "Dpkg::Options::='--force-confdef' -o " \
                      "Dpkg::Options::='--force-confold' install %s\"" % \
                      pkg_name.replace('*', '.*')
            self.exec_cmd_retry(cmd)
        elif self.is_pm_zypper():
            cmd = "zypper install -y -l --force-resolution %s" % pkg_name
            self.exec_cmd_retry(cmd)
        else:
            raise Exception("Unsupported system: %s" % self.os_name)

    def get_package_deps(self, pkgname):
        """
        :param pkgname
        :return:
        """
        if self.is_debian_based():
            cmd = "sh -c \"LANG=C dpkg -s %s\"" % pkgname
        else:
            cmd = "sh -c \"LANG=C rpm -q --requires %s\"" % pkgname
        result = command_executor(cmd, self.remote, self.host,
                                  REMOTE_ROOT, REMOTE_ROOT_PASSWORD,
                                  stdout=True).strip()
        if self.is_debian_based():
            for line in result.split('\n'):
                depprefix = 'Depends: '
                if line.startswith(depprefix):
                    return line[len(depprefix):]
        else:
            return ', '.join(result.split('\n'))

    def remove_package(self, pkg_name, purge=False):
        """
        :param pkg_name
        :return:
        """
        if self.is_pm_yum():
            # todo fix this
            cmd = "yum remove -y%s %s" % \
                  (' --noautoremove' if self.os_version.startswith(
                      '8') else '', pkg_name)
            command_executor(cmd, self.remote, self.host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        elif self.is_pm_apt():
            cmd = "apt-get %s -y %s" % (
                'purge' if purge and self.is_debian_based() else
                'remove',
                pkg_name.replace('*', '.*'))
            command_executor(cmd, self.remote, self.host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        elif self.is_pm_zypper():
            cmd = "rpm -qa %s" % pkg_name
            installed_pkgs = subprocess.check_output(cmd, shell=True). \
                decode(ConsoleEncoding).splitlines()
            if (len(installed_pkgs)):
                pkg_name = ' '.join(installed_pkgs)
                cmd = "zypper remove -y %s" % pkg_name
                command_executor(cmd, self.remote, self.host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        elif self.is_windows():
            raise Exception("Not implemented on Windows.")
        else:
            raise Exception("Unsupported system: %s." % self.os_name)

    def exec_cmd_retry(self, cmd, retry_cnt=5, stdout=False):
        timeout = 0
        attempt = 1
        while attempt < retry_cnt:
            try:
                return command_executor(cmd, self.remote, self.host,
                                        REMOTE_ROOT, REMOTE_ROOT_PASSWORD,
                                        stdout)
            except Exception as ex:
                print('Exception occured while running command "%s":' % cmd)
                print(ex)
                print('========')
                attempt += 1
                timeout += 5
                print('Retrying (attempt %d with delay for %d seconds)...' %
                      (attempt, timeout))
                time.sleep(timeout)
        if retry_cnt > 1:
            print('Last attempt to execute the command...\n')
        return command_executor(cmd, self.remote, self.host,
                                REMOTE_ROOT, REMOTE_ROOT_PASSWORD,
                                stdout)

    def get_all_installed_packages(self):
        result = []
        if self.is_windows():
            return result
        if self.is_pm_yum():
            cmd = "script -q -c \"stty cols 150; " \
                  "LANG=C yum -q list installed\""
            ysout = command_executor(cmd, self.remote, self.host,
                                     REMOTE_ROOT, REMOTE_ROOT_PASSWORD,
                                     stdout=True).split('\n')
            for line in ysout:
                line = line.strip()
                if line == 'Available Packages' or line == '' or \
                        line == 'Installed Packages':
                    continue
                pkginfo = line.split()
                if len(pkginfo) != 3:
                    print("Invalid line in yum list output:", line)
                    raise Exception('Invalid line in yum list output')
                pkgname = re.sub(r'\.(x86_64|noarch)$', '', pkginfo[0])
                result.append(pkgname)
        elif self.is_altlinux():
            cmd = "rpm -qa --qf '%{name}\\n'"
            acout = command_executor(cmd, self.remote, self.host,
                                     REMOTE_ROOT, REMOTE_ROOT_PASSWORD,
                                     stdout=True).split('\n')
            result = acout[:]
        elif self.is_pm_apt():
            result = []
            cmd = "apt list --installed"
            gsout = command_executor(cmd, self.remote, self.host,
                                     REMOTE_ROOT, REMOTE_ROOT_PASSWORD,
                                     stdout=True).split('\n')
            passthrough = True
            for line in gsout:
                if line == '':
                    continue
                if passthrough:
                    passthrough = line != 'Listing...'
                    continue
                result.append(line.split('/')[0])
        elif self.is_pm_zypper():
            cmd = "sh -c \"LANG=C zypper packages --installed-only\""
            zsout = command_executor(cmd, self.remote, self.host,
                                     REMOTE_ROOT, REMOTE_ROOT_PASSWORD,
                                     stdout=True).split('\n')
            for line in zsout:
                pkginfo = line.split('|')
                if len(pkginfo) != 5:
                    continue
                pkgname = pkginfo[2].strip()
                if (pkgname == 'Name'):
                    continue
                result.append(pkgname)
        return result

    def is_service_installed(self, service):
        if self.is_windows():
            winsrv = None
            try:
                winsrv = psutil.win_service_get(service)
            except psutil.NoSuchProcess:
                return False
            return winsrv is not None
        systemd_version = get_systemd_version()
        if systemd_version > 210:
            cmd = 'LANG=C systemctl list-unit-files' \
                    ' --no-legend --no-pager "%s.service"' % service
            try:
                result = subprocess.check_output(cmd, shell=True). \
                    decode(ConsoleEncoding).strip()
                if result:
                    if ' masked' in result:
                        return False
                    return True
                return False
            except Exception as e:
                return False
        cmd = 'LANG=C service "%s" status' % service
        srv = subprocess.Popen(cmd,
                            shell=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
        srvout, srverr = srv.communicate()
        srverr = srverr.decode(ConsoleEncoding)
        if srv.returncode == 0:
            return True
        elif srv.returncode == 1 or srv.returncode == 4:
            if srverr.strip().lower().endswith(': unrecognized service') or \
            srverr.strip().endswith(' could not be found.') or \
            srverr.startswith('service: no such service'):
                return False
        return True


    def is_service_running(self, service):
        if self.is_windows():
            winsrv = None
            try:
                winsrv = psutil.win_service_get(service).as_dict()
            except psutil.NoSuchProcess:
                return False
            if winsrv:
                return winsrv['status'] == 'running'
        cmd = 'service "%s" status' % service
        result = subprocess.call(cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                shell=True)
        return result == 0

    def service_action(self, service, action='start'):
        if self.is_windows():
            if action == 'restart':
                cmd = 'net stop "{0}" & net start "{0}"'.format(
                    service)
            else:
                cmd = 'net %s "%s"' % (action, service)
        else:
            cmd = 'service "%s" %s' % (service, action)
        subprocess.check_call(cmd, shell=True)


def download_file(url, path):
    """ Download file from remote path

    :param url: str
    :param path: str
    :return:
    """

    try:
        urlretrieve(url, path)
    except Exception:
        print("Failed to download %s" % url)


def parse_connstring(connstring):
    """Convert connection string to a dict with parameters
    """

    return dict(re.findall(r'(\S+)=(".*?"|\S+)', connstring))


def pg_bindir():
    """Get path to postgresql(postgrespro) bin directory

    :return: string path to bin directory
    """
    raise NotImplementedError()


def pg_config_dir():
    """Get path to pg_config utility

    :return: string path to pg_config utility
    """
    raise NotImplementedError()


def load_pgbench(connstring, params):
    """

    :param connstring: string with connection params
    :param params:
    :return: int exit code
    """
    raise NotImplementedError()


def delete_data_directory():
    """Delete all files in data directory

    :param data_directory_path: string data directory
    """
    raise NotImplementedError()


def get_directory_size(start_path):
    """ Get directory size recursively

    :param start_path: directory for start
    :return: total size of directory in bytes
    """
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(start_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)
    return total_size


def get_process_pids(process_names):
    """Get process ids
    :process_name: string: array of possible process names
    :return: list of process pids
    """
    pids = []
    for p in psutil.process_iter():
        if p.name() in process_names:
            pids.append(p.pid)
    return pids


def get_systemd_version():
    sysctl = subprocess.Popen("systemctl --version",
                              shell=True,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
    scout, scerr = sysctl.communicate()
    if sysctl.returncode != 0:
        return None
    firstline = scout.decode(ConsoleEncoding).splitlines()[0]
    m = re.match(r'systemd\s+(\d+)', firstline)
    if not m:
        return None
    return int(m.group(1))


def create_tablespace_directory():
    """Create new  directory for tablespace
    :return: str path to tablespace
    """

    import pwd
    import grp

    tmp_dir = '/tmp'
    tablespace_catalog = 'tablespace-' + str(random.randint(0, 100))
    tablespace_path = os.path.join(tmp_dir, tablespace_catalog)
    os.mkdir(tablespace_path)
    os.chown(tablespace_path,
             pwd.getpwnam("postgres").pw_uid,
             grp.getgrnam("postgres").gr_gid)
    return tablespace_path
