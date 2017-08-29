import logging
import os
import shutil
import sys
import urllib

from BeautifulSoup import BeautifulSoup

from helpers.utils import exec_command
from helpers.utils import command_executor
from helpers.utils import get_distro
from helpers.utils import REMOTE_ROOT
from helpers.utils import REMOTE_ROOT_PASSWORD
from helpers.utils import write_file

PGPRO_BRANCH_HOST = "http://localrepo.l.postgrespro.ru/branches/"
PGPRO_HOST = "http://repo.postgrespro.ru/"
PSQL_HOST = "https://download.postgresql.org/pub"
PACKAGES = ['server', 'contrib', 'libs', 'docs', 'docs-ru', 'plperl', 'plpython', 'pltcl']
DEB_PACKAGES = ['plperl', 'plpython', 'plpython3', 'pltcl']
ALT_PACKAGES = ['server', 'contrib', 'devel', 'docs', 'docs-ru', 'perl', 'python', 'tcl']
RPM_BASED = ['CentOS Linux', 'RHEL', 'CentOS',
             'Red Hat Enterprise Linux Server', 'Oracle Linux Server', 'SLES',
             'ROSA Enterprise Linux Server', 'ROSA SX \"COBALT\" ', 'GosLinux',
             '\xd0\x9c\xd0\xa1\xd0\x92\xd0\xa1\xd1\x84\xd0\xb5\xd1\x80\xd0\xb0 ']
DEB_BASED = ['debian', 'Ubuntu', 'Debian GNU/Linux', 'AstraLinuxSE',
             'Astra Linux SE', "\"Astra Linux SE\"", "\"AstraLinuxSE\"",
             "ALT Linux ", "ALT "]
