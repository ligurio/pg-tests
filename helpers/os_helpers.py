import urllib2
import os
import re
import sys
import subprocess


def download_file(url, path):

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
    pg_config_bin = os.environ['PG_CONFIG']
    if pg_config_bin is None:
        sys.exit()
    pg_bindir = subprocess.check_output([pg_config_bin, "--bindir"])

    return pg_bindir.strip()


def load_pgbench(connstring, params):

    conn_dict = parse_connstring(connstring)
    conn_params = ["--host", conn_dict['host'], "--username", conn_dict['user']]
    pgbench = os.path.join(pg_bindir(), "pgbench")
    cmd = ["sudo", "-u", "postgres", pgbench]

    return subprocess.check_call(cmd + conn_params + params)
