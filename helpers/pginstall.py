import fileinput
import os
import platform
import re
import subprocess
from subprocess import Popen
import urllib2

PGPRO_HOST = "http://repo.postgrespro.ru/"
PSQL_HOST = "https://download.postgresql.org/pub"
PACKAGES = ['server', 'contrib', 'libs']
RPM_BASED = ['centos', 'rhel', 'centos6', 'rhel7', 'oraclelinux']
DEB_BASED = ['debian', 'ubuntu']

PG_PASSWORD = 'password'
dist = {"Oracle Linux Server": 'oraclelinux',
        "CentOS Linux": 'centos',
        "CentOS": 'centos6',
        "RHEL": 'rhel',
        "Red Hat Enterprise Linux Server": 'rhel7',
        "debian": 'debian',
        "Ubuntu": 'ubuntu',
        "SLES": 'sles'}


def setup_repo(name, version, edition, milestone, build):

    distro = platform.linux_distribution()[0]
    major = version.split(".")[0]
    minor = version.split(".")[1]

    if name == "postgresql":
        gpg_key_url = "https://download.postgresql.org/pub/repos/yum/RPM-GPG-KEY-PGDG-%s%s" % (
            major, minor)
        # gpg_key_url = "https://www.postgresql.org/media/keys/ACCC4CF8.asc"
        product_dir = "/repos/yum/%s/redhat/rhel-$releasever-$basearch" % version
        baseurl = PSQL_HOST + product_dir
    elif name == "postgrespro":
        if edition == "ee":
            product_dir = "pgproee-%s" % version
        elif edition == "standard":
            product_dir = "pgpro-%s" % version
        if milestone:
            product_dir = product_dir + "-" + milestone
        gpg_key_url = "https://repo.postgrespro.ru/pgpro-%s/keys/GPG-KEY-POSTGRESPRO" % version
        baseurl = os.path.join(PGPRO_HOST, product_dir, dist[distro].lower())

    if dist[distro] in RPM_BASED:
        # Example:
        # http://repo.postgrespro.ru/pgproee-9.6-beta/centos/$releasever/os/$basearch/rpms
        if name == "postgrespro":
            baseurl = os.path.join(baseurl, "$releasever/os/$basearch/rpms")

        repo = """
[%s-%s]
name=%s-%s
baseurl=%s
enabled=1
""" % (name, version, name, version, baseurl)

        repofile = "/etc/yum.repos.d/%s-%s.repo" % (name, version)
        with open(repofile, "w+") as f:
            print >> f, repo
        subprocess.call(["rpm", "--import", gpg_key_url])

    elif dist[distro] in DEB_BASED:
        subprocess.call(["apt-get", "install", "-y", "lsb-release"])
        lsb = subprocess.Popen(
            (["lsb_release", "-cs"]), stdout=subprocess.PIPE)
        codename = lsb.stdout.readline().rstrip()

        repofile = "/etc/apt/sources.list.d/%s-%s.list" % (name, version)
        if name == "postgresql":
            repo = "deb http://apt.postgresql.org/pub/repos/apt/ %s-pgdg main" % codename
        elif name == "postgrespro":
            repo = "deb %s %s main" % (baseurl, codename)
        if not os.access(repofile, os.F_OK):
            with open(repofile, "w+") as f:
                print >> f, repo

        subprocess.call(["apt-get", "install", "-y",
                         "wget", "ca-certificates"])
        gpg_key = subprocess.Popen(
            ["wget", "--quiet", "-O", "-", gpg_key_url], stdout=subprocess.PIPE)
        subprocess.call(["apt-key", "add", "-"], stdin=gpg_key.stdout)
        subprocess.call(["apt-get", "update", "-y"])
    else:
        print "Unsupported distro %s" % distro
        return 1


def package_mgmt(name, version, edition, milestone, build):

    distro = platform.linux_distribution()[0]
    major = version.split(".")[0]
    minor = version.split(".")[1]

    if dist[distro] in RPM_BASED:
        if edition == "ee":
            pkg_name = "%s-enterprise%s%s" % (name, major, minor)
        else:
            pkg_name = name + major + minor

        for p in PACKAGES:
            subprocess.call(["yum", "install", "-y", "%s-%s" % (pkg_name, p)])

    elif dist[distro] in DEB_BASED:
        subprocess.call(["apt-get", "install", "-y",
                         "%s-%s" % (name, version)])


def manage_psql(version, action, init=False):
    """ Manage Postgres instance
    :param version 9.5, 9.6 etc
    :param action: start, restart, stop etc
    :param init: Initialization before a first start
    :return:
    """

    distro = platform.linux_distribution()[0]
    major = version.split(".")[0]
    minor = version.split(".")[1]

    if dist[distro] in RPM_BASED:
        service_name = "postgresql-%s.%s" % (major, minor)
    elif dist[distro] in DEB_BASED:
        service_name = "postgresql"

    if init:
        if dist[distro] in RPM_BASED:
            subprocess.call(["service", service_name, "initdb"])
            # subprocess.call(["chkconfig", service_name, "on"])
            # subprocess.call(["systemctl", "enable", "postgresql"])

    return subprocess.call(["service", service_name, action])


def setup_psql(name, version, edition, milestone, build):

    distro = platform.linux_distribution()[0]
    major = version.split(".")[0]
    minor = version.split(".")[1]

    print "Setup PostgreSQL service"
    manage_psql(version, "start", True)

    os.environ['PATH'] += ":/usr/pgsql-%s.%s/bin/" % (major, minor)
    subprocess.call(["sudo", "-u", "postgres", "psql", "-c",
                     "ALTER USER postgres WITH PASSWORD '%s';" % PG_PASSWORD])

    hba_auth = """
local   all             all                                     peer
host    all             all             0.0.0.0/0               trust
host    all             all             ::0/0                   trust"""

    cmd = ["sudo", "-u", "postgres", "psql", "-t", "-P",
           "format=unaligned", "-c", "SHOW hba_file;"]
    p = Popen(cmd, stdout=subprocess.PIPE)
    response = p.communicate()
    if p.returncode != 0:
        print "Failed to find hba_file %s" % response[1]
        return 1

    hba_file = response[0].rstrip()
    print "Path to hba_file is", hba_file
    hba = fileinput.FileInput(hba_file, inplace=True)
    for line in hba:
        if line[0] != '#':
            line = re.sub('^', '#', line.rstrip())
        print line.rstrip()

    with open(hba_file, 'a') as hba:
        hba.write(hba_auth)

    subprocess.call(["chown", "postgres:postgres", hba_file])
    subprocess.call(["sudo", "-u", "postgres", "psql", "-c",
                     "ALTER SYSTEM SET listen_addresses to '*';"])
    manage_psql(version, "restart")


def install_product(name, version, edition, milestone, build):
    """ Install product
    Parameter: Product name: postgrespro, postgresql
    Parameter: Product version: 9.5, 9.6 etc
    Parameter: Product editions (postgrespro only): standard, ee
    Parameter: Product milestone (postgrespro only): beta
    """
    os.environ[
        'PATH'] += ":/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

    setup_repo(name, version, edition, milestone, build)
    package_mgmt(name, version, edition, milestone, build)
    setup_psql(name, version, edition, milestone, build)

    return {'name': name,
            'version': version,
            'edition': edition,
            'milestone': milestone}