WIN_BASED = ['2012ServerR2']

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
    retcode, stdout, stderr = exec_command(cmd, ip, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
    if retcode == 0:
        return dict(
            v.split("=") for v in stdout.replace(
                '\t', ' ').strip().split('\n') if v.strip() and "=" in v)
    else:
        return None


def generate_repo_info(distro, osversion, **kwargs):
    """Generate information about repository: url to packages and path to gpg key

    :param distro:
    :param osversion:
    :param kwargs:
    :return:
    """
    major = kwargs['version'].split(".")[0]
    minor = kwargs['version'].split(".")[1]

    distname = ""
    product_dir = ""
    gpg_key_url = ""
    if kwargs['name'] == "postgresql":
        if distro in RPM_BASED:
            gpg_key_url = "https://download.postgresql.org/pub/repos/yum/RPM-GPG-KEY-PGDG-%s%s" % (
                major, minor)
        elif distro in DEB_BASED or distro == "ALT Linux ":
            gpg_key_url = "https://www.postgresql.org/media/keys/ACCC4CF8.asc"
        product_dir = "/repos/yum/%s/redhat/rhel-$releasever-$basearch" % kwargs['version']
        baseurl = PSQL_HOST + product_dir
        return baseurl, gpg_key_url
    elif kwargs['name'] == "postgrespro":
        if kwargs['edition'] == "ee":
            product_dir = "pgproee-%s" % kwargs['version']
        elif kwargs['edition'] == "standard":
            product_dir = "pgpro-%s" % kwargs['version']
        elif kwargs['edition'] == "cert-standard":
            product_dir = "pgpro-standard-9.6.3.1-cert/repo"
        elif kwargs['edition'] == "cert-enterprise":
            product_dir = "pgpro-enterprise-9.6.4.1-cert/repo"
        if kwargs['milestone']:
            product_dir = product_dir + "-" + kwargs['milestone']
        gpg_key_url = "https://repo.postgrespro.ru/pgpro-%s/keys/GPG-KEY-POSTGRESPRO" % kwargs['version']
        if distro == "ALT Linux " and osversion in ["7.0.4", "6.0.1"]:
            distname = "altlinux-spt"
        elif distro == "ALT Linux " and osversion == "7.0.5":
            distname = "altlinux"
        elif distro == "ROSA Enterprise Linux Server" and osversion != "6.8":
            distname = "rosa-el"
        elif distro == "ROSA Enterprise Linux Server" and osversion == "6.8":
            distname = "rosa-chrome"
        elif distro == "ROSA SX \"COBALT\" ":
            distname = "rosa-sx"
        elif distro == "AstraLinuxSE" or distro == "Astra Linux SE":
            if osversion == "1.4":
                distname = "astra-smolensk/1.4"
            elif osversion == "1.5":
                distname = "astra-smolensk/1.5"
        elif distro == "\xd0\x9c\xd0\xa1\xd0\x92\xd0\xa1\xd1\x84\xd0\xb5\xd1\x80\xd0\xb0 ":
            distname = "msvsphere"
        elif distro == "2012ServerR2":
            distname = "Windows"
        else:
            distname = dist[distro].lower()
        if kwargs['edition'] in ['cert-standard', 'cert-enterprise']:
            baseurl = os.path.join("http://localrepo.l.postgrespro.ru", product_dir, distname)
        else:
            if distro in WIN_BASED:
                baseurl = "{}{}/win/".format(PGPRO_HOST, product_dir)
            elif kwargs['branch'] is not None:
                baseurl = os.path.join(PGPRO_BRANCH_HOST, kwargs['branch'], product_dir, distname)
            else:
                baseurl = os.path.join(PGPRO_HOST, product_dir, distname)
        logging.debug("Installation repo path: %s" % baseurl)
        logging.debug("GPG key url for installation: %s" % gpg_key_url)
        return baseurl, gpg_key_url


def setup_repo(remote=False, host=None, **kwargs):
    """ Setup yum or apt repo for Linux Based envs and download windows installer for Windows based

    :param remote: bool: remote or local installation
    :param host:  str: ip address
    :param kwargs: list of args about what we installing
    :return: exit code 0 if all is ok and 1 if failed
    """
    dist_info = get_distro(remote, host)
    repo_info = generate_repo_info(dist_info[0], dist_info[1], version=kwargs['version'],
                                   name=kwargs['name'], edition=kwargs['edition'],
                                   milestone=kwargs['milestone'], branch=kwargs['branch'])
    baseurl = repo_info[0]
    gpg_key_url = repo_info[1]
    if dist_info[0] in RPM_BASED:
        # Example:
        # http://repo.postgrespro.ru/pgproee-9.6-beta/centos/$releasever/os/$basearch/rpms
        if kwargs['name'] == "postgrespro":
            if dist_info[0] == "ROSA Enterprise Linux Server" and dist_info[1] == "6.8":
                baseurl = os.path.join(baseurl, "6.8Server/os/$basearch/rpms")
            elif dist_info[0] == "\xd0\x9c\xd0\xa1\xd0\x92\xd0\xa1\xd1\x84\xd0\xb5\xd1\x80\xd0\xb0 ":
                baseurl = os.path.join(baseurl, "6.3Server/os/$basearch/rpms")
            else:
                baseurl = os.path.join(baseurl, "$releasever/os/$basearch/rpms")

        repo = """
[%s-%s]
name=%s-%s
baseurl=%s
enabled=1
        """ % (kwargs['name'], kwargs['version'], kwargs['name'], kwargs['version'], baseurl)
        repofile = "/etc/yum.repos.d/%s-%s.repo" % (kwargs['name'], kwargs['version'])
        write_file(repofile, repo, remote, host)
        cmd = "rpm --import %s" % gpg_key_url
        command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        return repofile
    elif dist_info[0] in DEB_BASED or "ALT" in dist_info[0]:
        cmd = "apt-get install -y lsb-release"
        command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        cmd = "lsb_release -cs"
        codename = ""
        if remote:
            codename = command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)[1].rstrip()
        else:
            codename = command_executor(cmd, remote, stdout=True)
        repofile = "/etc/apt/sources.list.d/%s-%s.list" % (kwargs['name'],
                                                           kwargs['version'])
        if kwargs['name'] == "postgresql":
            repo = "deb http://apt.postgresql.org/pub/repos/apt/ %s-pgdg main" % codename
        elif kwargs['name'] == "postgrespro":
            repo = "deb %s %s main" % (baseurl, codename)
            if dist_info[0] == "ALT Linux " and dist_info[1] in ["7.0.4", "7.0.5"]:
                repo = "rpm %s/7 x86_64 pgpro\n rpm %s/7 noarch pgpro\n" % (baseurl, baseurl)
            elif dist_info[0] == "ALT Linux " and dist_info[1] == "6.0.1":
                repo = "rpm %s/6 x86_64 pgpro\n rpm %s/6 noarch pgpro\n" % (baseurl, baseurl)
            elif dist_info[0] == "ALT ":
                repo = "rpm %s/8 x86_64 pgpro\n rpm %s/8 noarch pgpro\n" % (baseurl, baseurl)

        write_file(repofile, repo, remote, host)

        if "ALT " in dist_info[0]:
            cmd = "apt-get update -y"
            command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)

        else:
            cmd = "apt-get install -y wget ca-certificates"
            command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            cmd = "wget --quiet -O - %s | apt-key add -" % gpg_key_url
            command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            cmd = "apt-get update -y"
            command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        return repofile
    elif dist_info[0] in WIN_BASED:
        windows_installer = urllib.URLopener()
        installer_name = get_last_windows_installer_file(baseurl)
        windows_installer_url = baseurl + installer_name
        windows_installer.retrieve(windows_installer_url, "./" + installer_name)
        install_windows_console(installer_name)
    else:
        print "Unsupported distro %s" % dist_info[0]
        sys.exit(1)


