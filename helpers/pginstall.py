import logging
import os

from helpers.utils import exec_command
from helpers.utils import command_executor
from helpers.utils import get_distro
from helpers.utils import SSH_ROOT
from helpers.utils import SSH_ROOT_PASSWORD
from helpers.utils import write_file


PGPRO_HOST = "http://repo.postgrespro.ru/"
PSQL_HOST = "https://download.postgresql.org/pub"
PACKAGES = ['server', 'contrib', 'libs']
ALT_PACKAGES = ['server', 'contrib', 'devel']
RPM_BASED = ['CentOS Linux', 'RHEL', 'CentOS',
             'Red Hat Enterprise Linux Server', 'Oracle Linux Server', 'SLES',
             'ROSA Enterprise Linux Server', 'ROSA SX \"COBALT\" ']
DEB_BASED = ['debian', 'Ubuntu', 'Debian GNU/Linux', 'AstraLinuxSE']

dist = {"Oracle Linux Server": 'oraclelinux',
        "CentOS Linux": 'centos',
        "CentOS": 'centos6',
        "RHEL": 'rhel',
        "Red Hat Enterprise Linux Server": 'rhel7',
        "debian": 'debian',
        "Debian GNU/Linux": 'debian',
        "Ubuntu": 'ubuntu',
        "ROSA Enterprise Linux Server": 'rosa-el',
        "ROSA SX \"COBALT\" ": 'rosa-sx',
        "SLES": 'sles'}


def get_os_type(ip):
    cmd = 'cat /etc/*-release'
    retcode, stdout, stderr = exec_command(cmd, ip, SSH_ROOT, SSH_ROOT_PASSWORD)
    if retcode == 0:
        return dict(
            v.split("=") for v in stdout.replace(
                '\t', ' ').strip().split('\n') if v.strip() and "=" in v)
    else:
        return None


def generate_repo_info(distro, osversion, **kwargs):

    major = kwargs['version'].split(".")[0]
    minor = kwargs['version'].split(".")[1]

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
        elif kwargs['edition'] == "cert":
            product_dir = "pgpro-standard-9.6.2.2-cert/repo"
        if kwargs['milestone']:
            product_dir = product_dir + "-" + kwargs['milestone']
        gpg_key_url = "https://repo.postgrespro.ru/pgpro-%s/keys/GPG-KEY-POSTGRESPRO" % kwargs['version']
        if distro == "ALT Linux " and osversion == "7.0.4":
            distname = "altlinux-spt"
        elif distro == "ROSA Enterprise Linux Server":
            distname = "rosa-el"
        elif distro == "ROSA SX \"COBALT\" ":
            distname = "rosa-sx"
        elif distro == "AstraLinuxSE":
            distname = "astra-smolensk"
        else:
            distname = dist[distro].lower()
        if kwargs['edition'] == "cert" and distro == "AstraLinuxSE":
            baseurl = os.path.join("http://localrepo.l.postgrespro.ru", product_dir, distname, "1.5")
        elif kwargs['edition'] == "cert":
            baseurl = os.path.join("http://localrepo.l.postgrespro.ru", product_dir, distname)
        else:
            baseurl = os.path.join(PGPRO_HOST, product_dir, distname)
        logging.debug("Installation repo path: %s" % baseurl)
        logging.debug("GPG key url for installation: %s" % gpg_key_url)
        return baseurl, gpg_key_url


def setup_repo(remote=False, host=None, **kwargs):
    dist_info = get_distro(remote, host)
    repo_info = generate_repo_info(dist_info[0], dist_info[1], version=kwargs['version'],
                                   name=kwargs['name'], edition=kwargs['edition'],
                                   milestone=kwargs['milestone'], build=kwargs['build'])
    baseurl = repo_info[0]
    gpg_key_url = repo_info[1]
    if dist_info[0] in RPM_BASED:
        # Example:
        # http://repo.postgrespro.ru/pgproee-9.6-beta/centos/$releasever/os/$basearch/rpms
        if kwargs['name'] == "postgrespro":
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
        command_executor(cmd, remote, host, SSH_ROOT, SSH_ROOT_PASSWORD)
    elif dist_info[0] in DEB_BASED or dist_info[0] == "ALT Linux ":
        cmd = "apt-get install -y lsb-release"
        command_executor(cmd, remote, host, SSH_ROOT, SSH_ROOT_PASSWORD)
        cmd = "lsb_release -cs"
        codename = ""
        if remote:
            codename = command_executor(cmd, remote, host, SSH_ROOT, SSH_ROOT_PASSWORD)[1].rstrip()
        else:
            codename = command_executor(cmd, remote, stdout=True)
        repofile = "/etc/apt/sources.list.d/%s-%s.list" % (kwargs['name'],
                                                           kwargs['version'])
        if kwargs['name'] == "postgresql":
            repo = "deb http://apt.postgresql.org/pub/repos/apt/ %s-pgdg main" % codename
        elif kwargs['name'] == "postgrespro":
            repo = "deb %s %s main" % (baseurl, codename)
            if dist_info[0] == "ALT Linux " and dist_info[1] == "7.0.4":
                repo = "rpm %s/7 x86_64 pgpro" % baseurl
        write_file(repofile, repo, remote, host)

        if dist_info[0] == "ALT Linux " and dist_info[1] == "7.0.4":
            cmd = "apt-get update -y"
            command_executor(cmd, remote, host, SSH_ROOT, SSH_ROOT_PASSWORD)
        else:
            cmd = "apt-get install -y wget ca-certificates"
            command_executor(cmd, remote, host, SSH_ROOT, SSH_ROOT_PASSWORD)
            cmd = "wget --quiet -O - %s | apt-key add -" % gpg_key_url
            command_executor(cmd, remote, host, SSH_ROOT, SSH_ROOT_PASSWORD)
            cmd = "apt-get update -y"
            command_executor(cmd, remote, host, SSH_ROOT, SSH_ROOT_PASSWORD)
    else:
        print "Unsupported distro %s" % dist_info[0]
        return 1


def package_mgmt(remote=False, host=None, **kwargs):
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
            cmd = "yum install -y %s-%s" % (pkg_name, p)
            command_executor(cmd, remote, host, SSH_ROOT, SSH_ROOT_PASSWORD)
        cmd = "yum install -y libpq-dev"
        command_executor(cmd, remote, host, SSH_ROOT, SSH_ROOT_PASSWORD)

    elif dist_info[0] in DEB_BASED:
        cmd = "apt-get install -y %s-%s" % (kwargs['name'], kwargs['version'])
        command_executor(cmd, remote, host, SSH_ROOT, SSH_ROOT_PASSWORD)
        cmd = "apt-get install -y libpq-dev"
        command_executor(cmd, remote, host, SSH_ROOT, SSH_ROOT_PASSWORD)

    elif dist_info[0] == "ALT Linux ":
        if kwargs['edition'] == "ee":
            pkg_name = "%s-enterprise%s.%s" % (kwargs['name'], major, minor)
        elif kwargs['edition'] == "cert":
            pkg_name = "postgrespro%s.%s" % (major, minor)
        else:
            pkg_name = kwargs['name'] + major + minor

        for p in ALT_PACKAGES:
            cmd = "apt-get install -y %s-%s" % (pkg_name, p)
            command_executor(cmd, remote, host, SSH_ROOT, SSH_ROOT_PASSWORD)
