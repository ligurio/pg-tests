import os
import platform
import subprocess

PGPRO_HOST = "http://repo.postgrespro.ru/"
PSQL_HOST = "https://download.postgresql.org/pub"
PACKAGES = ['server', 'contrib', 'libs']
ALT_PACKAGES = ['server', 'contrib', 'devel']
RPM_BASED = ['CentOS Linux', 'RHEL', 'CentOS',
             'Red Hat Enterprise Linux Server', 'Oracle Linux Server', 'SLES']
DEB_BASED = ['debian', 'Ubuntu']

dist = {"Oracle Linux Server": 'oraclelinux',
        "CentOS Linux": 'centos',
        "CentOS": 'centos6',
        "RHEL": 'rhel',
        "Red Hat Enterprise Linux Server": 'rhel7',
        "debian": 'debian',
        "Ubuntu": 'ubuntu',
        "SLES": 'sles'}


def setup_repo(name, version, edition=None, milestone=None, build=None):

    distro = platform.linux_distribution()[0]
    osversion = platform.linux_distribution()[1]
    major = version.split(".")[0]
    minor = version.split(".")[1]

    product_dir = ""
    if name == "postgresql":
        if distro in RPM_BASED:
            gpg_key_url = "https://download.postgresql.org/pub/repos/yum/RPM-GPG-KEY-PGDG-%s%s" % (
                major, minor)
        elif distro in DEB_BASED or distro == "ALT Linux ":
            gpg_key_url = "https://www.postgresql.org/media/keys/ACCC4CF8.asc"
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
        if distro == "ALT Linux " and osversion == "7.0.4":
            distname = "altlinux-spt"
        else:
            distname = dist[distro].lower()
        baseurl = os.path.join(PGPRO_HOST, product_dir, distname)

    if distro in RPM_BASED:
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

    elif distro in DEB_BASED or distro == "ALT Linux ":
        subprocess.call(["apt-get", "install", "-y", "lsb-release"])
        lsb = subprocess.Popen(
            (["lsb_release", "-cs"]), stdout=subprocess.PIPE)
        codename = lsb.stdout.readline().rstrip()

        repofile = "/etc/apt/sources.list.d/%s-%s.list" % (name, version)
        if name == "postgresql":
            repo = "deb http://apt.postgresql.org/pub/repos/apt/ %s-pgdg main" % codename
        elif name == "postgrespro":
            repo = "deb %s %s main" % (baseurl, codename)
            if distro == "ALT Linux " and osversion == "7.0.4":
                repo = "rpm %s/7 x86_64 pgpro" % baseurl
        if not os.access(repofile, os.F_OK):
            with open(repofile, "w+") as f:
                print >> f, repo

        if distro == "ALT Linux " and osversion == "7.0.4":
            # subprocess.call(["rpm", "--import", gpg_key_url])
            pass
        else:
            subprocess.call(["apt-get", "install", "-y",
                             "wget", "ca-certificates"])
            gpg_key = subprocess.Popen(
                ["wget", "--quiet", "-O", "-", gpg_key_url], stdout=subprocess.PIPE)
            subprocess.call(["apt-key", "add", "-"], stdin=gpg_key.stdout)

        subprocess.call(["apt-get", "update", "-y"])
    else:
        print "Unsupported distro %s" % distro
        return 1


def package_mgmt(name, version, edition=None, milestone=None, build=None):

    distro = platform.linux_distribution()[0]
    major = version.split(".")[0]
    minor = version.split(".")[1]
    pkg_name = ""
    if distro in RPM_BASED:
        if edition == "ee":
            pkg_name = "%s-enterprise%s%s" % (name, major, minor)
        else:
            pkg_name = name + major + minor

        for p in PACKAGES:
            subprocess.call(["yum", "install", "-y", "%s-%s" % (pkg_name, p)])

    elif distro in DEB_BASED:
        if distro == "ALT Linux ":
            if edition == "ee":
                pkg_name = "%s-enterprise%s.%s" % (name, major, minor)
            else:
                pkg_name = name + major + minor

            for p in ALT_PACKAGES:
                subprocess.call(
                    ["apt-get", "install", "-y", "%s-%s" % (pkg_name, p)])
                # postgrespro-enterprise9.6-devel
        else:
            subprocess.call(["apt-get", "install", "-y",
                             "%s-%s" % (name, version)])