def package_mgmt(remote=False, host=None, **kwargs):
    dist_info = get_distro(remote, host)
    major = kwargs['version'].split(".")[0]
    minor = kwargs['version'].split(".")[1]
    pkg_name = ""
    if dist_info[0] in RPM_BASED:
        if kwargs['edition'] in ["ee", "cert-enterprise"]:
            pkg_name = "%s-enterprise%s%s" % (kwargs['name'], major, minor)
        else:
            pkg_name = kwargs['name'] + major + minor

        for p in PACKAGES:
            cmd = "yum install -y %s-%s" % (pkg_name, p)
            command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        if kwargs['version'] != '9.5':
            cmd = "yum install -y %s-%s" % (pkg_name, "pg_probackup")
            command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        if kwargs['edition'] in ['cert-standard', 'cert-enterprise']:
            cmd = "yum install -y pgbouncer"
            command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        if kwargs['edition'] == 'ee':
            cmd = "yum install -y pg_repack%s%s" % (major, minor)
            command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)

    elif dist_info[0] in DEB_BASED and "ALT" not in dist_info[0]:
        cmd = "apt-get install -y %s-%s" % (kwargs['name'], kwargs['version'])
        command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        cmd = "apt-get install -y %s-doc-%s" % (kwargs['name'], kwargs['version'])
        command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        cmd = "apt-get install -y %s-doc-ru-%s" % (kwargs['name'], kwargs['version'])
        command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        cmd = "apt-get install -y libpq-dev"
        command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        if kwargs['version'] != '9.5':
            cmd = "apt-get install -y %s-pg-probackup-%s" % (kwargs['name'], kwargs['version'])
            command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        if kwargs['edition'] in ['cert-standard', 'cert-enterprise']:
            cmd = "apt-get install -y pgbouncer"
            command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        for p in DEB_PACKAGES:
            cmd = "apt-get install -y %s-%s-%s" % (kwargs['name'], p, kwargs['version'])
            command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        if kwargs['edition'] == 'ee':
            cmd = "apt-get install -y pg-repack-%s" % kwargs['version']
            command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)

    elif "ALT" in dist_info[0]:
        if kwargs['edition'] in ["ee", "cert-enterprise"]:
            pkg_name = "%s-enterprise%s.%s" % (kwargs['name'], major, minor)
        elif kwargs['edition'] == "cert-standard":
            pkg_name = "postgrespro%s.%s" % (major, minor)
        elif kwargs['edition'] == "standard":
            pkg_name = "postgrespro%s.%s" % (major, minor)
        else:
            pkg_name = kwargs['name'] + major + minor

        for p in ALT_PACKAGES:
            cmd = "apt-get install -y %s-%s" % (pkg_name, p)
            command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        if kwargs['version'] != '9.5':
            cmd = "apt-get install -y %s-%s" % (pkg_name, "pg_probackup")
            command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        if kwargs['edition'] in ['cert-standard', 'cert-enterprise']:
            cmd = "apt-get install -y pgbouncer"
            command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        if kwargs['edition'] == 'ee':
            cmd = "apt-get install -y pg_repack%s%s" % (major, minor)
            command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)


