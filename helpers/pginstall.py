import logging
import os
import subprocess
import tempfile
import urllib
import re
import time
import shutil
import glob

from BeautifulSoup import BeautifulSoup

from helpers.utils import command_executor
from helpers.utils import get_distro
from helpers.utils import REMOTE_ROOT
from helpers.utils import REMOTE_ROOT_PASSWORD
from helpers.utils import write_file
from helpers.utils import refresh_env_win

PGPRO_ARCHIVE_STANDARD = "http://repo.postgrespro.ru/pgpro-archive/"
PGPRO_ARCHIVE_ENTERPRISE = "http://repoee.l.postgrespro.ru/archive/"
PGPRO_DEV_SOURCES_BASE = "http://localrepo.l.postgrespro.ru/dev/src"
PGPRO_ARCHIVE_SOURCES_BASE = "http://localrepo.l.postgrespro.ru/stable/src"
PGPRO_STABLE_SOURCES_BASE = "http://localrepo.l.postgrespro.ru/stable/src"
PGPRO_BRANCH_BASE = "http://localrepo.l.postgrespro.ru/branches/"
PGPRO_BASE = "http://repo.postgrespro.ru/"
PGPRO_BASE_ENTERPRISE = "http://repoee.l.postgrespro.ru/"
PGPRO_BASE_ENTERPRISE_BETA = "http://repo.l.postgrespro.ru/"
PGPROALPHA_BASE = "http://localrepo.l.postgrespro.ru/dev/"
PGPROBETA_BASE = "http://localrepo.l.postgrespro.ru/stable/"
PGPROCERT_BASE = "http://localrepo.l.postgrespro.ru/cert/"
PSQL_BASE = "http://download.postgresql.org/pub"
WIN_INST_DIR = "C:\\Users\\test\\pg-tests\\pg_installer"
REDHAT_BASED = ['CentOS Linux', 'RHEL', 'CentOS',
                'Red Hat Enterprise Linux Server', 'Red Hat Enterprise Linux',
                'Oracle Linux Server',
                'ROSA Enterprise Linux Server', 'ROSA SX \"COBALT\" ',
                'ROSA Enterprise Linux Cobalt', 'GosLinux',
                '\xd0\x9c\xd0\xa1\xd0\x92\xd0\xa1'
                '\xd1\x84\xd0\xb5\xd1\x80\xd0\xb0 ',
                'RED OS release MUROM (', 'AlterOS']
YUM_BASED = ['CentOS Linux', 'RHEL', 'CentOS',
             'Red Hat Enterprise Linux Server', 'Red Hat Enterprise Linux',
             'Oracle Linux Server',
             'ROSA Enterprise Linux Server', 'ROSA SX \"COBALT\" ',
             'ROSA Enterprise Linux Cobalt', 'GosLinux',
             '\xd0\x9c\xd0\xa1\xd0\x92\xd0\xa1'
             '\xd1\x84\xd0\xb5\xd1\x80\xd0\xb0 ',
             'RED OS release MUROM (', 'AlterOS']
DEBIAN_BASED = ['debian', 'Ubuntu', 'Debian GNU/Linux', 'AstraLinuxSE',
                'Astra Linux SE', "\"Astra Linux SE\"", "\"AstraLinuxSE\"",
                'AstraLinuxCE']
APT_BASED = ['debian', 'Ubuntu', 'Debian GNU/Linux', 'AstraLinuxSE',
             'Astra Linux SE', "\"Astra Linux SE\"", "\"AstraLinuxSE\"",
             'AstraLinuxCE',
             "ALT Linux ", "ALT ", "ALT"]
ASTRA_BASED = ['AstraLinuxSE', 'Astra Linux SE', "\"Astra Linux SE\"",
               "\"AstraLinuxSE\"", 'AstraLinuxCE']
ALT_BASED = ['ALT Linux ', 'ALT ', 'ALT']
SUSE_BASED = ['SUSE Linux Enterprise Server ']
ZYPPER_BASED = ['SUSE Linux Enterprise Server ']
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
        "ROSA Enterprise Linux Server": 'rosa-el',
        "ROSA SX \"COBALT\" ": 'rosa-sx',
        "SLES": 'sles',
        "ALT ": 'altlinux',
        "ALT": 'altlinux',
        "GosLinux": 'goslinux',
        "RED OS release MUROM (": 'redos',
        "AlterOS": 'alteros'}

PRELOAD_LIBRARIES = {
    'ent-12':
        ['auth_delay', 'auto_explain', 'in_memory',
         'pg_stat_statements', 'plantuner',
         'shared_ispell', 'pg_wait_sampling',
         'pg_pathman'],
    'ent-11':
        ['auth_delay', 'auto_explain', 'in_memory',
         'pgpro_scheduler',
         'pg_stat_statements', 'plantuner',
         'shared_ispell', 'pg_wait_sampling', 'pg_pageprep', 'pg_shardman',
         'pg_pathman'],
    'std-11':
        ['auth_delay', 'auto_explain',
         'plantuner', 'shared_ispell', 'pg_pageprep', 'pg_pathman'],
    'std-12':
        ['auth_delay', 'auto_explain',
         'plantuner', 'shared_ispell', 'pg_pathman'],
    'std-cert-11':
        ['auth_delay', 'auto_explain',
         'plantuner', 'shared_ispell', 'pg_pageprep', 'pg_pathman',
         'pg_proaudit'],
    'std-10':
        ['auth_delay', 'auto_explain',
         'plantuner', 'shared_ispell', 'pg_pageprep', 'pg_pathman'],
    'ent-10':
        ['auth_delay', 'auto_explain', 'in_memory',
         'pgpro_scheduler', 'pg_stat_statements', 'plantuner',
         'shared_ispell', 'pg_wait_sampling', 'pg_pageprep', 'pg_shardman',
         'pg_pathman'],
    'std-cert-10':
        ['auth_delay', 'auto_explain', 'pgaudit',
         'plantuner', 'shared_ispell', 'pg_pathman'],
    'std-9.6':
        ['auth_delay', 'auto_explain',
         'plantuner', 'shared_ispell', 'pg_pageprep', 'pg_pathman'],
    'ent-9.6':
        ['auth_delay', 'auto_explain',
         'pgpro_scheduler', 'pg_stat_statements', 'plantuner',
         'shared_ispell', 'pg_wait_sampling', 'pg_pageprep',  'pg_pathman'],
    'ent-cert-9.6':
        ['auth_delay', 'auto_explain',
         'pgpro_scheduler', 'pg_stat_statements', 'plantuner',
         'shared_ispell', 'pg_wait_sampling', 'pg_pathman'],
    'ent-cert-10':
        ['auth_delay', 'auto_explain', 'in_memory', 'pgaudit',
         'pgpro_scheduler', 'pg_stat_statements', 'plantuner',
         'shared_ispell', 'pg_wait_sampling', 'pg_shardman',
         'pg_pathman'],
    'ent-cert-11':
        ['auth_delay', 'auto_explain', 'in_memory', 'pg_proaudit',
         'pgpro_scheduler', 'pg_stat_statements', 'plantuner',
         'shared_ispell', 'pg_wait_sampling', 'pg_shardman',
         'pg_pathman', 'pg_pageprep', 'passwordcheck'],
    '1c-10':
        ['auth_delay', 'auto_explain', 'plantuner'],
    '1c-11':
        ['auth_delay', 'auto_explain', 'plantuner'],
    '1c-12':
        ['auth_delay', 'auto_explain', 'plantuner'],
}


