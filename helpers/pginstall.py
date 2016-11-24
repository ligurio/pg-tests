import fileinput
import os
import platform
import re
import subprocess
import sys
from subprocess import Popen
import urllib2

rpm = ['server', 'contrib', 'perl', 'python',
       'tcl', 'devel', 'docs', 'docs-ru']
deb = ['server', 'contrib', 'plperl', 'plpython',
       'pltcl', 'libs', 'devel', 'doc', 'doc-ru']

repohost = "http://repo.postgrespro.ru"

dist = {'oracle': "Oracle Linux Server",
        'centos': "CentOS Linux",
        'centos6': "CentOS",
        'rhel': "RHEL",
        'rhel7': "Red Hat Enterprise Linux Server",
        'debian': "debian",
        'ubuntu': "Ubuntu",
        'sles': "SLES",
        'alt-centaur': "AltLinux",
        'alt-spt6': "AltLinux",
        'alt-spt7': "AltLinux",
        'rosa': "ROSA",
        'rosa-sx': "ROSA SX",
        'rosa-dx': "ROSA DX",
        'rosa-marathon': "ROSA Marathon",
        'astra': "Astra Linux"}

rpm_based = [dist['centos'], dist['rhel'],
             dist['centos6'], dist['rhel7'], dist['oracle']]
deb_based = [dist['debian'], dist['ubuntu']]


def get_distro():
    """
    Detect OS family and version
    """

    os = {
        'type': platform.system(),
        'distro': platform.linux_distribution()[0],
        'version': platform.linux_distribution()[1].split(".")[0],
        'arch': platform.architecture()[0]
    }

    return os


def product_name(name, edition, major, minor, milestone):

    product_dir = "pgpro-%s.%s" % (major, minor)
    if edition == "ee":
        product_dir = "pgproee-%s.%s" % (major, minor)
    if milestone:
        product_dir = product_dir + "-" + milestone

    return product_dir


def get_gpg_key(repohost, product_dir):

    # http://repo.postgrespro.ru/pgpro-9.6/keys/GPG-KEY-POSTGRESPRO
    keyurl = "%s/%s/keys/GPG-KEY-POSTGRESPRO" % (repohost, product_dir)
    print "GPG key URL", keyurl

    response = urllib2.urlopen(keyurl)
    key = response.read()

    filename = keyurl.rsplit('/', 1)[1]
    if not os.access(filename, os.F_OK):
        with open(filename, "a") as f:
            f.write(key)
    return filename


def setup_repo(d, major, minor, name, edition, milestone, build):

    product_dir = product_name(name, edition, major, minor, milestone)

    print "Install PostgreSQL repo package"

    if d['distro'] == dist['centos'] or d['distro'] == dist['centos6']:
        base_url = os.path.join(product_dir, "centos", d['version'], "os/x86_64/rpms/")
        repo_package = "postgrespro-%s.%s.centos.pro.yum-%s.%s-0.%s.noarch.rpm" % (major, minor, major, minor, build)
        repo_file = "/etc/yum.repos.d/postgrespro-%s.%s.centos.pro.repo" % (major, minor)
    elif d['distro'] == dist['oracle']:
        base_url = os.path.join(product_dir, "oraclelinux", d['version'] + "Server", "os/x86_64/rpms/")
        repo_package = "postgrespro-%s.%s.oraclelinux.pro.yum-%s.%s-0.%s.noarch.rpm" % (major, minor, major, minor, build)
        repo_file = "/etc/yum.repos.d/postgrespro-%s.%s.oraclelinux.pro.repo" % (major, minor)
    elif d['distro'] == dist['rhel'] or d['distro'] == dist['rhel7']:
        base_url = os.path.join(product_dir, "rhel", d['version'] + "Server", "os/x86_64/rpms/")
        repo_package = "postgrespro-%s.%s.rhel.pro.yum-%s.%s-0.%s.noarch.rpm" % (major, minor, major, minor, build)
        repo_file = "/etc/yum.repos.d/postgrespro-%s.%s.rhel.pro.repo" % (major, minor)
    elif d['distro'] == dist['debian'] or d['distro'] == dist['ubuntu']:
        subprocess.call(["apt-get", "install", "-y", "lsb-release"])
        lsb = subprocess.Popen((["lsb_release", "-cs"]), stdout=subprocess.PIPE)
        codename = lsb.stdout.readline().rstrip()

        if d['distro'] == dist['debian']:
            repo = "deb %s/%s/debian %s main" % (repohost, product_dir, codename)
        else:
            repo = "deb %s/%s/ubuntu %s main" % (repohost, product_dir, codename)

        deb_repo = "/etc/apt/sources.list.d/postgrespro.list"
        if not os.access(deb_repo, os.F_OK):
            with open(deb_repo, "a") as f:
                print >> f, repo
        else:
            print "Repo file %s is already exist" % deb_repo
            sys.exit(1)

        subprocess.call(["apt-key", "add", get_gpg_key(repohost, product_dir)])
        subprocess.call(["apt-get", "update", "-y"])
    else:
        print "Unsupported distro ", d
        sys.exit(1)

    if d['distro'] in rpm_based:
        pkg_url = os.path.join(repohost, base_url, repo_package)
        print "URL to the package with repository", pkg_url
        retcode = subprocess.call(["rpm", "-ihv", pkg_url])
        if retcode:
            print "Installation of %s failed" % pkg_url
            sys.exit(1)
        fix_version(major, minor, milestone, edition, repo_file)