def install_windows_console(installer):
    """Run shell command for silent installation
    :return:
    """
    cmd = "C:/Users/test/pg-tests/{installer} /S".format(installer=installer)
    return command_executor(cmd, windows=True)


def get_last_windows_installer_file(url):
    """Get last uploaded postgrespro installation file from postgrespro repo

    :param url: str:
    :return: str: last postgrespro exe file
    """
    f = urllib.urlopen(url)
    soup = BeautifulSoup(f)
    postgres_files = []
    for link in soup.findAll('a'):
        if "Postgres" in link.get('href'):
            postgres_files.append(link.get('href'))
    return postgres_files[-1]


def delete_repo(remote=False, host=None, **kwargs):
    """ Delete repo file
    """
    dist_info = get_distro(remote, host)
    if dist_info[0] in RPM_BASED:
        repofile = "/etc/yum.repos.d/%s-%s.repo" % (kwargs['name'], kwargs['version'])
        cmd = "rm -f %s" % repofile
        command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        cmd = "yum update -y && yum clean cache"
        command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
    elif dist_info[0] in DEB_BASED or "ALT" in dist_info[0]:
        repofile = "/etc/apt/sources.list.d/%s-%s.list" % (kwargs['name'],
                                                           kwargs['version'])
        cmd = "rm -f %s" % repofile
        command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        cmd = "apt-get update -y && apt-get clean cache"
        command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
    else:
        print "Unsupported distro %s" % dist_info[0]
        sys.exit(1)


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
            command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        if kwargs['version'] != '9.5':
            cmd = "yum remove -y %s-%s" % (pkg_name, "pg_probackup")
            command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        if kwargs['edition'] in ['cert-standard', 'cert-enterprise']:
            cmd = "yum remove -y pgbouncer"
            command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)

    elif dist_info[0] in DEB_BASED and "ALT" not in dist_info[0]:
        cmd = "apt-get remove -y %s-%s" % (kwargs['name'], kwargs['version'])
        command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        cmd = "apt-get remove -y %s-doc-%s" % (kwargs['name'], kwargs['version'])
        command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        cmd = "apt-get remove -y %s-doc-ru-%s" % (kwargs['name'], kwargs['version'])
        command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        cmd = "apt-get remove -y libpq-dev"
        command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        if kwargs['version'] != '9.5':
            cmd = "apt-get remove -y %s-pg-probackup-%s" % (kwargs['name'], kwargs['version'])
            command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        if kwargs['edition'] in ['cert-standard', 'cert-enterprise']:
            cmd = "apt-get remove -y pgbouncer"
            command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        for p in DEB_PACKAGES:
            cmd = "apt-get remove -y %s-%s-%s" % (kwargs['name'], p, kwargs['version'])
            command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)

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
            command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        if kwargs['version'] != '9.5':
            cmd = "apt-get remove -y %s-%s" % (pkg_name, "pg_probackup")
            command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
        if kwargs['edition'] in ['cert-standard', 'cert-enterprise']:
            cmd = "apt-get remove -y pgbouncer"
            command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