class PgInstall:

    def __init__(self, product, edition, version, milestone=None, branch=None,
                 windows=False, remote=False, host=None):
        self.product = product
        self.edition = edition
        self.fullversion = version
        if version.startswith('9.'):
            self.version = '9.' + version.split('.')[1]
        else:
            self.version = version.split('.')[0]
        self.milestone = milestone
        self.branch = branch
        self.windows = windows
        self.installer_name = None
        self.repo_file = None
        self.repo_package = None
        self.remote = remote
        self.host = host
        self.dist_info = get_distro(remote, host)
        self.os_name = self.dist_info[0]
        self.os_version = self.dist_info[1]
        self.os_arch = self.dist_info[2]
        self.srvhost = None
        self.port = None
        self.env = None
        addoption = '-E '
        if self.__is_os_altlinux() and (
                self.os_version.startswith('6.') or
                self.os_version.startswith('7.') or
                self.os_version.startswith('8.')):
            addoption = ''
        self.pg_preexec = '' if windows else \
            ('sudo %s-u postgres ' % addoption)
        self.client_installed = False
        self.server_installed = False
        self.client_path_needed = True
        self.server_path_needed = True
        if edition in ['std', 'std-cert']:
            self.alter_edtn = 'std'
        elif edition in ['ent', 'ent-cert']:
            self.alter_edtn = 'ent'
        else:
            self.alter_edtn = edition
        self.pg_prefix = self.get_default_pg_prefix()
        self.datadir = self.get_default_datadir()
        self.configdir = self.get_default_configdir()
        self.service_name = self.get_default_service_name()
        self.reponame = None
        self.all_packages_in_repo = None
        self.epel_needed = self.version not in ['9.5', '9.6']

    def get_repo_base(self):
        if self.edition in ['std-cert', 'ent-cert']:
            return PGPROCERT_BASE
        if self.milestone == "alpha":
            return PGPROALPHA_BASE
        if self.milestone == "beta":
            return PGPROBETA_BASE
        if self.milestone == "archive":
            if self.product == "postgrespro":
                if self.edition == "ent":
                    return PGPRO_ARCHIVE_ENTERPRISE
                else:
                    return PGPRO_ARCHIVE_STANDARD
            else:
                raise Exception("Archived versions are not supported for %s." %
                                self.product)
        if self.product == "postgrespro" and self.edition == "ent":
            return (PGPRO_BASE_ENTERPRISE_BETA if self.milestone == "beta"
                    else PGPRO_BASE_ENTERPRISE)
        return PGPRO_BASE

    def __get_product_dir(self):
        product_dir = ""
        if self.product == "postgrespro":
            product_version = self.fullversion if self.milestone == 'archive' \
                else self.version
            if self.edition == "ent":
                product_dir = "pgproee-%s" % product_version
            elif self.edition == "std":
                product_dir = "pgpro-%s" % product_version
            elif self.edition == "std-cert" and self.version == "9.6":
                product_dir = "pgpro-std-9.6.3.1/repo"
            elif self.edition == "ent-cert" and self.version == "9.6":
                product_dir = "pgpro-ent-9.6.8.2/repo"
            elif self.edition == "ent-cert" and self.version == "10":
                product_dir = "pgpro-ent-10.3.3/repo"
            elif self.edition == "std-cert" and self.version == "10":
                product_dir = "pgpro-std-10.4.1/repo"
            elif self.edition == "std-cert" and self.version == "11":
                product_dir = "pgpro-std-11.5.4/repo"
            elif self.edition == "ent-cert" and self.version == "11":
                product_dir = "pgpro-ent-11.6.1/repo"
            elif self.edition == "1c":
                product_dir = "pg1c-%s" % product_version
            elif self.edition == "sql":
                product_dir = "pgsql-%s" % product_version
        return product_dir

    def get_base_package_name(self):
        if self.product == 'postgrespro':
            if self.version in ['9.5', '9.6']:
                if self.__is_os_altlinux():
                    if self.edition in ['ent', 'ent-cert']:
                        return '%s-%s%s' % (self.product, 'enterprise',
                                            self.version)
                    return '%s%s' % (self.product, self.version)
                if self.__is_os_redhat_based() or self.__is_os_suse():
                    if self.edition in ['ent', 'ent-cert']:
                        return '%s-%s%s' % (self.product, 'enterprise',
                                            self.version.replace('.', ''))
                    return '%s%s' % (self.product,
                                     self.version.replace('.', ''))
                return '%s-%s' % (self.product, self.version)
            return '%s-%s-%s' % (self.product, self.alter_edtn, self.version)
        elif self.product == 'postgresql':
            if self.__is_os_redhat_based() or self.__is_os_suse():
                return '%s%s' % (self.product, self.version.replace('.', ''))
            return '%s-%s' % (self.product, self.version)
        return '%s-%s' % (self.product, self.version.replace('.', '')) \
            if self.version else '%s' % (self.product)

    def get_server_package_name(self):
        base_package = self.get_base_package_name()
        if self.product == 'postgrespro':
            if self.version in ['9.5', '9.6']:
                if self.__is_os_debian_based():
                    return base_package
            return base_package + '-server'
        elif self.product == 'postgresql':
            if self.__is_os_debian_based():
                return base_package
            return base_package + '-server'
        return base_package

    def get_client_package_name(self):
        base_package = self.get_base_package_name()
        if self.product == 'postgrespro':
            if self.version in ['9.5', '9.6']:
                if self.__is_os_debian_based():
                    return '%s-client-%s' % (self.product, self.version)
                return base_package
            return base_package + '-client'
        elif self.product == 'postgresql':
            if self.__is_os_debian_based():
                return '%s-client-%s' % (self.product, self.version)
            return base_package
        return base_package

    def get_dev_package_name(self):
        base_package = self.get_base_package_name()
        if self.product == 'postgrespro':
            if self.version in ['9.5', '9.6']:
                if self.__is_os_debian_based():
                    return '%s-server-dev-%s' % (self.product, self.version)
            return base_package + (
                '-dev' if self.__is_os_debian_based() else '-devel')
        elif self.product == 'postgresql':
            if self.__is_os_debian_based():
                return '%s-server-dev-%s' % (self.product, self.version)
            return base_package + '-devel'
        return base_package

    def __get_package_version(self, package_name):
        cmd = ''
        if self.__is_pm_yum():
            cmd = "sh -c \"LANG=C yum info %s\"" % package_name
        elif self.__is_pm_apt():
            cmd = "sh -c \"LANG=C apt-cache show %s\"" % package_name
        elif self.__is_pm_zypper():
            cmd = "sh -c \"LANG=C zypper info %s\"" % package_name

        if cmd:
            out = command_executor(cmd, self.remote, self.host,
                                   REMOTE_ROOT, REMOTE_ROOT_PASSWORD,
                                   stdout=True).split('\n')
            for line in out:
                # Find "Version : 9.6.15.2-alt1" or "Version: 2:9.6.15.2-alt1"
                # or "Version: 10.10.2"
                vere = re.search(r'Version\s*:.*[:\s]([0-9.]+)', line)
                if (vere):
                    return vere.group(1)
        return None

    def get_product_minor_version(self):
        if self.__is_os_windows():
            if not self.installer_name:
                raise Exception("Installer name is not defined")
            vere = re.search(r'_([0-9.]+)_', self.installer_name)
            if vere:
                return vere.group(1)
        else:
            return self.__get_package_version(
                self.get_base_package_name() +
                ('' if self.version == '9.6' else '-libs'))

    def get_packages_in_repo(self):
        result = []
        if self.__is_os_windows():
            return result
        if self.__is_pm_yum():
            cmd = "script -q -c \"stty cols 150; "\
                  "LANG=C yum -q --disablerepo='*' "\
                  "--enablerepo='%s' list available\"" % self.reponame
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
            if self.version == '9.6':
                if 'pgbadger' in result and 'pgpro-pgbadger' in result:
                    result.remove('pgbadger')
        elif self.__is_os_altlinux():
            # Parsing binary package info in lists/ is unfeasible,
            # so the only way to find packages from the repository is
            # to parse `apt-cache showpkg` output
            # Use only relevant lists in separate directory to optimize parsing
            cmd = "sh -c \"rm -rf /tmp/t_r 2>/dev/null; mkdir /tmp/t_r;" \
                "cp /var/lib/apt/lists/%s* /tmp/t_r/;" \
                "echo 'Dir::State::Lists \\\"/tmp/t_r\\\";'>/tmp/t_apt.conf;" \
                "APT_CONFIG=/tmp/t_apt.conf " \
                "apt-cache --names-only search .\"" % self.reponame
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
                    if ('(/tmp/t_r/' + self.reponame) in line:
                        result.append(pkgname)
        elif self.__is_pm_apt():
            cmd = "sh -c \"grep -h -e 'Package:\\s\\+' "\
                "/var/lib/apt/lists/%s*\"" % self.reponame
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
            if self.version == '9.6':
                # PGPRO-2286
                exclude = []
                for pkgname in result:
                    if pkgname.startswith('lib'):
                        if ('postgrespro-' + pkgname) in result:
                            exclude.append(pkgname)
                for pkgname in exclude:
                    result.remove(pkgname)
        elif self.__is_pm_zypper():
            cmd = "sh -c \"LANG=C zypper search --repo %s\"" % self.reponame
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
        if self.__is_os_debian_based():
            cmd = "sh -c \"LANG=C dpkg --listfiles %s\"" % pkgname
        else:
            cmd = "sh -c \"LANG=C rpm -q --list %s 2>&1\"" % pkgname
        result = command_executor(cmd, self.remote, self.host,
                                  REMOTE_ROOT, REMOTE_ROOT_PASSWORD,
                                  stdout=True).strip().split('\n')
        if result and result[0] == '(contains no files)':
            return []
        return result

    def get_all_packages_in_repo(self):
        if self.product == 'postgresql':
            if self.__is_os_suse():
                # Filter out packages, which are not installable and
                # not supported by Postgres Pro
                pkgs = [pkg for pkg in self.get_packages_in_repo() if
                        pkg.startswith(self.get_base_package_name()) and
                        not(pkg.endswith('-tcl') or pkg.endswith('-llvmjit'))]
            elif self.__is_os_altlinux():
                pkgs = ['^%s%s.*$' % (self.product,
                                      self.version.replace('.', '\\.'))]
            elif self.__is_os_debian_based():
                pkgs = ['^%s-*%s$' % (self.product,
                                      self.version.replace('.', '\\.'))]
            else:
                pkgs = [self.get_base_package_name() + '*']

        else:
            # PGPRO-????
            # Filter out the package that is not supported by Postgres Pro yet
            pkgs = [pkg for pkg in self.get_packages_in_repo() if
                    not (pkg.startswith("oracle-fdw-"))]

        return pkgs

    def __is_os_redhat_based(self):
        return self.os_name in REDHAT_BASED

    def __is_os_debian_based(self):
        return self.os_name in DEBIAN_BASED

    def __is_os_astra(self):
        return self.os_name in ASTRA_BASED

    def __is_os_altlinux(self):
        return self.os_name in ALT_BASED

    def __is_os_suse(self):
        return self.os_name in SUSE_BASED

    def __is_os_debian(self):
        return self.os_name == 'debian'

    def __is_os_windows(self):
        return self.os_name in WIN_BASED

    def __is_pm_apt(self):
        return self.os_name in APT_BASED

    def __is_pm_zypper(self):
        return self.os_name in ZYPPER_BASED

    def __is_pm_yum(self):
        return self.os_name in YUM_BASED

    def get_supported_vanilla_versions(self):
        if self.__is_os_altlinux():
            return ['10']
        elif self.__is_os_redhat_based() or self.__is_os_debian_based():
            return ['9.6', '10', '11']
        elif self.__is_os_suse() and self.os_version != "11":
            return ['9.6', '10', '11']
        return []

    def get_distname_for_pgpro(self):
        if self.os_name == "ALT Linux " and \
           self.os_version in ["7.0.4", "6.0.1"]:
            return "altlinux-spt"
        elif self.os_name == "ALT Linux " and self.os_version == "7.0.5":
            return "altlinux"
        elif self.os_name == "ALT " and self.os_version == "8":
            return "alt-sp"
        elif self.os_name == "ROSA Enterprise Linux Server":
            if self.os_version == "6.8":
                return "rosa-chrome"
            else:
                return "rosa-el"
        elif self.os_name == "ROSA SX \"COBALT\" " or \
                self.os_name == "ROSA Enterprise Linux Cobalt":
            return "rosa-sx"
        elif self.os_name == "SUSE Linux Enterprise Server ":
            return "sles"
        elif self.os_name in ["AstraLinuxSE", "Astra Linux SE"]:
            if self.os_version == "1.4":
                return "astra-smolensk/1.4"
            elif self.os_version == "1.5":
                return "astra-smolensk/1.5"
            elif self.os_version == "1.6":
                return "astra-smolensk/1.6"
        elif self.os_name == "AstraLinuxCE":
            if self.os_version.startswith("2.12"):
                return "astra-orel/2.12"
        elif self.os_name == "\xd0\x9c\xd0\xa1\xd0\x92\xd0\xa1" \
                "\xd1\x84\xd0\xb5\xd1\x80\xd0\xb0 ":
            return "msvsphere"
        elif self.__is_os_windows():
            return "Windows"
        else:
            return dist[self.os_name].lower()

    def __generate_repo_info(self):
        """Generate information about repository: url to packages
            and path to gpg key
        """

        distname = ""
        product_dir = ""
        gpg_key_url = None
        if self.product == "postgresql":
            if self.__is_pm_yum():
                gpg_key_url = "http://download.postgresql.org/" \
                    "pub/repos/yum/RPM-GPG-KEY-PGDG-%s" % \
                    self.version.replace('.', '')
                product_dir = "/repos/yum/%s/redhat/" \
                    "rhel-$releasever-$basearch" % self.version
            elif self.__is_pm_apt():
                gpg_key_url = "http://www.postgresql.org/"\
                    "media/keys/ACCC4CF8.asc"
                baseurl = "http://apt.postgresql.org/pub/repos/apt/"
                return baseurl, gpg_key_url
            elif self.__is_pm_zypper():
                product_dir = "/repos/zypp/%s/suse/sles-%s-$basearch" % \
                    (self.version,
                     "$releasever" if self.os_version != "12" else "12")
            baseurl = PSQL_BASE + product_dir
            return baseurl, gpg_key_url
        elif self.product == "postgrespro":
            product_dir = self.__get_product_dir()
            gpg_key_url = "%s/%s/keys/GPG-KEY-POSTGRESPRO" % \
                          (self.get_repo_base(), product_dir)
            distname = self.get_distname_for_pgpro()
            if self.edition in ['std-cert', 'ent-cert']:
                baseurl = "/".join([
                    PGPROCERT_BASE,
                    product_dir, distname])
            else:
                if self.__is_os_windows():
                    baseurl = "{}{}/win/".format(self.get_repo_base(),
                                                 product_dir)
                elif self.branch is not None:
                    baseurl = os.path.join(PGPRO_BRANCH_BASE,
                                           self.branch,
                                           product_dir,
                                           distname)
                else:
                    baseurl = os.path.join(self.get_repo_base(),
                                           product_dir,
                                           distname)
            logging.debug("Installation repo path: %s", baseurl)
            logging.debug("GPG key url for installation %s", gpg_key_url)
            return baseurl, gpg_key_url

    def setup_repo(self):
        """ Setup yum or apt repo for Linux Based envs and
            download windows installer for Windows based
        """
        repo_info = self.__generate_repo_info()
        baseurl = repo_info[0]
        gpg_key_url = repo_info[1]
        reponame = None
        if self.__is_pm_yum():

            if self.product == 'postgresql' and \
                    self.os_name == "Red Hat Enterprise Linux" and \
                    self.os_version.startswith("8."):
                cmd = 'yum -qy module disable postgresql'
                self.exec_cmd_retry(cmd)

            product_dir = self.__get_product_dir()

            reponame = "%s-%s%s" % (
                self.product,
                self.edition + '-' if self.product == 'postgrespro' else '',
                self.version)

            if self.milestone != 'archive':
                repo_rpm = "%s/%s/keys/" % \
                           (self.get_repo_base(), product_dir)
                dist_name = self.get_distname_for_pgpro()
                try:
                    soup = BeautifulSoup(urllib.urlopen(repo_rpm))
                    for link in soup.findAll('a'):
                        href = link.get('href')
                        if href.startswith('%s.%s' % (reponame, dist_name)):
                            self.exec_cmd_retry('yum install -y %s%s' %
                                                (repo_rpm, href))
                            self.repo_package = self.exec_cmd_retry(
                                'rpm -qp "%s%s"' % (repo_rpm, href),
                                stdout=True)
                            self.epel_needed = False
                            break
                except Exception:
                    pass

            if not self.repo_package:
                # Example:
                # http://repo.postgrespro.ru/pgproee-9.6-beta/
                #  centos/$releasever/os/$basearch/rpms
                if self.product == "postgrespro":
                    if self.os_name == "ROSA Enterprise Linux Server" and \
                     self.os_version == "6.8":
                        baseurl = os.path.join(baseurl,
                                               "6.8Server/os/$basearch/rpms")
                    elif self.os_name == "ROSA Enterprise Linux Cobalt" and \
                            self.os_version == "7.3":
                        baseurl = os.path.join(baseurl,
                                               "7Server/os/$basearch/rpms")
                    elif self.os_name == "\xd0\x9c\xd0\xa1\xd0\x92\xd0\xa1" \
                                         "\xd1\x84\xd0\xb5\xd1\x80\xd0\xb0 ":
                        baseurl = os.path.join(baseurl,
                                               "6.3Server/os/$basearch/rpms")
                    elif self.os_name == "GosLinux" and \
                            self.os_version.startswith("7."):
                        baseurl = os.path.join(baseurl,
                                               "7/os/$basearch/rpms")
                    elif self.os_name == "RED OS release MUROM (" and \
                            self.os_version == "7.1":
                        baseurl = os.path.join(baseurl,
                                               "7/os/$basearch/rpms")
                    elif self.os_name == "Red Hat Enterprise Linux" and \
                            self.os_version.startswith("8."):
                        baseurl = os.path.join(baseurl,
                                               "8Server/os/$basearch/rpms")
                    else:
                        baseurl = os.path.join(baseurl,
                                               "$releasever/os/$basearch/rpms")

                repo = """
[%s]
name=%s
enabled=1
baseurl=%s
                """ % (reponame,
                       reponame,
                       baseurl)
                self.repo_file = "/etc/yum.repos.d/%s-%s%s.repo" % (
                    self.product,
                    self.edition + '-' if self.product == 'postgrespro'
                    else '',
                    self.version)
                write_file(self.repo_file, repo, self.remote, self.host)
                cmd = "rpm --import %s" % gpg_key_url
                self.exec_cmd_retry(cmd)
                cmd = "yum --enablerepo=%s clean metadata" % reponame
                command_executor(cmd, self.remote, self.host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        elif self.__is_pm_apt():
            cmd = "apt-get install -y lsb-release"
            self.exec_cmd_retry(cmd)
            cmd = "lsb_release -cs"
            if self.remote:
                codename = command_executor(
                    cmd, self.remote, self.host,
                    REMOTE_ROOT, REMOTE_ROOT_PASSWORD)[1].rstrip()
            else:
                codename = command_executor(
                    cmd, self.remote, stdout=True).rstrip()
            self.repo_file = "/etc/apt/sources.list.d/%s-%s.list" % (
                self.product, self.version)
            repo = None
            if self.product == "postgresql":
                if not self.__is_os_altlinux():
                    repo = "deb %s %s-pgdg main" % (baseurl, codename)
            elif self.product == "postgrespro":
                repo = "deb %s %s main" % (baseurl, codename)
                if self.os_name == "ALT Linux ":
                    if self.os_version in ["7.0.4", "7.0.5"]:
                        repo = "rpm %s/7 x86_64 pgpro\n" \
                               "rpm %s/7 noarch pgpro\n" % \
                               (baseurl, baseurl)
                    elif self.os_version == "6.0.1":
                        repo = "rpm %s/6 x86_64 pgpro\n" \
                               "rpm %s/6 noarch pgpro\n" % \
                               (baseurl, baseurl)
                elif self.os_name == "ALT ":
                    repo = "rpm %s/8 x86_64 pgpro\n" \
                           "rpm %s/8 noarch pgpro\n" % \
                           (baseurl, baseurl)
                elif (self.os_name == "ALT" and
                      self.os_version.startswith('9.')):
                    repo = "rpm %s/9 x86_64 pgpro\n" \
                           "rpm %s/9 noarch pgpro\n" % \
                           (baseurl, baseurl)

            if repo:
                write_file(self.repo_file, repo, self.remote, self.host)
                reponame = re.sub(r"^http(s)?://", "", baseurl).\
                    replace('/', '_')

                if not self.__is_os_altlinux():
                    cmd = "apt-get install -y wget ca-certificates"
                    self.exec_cmd_retry(cmd)
                    cmd = "wget -nv %s -O gpg.key" % gpg_key_url
                    self.exec_cmd_retry(cmd)
                    cmd = "apt-key add gpg.key"
                    self.exec_cmd_retry(cmd)
                cmd = "apt-get update -y"
                self.exec_cmd_retry(cmd)
        elif self.__is_pm_zypper():
            reponame = "%s-%s" % (self.product, self.version)
            if gpg_key_url:
                cmd = "wget -nv %s -O gpg.key" % gpg_key_url
                self.exec_cmd_retry(cmd)
                cmd = "rpm --import ./gpg.key"
                try:
                    # SLES 11 fails when the key is already imported
                    command_executor(cmd, self.remote, self.host,
                                     REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
                except Exception:
                    pass
            if self.product == "postgrespro":
                dir = self.os_version
                if self.os_name == 'SUSE Linux Enterprise Server ' and \
                   self.os_version.startswith('12') and \
                   self.milestone == 'archive':
                    last12_1 = ''
                    if self.fullversion.startswith('9.6.'):
                        last12_1 = '   9.   6.  12.   1'
                    elif self.fullversion.startswith('10.'):
                        last12_1 = '  10.   7.   1'
                    elif self.fullversion.startswith('11.'):
                        last12_1 = '  11.   2.   1'
                    if (last12_1 and
                            '.'.join(
                                [d.rjust(4) for d in
                                 self.fullversion.split('.')]
                            ) <= last12_1):
                        dir = "12.1"
                baseurl = os.path.join(baseurl, dir)
            cmd = "zypper removerepo %s" % (reponame)
            command_executor(cmd, self.remote, self.host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            cmd = "zypper addrepo %s %s" % (baseurl, reponame)
            command_executor(cmd, self.remote, self.host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            cmd = "zypper --gpg-auto-import-keys refresh"
            self.exec_cmd_retry(cmd)
        elif self.__is_os_windows():
            installer_name = self.__get_last_winstaller_file(
                baseurl, self.os_arch)
            windows_installer_url = baseurl + installer_name
            windows_installer = urllib.URLopener()
            if not os.path.exists(WIN_INST_DIR):
                os.mkdir(WIN_INST_DIR)
            print(baseurl + installer_name)
            self.installer_name = os.path.join(WIN_INST_DIR,
                                               installer_name)
            windows_installer.retrieve(windows_installer_url,
                                       self.installer_name)
            msi_files = self.__get_msi_files(baseurl)
            for msi in msi_files:
                windows_installer = urllib.URLopener()
                windows_installer.retrieve(
                    baseurl + msi,
                    os.path.join(WIN_INST_DIR, msi))
        else:
            raise Exception("Unsupported distro %s" % self.os_name)
        self.reponame = reponame
        self.all_packages_in_repo = self.get_all_packages_in_repo()

    def setup_extra_repos(self):
        if self.product == 'postgrespro' and self.__is_os_altlinux():
            cmd = r"perl -i -pe 's/^\s*([^#](.*?)x86_64)(\s+classic\s*)$/" \
                  "$1$3$1 debuginfo\n/' /etc/apt/sources.list.d/%s.list" % \
                  ('yandex' if self.os_version.startswith('9.') else 'alt')
            command_executor(cmd, self.remote, self.host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            self.exec_cmd_retry('apt-get update')
        if self.epel_needed:
            # Install epel for v.10+
            cmd = None
            if (self.os_name == 'CentOS Linux' and
               self.os_version.startswith('7.')):
                cmd = "yum install -y epel-release"
            elif (self.os_name in ['Oracle Linux Server', 'CentOS',
                                   'Red Hat Enterprise Linux Server'] and
                  self.os_version.startswith('6.')):
                self.exec_cmd_retry("wget https://dl.fedoraproject.org/pub/"
                                    "epel/epel-release-latest-6.noarch.rpm")
                self.exec_cmd_retry("rpm -iv --force "
                                    "epel-release-latest-6.noarch.rpm", 0)
                self.exec_cmd_retry("sed -i s/https:/http:/ "
                                    "/etc/yum.repos.d/epel.repo", 0)
            elif (self.os_name in ['Oracle Linux Server',
                                   'Red Hat Enterprise Linux Server',
                                   'AlterOS',
                                   'ROSA Enterprise Linux Cobalt',
                                   'ROSA Enterprise Linux Server'] and
                  self.os_version.startswith('7.')):
                cmd = "yum localinstall -y https://dl.fedoraproject.org/pub/" \
                    "epel/epel-release-latest-7.noarch.rpm"
            if cmd:
                self.exec_cmd_retry(cmd)

    def download_source(self):
        baseurl = ''
        if self.product == "postgresql":
            pass
        elif self.product == "postgrespro":
            if self.edition in ['ent-cert', 'std-cert']:
                product_dir = self.__get_product_dir()
                baseurl = PGPROCERT_BASE + \
                    product_dir.replace('/repo', '/sources')
            else:
                if self.milestone == 'alpha':
                    baseurl = PGPRO_DEV_SOURCES_BASE
                elif self.milestone == 'beta':
                    baseurl = PGPRO_STABLE_SOURCES_BASE
                else:
                    baseurl = PGPRO_ARCHIVE_SOURCES_BASE
        edition = ''
        product = 'postgresql' if self.edition == '1c' else 'postgrespro'
        if self.edition in ['std', 'std-cert'] \
                and self.version not in ['9.6', '9.5']:
            edition = '-standard'
        elif self.edition in ['ent', 'ent-cert']:
            edition = '-enterprise'
        tar_href = '%s%s-%s.tar.bz2' % \
                   (product, edition, self.get_product_minor_version())
        tar_url = baseurl + '/' + tar_href
        sourcetar = urllib.URLopener()
        attempt = 1
        timeout = 0
        while attempt < 9:
            try:
                sourcetar.retrieve(tar_url, tar_href)
                return
            except Exception as ex:
                print('Exception occured while downloading sources "%s":' %
                      tar_url)
                print(ex)
                attempt += 1
                timeout += 5
                print('Retrying (attempt %d with delay for %d seconds)...' %
                      (attempt, timeout))
                time.sleep(timeout)
        # Last attempt
        sourcetar.retrieve(tar_url, tar_href)

    def install_package(self, pkg_name):
        """
        :param pkg_name
        :return:
        """
        if self.__is_pm_yum():
            cmd = "yum install -y %s" % pkg_name
            self.exec_cmd_retry(cmd)
        elif self.__is_pm_apt():
            if self.__is_os_altlinux():
                cmd = "sh -c \"apt-get install -y %s\"" % \
                      pkg_name.replace('*', '.*')
            else:
                cmd = "sh -c \"DEBIAN_FRONTEND='noninteractive' " \
                      "apt-get -y -o " \
                      "Dpkg::Options::='--force-confdef' -o " \
                      "Dpkg::Options::='--force-confold' install %s\"" % \
                      pkg_name.replace('*', '.*')
            self.exec_cmd_retry(cmd)
        elif self.__is_pm_zypper():
            cmd = "zypper install -y -l --force-resolution %s" % pkg_name
            self.exec_cmd_retry(cmd)
        else:
            raise Exception("Unsupported system: %s" % self.os_name)

    def get_package_deps(self, pkgname):
        """
        :param pkgname
        :return:
        """
        if self.__is_os_debian_based():
            cmd = "sh -c \"LANG=C dpkg -s %s\"" % pkgname
        else:
            cmd = "sh -c \"LANG=C rpm -q --requires %s\"" % pkgname
        result = command_executor(cmd, self.remote, self.host,
                                  REMOTE_ROOT, REMOTE_ROOT_PASSWORD,
                                  stdout=True).strip()
        if self.__is_os_debian_based():
            for line in result.split('\n'):
                depprefix = 'Depends: '
                if line.startswith(depprefix):
                    return line[len(depprefix):]
        else:
            return ', '.join(result.split('\n'))

    def update_all_packages(self):
        """
        :return:
        """
        if self.__is_pm_yum():
            cmd = "yum update -y --disablerepo='*'   --enablerepo='%s'" % \
                  self.reponame
            self.exec_cmd_retry(cmd)
        elif self.__is_pm_apt():
            precmd = "rm -rf /tmp/t_r 2>/dev/null;" \
                     "mkdir /tmp/t_r /tmp/t_r/partial;" \
                     "cp /var/lib/apt/lists/%s* /tmp/t_r/;" \
                     "echo 'Dir::State::Lists \\\"/tmp/t_r\\\";'" \
                     ">/tmp/t_apt.conf; " \
                     "APT_CONFIG=/tmp/t_apt.conf " % self.reponame
            if self.__is_os_altlinux():
                cmd = "sh -c \"%sapt-get dist-upgrade -y\"" % precmd
            else:
                cmd = "sh -c \"%sDEBIAN_FRONTEND='noninteractive' " \
                      "apt-get -y -o " \
                      "Dpkg::Options::='--force-confdef' -o " \
                      "Dpkg::Options::='--force-confold' dist-upgrade\"" % \
                      precmd
            self.exec_cmd_retry(cmd)
        elif self.__is_pm_zypper():
            cmd = "zypper update -y -r %s" % self.reponame
            self.exec_cmd_retry(cmd)
        else:
            raise Exception("Unsupported system: %s" % self.os_name)

    def install_base(self):
        self.install_package(self.get_base_package_name())
        if self.product == "postgrespro":
            if self.version in ['9.5', '9.6']:
                if self.__is_os_altlinux() or \
                   self.__is_os_redhat_based() or \
                   self.__is_os_suse():
                    self.install_package(self.get_server_package_name())
        self.client_installed = True
        self.server_installed = True
        self.client_path_needed = False
        self.server_path_needed = False
        if self.product == "postgrespro":
            if self.version in ['9.5', '9.6']:
                if self.__is_os_astra() or \
                   self.__is_os_redhat_based() or \
                   self.__is_os_debian_based():
                    self.client_path_needed = True
                    self.server_path_needed = True
        elif self.product == "postgresql":
            if self.__is_os_redhat_based() or \
               self.__is_os_debian_based() or \
               self.__is_os_suse():
                self.client_path_needed = True
                self.server_path_needed = True

    def install_full(self):
        self.setup_extra_repos()
        self.install_package(" ".join(self.all_packages_in_repo))
        self.client_installed = True
        self.server_installed = True
        self.client_path_needed = False
        self.server_path_needed = False
        if self.product == "postgrespro" and self.version in ['9.5', '9.6']:
            if self.__is_os_astra() or \
               self.__is_os_redhat_based() or \
               self.__is_os_debian_based():
                self.client_path_needed = True
                self.server_path_needed = True
        elif self.product == "postgresql":
            if self.__is_os_redhat_based() or \
               self.__is_os_debian_based() or \
               self.__is_os_suse():
                self.client_path_needed = True
                self.server_path_needed = True

    def install_full_topless(self):
        self.setup_extra_repos()
        pkgs = self.all_packages_in_repo
        # pgbadger
        for pkg in pkgs[:]:
            # PGPRO-3218
            if self.__is_os_suse() and self.os_version.startswith('15') \
                    and 'zstd' in pkg:
                pkgs.remove(pkg)
            if 'pgbadger' in pkg:
                pkgs.remove(pkg)
        if self.product == 'postgrespro' and \
                self.version not in ['9.5', '9.6'] and \
                self.get_base_package_name():
            pkgs.remove(self.get_base_package_name())
            if self.__is_os_altlinux():
                for pkg in pkgs[:]:
                    if re.match('.*-deb.*', pkg):
                        pkgs.remove(pkg)
        self.install_package(" ".join(pkgs))
        self.client_installed = True
        self.server_installed = True
        self.client_path_needed = True
        self.server_path_needed = True

    def install_server_dev(self):
        self.install_package(self.get_dev_package_name())
        self.client_installed = True
        self.server_installed = True
        self.client_path_needed = True
        self.server_path_needed = True

    def install_server_only(self):
        self.install_package(self.get_server_package_name())
        self.server_installed = True
        self.server_path_needed = True
        self.client_path_needed = True

    def install_client_only(self):
        self.install_package(self.get_client_package_name())
        self.client_installed = True
        self.client_path_needed = True

    def install_postgres_win(self, port=None):
        self.port = port
        if not self.installer_name:
            raise Exception("Installer name is not defined")
        if not os.path.exists(self.installer_name):
            raise Exception(
                "Executable installer %s not found." %
                self.installer_name)
        ininame = os.path.join(WIN_INST_DIR, "pgpro.ini")
        with open(ininame, "w") as ini:
            ini.write("[options]\nenvvar=1\nneedoptimization=0\n" +
                      (("port=%s\n" % port) if port else ""))
        cmd = "%s /S /init=%s" % (self.installer_name, ininame)
        command_executor(cmd, windows=True)
        msis = glob.glob(os.path.join(WIN_INST_DIR, '*.msi'))
        for msi in sorted(msis):
            # pageprep will be removed
            if not (self.edition == '1c' and 'pageprep' in msi):
                msilog = "%s.log" % msi
                cmd = 'msiexec /i %s /quiet /qn /norestart /log %s' % \
                    (msi, msilog)
                command_executor(cmd, windows=True)
        refresh_env_win()
        self.client_path_needed = False
        self.server_path_needed = False

    def install_perl_win(self):
        if self.os_arch == 'AMD64':
            exename = 'ActivePerl-5.26.1.2601-MSWin32-x64-404865.exe'
        else:
            exename = 'ActivePerl-5.22.4.2205-MSWin32-x86-64int-403863.exe'
        url = 'http://webdav.l.postgrespro.ru/DIST/resources/windows/' + \
            exename
        if not os.path.exists(WIN_INST_DIR):
            os.mkdir(WIN_INST_DIR)
        perl_installer = urllib.URLopener()
        target_path = os.path.join(WIN_INST_DIR, exename)
        perl_installer.retrieve(url, target_path)

        cmd = target_path + " /quiet PERL_PATH=Yes PERL_EXT=Yes ADDLOCAL=PERL"
        command_executor(cmd, windows=True)
        refresh_env_win()

    def remove_package(self, pkg_name, purge=False):
        """
        :param pkg_name
        :return:
        """
        if self.__is_pm_yum():
            # todo fix this
            cmd = "yum remove -y%s %s" % \
                  (' --noautoremove' if self.os_version.startswith(
                       '8.') else '', pkg_name)
            command_executor(cmd, self.remote, self.host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        elif self.__is_pm_apt():
            cmd = "apt-get %s -y %s" % (
                    'purge' if purge and self.__is_os_debian_based() else
                    'remove',
                    pkg_name.replace('*', '.*'))
            command_executor(cmd, self.remote, self.host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        elif self.__is_pm_zypper():
            cmd = "rpm -qa %s" % pkg_name
            installed_pkgs = subprocess.check_output(cmd, shell=True).\
                splitlines()
            if (len(installed_pkgs)):
                pkg_name = ' '.join(installed_pkgs)
                cmd = "zypper remove -y %s" % pkg_name
                command_executor(cmd, self.remote, self.host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        elif self.__is_os_windows():
            raise Exception("Not implemented on Windows.")
        else:
            raise Exception("Unsupported system: %s." % self.os_name)

    def remove_full(self, remove_data=False, purge=False, do_not_remove=None):
        if self.__is_os_windows():
            # TODO: Don't stop the service manually
            if self.pg_isready():
                self.stop_service()
            # TODO: Wait for completion without sleep
            subprocess.check_call([
                os.path.join(self.get_pg_prefix(), 'Uninstall.exe'),
                '/S'])
            for i in range(100, 0, -1):
                if (not os.path.exists(os.path.join(
                        self.get_pg_prefix(), 'bin')) and
                    not os.path.exists(os.path.join(
                        self.get_pg_prefix(), 'share'))):
                    break
                if i == 1:
                    raise Exception("Uninstallation failed.")
                time.sleep(1)
        else:
            pkgs = self.all_packages_in_repo
            if do_not_remove:
                for pkg in pkgs[:]:
                    for template in do_not_remove:
                        if re.match(template, pkg):
                            pkgs.remove(pkg)
            self.remove_package(" ".join(pkgs), purge)
            self.delete_repo()
        if remove_data:
            self.remove_data()
            if self.__is_os_windows():
                time.sleep(3)  # Let uninstallation finish
                if os.path.exists(self.get_pg_prefix()):
                    shutil.rmtree(self.get_pg_prefix())
        self.client_installed = False
        self.server_installed = False
        self.client_path_needed = True
        self.server_path_needed = True

    def remove_data(self, check_existense=False):
        if check_existense and not os.path.exists(self.get_datadir()):
            return
        shutil.rmtree(self.get_datadir())
        if self.get_configdir() != self.get_datadir():
            shutil.rmtree(self.get_configdir())

    def __get_last_winstaller_file(self, url, arch):
        """Get last uploaded postgrespro installation file from our repo

        :param url: str:
        :return: str: last postgrespro exe file
        """
        soup = BeautifulSoup(urllib.urlopen(url))
        exe_arch = r'_[X]?64bit_' if arch == 'AMD64' else r'_32bit_'
        setup_files = []
        for link in soup.findAll('a'):
            href = link.get('href')
            if "Postgre" in href and re.search(exe_arch, href):
                setup_files.append(href)
        if not setup_files:
            raise Exception("No Postgres (%s) setup files found in %s." %
                            (exe_arch, url))
        return setup_files[-1]

    def __get_msi_files(self, url):
        """Get all msi files from our repo
        :param url: str:
        :return: array with file names
        """

        msi_files = []
        soup = BeautifulSoup(urllib.urlopen(url))
        for link in soup.findAll('a'):
            href = link.get('href')
            if re.search(r'\.msi$', href, re.I):
                # PGPRO-3184
                # (pg-probackup-std-10-2.1.5.msi,
                #  pg-probackup-std-10-2.1.5-standalone-en.msi, and
                #  pg-probackup-std-10-2.1.5-standalone-en.msi conflict)
                if re.search('pg-probackup-.*standalone', href):
                    continue
                msi_files.append(href)
        return msi_files

    def delete_repo(self):
        """ Delete repo file
        """
        if self.__is_pm_yum():
            cmd = "yum clean all"
            self.exec_cmd_retry(cmd)
        if self.repo_package:
            self.remove_package(self.repo_package)
            return
        if not self.repo_file:
            return
        cmd = 'rm -f "%s"' % self.repo_file
        command_executor(cmd, self.remote, self.host,
                         REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        if self.__is_pm_apt():
            cmd = "apt-get clean cache && apt-get update -y"
            self.exec_cmd_retry(cmd)

    def exec_psql(self, query, options=''):
        cmd = '%s"%spsql" %s %s %s -c "%s"' % \
            (
                self.pg_preexec,
                self.get_client_bin_path(),
                '' if not(self.srvhost) else '-h ' + self.srvhost,
                '' if not(self.port) else '-p ' + str(self.port),
                options, query
            )
        return subprocess.check_output(cmd, shell=True,
                                       cwd="/", env=self.env).strip()

    def exec_psql_select(self, query, options=''):
        return self.exec_psql(query, '%s -t -P format=unaligned' % options)

    def exec_psql_script(self, script, options=''):
        handle, script_path = \
            tempfile.mkstemp(suffix='.sql',
                             dir=('/tmp' if os.path.exists('/tmp') else None))
        with os.fdopen(handle, 'w') as script_file:
            script_file.write(script)
        os.chmod(script_path, 0644)
        self.exec_psql_file(script_path, options)
        os.unlink(script_path)

    def exec_psql_file(self, sql_file, options='', stdout=None):
        cmd = '%s"%spsql" %s %s %s -f "%s"' % \
            (
                self.pg_preexec,
                self.get_client_bin_path(),
                '' if not(self.srvhost) else '-h ' + self.srvhost,
                '' if not(self.port) else '-p ' + str(self.port),
                options, sql_file
            )
        subprocess.check_call(cmd, shell=True,
                              cwd="/", env=self.env, stdout=stdout)

    def get_server_version(self):
        return self.exec_psql_select("SELECT version()")

    def get_psql_version(self):
        """ Get client version
        """
        cmd = '"%spsql" --version' % self.get_client_bin_path()
        return subprocess.check_output(cmd, shell=True, env=self.env).strip()

    def get_initdb_props(self):
        """ Get properties returned by initdb
        """
        cmd = '%s"%sinitdb" -s -D .' % \
            (
                self.pg_preexec,
                self.get_server_bin_path()
            )
        props = {}
        for line in subprocess.check_output(cmd, shell=True,
                                            stderr=subprocess.STDOUT,
                                            cwd="/", env=self.env).split('\n'):
            if '=' in line:
                (name, val) = line.split('=', 1)
                props[name] = val.strip()
        return props

    def get_pg_setting(self, setting):
        return self.exec_psql_select(
            "SELECT setting FROM pg_settings WHERE name='%s'" % setting)

    def get_default_service_name(self):
        if self.__is_os_windows():
            if self.product == "postgrespro":
                if self.edition == "1c":
                    return 'postgresql-1c-' + \
                        self.version + \
                        ('' if self.os_arch == 'AMD64' else '-32bit')
                if self.edition == "sql":
                    return 'postgresql-' + \
                        self.version + \
                        ('' if self.os_arch == 'AMD64' else '-32bit')
                return 'postgrespro' + '-' + \
                    ('enterprise-' if self.edition == 'ent' else '') + \
                    ('X64' if self.os_arch == 'AMD64' else 'X86') + '-' + \
                    self.version
            else:
                raise Exception('Product %s is not supported.' % self.product)
        else:
            if self.product == "postgrespro":
                if self.version in ['9.5', '9.6']:
                    if self.__is_os_suse():
                        return 'postgresql'
                    elif self.__is_os_astra():
                        return 'postgresql'
                    elif self.__is_os_debian_based():
                        if os.path.isdir('/run/systemd/system'):
                            return 'postgresql@%s-main' % self.version
                        return 'postgresql'
                    elif (self.__is_os_altlinux() or
                          self.fullversion[:6] in ['9.6.0.', '9.6.1.']):
                        return 'postgresql-%s' % self.version
                    return '%s-%s%s' % (self.product,
                                        'enterprise-'
                                        if self.edition in
                                        ["ent", "ent-cert"] else
                                        '',
                                        self.version)
                return '%s-%s-%s' % (self.product,
                                     self.alter_edtn,
                                     self.version)
            elif self.product == "postgresql":
                if self.__is_os_altlinux():
                    return 'postgresql'
                if self.__is_os_debian_based():
                    if os.path.isdir('/run/systemd/system'):
                        return 'postgresql@%s-main' % self.version
                    return 'postgresql'
                return '%s-%s' % (self.product, self.version)
            else:
                raise Exception('Product %s is not supported.' % self.product)

    def get_default_pg_prefix(self):
        if not self.__is_os_windows():
            if self.product == 'postgrespro':
                if self.version in ['9.5', '9.6']:
                    if self.__is_os_debian_based():
                        return '/usr/lib/postgresql/%s' % (self.version)
                    if self.__is_os_suse():
                        return '/usr/lib/postgrespro%s%s' % (
                            '-enterprise'
                            if self.edition in ["ent", "ent-cert"] else
                            '',
                            self.version.replace('.', '')
                        )
                    if self.__is_os_altlinux():
                        return '/usr'
                    if self.fullversion[:6] in ['9.6.0.', '9.6.1.']:
                        return '/usr/pgsql-%s' % (self.version)
                    return '/usr/pgpro%s-%s' % (
                        'ee'
                        if self.edition in ["ent", "ent-cert"] else
                        '',
                        self.version)
                return '/opt/pgpro/%s-%s' % (self.alter_edtn,
                                             self.version)
            elif self.product == 'postgresql':
                if self.__is_os_altlinux():
                    return '/usr'
                if self.__is_os_debian_based():
                    return '/usr/lib/postgresql/%s' % (self.version)
                return '/usr/pgsql-%s' % (self.version)
        else:
            if self.product == 'postgrespro':
                return 'C:\\Program Files\\%s%s\\%s' % \
                    ('PostgreSQL' if self.edition == 'sql' else
                     'PostgreSQL 1C' if self.edition == '1c' else
                     'PostgresPro',
                     'Enterprise'
                     if self.edition in ["ent", "ent-cert"] else
                     '',
                     self.version)
            raise Exception('Product %s is not supported.' % self.product)

    def get_pg_prefix(self):
        return self.pg_prefix

    def get_default_bin_path(self):
        return os.path.join(self.get_pg_prefix(), 'bin')

    def get_bin_path(self):
        return os.path.join(self.get_pg_prefix(), 'bin')

    def get_server_bin_path(self):
        path = ''
        if self.server_path_needed:
            path = self.get_bin_path() + os.sep
        return path

    def get_client_bin_path(self):
        path = ''
        if self.client_path_needed:
            path = self.get_bin_path() + os.sep
        return path

    def get_default_datadir(self):
        if not self.__is_os_windows():
            if self.product == 'postgrespro':
                if self.version in ['9.5', '9.6']:
                    if self.__is_os_debian_based():
                        return '/var/lib/postgresql/%s/main' % (self.version)
                    if self.__is_os_suse():
                        return '/var/lib/pgsql/data'
                    if (self.__is_os_altlinux() or
                       self.fullversion[:6] in ['9.6.0.', '9.6.1.']):
                        return '/var/lib/pgsql/%s/data' % (self.version)
                    return '/var/lib/pgpro%s/%s/data' % (
                        'ee'
                        if self.edition in ['ent', 'ent-cert'] else
                        '',
                        self.version
                        )
                return '/var/lib/pgpro/%s-%s/data' % (
                    self.alter_edtn,
                    self.version)
            elif self.product == 'postgresql':
                if self.__is_os_altlinux():
                    return '/var/lib/pgsql/data'
                if self.__is_os_debian_based():
                    return '/var/lib/postgresql/%s/main' % (self.version)
                return '/var/lib/pgsql/%s/data' % (self.version)
            raise Exception('Product %s is not supported.' % self.product)
        else:
            if self.product == 'postgrespro':
                return os.path.join(self.get_pg_prefix(), 'data')
            raise Exception('Product %s is not supported.' % self.product)

    def get_datadir(self):
        return self.datadir

    def get_default_configdir(self):
        if self.__is_os_debian_based():
            if self.version in ['9.5', '9.6'] or \
               self.product == 'postgresql':
                return '/etc/postgresql/%s/main' % (self.version)
        return self.get_default_datadir()

    def get_configdir(self):
        return self.configdir

    def get_port(self):
        if self.port:
            return self.port
        return 5432

    def initdb_start(self):
        if self.product == 'postgrespro' and self.version == '9.6':
            if self.__is_os_debian_based():
                return
            if self.__is_os_redhat_based():
                if subprocess.call("which systemctl", shell=True) == 0:
                    binpath = self.get_bin_path()
                    if self.fullversion[:6] in ['9.6.0.', '9.6.1.']:
                        cmd = '%s/postgresql96-setup initdb' % binpath
                    else:
                        cmd = '%s/pg-setup initdb' % binpath
                else:
                    cmd = 'service "%s" initdb' % self.service_name
                subprocess.check_call(cmd, shell=True)
                self.start_service()
            elif self.__is_os_altlinux():
                subprocess.check_call('/etc/init.d/postgresql-%s initdb' %
                                      self.version, shell=True)
                self.start_service()
            elif self.__is_os_suse():
                self.start_service()
            else:
                raise Exception('OS %s is not supported.' % self.os_name)
        elif self.product == 'postgresql':
            if self.__is_os_debian_based():
                return
            if self.__is_os_redhat_based() or self.__is_os_suse():
                if subprocess.call("which systemctl", shell=True) == 0:
                    binpath = self.get_bin_path()
                    cmd = '%s/postgresql%s-setup initdb' % \
                        (binpath,
                         self.version.replace('.', '') if
                         self.version.startswith('9.') else
                         '-' + self.version)
                else:
                    cmd = 'service "%s" initdb' % self.service_name
                subprocess.check_call(cmd, shell=True)
                self.start_service()
            elif self.__is_os_altlinux():
                subprocess.check_call('/etc/init.d/postgresql initdb',
                                      shell=True)
                self.start_service()
            else:
                raise Exception('OS %s is not supported.' % self.os_name)

    def init_cluster(self, force_remove, params=''):
        if (os.path.exists(self.get_datadir())):
            if force_remove:
                self.remove_data()
        os.makedirs(self.get_datadir())
        if not self.__is_os_windows():
            subprocess.check_call('chown -R postgres:postgres %s' %
                                  self.get_datadir(), shell=True)
        else:
            subprocess.check_call(
                'icacls "%s" /grant *S-1-5-32-545:(OI)(CI)F /T' %
                self.get_datadir(),
                shell=True)
            params += ' -U postgres '

        cmd = '%s"%sinitdb" %s -D "%s"' % \
              (
                  self.pg_preexec,
                  self.get_server_bin_path(),
                  params,
                  self.get_datadir()
              )
        subprocess.check_call(cmd, shell=True, cwd="/")
        self.configdir = self.get_datadir()

    def service_action(self, action='start', wait_for_completion=True):
        if self.__is_os_windows():
            if action == 'restart':
                cmd = 'net stop "{0}" & net start "{0}"'.format(
                    self.service_name)
            else:
                cmd = 'net %s "%s"' % (action, self.service_name)
        else:
            cmd = 'service "%s" %s' % (self.service_name, action)
        subprocess.check_call(cmd, shell=True)
        action_timeout = 120
        if wait_for_completion:
            for i in range(1, action_timeout):
                if action == 'stop':
                    if not self.pg_isready():
                        return True
                else:
                    if self.pg_isready():
                        return True
                time.sleep(1)
            raise Exception("Service action '%s' failed to complete"
                            " in %d seconds." % (action, action_timeout))
        return True

    def start_service(self):
        return self.service_action('start')

    def restart_service(self):
        return self.service_action('restart')

    def stop_service(self):
        return self.service_action('stop')

    def exec_client_bin(self, bin, options=''):
        cmd = '%s"%s%s" %s' % \
            (
                self.pg_preexec,
                self.get_client_bin_path(),
                bin,
                options
            )
        return subprocess.check_output(cmd, shell=True,
                                       cwd="/", env=self.env)

    def exec_server_bin(self, bin, options=''):
        cmd = '%s"%s%s" %s' % \
            (
                self.pg_preexec,
                self.get_server_bin_path(),
                bin,
                options
            )
        return subprocess.check_output(cmd, shell=True,
                                       cwd="/", env=self.env)

    def pg_isready(self):
        cmd = '%s"%spg_isready" %s %s' % \
            (
                self.pg_preexec,
                self.get_server_bin_path(),
                '' if not(self.srvhost) else '-h ' + self.srvhost,
                '' if not(self.port) else '-p ' + str(self.port)
            )
        return subprocess.call(cmd, shell=True, env=self.env) == 0

    def pg_control(self, action, data_dir, preaction=''):
        """ Manage Postgres instance
        :param action: start, restart, stop etc
        :param data_dir: data directory of the Postgres instance
        :return:
        """
        cmd = '%s%s"%spg_ctl" -w -D "%s" %s >"%s" 2>&1' % \
            (
                self.pg_preexec,
                preaction,
                self.get_server_bin_path(), data_dir,
                action, os.path.join(data_dir, 'pg_ctl.log')
            )
        # sys.stdout.encoding = 'cp866'?
        subprocess.check_call(cmd, shell=True, cwd=tempfile.gettempdir(),
                              env=self.env)

    def load_shared_libraries(self, libs=None, restart_service=True):
        if libs is None and self.product == 'postgrespro':
            pgid = '%s-%s' % (self.edition, self.version)
            if pgid in PRELOAD_LIBRARIES:
                preload_libs = PRELOAD_LIBRARIES[pgid]
                libs = ','.join(preload_libs)
        if libs:
            self.exec_psql(
                "ALTER SYSTEM SET shared_preload_libraries = %s" % libs)
            if restart_service:
                self.restart_service()

    def exec_cmd_retry(self, cmd, retry_cnt=10, stdout=False):
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

    def get_product_dir(self):
        return self.__get_product_dir()
