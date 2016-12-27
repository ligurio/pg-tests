import os
import platform
import subprocess

PGPRO_HOST = "http://repo.postgrespro.ru/"
PSQL_HOST = "https://download.postgresql.org/pub"
PACKAGES = ['server', 'contrib', 'libs']
# Change to key names from dist
RPM_BASED = ['centos', 'rhel', 'centos6', 'rhel7', 'oraclelinux']
DEB_BASED = ['debian', 'ubuntu']

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
# Change dist[distro] to distro
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