def package_mgmt(major, minor, milestone, edition, distro, action):

    if distro in rpm_based:
        pkg_mask = "postgrespro%s%s-*" % (major, minor)
        if edition == "ee":
            pkg_mask = "postgrespro-enterprise%s%s-*" % (major, minor)
        if action == "install":
            print "Install PostgreSQL packages with mask", pkg_mask
            subprocess.call(["yum", "install", "-y", pkg_mask])
        elif action == "remove":
            print "Remove PostgreSQL packages with mask", pkg_mask
            subprocess.call(["service", "postgresql-%s.%s" % (major, minor), "stop"])
            subprocess.call(["yum", "remove", "-y", pkg_mask])
            subprocess.call(["yum", "remove", "-y", "postgrespro-%s.%s" % (major, minor)])

    if distro in deb_based:
        pkg_mask = "postgrespro-*"
        if action == "install":
            print "Install PostgreSQL packages with mask %s" % pkg_mask
            subprocess.call(["apt-get", "install", "-y", pkg_mask])
        elif action == "remove":
            print "Remove PostgreSQL packages with mask", pkg_mask
            subprocess.call(["service", "postgresql-%s.%s" % (major, minor), "stop"])
            subprocess.call(["apt-get", "remove", "-y", pkg_mask])


def setup_psql(major, minor, distro):

    print "Setup PostgreSQL service"
    if distro in rpm_based:
        subprocess.call(["service", "postgresql-%s.%s" % (major, minor), "initdb"])
        subprocess.call(["service", "postgresql-%s.%s" % (major, minor), "start"])
        subprocess.call(["chkconfig", "postgresql-%s.%s" % (major, minor), "on"])
    elif distro in deb_based:
        subprocess.call(["service", "postgresql", "start"])
        # subprocess.call(["chkconfig", "postgresql", "on"])

    os.environ['PATH'] += ":/usr/pgsql-%s.%s/bin/" % (major, minor)
    PG_PASSWORD = 'password'
    subprocess.call(["sudo", "-u", "postgres", "psql", "-c", "ALTER USER postgres WITH PASSWORD '%s';" % PG_PASSWORD])

    hba_auth = """
local   all             all                                     peer
host    all             all             0.0.0.0/0               trust
host    all             all             ::0/0                   trust"""

    cmd = ["sudo", "-u", "postgres", "psql", "-t", "-P", "format=unaligned", "-c", "SHOW hba_file;"]
    p = Popen(cmd, stdout=subprocess.PIPE)
    response = p.communicate()
    if p.returncode != 0:
        print "Failed to find hba_file", response[1]
        sys.exit(1)

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
    subprocess.call(["sudo", "-u", "postgres", "psql", "-c", "ALTER SYSTEM SET listen_addresses to '*';"])
    if distro in rpm_based:
        subprocess.call(["service", "postgresql-%s.%s" % (major, minor), "restart"])
    elif distro in deb_based:
        subprocess.call(["service", "postgresql", "restart"])  # Ubuntu 14.04
        #  subprocess.call(["systemctl", "restart", "postgresql"]) # Debian 8


def fix_version(major, minor, milestone, edition, repo_file):

    if milestone:
        print "Fix product version in", repo_file
        product = "pgpro"
        if edition == "ee":
            product = "pgproee"
        find = product + "-" + major + "." + minor
        replace = find + "-" + milestone + "/"
        find = product + "-" + major + "." + minor + "/"
        repo = fileinput.FileInput(repo_file, inplace=True)
        for line in repo:
            line = re.sub(find, replace, line.rstrip())
            print(line)


def install_product(version, milestone, name, edition, build):

    major = version.split(".")[0]
    minor = version.split(".")[1]

    os.environ['PATH'] += ":/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    d = get_distro()
    setup_repo(d, major, minor, name, edition, milestone, build)
    package_mgmt(major, minor, milestone, edition, d['distro'], "install")
    setup_psql(major, minor, d['distro'])
    return {'version': version,
            'milestone': milestone,
            'name': name,
            'edition': edition,
            'build': build}
