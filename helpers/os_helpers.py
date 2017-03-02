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
    pg_config = os.path.join(pg_config_bin, "pg_config")
    pg_bindir = subprocess.check_output([pg_config, "--bindir"])

    return pg_bindir.strip()
