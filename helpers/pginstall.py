import logging
import os
import subprocess
import tempfile
import urllib
import re
import time
import shutil

from BeautifulSoup import BeautifulSoup

from helpers.utils import command_executor
from helpers.utils import get_distro
from helpers.utils import REMOTE_ROOT
from helpers.utils import REMOTE_ROOT_PASSWORD
from helpers.utils import write_file
from helpers.utils import refresh_env_win

PGPRO_ARCHIVE_STANDARD = "http://repo.postgrespro.ru/pgpro-archive/"
PGPRO_ARCHIVE_ENTERPRISE = "http://repoee.l.postgrespro.ru/archive/"
PGPRO_BRANCH_BASE = "http://localrepo.l.postgrespro.ru/branches/"
PGPRO_BASE = "http://repo.postgrespro.ru/"
PGPROALPHA_BASE = "http://localrepo.l.postgrespro.ru/dev/"
PGPROCERT_BASE = "http://localrepo.l.postgrespro.ru/cert/"
PSQL_BASE = "https://download.postgresql.org/pub"
WIN_INST_DIR = "C:\\Users\\test\\pg-tests\\pg_installer"
PACKAGES = ['server', 'contrib', 'libs', 'docs', 'docs-ru',
            'plperl', 'plpython', 'pltcl']
DEB_PACKAGES = ['plperl', 'plpython', 'plpython3', 'pltcl']
ALT_PACKAGES = ['server', 'contrib', 'devel', 'docs', 'docs-ru',
                'perl', 'python', 'tcl']
RPM_BASED = ['CentOS Linux', 'RHEL', 'CentOS',
             'Red Hat Enterprise Linux Server', 'Oracle Linux Server', 'SLES',
             'ROSA Enterprise Linux Server', 'ROSA SX \"COBALT\" ',
             'ROSA Enterprise Linux Cobalt', 'GosLinux',
             '\xd0\x9c\xd0\xa1\xd0\x92\xd0\xa1'
             '\xd1\x84\xd0\xb5\xd1\x80\xd0\xb0 ',
             'RED OS release MUROM (']
DEBIAN_BASED = ['debian', 'Ubuntu', 'Debian GNU/Linux', 'AstraLinuxSE',
                'Astra Linux SE', "\"Astra Linux SE\"", "\"AstraLinuxSE\""]
DEB_BASED = ['debian', 'Ubuntu', 'Debian GNU/Linux', 'AstraLinuxSE',
             'Astra Linux SE', "\"Astra Linux SE\"", "\"AstraLinuxSE\"",
             "ALT Linux ", "ALT "]
ASTRA_BASED = ['AstraLinuxSE', 'Astra Linux SE', "\"Astra Linux SE\"",
               "\"AstraLinuxSE\""]
ALT_BASED = ['ALT Linux ', 'ALT ']
ZYPPER_BASED = ['SUSE Linux Enterprise Server ']
WIN_BASED = ['Windows-2012ServerR2', 'Windows-10', 'Windows-8.1', 'Windows-7']

