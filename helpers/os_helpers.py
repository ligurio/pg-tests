import os
import platform
import re
import shutil
import subprocess
import urllib2

from helpers.pginstall import DEB_BASED, RPM_BASED


def download_file(url, path):
    """ Download file from remote path

    :param url: str
    :param path: str
    :return:
    """

    try:
        blob = urllib2.urlopen(url)
    except urllib2.URLError:
        print "Failed to download %s" % url

    with open(path, 'wb') as output:
        output.write(blob.read())


def parse_connstring(connstring):
    """Convert connection string to a dict with parameters
    """

    return dict(re.findall(r'(\S+)=(".*?"|\S+)', connstring))


def pg_bindir():
    distro = platform.linux_distribution()[0]
    try:
        pg_config_bin = os.environ['PG_CONFIG']
    except KeyError as e:
        print("PG_CONFIG variable not in environment variables\n", e)
        print("Trying to install pg_config and set PG_CONFIG\n")
        if distro in RPM_BASED:
            return subprocess.check_output(['/usr/pgproee-9.6/bin/pg_config', "--bindir"]).strip()
        elif distro in DEB_BASED:
            a = subprocess.check_output(['/usr/bin/pg_config', "--bindir"]).strip()
            print(a)
            return a
    else:
        return subprocess.check_output([pg_config_bin, "--bindir"]).strip()


def rmdir(dirname):
    for item in os.listdir(dirname):
        path = os.path.join(dirname, item)
        try:
            if os.path.isfile(path):
                os.unlink(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
        except Exception as e:
            print(e)


def load_pgbench(connstring, params):

    conn_dict = parse_connstring(connstring)
    conn_params = ["--host", conn_dict['host'], "--username", conn_dict['user']]
    pgbench = os.path.join(pg_bindir(), "pgbench")
    cmd = ["sudo", "-u", "postgres", pgbench]

    return subprocess.check_call(cmd + conn_params + params)
