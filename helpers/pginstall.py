import logging
import os
import sys
import subprocess
import tempfile
import urllib
import re

from BeautifulSoup import BeautifulSoup

from helpers.utils import exec_command
from helpers.utils import command_executor
from helpers.utils import get_distro
from helpers.utils import REMOTE_ROOT
from helpers.utils import REMOTE_ROOT_PASSWORD
from helpers.utils import write_file
from helpers.utils import refresh_env_win

PGPRO_ARCHIVE_STANDARD = "http://repo.postgrespro.ru/pgpro-archive/"
PGPRO_ARCHIVE_ENTERPRISE = "http://repoee.l.postgrespro.ru/archive/"
PGPRO_BRANCH_HOST = "http://localrepo.l.postgrespro.ru/branches/"
PGPRO_HOST = "http://repo.postgrespro.ru/"
PSQL_HOST = "https://download.postgresql.org/pub"
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
             '\xd1\x84\xd0\xb5\xd1\x80\xd0\xb0 ']
DEBIAN_BASED = ['debian', 'Ubuntu', 'Debian GNU/Linux', 'AstraLinuxSE',
                'Astra Linux SE', "\"Astra Linux SE\"", "\"AstraLinuxSE\""]
DEB_BASED = ['debian', 'Ubuntu', 'Debian GNU/Linux', 'AstraLinuxSE',
             'Astra Linux SE', "\"Astra Linux SE\"", "\"AstraLinuxSE\"",
             "ALT Linux ", "ALT "]
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
        "GosLinux": 'goslinux'}