dist = {"Oracle Linux Server": 'oraclelinux',
        "CentOS Linux": 'centos',
        "CentOS": 'centos',
        "RHEL": 'rhel',
        "Red Hat Enterprise Linux Server": 'rhel',
        "debian": 'debian',
        "Debian GNU/Linux": 'debian',
        "Ubuntu": 'ubuntu',
        "ROSA Enterprise Linux Server": 'rosa-el',
        "ROSA SX \"COBALT\" ": 'rosa-sx',
        "SLES": 'sles',
        "ALT ": 'altlinux',
        "GosLinux": 'goslinux',
        "RED OS release MUROM (": 'redos'}


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
        self.remote = remote
        self.host = host
        self.dist_info = get_distro(remote, host)
        self.os_name = self.dist_info[0]
        self.os_version = self.dist_info[1]
        self.os_arch = self.dist_info[2]
        self.client_installed = False
        self.server_installed = False
        self.client_path_needed = False
        self.server_path_needed = False

        self.pg_prefix = self.get_default_pg_prefix()
        self.datadir = self.get_default_datadir()
        self.configdir = self.get_default_configdir()

        if edition in ['std', 'std-cert']:
            self.alter_edtn = 'std'
        elif edition in ['ent', 'ent-cert']:
            self.alter_edtn = 'ent'
        else:
            self.alter_edtn = edition

    def get_repo_base(self):
        if self.milestone == "alpha":
            return PGPROALPHA_BASE
        if self.milestone == "archive":
            if self.product == "postgrespro":
                if self.edition == "ent":
                    return PGPRO_ARCHIVE_ENTERPRISE
                else:
                    return PGPRO_ARCHIVE_STANDARD
            else:
                raise Exception("Archived versions are not supported for %s." %
                                self.product)
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
            elif self.edition == "1c":
                product_dir = "1c-%s" % product_version
            if self.milestone == "beta":
                product_dir += "-" + self.milestone
        return product_dir

    def get_base_package_name(self):
        if self.product == 'postgrespro':
            if self.version == '9.5' or self.version == '9.6':
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
        return '%s-%s' % (self.product, self.version.replace('.', '')) \
            if self.version else '%s' % (self.product)

    def get_server_package_name(self):
        base_package = self.get_base_package_name()
        if self.product == 'postgrespro':
            if self.version == '9.5' or self.version == '9.6':
                if self.__is_os_debian_based():
                    return base_package
            return base_package + '-server'
        return base_package

    def get_client_package_name(self):
        base_package = self.get_base_package_name()
        if self.product == 'postgrespro':
            if self.version == '9.5' or self.version == '9.6':
                if self.__is_os_debian_based():
                    return '%s-client-%s' % (self.product, self.version)
                return base_package
            return base_package + '-client'
        return base_package

    def get_dev_package_name(self):
        base_package = self.get_base_package_name()
        if self.product == 'postgrespro':
            if self.version == '9.5' or self.version == '9.6':
                if self.__is_os_debian_based():
                    return '%s-server-dev-%s' % (self.product, self.version)
            return base_package + (
                '-dev' if self.__is_os_debian_based() else '-devel')
        return base_package

    def get_all_packages_name(self):
        if self.product == 'postgrespro':
            if self.version == '9.5' or self.version == '9.6':
                if self.__is_os_debian_based():
                    return self.get_base_package_name() + '*' + \
                        ' %s-.*-%s' % (self.product,
                                       self.version.replace('.', '\\.')) + \
                        ' postgrespro-libecpg*'
        return self.get_base_package_name() + '*'

    def __is_os_redhat_based(self):
        return self.os_name in RPM_BASED

    def __is_os_debian_based(self):
        return self.os_name in DEBIAN_BASED

    def __is_os_altlinux(self):
        return self.os_name in ALT_BASED

    def __is_os_suse(self):
        return self.os_name in ZYPPER_BASED

    def __generate_repo_info(self, action="install"):
        """Generate information about repository: url to packages
            and path to gpg key

        :param action: action what we do install or upgrade
        :return:
        """

        distname = ""
        product_dir = ""
        gpg_key_url = ""
        if self.product == "postgresql":
            if self.os_name in RPM_BASED:
                gpg_key_url = "https://download.postgresql.org/" \
                    "pub/repos/yum/RPM-GPG-KEY-PGDG-%s" % \
                    self.version.replace('.', '')
            elif self.os_name in DEB_BASED:
                gpg_key_url = "https://www.postgresql.org/"\
                    "media/keys/ACCC4CF8.asc"
            product_dir = "/repos/yum/%s/redhat/rhel-$releasever-$basearch" % \
                self.version
            baseurl = PSQL_BASE + product_dir
            return baseurl, gpg_key_url
        elif self.product == "postgrespro":
            product_dir = self.__get_product_dir()
            gpg_key_url = "%s/%s/keys/GPG-KEY-POSTGRESPRO" % \
                          (self.get_repo_base(), product_dir)
            if self.os_name == "ALT Linux " and \
               self.os_version in ["7.0.4", "6.0.1"]:
                distname = "altlinux-spt"
            elif self.os_name == "ALT Linux " and self.os_version == "7.0.5":
                distname = "altlinux"
            elif self.os_name == "ALT " and self.os_version == "8":
                distname = "alt-sp"
            elif self.os_name == "ROSA Enterprise Linux Server":
                if self.os_version == "6.8":
                    distname = "rosa-chrome"
                else:
                    distname = "rosa-el"
            elif self.os_name == "ROSA SX \"COBALT\" " or \
                    self.os_name == "ROSA Enterprise Linux Cobalt":
                distname = "rosa-sx"
            elif self.os_name == "SUSE Linux Enterprise Server ":
                distname = "sles"
            elif self.os_name in ["AstraLinuxSE", "Astra Linux SE"]:
                if self.os_version == "1.4":
                    distname = "astra-smolensk/1.4"
                elif self.os_version == "1.5":
                    distname = "astra-smolensk/1.5"
                elif self.os_version == "1.5.28":
                    distname = "astra-smolensk/1.6"
            elif self.os_name == "\xd0\x9c\xd0\xa1\xd0\x92\xd0\xa1" \
                    "\xd1\x84\xd0\xb5\xd1\x80\xd0\xb0 ":
                distname = "msvsphere"
            elif self.os_name in WIN_BASED:
                distname = "Windows"
            else:
                distname = dist[self.os_name].lower()
            if self.edition in ['std-cert', 'ent-cert']:
                baseurl = "/".join([
                    PGPROCERT_BASE,
                    product_dir, distname])
            else:
                if action == "install":
                    if self.os_name in WIN_BASED:
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
                elif action == "upgrade":
                    if self.os_name in WIN_BASED:
                        baseurl = "{}{}/win/".format(self.get_repo_base(),
                                                     product_dir)
                    elif self.edition == "ent":
                        baseurl = os.path.join(
                            PGPRO_ARCHIVE_ENTERPRISE, self.version, distname)
                        gpg_key_url = PGPRO_ARCHIVE_ENTERPRISE + self.version
                    elif self.edition == "std":
                        baseurl = os.path.join(
                            PGPRO_ARCHIVE_STANDARD, self.version, distname)
                        gpg_key_url = PGPRO_ARCHIVE_STANDARD + self.version
                    gpg_key_url += '/keys/GPG-KEY-POSTGRESPRO'
            logging.debug("Installation repo path: %s", baseurl)
            logging.debug("GPG key url for installation %s", gpg_key_url)
            return baseurl, gpg_key_url

    def setup_repo(self):
        """ Setup yum or apt repo for Linux Based envs and
            download windows installer for Windows based

        :return: exit code 0 if all is ok and 1 if failed
        """
        repo_info = self.__generate_repo_info()
        baseurl = repo_info[0]
        gpg_key_url = repo_info[1]
        if self.os_name in RPM_BASED:
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
                        self.os_version == "7.08":
                    baseurl = os.path.join(baseurl,
                                           "7/os/$basearch/rpms")
                elif self.os_name == "RED OS release MUROM (" and \
                        self.os_version == "7.1":
                    baseurl = os.path.join(baseurl,
                                           "7/os/$basearch/rpms")
                else:
                    baseurl = os.path.join(baseurl,
                                           "$releasever/os/$basearch/rpms")

            repo = """
[%s-%s]
name=%s-%s
enabled=1
baseurl=%s
            """ % (self.product, self.version,
                   self.product, self.version,
                   baseurl)
            repofile = "/etc/yum.repos.d/%s-%s.repo" % (
                self.product, self.version)
            write_file(repofile, repo, self.remote, self.host)
            cmd = "rpm --import %s" % gpg_key_url
            command_executor(cmd, self.remote, self.host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            cmd = "yum --enablerepo=%s-%s clean metadata" % \
                (self.product, self.version)
            command_executor(cmd, self.remote, self.host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            return repofile
        elif self.os_name in DEB_BASED:
            cmd = "apt-get install -y lsb-release"
            command_executor(cmd, self.remote, self.host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            cmd = "lsb_release -cs"
            codename = ""
            if self.remote:
                codename = command_executor(
                    cmd, self.remote, self.host,
                    REMOTE_ROOT, REMOTE_ROOT_PASSWORD)[1].rstrip()
            else:
                codename = command_executor(cmd, self.remote, stdout=True)
            repofile = "/etc/apt/sources.list.d/%s-%s.list" % (self.product,
                                                               self.version)
            if self.product == "postgresql":
                repo = "deb http://apt.postgresql.org/pub/repos/apt/" \
                    " %s-pgdg main" % codename
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

            write_file(repofile, repo, self.remote, self.host)

            if "ALT " in self.os_name:
                cmd = "apt-get update -y"
                command_executor(cmd, self.remote, self.host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            else:
                cmd = "apt-get install -y wget ca-certificates"
                command_executor(cmd, self.remote, self.host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
                cmd = "wget -nv %s -O gpg.key" % gpg_key_url
                command_executor(cmd, self.remote, self.host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
                cmd = "apt-key add gpg.key"
                command_executor(cmd, self.remote, self.host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
                cmd = "apt-get update -y"
                command_executor(cmd, self.remote, self.host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
                return repofile
        elif self.os_name in ZYPPER_BASED:
            reponame = "%s-%s" % (self.product, self.version)
            repofile = '/etc/zypp/repos.d/%s.repo' % reponame
            cmd = "wget -nv %s -O gpg.key" % gpg_key_url
            command_executor(cmd, self.remote, self.host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            cmd = "rpm --import ./gpg.key"
            command_executor(cmd, self.remote, self.host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            if self.os_name == 'SUSE Linux Enterprise Server ' and \
               self.os_version == "12":
                baseurl = os.path.join(baseurl, "12.1")
            else:
                baseurl = os.path.join(baseurl, self.os_version)
            cmd = "zypper addrepo %s %s" % (baseurl, reponame)
            command_executor(cmd, self.remote, self.host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            cmd = "zypper refresh"
            command_executor(cmd, self.remote, self.host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            return repofile
        elif self.os_name in WIN_BASED:
            installer_name = self.__get_last_winstaller_file(
                baseurl, self.os_arch)
            windows_installer_url = baseurl + installer_name
            windows_installer = urllib.URLopener()
            if not os.path.exists(WIN_INST_DIR):
                os.mkdir(WIN_INST_DIR)
            print(baseurl + installer_name)
            windows_installer.retrieve(windows_installer_url,
                                       os.path.join(WIN_INST_DIR,
                                                    installer_name))
        else:
            raise Exception("Unsupported distro %s" % self.os_name)

    def download_source(self):
        if self.product == "postgresql":
            pass
        elif self.product == "postgrespro":
            product_dir = self.__get_product_dir()
            if self.edition in ['ent-cert', 'std-cert']:
                baseurl = PGPROCERT_BASE + \
                    product_dir.replace('/repo', '/sources')
            else:
                baseurl = "/".join([self.get_repo_base(), product_dir, 'src'])
        soup = BeautifulSoup(urllib.urlopen(baseurl))
        tar_href = None
        # TODO: Download exactly installed version
        # (using apt-get source or alike)
        for link in soup.findAll('a'):
            href = link.get('href')
            if re.search(r'^postgres', href, re.I) and \
               re.search(r'\.tar\b', href, re.I):
                if re.search(r'-common-', href):  # 9.5, 9.6 (Debian)
                    continue
                print("source:", baseurl + '/' + href, "target:", href)
                tar_href = href
        if not tar_href:
            raise Exception("Source tarball is not found at %s." % baseurl)
        sourcetar = urllib.URLopener()
        sourcetar.retrieve(baseurl + '/' + tar_href, tar_href)

    def install_package(self, pkg_name):
        """
        :param pkg_name
        :return:
        """
        if self.os_name in RPM_BASED:
            cmd = "yum install -y %s" % pkg_name
            command_executor(cmd, self.remote, self.host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        elif self.os_name in DEB_BASED:
            cmd = "apt-get install -y %s" % pkg_name
            command_executor(cmd, self.remote, self.host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        elif self.os_name in ZYPPER_BASED:
            cmd = "zypper install -y -l --force-resolution %s" % pkg_name
            command_executor(cmd, self.remote, self.host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        else:
            raise Exception("Unsupported system: %s" % self.os_name)

    def install_base(self):
        self.install_package(self.get_base_package_name())
        if self.product == "postgrespro":
            if self.version == '9.5' or self.version == '9.6':
                if self.__is_os_altlinux() or \
                   self.__is_os_redhat_based() or \
                   self.__is_os_suse():
                    self.install_package(self.get_server_package_name())
        self.client_installed = True
        self.server_installed = True
        self.client_path_needed = False
        self.server_path_needed = False
        if self.product == "postgrespro":
            if self.version == '9.5' or self.version == '9.6':
                if self.os_name in ASTRA_BASED or \
                   self.os_name in RPM_BASED or \
                   self.os_name in DEBIAN_BASED:
                    self.server_path_needed = True

    def install_full(self):
        self.install_package(self.get_all_packages_name())
        self.client_installed = True
        self.server_installed = True
        self.client_path_needed = False
        self.server_path_needed = False
        if self.product == "postgrespro":
            if self.version == '9.5' or self.version == '9.6':
                if self.os_name in ASTRA_BASED or \
                   self.os_name in RPM_BASED or \
                   self.os_name in DEBIAN_BASED:
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
        exename = None
        for filename in os.listdir(WIN_INST_DIR):
            if os.path.splitext(filename)[1] == '.exe' and \
               filename.upper().startswith('POSTGRES'):
                exename = filename
                break
        if not exename:
            raise Exception(
                "Executable installer not found in %s." %
                WIN_INST_DIR)
        ininame = os.path.join(WIN_INST_DIR, "pgpro.ini")
        with open(ininame, "w") as ini:
            ini.write("[options]\nenvvar=1\nneedoptimization=0\n" +
                      (("port=%s\n" % port) if port else ""))
        cmd = "%s /S /init=%s" % (os.path.join(WIN_INST_DIR, exename),
                                  ininame)
        command_executor(cmd, windows=True)
        refresh_env_win()

    def install_perl_win(self):
        # Workaround for PGPRO-2021
        if self.os_arch == 'AMD64':
            exename = 'ActivePerl-5.22.4.2205-MSWin32-x64-403863.exe'
        else:
            exename = 'ActivePerl-5.22.4.2205-MSWin32-x86-64int-403863.exe'
        url = 'http://webdav.l.postgrespro.ru/DIST/windows/resources/' + \
            exename
        if not os.path.exists(WIN_INST_DIR):
            os.mkdir(WIN_INST_DIR)
        perl_installer = urllib.URLopener()
        target_path = os.path.join(WIN_INST_DIR, exename)
        perl_installer.retrieve(url, target_path)

        cmd = target_path + " /quiet PERL_PATH=Yes PERL_EXT=Yes ADDLOCAL=PERL"
        command_executor(cmd, windows=True)
        refresh_env_win()

    def remove_package(self, pkg_name):
        """
        :param pkg_name
        :return:
        """
        if self.os_name in RPM_BASED:
            cmd = "yum remove -y %s" % pkg_name
            command_executor(cmd, self.remote, self.host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        elif self.os_name in DEB_BASED:
            cmd = "apt-get remove -y %s" % pkg_name
            command_executor(cmd, self.remote, self.host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        elif self.os_name in ZYPPER_BASED:
            cmd = "zypper remove -y %s" % pkg_name
            command_executor(cmd, self.remote, self.host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        elif self.os_name in WIN_BASED:
            raise Exception("Not implemented on Windows.")
        else:
            raise Exception("Unsupported system: %s." % self.os_name)

    def remove_full(self, remove_data=False):
        if self.os_name in WIN_BASED:
            # TODO: Don't stop the service manually
            self.stop_service()
            # TODO: Wait for completion without sleep
            subprocess.check_call([
                os.path.join(self.get_pg_prefix(), 'Uninstall.exe'),
                '/S'])
            time.sleep(10)
        else:
            self.remove_package(self.get_all_packages_name())
        if remove_data:
            shutil.rmtree(self.get_datadir())
            if self.get_configdir() != self.get_datadir():
                shutil.rmtree(self.get_configdir())
        self.client_installed = False
        self.server_installed = False

    def package_mgmt(self, action="install"):
        """
        :param action: install or upgrade
        :return:
        """
        major = self.version.split(".")[0]
        minor = self.version.split(".")[1]
        pkg_name = ""
        if self.os_name in RPM_BASED:
            if action == "install":
                if self.edition in ["ent", "ent-cert"]:
                    pkg_name = "%s-enterprise%s%s" % (
                        self.product, major, minor)
                else:
                    pkg_name = self.product + major + minor
                for pkg in PACKAGES:
                    cmd = "yum install -y %s-%s" % (pkg_name, pkg)
                    command_executor(cmd, self.remote, self.host,
                                     REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
                if self.version != '9.5':
                    cmd = "yum install -y %s-%s" % (pkg_name, "pg_probackup")
                    command_executor(cmd, self.remote, self.host,
                                     REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
                if self.edition in ['std-cert', 'ent-cert']:
                    cmd = "yum install -y pgbouncer"
                    command_executor(cmd, self.remote, self.host,
                                     REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
                if self.edition == 'ent':
                    cmd = "yum install -y pg_repack%s%s" % (major, minor)
                    command_executor(cmd, self.remote, self.host,
                                     REMOTE_ROOT, REMOTE_ROOT_PASSWORD)

            elif action == "upgrade":
                if self.edition in ["ent", "ent-cert"]:
                    pkg_name = "%s-enterprise%s%s" % (
                        self.product, major, minor)
                else:
                    pkg_name = self.product + major + minor

                for pkg in PACKAGES:
                    cmd = "yum install -y %s-%s" % (pkg_name, pkg)
                    command_executor(cmd, self.remote, self.host,
                                     REMOTE_ROOT, REMOTE_ROOT_PASSWORD)

        elif self.os_name in DEB_BASED and "ALT" not in self.os_name:
            if action == "install":
                cmd = "apt-get install -y %s-%s" % (
                    self.product, self.version)
                command_executor(cmd, self.remote, self.host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
                cmd = "apt-get install -y %s-doc-%s" % (
                    self.product, self.version)
                command_executor(cmd, self.remote, self.host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
                cmd = "apt-get install -y %s-doc-ru-%s" % (
                    self.product, self.version)
                command_executor(cmd, self.remote, self.host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
                cmd = "apt-get install -y libpq-dev"
                command_executor(cmd, self.remote, self.host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
                if self.version != '9.5':
                    cmd = "apt-get install -y %s-pg-probackup-%s" % (
                        self.product, self.version)
                    command_executor(cmd, self.remote, self.host,
                                     REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
                if self.edition in ['std-cert', 'ent-cert']:
                    cmd = "apt-get install -y pgbouncer"
                    command_executor(cmd, self.remote, self.host,
                                     REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
                for pkg in DEB_PACKAGES:
                    cmd = "apt-get install -y %s-%s-%s" % (
                        self.product, pkg, self.version)
                    command_executor(cmd, self.remote, self.host,
                                     REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
                if self.edition == 'ent':
                    cmd = "apt-get install -y pg-repack-%s" % self.version
                    command_executor(cmd, self.remote, self.host,
                                     REMOTE_ROOT, REMOTE_ROOT_PASSWORD)

            elif action == "upgrade":
                cmd = "apt-get install -y %s-%s" % (
                    self.product, self.version)
                command_executor(cmd, self.remote, self.host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
                cmd = "apt-get install -y libpq-dev"
                command_executor(cmd, self.remote, self.host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)

                for pkg in DEB_PACKAGES:
                    cmd = "apt-get install -y %s-%s-%s" % (
                        self.product, pkg, self.version)
                    command_executor(cmd, self.remote, self.host,
                                     REMOTE_ROOT, REMOTE_ROOT_PASSWORD)

        elif "ALT" in self.os_name:
            if action == "install":
                if self.edition in ["ent", "ent-cert"]:
                    pkg_name = "%s-enterprise%s.%s" % (
                        self.product, major, minor)
                elif self.edition == "std-cert":
                    pkg_name = "postgrespro%s.%s" % (
                        major, minor)
                elif self.edition == "std":
                    pkg_name = "postgrespro%s.%s" % (
                        major, minor)
                else:
                    pkg_name = self.product + major + minor

                for pkg in ALT_PACKAGES:
                    cmd = "apt-get install -y %s-%s" % (pkg_name, pkg)
                    command_executor(cmd, self.remote, self.host,
                                     REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
                if self.version != '9.5':
                    cmd = "apt-get install -y %s-%s" % (pkg_name,
                                                        "pg_probackup")
                    command_executor(cmd, self.remote, self.host,
                                     REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
                if self.edition in ['std-cert', 'ent-cert']:
                    cmd = "apt-get install -y pgbouncer"
                    command_executor(cmd, self.remote, self.host,
                                     REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
                if self.edition == 'ent':
                    cmd = "apt-get install -y pg_repack%s%s" % (major, minor)
                    command_executor(cmd, self.remote, self.host,
                                     REMOTE_ROOT, REMOTE_ROOT_PASSWORD)

            elif action == "upgrade":
                if self.edition in ["ent", "ent-cert"]:
                    pkg_name = "%s-enterprise%s.%s" % (
                        self.product, major, minor)
                elif self.edition == "std":
                    pkg_name = "postgrespro%s.%s" % (
                        major, minor)
                else:
                    pkg_name = self.product + major + minor

                for pkg in ALT_PACKAGES:
                    cmd = "apt-get install -y %s-%s" % (pkg_name, pkg)
                    command_executor(cmd, self.remote, self.host,
                                     REMOTE_ROOT, REMOTE_ROOT_PASSWORD)

    def __get_last_winstaller_file(self, url, arch):
        """Get last uploaded postgrespro installation file from our repo

        :param url: str:
        :return: str: last postgrespro exe file
        """
        soup = BeautifulSoup(urllib.urlopen(url))
        exe_arch = '_64bit_' if arch == 'AMD64' else '_32bit_'
        setup_files = []
        for link in soup.findAll('a'):
            href = link.get('href')
            if "Postgre" in href and exe_arch in href:
                setup_files.append(href)
        if not setup_files:
            raise Exception("No Postgres (%s) setup files found in %s." %
                            (exe_arch, url))
        return setup_files[-1]

    def delete_repo(self):
        """ Delete repo file
        """
        if self.os_name in RPM_BASED:
            repofile = "/etc/yum.repos.d/%s-%s.repo" % (
                self.product, self.version)
            cmd = "rm -f %s" % repofile
            command_executor(cmd, self.remote, self.host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            cmd = "yum update -y && yum clean cache"
            command_executor(cmd, self.remote, self.host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        elif self.os_name in DEB_BASED:
            repofile = "/etc/apt/sources.list.d/%s-%s.list" % (self.product,
                                                               self.version)
            cmd = "rm -f %s" % repofile
            command_executor(cmd, self.remote, self.host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            cmd = "apt-get update -y && apt-get clean cache"
            command_executor(cmd, self.remote, self.host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        else:
            raise Exception("Unsupported distro %s." % self.os_name)

    def delete_packages(self):
        """ Delete postgrespro packages

        :return:
        """
        major = self.version.split(".")[0]
        minor = self.version.split(".")[1]
        pkg_name = ""
        if self.os_name in RPM_BASED:
            if self.edition == "ent":
                pkg_name = "%s-enterprise%s%s" % (self.product, major, minor)
            else:
                pkg_name = self.product + major + minor

            for pkg in PACKAGES:
                cmd = "yum remove -y %s-%s" % (pkg_name, pkg)
                command_executor(cmd, self.remote, self.host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            if self.version != '9.5':
                cmd = "yum remove -y %s-%s" % (pkg_name, "pg_probackup")
                command_executor(cmd, self.remote, self.host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            if self.edition in ['std-cert', 'ent-cert']:
                cmd = "yum remove -y pgbouncer"
                command_executor(cmd, self.remote, self.host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)

        elif self.os_name in DEB_BASED and "ALT" not in self.os_name:
            cmd = "apt-get remove -y %s-%s" % (
                self.product, self.version)
            command_executor(cmd, self.remote, self.host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            cmd = "apt-get remove -y %s-doc-%s" % (
                self.product, self.version)
            command_executor(cmd, self.remote, self.host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            cmd = "apt-get remove -y %s-doc-ru-%s" % (
                self.product, self.version)
            command_executor(cmd, self.remote, self.host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            cmd = "apt-get remove -y libpq-dev"
            command_executor(cmd, self.remote, self.host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            if self.version != '9.5':
                cmd = "apt-get remove -y %s-pg-probackup-%s" % (
                    self.product, self.version)
                command_executor(cmd, self.remote, self.host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            if self.edition in ['std-cert', 'ent-cert']:
                cmd = "apt-get remove -y pgbouncer"
                command_executor(cmd, self.remote, self.host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            for pkg in DEB_PACKAGES:
                cmd = "apt-get remove -y %s-%s-%s" % (
                    self.product, pkg, self.version)
                command_executor(cmd, self.remote, self.host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)

        elif "ALT" in self.os_name:
            if self.edition in ["ent", "ent-cert"]:
                pkg_name = "%s-enterprise%s.%s" % (self.product, major, minor)
            elif self.edition == 'std-cert':
                pkg_name = "postgrespro%s.%s" % (major, minor)
            elif self.edition == "std":
                pkg_name = "postgrespro%s.%s" % (major, minor)
            else:
                pkg_name = self.product + major + minor

            for pkg in ALT_PACKAGES:
                cmd = "apt-get remove -y %s-%s" % (pkg_name, pkg)
                command_executor(cmd, self.remote, self.host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            if self.version != '9.5':
                cmd = "apt-get remove -y %s-%s" % (pkg_name, "pg_probackup")
                command_executor(cmd, self.remote, self.host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            if self.edition in ['std-cert', 'ent-cert']:
                cmd = "apt-get remove -y pgbouncer"
                command_executor(cmd, self.remote, self.host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)

    def exec_psql(self, query, options=''):
        cmd = '%s%spsql %s -c "%s"' % \
            (
                ('' if self.os_name in WIN_BASED else 'sudo -u postgres '),
                self.get_client_bin_path(),
                options, query
            )
        return subprocess.check_output(cmd, shell=True, cwd="/").strip()

    def exec_psql_select(self, query):
        return self.exec_psql(query, '-t -P format=unaligned')

    def exec_psql_script(self, script, options=''):
        handle, script_path = \
            tempfile.mkstemp(suffix='.sql',
                             dir=('/tmp' if os.path.exists('/tmp') else None))
        with os.fdopen(handle, 'w') as script_file:
            script_file.write(script)
        os.chmod(script_path, 0644)

        cmd = '%s%spsql %s -f %s' % \
            (
                ('' if self.os_name in WIN_BASED else 'sudo -u postgres '),
                self.get_client_bin_path(),
                options, script_path
            )
        result = subprocess.check_output(cmd, shell=True, cwd="/").strip()
        os.unlink(script_path)
        return result

    def get_server_version(self):
        return self.exec_psql_select("SELECT version()")

    def get_psql_version(self):
        """ Get client version
        """
        cmd = '%spsql --version' % self.get_client_bin_path()
        return subprocess.check_output(cmd, shell=True).strip()

    def get_initdb_props(self):
        """ Get properties returned by initdb
        """
        cmd = '%s%sinitdb -s -D .' % \
            (
                ('' if self.os_name in WIN_BASED else 'sudo -u postgres '),
                self.get_server_bin_path()
            )
        props = {}
        for line in subprocess.check_output(cmd, shell=True,
                                            stderr=subprocess.STDOUT,
                                            cwd="/").split('\n'):
            if '=' in line:
                (name, val) = line.split('=', 1)
                props[name] = val.strip()
        return props

    def get_pg_setting(self, setting):
        return self.exec_psql_select(
            "SELECT setting FROM pg_settings WHERE name='%s'" % setting)

    def get_default_service_name(self):
        if self.os_name in WIN_BASED:
            if self.product == "postgrespro":
                if self.edition == "1c":
                    return 'postgresql-1c-' + \
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
                if self.version == '9.5' or self.version == '9.6':
                    if self.os_name in ZYPPER_BASED:
                        return 'postgresql'
                    elif self.os_name in ASTRA_BASED:
                        return 'postgresql'
                    elif self.os_name in DEBIAN_BASED:
                        if os.path.isdir('/run/systemd/system'):
                            return 'postgresql@%s-main' % self.version
                        return 'postgresql'
                    elif (self.os_name in ALT_BASED or
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
            else:
                raise Exception('Product %s is not supported.' % self.product)

    def get_default_pg_prefix(self):
        if self.os_name not in WIN_BASED:
            if self.product == 'postgrespro':
                if self.version == '9.5' or self.version == '9.6':
                    if self.os_name in DEBIAN_BASED:
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
        else:
            if self.product == 'postgrespro':
                return 'C:\\Program Files\\PostgresPro%s\\%s' % \
                    ('Enterprise'
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
        if self.os_name not in WIN_BASED:
            if self.product == 'postgrespro':
                if self.version == '9.5' or self.version == '9.6':
                    if self.os_name in DEBIAN_BASED:
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
            raise Exception('Product %s is not supported.' % self.product)
        else:
            if self.product == 'postgrespro':
                return os.path.join(self.get_pg_prefix(), 'data')
            raise Exception('Product %s is not supported.' % self.product)

    def get_datadir(self):
        return self.datadir

    def get_default_configdir(self):
        if self.os_name in DEBIAN_BASED:
            if self.version in ['9.5', '9.6'] or \
               self.product == 'postgresql':
                return '/etc/postgresql/%s/main' % (self.version)
        return self.get_default_datadir()

    def get_configdir(self):
        return self.configdir

    def initdb_start(self):
        if self.product == 'postgrespro' and self.version == '9.6':
            if self.os_name in DEBIAN_BASED:
                return
            if self.os_name in RPM_BASED:
                service_name = self.get_default_service_name()
                if subprocess.call("which systemctl", shell=True) == 0:
                    binpath = self.get_bin_path()
                    if self.fullversion[:6] in ['9.6.0.', '9.6.1.']:
                        cmd = '%s/postgresql96-setup initdb' % binpath
                    else:
                        cmd = '%s/pg-setup initdb' % binpath
                else:
                    cmd = 'service "%s" initdb' % service_name
                subprocess.check_call(cmd, shell=True)
                self.start_service()
            elif self.os_name in ALT_BASED:
                subprocess.check_call('/etc/init.d/postgresql-%s initdb' %
                                      self.version, shell=True)
                service_name = self.get_default_service_name()
                self.start_service()
            elif self.os_name in ZYPPER_BASED:
                self.start_service()
            else:
                raise Exception('OS %s is not supported.' % self.os_name)

    def service_action(self, action='start', service_name=None):
        if not service_name:
            service_name = self.get_default_service_name()
        if self.os_name in WIN_BASED:
            if action == 'restart':
                cmd = 'net stop "{0}" & net start "{0}"'.format(service_name)
            else:
                cmd = 'net %s "%s"' % (action, service_name)
        else:
            cmd = 'service "%s" %s' % (service_name, action)
        subprocess.check_call(cmd, shell=True)

    def start_service(self, service_name=None):
        return self.service_action('start', service_name)

    def restart_service(self, service_name=None):
        return self.service_action('restart', service_name)

    def stop_service(self, service_name=None):
        return self.service_action('stop', service_name)

    def pg_isready(self):
        cmd = '%s%spg_isready' % \
            (
                ('' if self.os_name in WIN_BASED else 'sudo -u postgres '),
                self.get_server_bin_path()
            )
        return subprocess.call(cmd) == 0

    def pg_control(self, action, data_dir, preaction=''):
        """ Manage Postgres instance
        :param action: start, restart, stop etc
        :param data_dir: data directory of the Postgres instance
        :return:
        """
        cmd = '%s%s"%spg_ctl" -w -D "%s" %s >pg_ctl.out 2>&1' % \
            (
                ('' if self.os_name in WIN_BASED else 'sudo -u postgres '),
                preaction,
                self.get_server_bin_path(), data_dir, action
            )
        # sys.stdout.encoding = 'cp866'?
        subprocess.check_call(cmd, shell=True, cwd=tempfile.gettempdir())
