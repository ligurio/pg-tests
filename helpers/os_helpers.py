import os
import platform
import psutil
import random
import re
import shutil
import subprocess
import urllib2


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
    """Get path to postgresql(postgrespro) bin directory

    :return: string path to bin directory
    """
    raise NotImplementedError()


def pg_config_dir():
    """Get path to pg_config utility

    :return: string path to pg_config utility
    """
    raise NotImplementedError()


def load_pgbench(connstring, params):
    """

    :param connstring: string with connection params
    :param params:
    :return: int exit code
    """
    raise NotImplementedError()


def delete_data_directory():
    """Delete all files in data directory

    :param data_directory_path: string data directory
    """
    raise NotImplementedError()


def get_directory_size(start_path):
    """ Get directory size recursively

    :param start_path: directory for start
    :return: total size of directory in bytes
    """
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(start_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)
    return total_size


def get_process_pids(process_names):
    """Get process ids
    :process_name: string: array of possible process names
    :return: list of process pids
    """
    pids = []
    for p in psutil.process_iter():
        if p.name() in process_names:
            pids.append(p.pid)
    return pids


def create_tablespace_directory():
    """Create new  directory for tablespace
    :return: str path to tablespace
    """

    import pwd
    import grp

    tmp_dir = '/tmp'
    tablespace_catalog = 'tablespace-' + str(random.randint(0, 100))
    tablespace_path = os.path.join(tmp_dir, tablespace_catalog)
    os.mkdir(tablespace_path)
    os.chown(tablespace_path,
             pwd.getpwnam("postgres").pw_uid,
             grp.getgrnam("postgres").gr_gid)
    return tablespace_path
