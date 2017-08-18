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
            try:
                print("Trying to execute pg_config for enterprise version")
                os.environ['PG_CONFIG'] = '/usr/pgproee-9.6/bin/pg_config'
                return subprocess.check_output(['/usr/pgproee-9.6/bin/pg_config', "--bindir"]).strip()
            except OSError as e:
                print(e)
                print("Cannot find pg_config for enterprise version")
                print("Trying to execute pg_config for standard version")
                try:
                    os.environ['PG_CONFIG'] = '/usr/pgpro-9.6/bin/pg_config'
                    return subprocess.check_output(['/usr/pgpro-9.6/bin/pg_config', "--bindir"]).strip()
                except OSError as e:
                    print(e)
                    print("Cannot find pg_config for standard newest versions")
                    print("Trying to execute pg_config for standard old version")
                    os.environ['PG_CONFIG'] = '/usr/pgsql-9.6/bin/pg_config'
                    return subprocess.check_output(['/usr/pgsql-9.6/bin/pg_config', "--bindir"]).strip()
        elif distro in DEB_BASED:
            os.environ['PG_CONFIG'] = '/usr/bin/pg_config'
            a = subprocess.check_output(['/usr/bin/pg_config', "--bindir"]).strip()
            print(a)
            return a
    else:
        return subprocess.check_output([pg_config_bin, "--bindir"]).strip()


def pg_config_dir():
    distro = platform.linux_distribution()[0]
    try:
        pg_config_bin = os.environ['PG_CONFIG']
    except KeyError:
        if distro in RPM_BASED:
            try:
                os.environ['PG_CONFIG'] = '/usr/pgproee-9.6/bin/pg_config'
                return '/usr/pgproee-9.6/bin/pg_config'
            except OSError:
                os.environ['PG_CONFIG'] = '/usr/bin/pg_config'
                return '/usr/pgpro-9.6/bin/pg_config'
        elif distro in DEB_BASED:
            os.environ['PG_CONFIG'] = '/usr/bin/pg_config'
            return '/usr/bin/pg_config'
    else:
        return pg_config_bin


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


def find_postgresqlconf():
    """Walk on file system and find postgresql.conf file

    :return: string with path to postgresql.conf
    """
    if platform.system() == 'Linux':
        for root, dirs, files in os.walk("/"):
            for file in files:
                if file.endswith("postgresql.conf"):
                    return os.path.join(root, file)
    elif platform.system() == 'Windows':
        for root, dirs, files in os.walk("c:"):
            for file in files:
                if file.endswith("postgresql.conf"):
                    return os.path.join(root, file)


def get_data_directory_path():
    """Get data directory path

    :return: string data directory path
    """
    if platform.system() == 'Linux':
        path_list = find_postgresqlconf().split(os.sep)
        return "/".join(path_list[:-2])
    elif platform.system() == 'Windows':
        pass


def delete_data_directory():
    """Delete all files in data directory

    :param data_directory_path: string data directory
    """
    data_dir = get_data_directory_path()
    print("Data directory will be deleted %s" % data_dir)
    shutil.rmtree(data_dir)
