#!/usr/bin/env python

import fileinput
import os
import platform
import re
import shutil
import subprocess
import sys
from subprocess import Popen, PIPE, STDOUT
import urllib2

rpm = [ 'server', 'contrib', 'perl', 'python', 'tcl', 'devel', 'docs', 'docs-ru' ]
deb = [ 'server', 'contrib', 'plperl', 'plpython', 'pltcl', 'libs', 'devel', 'docs', 'docs-ru' ]

repohost = "http://repo.postgrespro.ru"

dist = { 'oracle': "Oracle Linux Server", 		\
         'centos': "CentOS Linux",         		\
         'centos6': "CentOS",               		\
         'rhel': "RHEL",                   		\
         'rhel7': "Red Hat Enterprise Linux Server",   	\
         'debian': "debian",               		\
         'ubuntu': "Ubuntu",               		\
         'sles': "SLES",                   		\
         'alt-centaur': "AltLinux",       		\
         'alt-spt6': "AltLinux",           		\
         'alt-spt7': "AltLinux",           		\
         'rosa': "ROSA",                   		\
         'rosa-sx': "ROSA SX",             		\
         'rosa-dx': "ROSA DX",             		\
         'rosa-marathon': "ROSA Marathon", 		\
         'astra': "Astra Linux" }

rpm_based = [dist['centos'], dist['rhel'], dist['centos6'], dist['rhel7'], dist['oracle']]
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

def get_gpg_key():

    keyurl = "%s/%s/keys/GPG-KEY-POSTGRESPRO-%s%s" % \
	(repohost, product_dir, major, minor)
    print keyurl

    response= urllib2.urlopen(keyurl)
    key = response.read()

    filename = keyurl.rsplit('/', 1)[1]
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
    else:
       print "Unsupported distro ", d
       sys.exit(1)

    pkg_url = os.path.join(repohost, base_url, repo_package)
    print "URL to the package with repository", pkg_url
    retcode = subprocess.call(["rpm", "-ihv", pkg_url])
    if retcode:
       print "Installation of %s failed" % pkg_url
       sys.exit(1)

    fix_version(major, minor, milestone, edition, repo_file)

def package_mgmt(major, minor, milestone, edition, distro, action):

    pkg_mask = "postgrespro%s%s-*" % (major, minor)
    if edition == "ee":
       pkg_mask = "postgrespro-enterprise%s%s-*" % (major, minor)
    
    if distro in rpm_based:
       if action == "install":
          print "Install PostgreSQL packages with mask", pkg_mask
          subprocess.call(["yum", "install", "-y", pkg_mask])
       elif action == "remove":
          print "Remove PostgreSQL packages with mask", pkg_mask
          subprocess.call(["service", "postgresql-%s.%s" % (major, minor), "stop"])
          subprocess.call(["yum", "remove", "-y", pkg_mask])
          subprocess.call(["yum", "remove", "-y", "postgrespro-%s.%s" % (major, minor)])
          # FIXME: remove package with repo taken from setup_repo()

def setup_psql(major, minor, distro):

    print "Setup PostgreSQL service"
    if distro in rpm_based:
       subprocess.call(["service", "postgresql-%s.%s" %  (major, minor), "initdb"])
       subprocess.call(["service", "postgresql-%s.%s" % (major, minor), "start"])
       subprocess.call(["chkconfig", "postgresql-%s.%s" % (major, minor), "on"])

    os.environ['PATH'] = os.environ['PATH'] + "/usr/pgsql-%s.%s/bin/" % (major, minor)
    PG_PASSWORD = 'password'
    subprocess.call(["sudo", "-u", "postgres", "psql", "-c", "ALTER USER postgres WITH PASSWORD '%s';" % PG_PASSWORD])

    hba_auth = """
local   all             all                                     peer
host    all             all             0.0.0.0/0               trust
host    all             all             ::0/0                   trust"""

    #subprocess.call(["sudo", "-u", "postgres", "psql", "format=unaligned", "-c", "SHOW hba_file;"])
    hba_file = "/var/lib/pgsql/%s.%s/data/pg_hba.conf" % (major, minor)

    hba = fileinput.FileInput(hba_file, inplace=True)
    for line in hba:
        if line[0] <> '#':
           line = re.sub('^', '#', line.rstrip())
        print line.rstrip()

    with open(hba_file, 'a') as hba:
         hba.write(hba_auth)
    subprocess.call(["chown", "postgres:postgres", hba_file])

    subprocess.call(["sudo", "-u", "postgres", "psql", "-c", "ALTER SYSTEM SET listen_addresses to '*';"])
    subprocess.call(["service", "postgresql-%s.%s" % (major, minor), "restart"])

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

def install_product(name, edition, version, milestone, build):

    major = version.split(".")[0]
    minor = version.split(".")[1]

    os.environ['PATH'] = os.environ['PATH'] + "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin"
    d = get_distro()
    setup_repo(d, major, minor, name, edition, milestone, build)
    package_mgmt(major, minor, milestone, edition, d['distro'], "install")
    setup_psql(major, minor, d['distro'])

if __name__ == '__main__':

    version = "9.6"
    milestone = "beta"
    name = "postgrespro"
    edition = "opensource"
    build = "1"

    print "PARAMETERS:", name, edition, version, milestone
    install_product(name, edition, version, milestone, build)
