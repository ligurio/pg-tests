import os
import psutil
import random
import re
import subprocess
from helpers.utils import urlretrieve, ConsoleEncoding


def download_file(url, path):
    """ Download file from remote path

    :param url: str
    :param path: str
    :return:
    """

    try:
        urlretrieve(url, path)
    except Exception:
        print("Failed to download %s" % url)


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


def get_systemd_version():
    sysctl = subprocess.Popen("systemctl --version",
                              shell=True,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
    scout, scerr = sysctl.communicate()
    if sysctl.returncode != 0:
        return None
    firstline = scout.decode(ConsoleEncoding).splitlines()[0]
    m = re.match(r'systemd\s+(\d+)', firstline)
    if not m:
        return None
    return int(m.group(1))


def is_service_installed(service, windows=False):
    if windows:
        winsrv = None
        try:
            winsrv = psutil.win_service_get(service)
        except psutil.NoSuchProcess:
            return False
        return winsrv is not None
    systemd_version = get_systemd_version()
    if systemd_version > 210:
        cmd = 'LANG=C systemctl list-unit-files' \
                ' --no-legend --no-pager "%s.service"' % service
        result = subprocess.check_output(cmd, shell=True). \
            decode(ConsoleEncoding).strip()
        if result:
            if ' masked' in result:
                return False
            return True
        return False
    cmd = 'LANG=C service "%s" status' % service
    srv = subprocess.Popen(cmd,
                           shell=True,
                           stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
    srvout, srverr = srv.communicate()
    srverr = srverr.decode(ConsoleEncoding)
    if srv.returncode == 0:
        return True
    elif srv.returncode == 1 or srv.returncode == 4:
        if srverr.strip().lower().endswith(': unrecognized service') or \
           srverr.strip().endswith(' could not be found.') or \
           srverr.startswith('service: no such service'):
            return False
    return True


def is_service_running(service, windows=False):
    if windows:
        winsrv = None
        try:
            winsrv = psutil.win_service_get(service).as_dict()
        except psutil.NoSuchProcess:
            return False
        if winsrv:
            return winsrv['status'] == 'running'
    cmd = 'service "%s" status' % service
    result = subprocess.call(cmd,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             shell=True)
    return result == 0


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