def get_os_type(ip):
    cmd = 'cat /etc/*-release'
    retcode, stdout, stderr = exec_command(
        cmd, ip, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
    if retcode == 0:
        return dict(
            v.split("=") for v in stdout.replace(
                '\t', ' ').strip().split('\n') if v.strip() and "=" in v)
    else:
        return None


def alt_edtn(edition):
    if edition == 'standard':
        return 'std'
    elif edition == 'ee':
        return 'ent'
    return edition


def get_product_dir(**kwargs):
    product_dir = ""
    if kwargs['name'] == "postgrespro":
        if kwargs['edition'] == "ee":
            product_dir = "pgproee-%s" % kwargs['version']
        elif kwargs['edition'] == "standard":
            product_dir = "pgpro-%s" % kwargs['version']
        elif kwargs['edition'] == "cert-standard":
            product_dir = "pgpro-standard-9.6.3.1-cert/repo"
        elif kwargs['edition'] == "cert-enterprise":
            product_dir = "pgpro-enterprise-9.6.5.1-cert/repo"
        elif kwargs['edition'] == "1c":
            product_dir = "1c-%s" % kwargs['version']
        if kwargs['milestone']:
            product_dir += "-" + kwargs['milestone']
    return product_dir


def get_base_package_name(name, edition, version):
    if name == 'postgrespro':
        if version == '9.5' or version == '9.6':
            if is_os_redhat_based():
                return '%s%s' % (name, version.replace('.', ''))
            return '%s-%s' % (name, version)
        return '%s-%s-%s' % (name, alt_edtn(edition), version)
    return '%s-%s' % (name, version.replace('.', '')) if version \
        else '%s' % (name)


def get_server_package_name(name, edition, version):
    base_package = get_base_package_name(name, edition, version)
    if name == 'postgrespro':
        if version == '9.5' or version == '9.6':
            if is_os_debian_based():
                return base_package
    return base_package


def get_dev_package_name(name, edition, version):
    base_package = get_base_package_name(name, edition, version)
    if name == 'postgrespro':
        if version == '9.5' or version == '9.6':
            if is_os_debian_based():
                return '%s-server-dev-%s' % (name, version)
        else:
            return base_package + (
                '-dev' if is_os_debian_based() else '-devel')
    return base_package


def get_all_packages_name(name, edition, version):
    return get_base_package_name(name, edition, version) + '*'


def is_os_redhat_based(remote=False, host=None):
    dist_info = get_distro(remote, host)
    return dist_info[0] in RPM_BASED


def is_os_debian_based(remote=False, host=None):
    dist_info = get_distro(remote, host)
    return dist_info[0] in DEBIAN_BASED


def generate_repo_info(distro, osversion, action="install", **kwargs):
    """Generate information about repository: url to packages
        and path to gpg key

    :param distro:
    :param osversion:
    :param action: action what we do install or upgrade
    :param kwargs:
    :return:
    """

    distname = ""
    product_dir = ""
    gpg_key_url = ""
    if kwargs['name'] == "postgresql":
        if distro in RPM_BASED:
            gpg_key_url = "https://download.postgresql.org/" \
                "pub/repos/yum/RPM-GPG-KEY-PGDG-%s" % \
                kwargs['version'].replace('.', '')
        elif distro in DEB_BASED or distro == "ALT Linux ":
            gpg_key_url = "https://www.postgresql.org/media/keys/ACCC4CF8.asc"
        product_dir = "/repos/yum/%s/redhat/rhel-$releasever-$basearch" % \
            kwargs['version']
        baseurl = PSQL_HOST + product_dir
        return baseurl, gpg_key_url
    elif kwargs['name'] == "postgrespro":
        product_dir = get_product_dir(**kwargs)
        if kwargs['edition'] == "1c":
            gpg_key_dir = "1c-" + kwargs['version']
        else:
            gpg_key_dir = "pgpro-" + kwargs['version']
        if kwargs['milestone']:
            gpg_key_dir += "-" + kwargs['milestone']
        gpg_key_url = "https://repo.postgrespro.ru/%s/" \
            "keys/GPG-KEY-POSTGRESPRO" % gpg_key_dir
        if distro == "ALT Linux " and osversion in ["7.0.4", "6.0.1"]:
            distname = "altlinux-spt"
        elif distro == "ALT Linux " and osversion == "7.0.5":
            distname = "altlinux"
        elif distro == "ROSA Enterprise Linux Server" and osversion != "6.8":
            distname = "rosa-el"
        elif distro == "ROSA Enterprise Linux Server" and osversion == "6.8":
            distname = "rosa-chrome"
        elif distro == "ROSA SX \"COBALT\" " or \
                distro == "ROSA Enterprise Linux Cobalt":
            distname = "rosa-sx"
        elif distro == "SUSE Linux Enterprise Server ":
            distname = "sles"
        elif distro == "AstraLinuxSE" or distro == "Astra Linux SE":
            if osversion == "1.4":
                distname = "astra-smolensk/1.4"
            elif osversion == "1.5":
                distname = "astra-smolensk/1.5"
        elif distro == "\xd0\x9c\xd0\xa1\xd0\x92\xd0\xa1" \
                "\xd1\x84\xd0\xb5\xd1\x80\xd0\xb0 ":
            distname = "msvsphere"
        elif distro in WIN_BASED:
            distname = "Windows"
        else:
            distname = dist[distro].lower()
        if kwargs['edition'] in ['cert-standard', 'cert-enterprise']:
            baseurl = os.path.join("http://localrepo.l.postgrespro.ru",
                                   product_dir, distname)
        else:
            if action == "install":
                if distro in WIN_BASED:
                    baseurl = "{}{}/win/".format(PGPRO_HOST, product_dir)
                elif kwargs['branch'] is not None:
                    baseurl = os.path.join(
                        PGPRO_BRANCH_HOST, kwargs['branch'],
                        product_dir, distname)
                else:
                    baseurl = os.path.join(PGPRO_HOST, product_dir, distname)
            elif action == "upgrade":
                if distro in WIN_BASED:
                    baseurl = "{}{}/win/".format(PGPRO_HOST, product_dir)
                elif kwargs['edition'] == "ee":
                    baseurl = os.path.join(
                        PGPRO_ARCHIVE_ENTERPRISE, kwargs['version'], distname)
                    gpg_key_url = PGPRO_ARCHIVE_ENTERPRISE + kwargs['version']
                elif kwargs['edition'] == "standard":
                    baseurl = os.path.join(
                        PGPRO_ARCHIVE_STANDARD, kwargs['version'], distname)
                    gpg_key_url = PGPRO_ARCHIVE_STANDARD + kwargs['version']
                gpg_key_url += '/keys/GPG-KEY-POSTGRESPRO'
        logging.debug("Installation repo path: %s" % baseurl)
        logging.debug("GPG key url for installation: %s" % gpg_key_url)
        return baseurl, gpg_key_url


def setup_repo(remote=False, host=None, **kwargs):
    """ Setup yum or apt repo for Linux Based envs and
         download windows installer for Windows based

    :param remote: bool: remote or local installation
    :param host:  str: ip address
    :param kwargs: list of args about what we installing
    :return: exit code 0 if all is ok and 1 if failed
    """
    dist_info = get_distro(remote, host)
    repo_info = generate_repo_info(dist_info[0], dist_info[1],
                                   version=kwargs['version'],
                                   name=kwargs['name'],
                                   edition=kwargs['edition'],
                                   milestone=kwargs['milestone'],
                                   branch=kwargs['branch'])
    baseurl = repo_info[0]
    gpg_key_url = repo_info[1]
    if dist_info[0] in RPM_BASED:
        # Example:
        # http://repo.postgrespro.ru/pgproee-9.6-beta/
        #  centos/$releasever/os/$basearch/rpms
        if kwargs['name'] == "postgrespro":
            if dist_info[0] == "ROSA Enterprise Linux Server" and \
               dist_info[1] == "6.8":
                baseurl = os.path.join(baseurl, "6.8Server/os/$basearch/rpms")
            elif dist_info[0] == "ROSA Enterprise Linux Cobalt" and \
                    dist_info[1] == "7.3":
                baseurl = os.path.join(baseurl, "7Server/os/$basearch/rpms")
            elif dist_info[0] == "\xd0\x9c\xd0\xa1\xd0\x92\xd0\xa1" \
                                 "\xd1\x84\xd0\xb5\xd1\x80\xd0\xb0 ":
                baseurl = os.path.join(baseurl,
                                       "6.3Server/os/$basearch/rpms")
            else:
                baseurl = os.path.join(baseurl,
                                       "$releasever/os/$basearch/rpms")

        repo = """
[%s-%s]
name=%s-%s
baseurl=%s
enabled=1
        """ % (kwargs['name'],
               kwargs['version'],
               kwargs['name'],
               kwargs['version'],
               baseurl)
        repofile = "/etc/yum.repos.d/%s-%s.repo" % (
            kwargs['name'], kwargs['version'])
        write_file(repofile, repo, remote, host)
        cmd = "rpm --import %s" % gpg_key_url
        command_executor(cmd, remote, host,
                         REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        return repofile
    elif dist_info[0] in DEB_BASED or "ALT" in dist_info[0]:
        cmd = "apt-get install -y lsb-release"
        command_executor(cmd, remote, host,
                         REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        cmd = "lsb_release -cs"
        codename = ""
        if remote:
            codename = command_executor(
                cmd, remote, host,
                REMOTE_ROOT, REMOTE_ROOT_PASSWORD)[1].rstrip()
        else:
            codename = command_executor(cmd, remote, stdout=True)
        repofile = "/etc/apt/sources.list.d/%s-%s.list" % (kwargs['name'],
                                                           kwargs['version'])
        if kwargs['name'] == "postgresql":
            repo = "deb http://apt.postgresql.org/pub/repos/apt/" \
                   " %s-pgdg main" % codename
        elif kwargs['name'] == "postgrespro":
            repo = "deb %s %s main" % (baseurl, codename)
            if dist_info[0] == "ALT Linux " and \
               dist_info[1] in ["7.0.4", "7.0.5"]:
                repo = "rpm %s/7 x86_64 pgpro\n rpm %s/7 noarch pgpro\n" % \
                    (baseurl, baseurl)
            elif dist_info[0] == "ALT Linux " and dist_info[1] == "6.0.1":
                repo = "rpm %s/6 x86_64 pgpro\n rpm %s/6 noarch pgpro\n" % \
                    (baseurl, baseurl)
            elif dist_info[0] == "ALT ":
                repo = "rpm %s/8 x86_64 pgpro\n rpm %s/8 noarch pgpro\n" % \
                    (baseurl, baseurl)

        write_file(repofile, repo, remote, host)

        if "ALT " in dist_info[0]:
            cmd = "apt-get update -y"
            command_executor(cmd, remote, host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        else:
            cmd = "apt-get install -y wget ca-certificates"
            command_executor(cmd, remote, host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            cmd = "wget -nv %s -O gpg.key" % gpg_key_url
            command_executor(cmd, remote, host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            cmd = "apt-key add gpg.key"
            command_executor(cmd, remote, host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            cmd = "apt-get update -y"
            command_executor(cmd, remote, host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            return repofile
    elif dist_info[0] in ZYPPER_BASED:
        reponame = "%s-%s" % (kwargs['name'], kwargs['version'])
        repofile = '/etc/zypp/repos.d/%s.repo' % reponame
        cmd = "wget -nv %s -O gpg.key" % gpg_key_url
        command_executor(cmd, remote, host,
                         REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        cmd = "rpm --import ./gpg.key"
        command_executor(cmd, remote, host,
                         REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        if dist_info[0] == 'SUSE Linux Enterprise Server ' and \
           dist_info[1] == "12":
            baseurl = os.path.join(baseurl, "12.1")
        else:
            baseurl = os.path.join(baseurl, dist_info[1])
        cmd = "zypper addrepo %s %s" % (baseurl, reponame)
        command_executor(cmd, remote, host,
                         REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        cmd = "zypper refresh"
        command_executor(cmd, remote, host,
                         REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        return repofile
    elif dist_info[0] in WIN_BASED:
        installer_name = get_last_windows_installer_file(
            baseurl, dist_info[2])
        windows_installer_url = baseurl + installer_name
        windows_installer = urllib.URLopener()
        if not os.path.exists(WIN_INST_DIR):
            os.mkdir(WIN_INST_DIR)
        print(baseurl + installer_name)
        windows_installer.retrieve(windows_installer_url,
                                   os.path.join(WIN_INST_DIR, installer_name))
    else:
        raise Exception("Unsupported distro %s" % dist_info[0])


def download_source(remote=False, host=None, **kwargs):
    if kwargs['name'] == "postgresql":
        pass
    elif kwargs['name'] == "postgrespro":
        product_dir = get_product_dir(**kwargs)
        baseurl = os.path.join(PGPRO_HOST, product_dir, 'src')
    f = urllib.urlopen(baseurl)
    soup = BeautifulSoup(f)
    tar_href = None
    # TODO: Download exactly installed version (using apt-get source or alike)
    for link in soup.findAll('a'):
        href = link.get('href')
        if re.search(r'^postgres', href, re.I) and \
           re.search(r'\.tar\b', href, re.I):
            if re.search(r'-common-', href):  # 9.5, 9.6 (Debian)
                continue
            print("source:", os.path.join(baseurl, href), "target:", href)
            tar_href = href
    if not tar_href:
        raise Exception("Source tarball is not found at %s." % baseurl)
    sourcetar = urllib.URLopener()
    sourcetar.retrieve(os.path.join(baseurl, tar_href), tar_href)


def install_package(pkg_name, remote=False, host=None):
    """
    :param pkg_name
    :param remote:
    :param host:
    :return:
    """
    dist_info = get_distro(remote, host)
    if dist_info[0] in RPM_BASED:
        cmd = "yum install -y %s" % pkg_name
        command_executor(cmd, remote, host,
                         REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
    elif dist_info[0] in DEB_BASED:
        cmd = "apt-get install -y %s" % pkg_name
        command_executor(cmd, remote, host,
                         REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
    elif dist_info[0] in ZYPPER_BASED:
        cmd = "zypper install -y -l --force-resolution %s" % pkg_name
        command_executor(cmd, remote, host,
                         REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
    else:
        raise Exception("Unsupported system: %s" % dist_info[0])


def install_postgres_win(remote=False, host=None):
    exename = None
    for f in os.listdir(WIN_INST_DIR):
        if os.path.splitext(f)[1] == '.exe' and \
           f.upper().startswith('POSTGRES'):
            exename = f
            break
    if not exename:
        raise Exception(
            "Executable installer not found in %s." %
            WIN_INST_DIR)
    ininame = os.path.join(WIN_INST_DIR, "pgpro.ini")
    with open(ininame, "w") as ini:
        ini.write("[options]\nenvvar=1\n")
    cmd = "%s /S /init=%s" % (os.path.join(WIN_INST_DIR, exename),
                              ininame)
    command_executor(cmd, windows=True)
    refresh_env_win()


def install_perl_win(arch=None):
    if not arch:
        dist_info = get_distro()
        arch = dist_info[2]
    if arch == 'AMD64':
        exename = 'ActivePerl-5.22.4.2205-MSWin32-x64-403863.exe'
    else:
        exename = 'ActivePerl-5.22.4.2205-MSWin32-x86-64int-403863.exe'
    url = 'http://downloads.activestate.com/ActivePerl/' \
          'releases/5.22.4.2205/' + exename
    if not os.path.exists(WIN_INST_DIR):
        os.mkdir(WIN_INST_DIR)
    perl_installer = urllib.URLopener()
    target_path = os.path.join(WIN_INST_DIR, exename)
    perl_installer.retrieve(url, target_path)

    cmd = "%s /quiet PERL_PATH=Yes PERL_EXT=Yes ADDLOCAL=PERL" % target_path
    command_executor(cmd, windows=True)
    refresh_env_win()


def remove_package(pkg_name, remote=False, host=None):
    """
    :param pkg_name
    :param remote:
    :param host:
    :return:
    """
    dist_info = get_distro(remote, host)
    if dist_info[0] in RPM_BASED:
        cmd = "yum remove -y %s" % pkg_name
        command_executor(cmd, remote, host,
                         REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
    elif dist_info[0] in DEB_BASED:
        cmd = "apt-get remove -y %s" % pkg_name
        command_executor(cmd, remote, host,
                         REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
    elif dist_info[0] in ZYPPER_BASED:
        cmd = "zypper remove -y %s" % pkg_name
        command_executor(cmd, remote, host,
                         REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
    elif dist_info[0] in WIN_BASED:
        # TODO: Implement uninstall in windows
        pass
    else:
        raise Exception("Unsupported system: %s." % dist_info[0])


def package_mgmt(remote=False, host=None, action="install", **kwargs):
    """

    :param remote:
    :param host:
    :param action: install or upgrade
    :param kwargs:
    :return:
    """
    dist_info = get_distro(remote, host)
    major = kwargs['version'].split(".")[0]
    minor = kwargs['version'].split(".")[1]
    pkg_name = ""
    if dist_info[0] in RPM_BASED:
        if action == "install":
            if kwargs['edition'] in ["ee", "cert-enterprise"]:
                pkg_name = "%s-enterprise%s%s" % (
                    kwargs['name'], major, minor)
            else:
                pkg_name = kwargs['name'] + major + minor
            for p in PACKAGES:
                cmd = "yum install -y %s-%s" % (pkg_name, p)
                command_executor(cmd, remote, host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            if kwargs['version'] != '9.5':
                cmd = "yum install -y %s-%s" % (pkg_name, "pg_probackup")
                command_executor(cmd, remote, host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            if kwargs['edition'] in ['cert-standard', 'cert-enterprise']:
                cmd = "yum install -y pgbouncer"
                command_executor(cmd, remote, host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            if kwargs['edition'] == 'ee':
                cmd = "yum install -y pg_repack%s%s" % (major, minor)
                command_executor(cmd, remote, host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)

        elif action == "upgrade":
            if kwargs['edition'] in ["ee", "cert-enterprise"]:
                pkg_name = "%s-enterprise%s%s" % (
                    kwargs['name'], major, minor)
            else:
                pkg_name = kwargs['name'] + major + minor

            for p in PACKAGES:
                cmd = "yum install -y %s-%s" % (pkg_name, p)
                command_executor(cmd, remote, host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)

    elif dist_info[0] in DEB_BASED and "ALT" not in dist_info[0]:
        if action == "install":
            cmd = "apt-get install -y %s-%s" % (
                kwargs['name'], kwargs['version'])
            command_executor(cmd, remote, host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            cmd = "apt-get install -y %s-doc-%s" % (
                kwargs['name'], kwargs['version'])
            command_executor(cmd, remote, host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            cmd = "apt-get install -y %s-doc-ru-%s" % (
                kwargs['name'], kwargs['version'])
            command_executor(cmd, remote, host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            cmd = "apt-get install -y libpq-dev"
            command_executor(cmd, remote, host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            if kwargs['version'] != '9.5':
                cmd = "apt-get install -y %s-pg-probackup-%s" % (
                    kwargs['name'], kwargs['version'])
                command_executor(cmd, remote, host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            if kwargs['edition'] in ['cert-standard', 'cert-enterprise']:
                cmd = "apt-get install -y pgbouncer"
                command_executor(cmd, remote, host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            for p in DEB_PACKAGES:
                cmd = "apt-get install -y %s-%s-%s" % (
                    kwargs['name'], p, kwargs['version'])
                command_executor(cmd, remote, host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            if kwargs['edition'] == 'ee':
                cmd = "apt-get install -y pg-repack-%s" % kwargs['version']
                command_executor(cmd, remote, host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)

        elif action == "upgrade":
            cmd = "apt-get install -y %s-%s" % (
                kwargs['name'], kwargs['version'])
            command_executor(cmd, remote, host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            cmd = "apt-get install -y libpq-dev"
            command_executor(cmd, remote, host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)

            for p in DEB_PACKAGES:
                cmd = "apt-get install -y %s-%s-%s" % (
                    kwargs['name'], p, kwargs['version'])
                command_executor(cmd, remote, host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)

    elif "ALT" in dist_info[0]:
        if action == "install":
            if kwargs['edition'] in ["ee", "cert-enterprise"]:
                pkg_name = "%s-enterprise%s.%s" % (
                    kwargs['name'], major, minor)
            elif kwargs['edition'] == "cert-standard":
                pkg_name = "postgrespro%s.%s" % (
                    major, minor)
            elif kwargs['edition'] == "standard":
                pkg_name = "postgrespro%s.%s" % (
                    major, minor)
            else:
                pkg_name = kwargs['name'] + major + minor

            for p in ALT_PACKAGES:
                cmd = "apt-get install -y %s-%s" % (pkg_name, p)
                command_executor(cmd, remote, host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            if kwargs['version'] != '9.5':
                cmd = "apt-get install -y %s-%s" % (pkg_name, "pg_probackup")
                command_executor(cmd, remote, host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            if kwargs['edition'] in ['cert-standard', 'cert-enterprise']:
                cmd = "apt-get install -y pgbouncer"
                command_executor(cmd, remote, host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            if kwargs['edition'] == 'ee':
                cmd = "apt-get install -y pg_repack%s%s" % (major, minor)
                command_executor(cmd, remote, host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)

        elif action == "upgrade":
            if kwargs['edition'] in ["ee", "cert-enterprise"]:
                pkg_name = "%s-enterprise%s.%s" % (
                    kwargs['name'], major, minor)
            elif kwargs['edition'] == "standard":
                pkg_name = "postgrespro%s.%s" % (
                    major, minor)
            else:
                pkg_name = kwargs['name'] + major + minor

            for p in ALT_PACKAGES:
                cmd = "apt-get install -y %s-%s" % (pkg_name, p)
                command_executor(cmd, remote, host,
                                 REMOTE_ROOT, REMOTE_ROOT_PASSWORD)


def get_last_windows_installer_file(url, arch):
    """Get last uploaded postgrespro installation file from postgrespro repo

    :param url: str:
    :return: str: last postgrespro exe file
    """
    f = urllib.urlopen(url)
    soup = BeautifulSoup(f)
    exe_arch = '_64bit_' if arch == 'AMD64' else '_32bit_'
    setup_files = []
    for link in soup.findAll('a'):
        href = link.get('href')
        if "Postgres" in href and exe_arch in href:
            setup_files.append(href)
    if not setup_files:
        raise Exception("No Postgres (%s) setup files found in %s." %
                        (exe_arch, url))
    return setup_files[-1]


def delete_repo(remote=False, host=None, **kwargs):
    """ Delete repo file
    """
    dist_info = get_distro(remote, host)
    if dist_info[0] in RPM_BASED:
        repofile = "/etc/yum.repos.d/%s-%s.repo" % (
            kwargs['name'], kwargs['version'])
        cmd = "rm -f %s" % repofile
        command_executor(cmd, remote, host,
                         REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        cmd = "yum update -y && yum clean cache"
        command_executor(cmd, remote, host,
                         REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
    elif dist_info[0] in DEB_BASED or "ALT" in dist_info[0]:
        repofile = "/etc/apt/sources.list.d/%s-%s.list" % (kwargs['name'],
                                                           kwargs['version'])
        cmd = "rm -f %s" % repofile
        command_executor(cmd, remote, host,
                         REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        cmd = "apt-get update -y && apt-get clean cache"
        command_executor(cmd, remote, host,
                         REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
    else:
        raise Exception("Unsupported distro %s." % dist_info[0])


def delete_packages(remote=False, host=None, **kwargs):
    """ Delete postgrespro packages

    :param remote:
    :param host:
    :return:
    """
    dist_info = get_distro(remote, host)
    major = kwargs['version'].split(".")[0]
    minor = kwargs['version'].split(".")[1]
    pkg_name = ""
    if dist_info[0] in RPM_BASED:
        if kwargs['edition'] == "ee":
            pkg_name = "%s-enterprise%s%s" % (kwargs['name'], major, minor)
        else:
            pkg_name = kwargs['name'] + major + minor

        for p in PACKAGES:
            cmd = "yum remove -y %s-%s" % (pkg_name, p)
            command_executor(cmd, remote, host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        if kwargs['version'] != '9.5':
            cmd = "yum remove -y %s-%s" % (pkg_name, "pg_probackup")
            command_executor(cmd, remote, host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        if kwargs['edition'] in ['cert-standard', 'cert-enterprise']:
            cmd = "yum remove -y pgbouncer"
            command_executor(cmd, remote, host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)

    elif dist_info[0] in DEB_BASED and "ALT" not in dist_info[0]:
        cmd = "apt-get remove -y %s-%s" % (
            kwargs['name'], kwargs['version'])
        command_executor(cmd, remote, host,
                         REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        cmd = "apt-get remove -y %s-doc-%s" % (
            kwargs['name'], kwargs['version'])
        command_executor(cmd, remote, host,
                         REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        cmd = "apt-get remove -y %s-doc-ru-%s" % (
            kwargs['name'], kwargs['version'])
        command_executor(cmd, remote, host,
                         REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        cmd = "apt-get remove -y libpq-dev"
        command_executor(cmd, remote, host,
                         REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        if kwargs['version'] != '9.5':
            cmd = "apt-get remove -y %s-pg-probackup-%s" % (
                kwargs['name'], kwargs['version'])
            command_executor(cmd, remote, host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        if kwargs['edition'] in ['cert-standard', 'cert-enterprise']:
            cmd = "apt-get remove -y pgbouncer"
            command_executor(cmd, remote, host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        for p in DEB_PACKAGES:
            cmd = "apt-get remove -y %s-%s-%s" % (
                kwargs['name'], p, kwargs['version'])
            command_executor(cmd, remote, host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)

    elif "ALT" in dist_info[0]:
        if kwargs['edition'] in ["ee", "cert-enterprise"]:
            pkg_name = "%s-enterprise%s.%s" % (kwargs['name'], major, minor)
        elif kwargs['edition'] == 'cert-standard':
            pkg_name = "postgrespro%s.%s" % (major, minor)
        elif kwargs['edition'] == "standard":
            pkg_name = "postgrespro%s.%s" % (major, minor)
        else:
            pkg_name = kwargs['name'] + major + minor

        for p in ALT_PACKAGES:
            cmd = "apt-get remove -y %s-%s" % (pkg_name, p)
            command_executor(cmd, remote, host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        if kwargs['version'] != '9.5':
            cmd = "apt-get remove -y %s-%s" % (pkg_name, "pg_probackup")
            command_executor(cmd, remote, host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        if kwargs['edition'] in ['cert-standard', 'cert-enterprise']:
            cmd = "apt-get remove -y pgbouncer"
            command_executor(cmd, remote, host,
                             REMOTE_ROOT, REMOTE_ROOT_PASSWORD)


def exec_psql(query, options='', binpath=None):
    dist_info = get_distro()
    cmd = '%s%spsql %s -c "%s"' % \
        (
            ('' if dist_info[0] in WIN_BASED else 'sudo -u postgres '),
            ('' if binpath is None else (binpath + os.sep)),
            options, query
        )
    return subprocess.check_output(cmd, shell=True, cwd="/").strip()


def get_server_version(binpath=None):
    return exec_psql("SELECT version()", '-t -P format=unaligned',
                     binpath)


def get_psql_version(binpath=None):
    """ Get client version
    """
    cmd = '%spsql --version' % \
        ('' if binpath is None else (binpath + os.sep))
    return subprocess.check_output(cmd, shell=True).strip()


def get_initdb_props(binpath=None, **kwargs):
    """ Get properties returned by initdb
    """

    dist_info = get_distro()
    if binpath is None:
        if kwargs['name'] == "postgrespro":
            if kwargs['version'] == '9.5' or kwargs['version'] == '9.6':
                if dist_info[0] in DEBIAN_BASED:
                    binpath = get_default_bin_path(**kwargs)

    cmd = '%s%sinitdb -s -D .' % \
        (
            ('' if dist_info[0] in WIN_BASED else 'sudo -u postgres '),
            ('' if binpath is None else (binpath + os.sep))
        )
    props = {}
    for line in subprocess.check_output(cmd, shell=True,
                                        stderr=subprocess.STDOUT,
                                        cwd="/").split('\n'):
        if '=' in line:
            (name, val) = line.split('=', 1)
            props[name] = val.strip()
    return props


def get_pg_setting(setting, binpath=None):
    return exec_psql("SELECT setting FROM pg_settings"
                     " WHERE name='%s'" % setting,
                     '-t -P format=unaligned',
                     binpath)


def get_default_service_name(**kwargs):
    dist_info = get_distro()
    if dist_info[0] in WIN_BASED:
        if kwargs['name'] == "postgrespro":
            return 'postgrespro' + '-' + \
                   ('enterprise-' if kwargs['edition'] == 'ee'
                    else '') + \
                   ('X64' if dist_info[2] == 'AMD64' else 'X86') + '-' + \
                   kwargs['version']
        else:
            raise Exception('Product %s is not supported.' % kwargs['name'])
    else:
        if kwargs['name'] == "postgrespro":
            if kwargs['version'] == '9.5' or kwargs['version'] == '9.6':
                if dist_info[0] in ZYPPER_BASED:
                    return 'postgresql'
                elif dist_info[0] in DEBIAN_BASED:
                    return 'postgresql@%s-main' % kwargs['version']
                return '%s-%s' % (kwargs['name'],
                                  kwargs['version'])
            return '%s-%s-%s' % (kwargs['name'],
                                 alt_edtn(kwargs['edition']),
                                 kwargs['version'])
        else:
            raise Exception('Product %s is not supported.' % kwargs['name'])


def get_default_bin_path(**kwargs):
    dist_info = get_distro()
    if dist_info[0] not in WIN_BASED:
        if kwargs['name'] == 'postgrespro':
            if kwargs['version'] == '9.5' or kwargs['version'] == '9.6':
                if dist_info[0] in DEBIAN_BASED:
                    return '/usr/lib/postgresql/%s/bin' % (kwargs['version'])
                return '/usr/pgpro-%s/bin' % (kwargs['version'])
            return '/opt/pgpro/%s-%s/bin' % (alt_edtn(kwargs['edition']),
                                             kwargs['version'])
    else:
        raise Exception('OS %s is not supported.' % dist_info[0])


def get_default_datadir(**kwargs):
    dist_info = get_distro()
    if dist_info[0] not in WIN_BASED:
        if kwargs['name'] == 'postgrespro':
            if kwargs['version'] == '9.5' or kwargs['version'] == '9.6':
                if dist_info[0] in DEBIAN_BASED:
                    return '/var/lib/postgresql/%s/main' % (kwargs['version'])
                return '/var/lib/pgpro/%s/data' % (kwargs['version'])
            return ' /var/lib/pgpro/%s-%s/data' % (alt_edtn(kwargs['edition']),
                                                   kwargs['version'])
        raise Exception('Product %s is not supported.' % kwargs['name'])
    else:
        raise Exception('OS %s is not supported.' % dist_info[0])


def initdb_start_9_6(**kwargs):
    dist_info = get_distro()
    if dist_info[0] in DEBIAN_BASED:
        return
    if dist_info[0] in RPM_BASED:
        service_name = get_default_service_name(**kwargs)
        if subprocess.call("which systemctl", shell=True) == 0:
            binpath = get_default_bin_path(**kwargs)
            cmd = '%spg-setup initdb' % binpath
        else:
            cmd = 'service "%s" initdb' % service_name
        subprocess.check_call(cmd, shell=True)
        start_service(**kwargs)
    elif dist_info[0] in ZYPPER_BASED:
        start_service(**kwargs)
    else:
        raise Exception('OS %s is not supported.' % dist_info[0])


def initdb_start(server_only_install=False, **kwargs):
    if kwargs['name'] == 'postgrespro' and kwargs['version'] == '9.6':
        initdb_start_9_6(**kwargs)


def start_service(service_name=None, **kwargs):
    if not service_name:
        service_name = get_default_service_name(**kwargs)
    dist_info = get_distro()
    if dist_info[0] in WIN_BASED:
        cmd = 'net start "{0}"'.format(service_name)
    else:
        cmd = 'service "%s" start' % service_name
    subprocess.check_call(cmd, shell=True)


def restart_service(service_name=None, **kwargs):
    if not service_name:
        service_name = get_default_service_name(**kwargs)
    dist_info = get_distro()
    if dist_info[0] in WIN_BASED:
        cmd = 'net stop "{0}" & net start "{0}"'.format(service_name)
    else:
        cmd = 'service "%s" restart' % service_name
    subprocess.check_call(cmd, shell=True)


def pg_isready(binpath=None):
    dist_info = get_distro()
    cmd = '%s%spg_isready' % \
        (
            ('' if dist_info[0] in WIN_BASED else 'sudo -u postgres '),
            ('' if binpath is None else (binpath + os.sep))
        )
    return (subprocess.call(cmd) == 0)


def pg_control(action, data_dir, binpath=None):
    """ Manage Postgres instance
    :param action: start, restart, stop etc
    :param data_dir: data directory of the Postgres instance
    :return:
    """
    dist_info = get_distro()
    cmd = '%s%spg_ctl -w -D "%s" %s >pg_ctl.out 2>&1' % \
        (
            ('' if dist_info[0] in WIN_BASED else 'sudo -u postgres '),
            ('' if binpath is None else (binpath + os.sep)),
            data_dir,
            action
        )
    # sys.stdout.encoding = 'cp866'?
    subprocess.check_call(cmd, shell=True, cwd=tempfile.gettempdir())
