import platform

import pytest

import os

from allure_commons.types import LabelType
from helpers.pginstall import PgInstall, ALT_BASED
import time
import tempfile
import subprocess
import urllib
import difflib
import re

system = platform.system()

DUMPS_XREGRESS_URL = "http://webdav.l.postgrespro.ru/pgdatas/xregress/"

UPGRADE_ROUTES = {
    'postgrespro-std-10': {
        'from': [
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '9.6',
                'unsupported_platforms': [
                    "\xd0\x9c\xd0\xa1\xd0\x92\xd0\xa1\xd1\x84\xd0\xb5\xd1"
                        "\x80\xd0\xb0  6.3"
                ]
            }
        ]
    },

    'postgrespro-std-11': {
        'from': [
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '10',
                'unsupported_platforms': [
                    "GosLinux 7.08", "RED OS release MUROM ( 7.1",
                    "Ubuntu 18.10"
                ]
            }
        ]
    },

    'postgrespro-ent-10': {
        'from': [
            {
                'name': 'postgrespro', 'edition': 'ent', 'version': '9.6',
                'unsupported_platforms': [
                    "\xd0\x9c\xd0\xa1\xd0\x92\xd0\xa1\xd1\x84\xd0\xb5\xd1"
                        "\x80\xd0\xb0  6.3"
                ]
            }
        ]
    }
}

DUMP_RESTORE_ROUTES = {
    'postgrespro-std-10': {
        'from': [
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '9.6',
                'unsupported_platforms': [
                    "\xd0\x9c\xd0\xa1\xd0\x92\xd0\xa1\xd1\x84\xd0\xb5\xd1"
                        "\x80\xd0\xb0  6.3"
                ]
            }
        ]
    },

    'postgrespro-std-11': {
        'from': [
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '10',
                'unsupported_platforms': [
                    "GosLinux 7.08", "RED OS release MUROM ( 7.1",
                    "Ubuntu 18.10"
                ]
            }
        ]
    },

    'postgrespro-ent-10': {
        'from': [
            {
                'name': 'postgrespro', 'edition': 'ent', 'version': '9.6',
                'unsupported_platforms': [
                    "\xd0\x9c\xd0\xa1\xd0\x92\xd0\xa1\xd1\x84\xd0\xb5\xd1"
                        "\x80\xd0\xb0  6.3"
                ]
            }
        ]
    }

}


upgrade_dir = os.path.join(tempfile.gettempdir(), 'upgrade')


def start(pg):
    if not pg.pg_isready():
        if not system == "Windows":
            pg.pg_control("start", pg.get_datadir())
        else:
            pg.start_service()
        for i in range(1, 100):
            if pg.pg_isready():
                break
            time.sleep(1)


def stop(pg):
    if pg.pg_isready():
        if not system == "Windows":
            pg.pg_control("stop", pg.get_datadir())
        else:
            pg.stop_service()
        for i in range(1, 100):
            if not pg.pg_isready():
                break
            time.sleep(1)


def install_server(product, edition, version, milestone, branch, windows):
    pg = PgInstall(product=product, edition=edition,
                   version=version, milestone=milestone,
                   branch=branch, windows=windows)
    pg.setup_repo()
    if not windows:
        pg.install_full_topless()
        # PGPRO - 2136
        if pg.os_name in ALT_BASED:
            subprocess.check_call(r"sudo sed -e 's/#\(Defaults:WHEEL_USERS"
                                  r"\s\+!env_reset\)/\1/' -i /etc/sudoers",
                                  shell=True)
            with open('/etc/sysconfig/i18n', 'r') as file:
                for line in file:
                    kv = line.split('=')
                    if len(kv) == 2:
                        os.environ[kv[0]] = kv[1].strip()
        stop(pg)
        pg.init_cluster(True)
        start(pg)
        pg.load_shared_libraries(restart_service=False)
        stop(pg)
        start(pg)
    else:
        pg.install_postgres_win()
        pg.client_path_needed = True
        pg.server_path_needed = True
        pg.load_shared_libraries()
    return pg


def preprocess(str):
    replaced = re.sub(
        r"(ALTER ROLE.*)PASSWORD\s'[^']+'",
        r"\1PASSWORD ''",
        str
    )
    replaced = re.sub(
        r"(CREATE DATABASE.*)LC_COLLATE\s*=\s*'([^@]+)@[^']+'(.*)",
        r"\1LC_COLLATE = '\2'\3",
        replaced
    )
    replaced = re.sub(
        r"\s?--.*",
        r"",
        replaced
    )
    return replaced


def generate_db(pg, pgnew):
    key = "-".join([pg.product, pg.edition, pg.version])
    dump_file_name = "dump-%s.sql" % key
    dump_url = DUMPS_XREGRESS_URL + dump_file_name
    dump_file = urllib.URLopener()

    try:
        dump_file_name = os.path.join(tempfile.gettempdir(), dump_file_name)
        dump_file.retrieve(dump_url, dump_file_name)
        pg.exec_psql_file(dump_file_name)
    except Exception:
        pg.exec_psql(
            "CREATE TABLE t(id bigserial, val numeric); "
            "INSERT INTO t (val) (select random() from generate_series(1,10))"
        )

    dumpall(pgnew, os.path.join(tempfile.gettempdir(),
                                "%s-expected.sql" % key))


def diff_dbs(oldKey, pgNew, prefix):
    result_file_name = "%s-%s-result.sql" % (prefix, oldKey)
    tempdir = tempfile.gettempdir()
    dumpall(pgNew, result_file_name)
    file1 = os.path.join(tempdir, result_file_name)
    file2 = os.path.join(tempdir, '%s-expected.sql' % oldKey)
    lines1 = []
    with open(file1, 'rb') as f:
        for line in f:
            lines1.append(preprocess(line))
    lines2 = []
    with open(file2, 'rb') as f:
        for line in f:
            lines2.append(preprocess(line))
    difference = difflib.unified_diff(
        lines1,
        lines2,
        fromfile=file1,
        tofile=file2
    )
    diff_file = os.path.join(tempdir, "%s-%s.sql.diff" % (prefix, oldKey))
    with open(diff_file, "w") as file:
        file.writelines(difference)
        pos = file.tell()
    if pos > 0:
        with open(diff_file, "rb") as file:
            lines = file.readlines()
            i = 1
            for line in lines:
                print line
                if i > 20:
                    print "..."
                    break
                i = i + 1
        raise Exception("Difference found. See file " + diff_file)


def upgrade(pg, pgOld):
    # type: (PgInstall, PgInstall) -> str
    stop(pg)
    stop(pgOld)
    if not os.path.exists(upgrade_dir):
        os.makedirs(upgrade_dir)
        if not system == "Windows":
            subprocess.check_call("chown postgres:postgres ./",
                                  shell=True, cwd=upgrade_dir)

    cmd = '%s"%spg_upgrade" -d "%s" -b "%s" -D "%s" -B "%s"' % \
          (
              pg.pg_preexec,
              pg.get_server_bin_path(),
              pgOld.get_datadir(),
              pgOld.get_default_bin_path(),
              pg.get_datadir(),
              pg.get_default_bin_path()
          )

    subprocess.check_call(cmd, shell=True, cwd=upgrade_dir)


def dumpall(pg, file):
    cmd = '%s"%spg_dumpall" -h localhost -f "%s"' % \
          (
              pg.pg_preexec,
              pg.get_server_bin_path(),
              file
          )
    subprocess.check_call(cmd, shell=True, cwd=tempfile.gettempdir())


def after_upgrade(pg):
    if not system == "Windows":
        subprocess.check_call('sudo -u postgres ./analyze_new_cluster.sh',
                              shell=True, cwd=upgrade_dir)
        subprocess.check_call('./delete_old_cluster.sh',
                              shell=True, cwd=upgrade_dir)
    else:
        subprocess.check_call('analyze_new_cluster.bat',
                              shell=True, cwd=upgrade_dir)
        subprocess.check_call('delete_old_cluster.bat',
                              shell=True, cwd=upgrade_dir)
    # Find any sql's after upgrade
    for file in os.listdir(upgrade_dir):
        if ".sql" in file:
            file_name = os.path.join(upgrade_dir, file)
            pg.exec_psql_file(file_name)
    # PGPRO - 2223
    key = "-".join([pg.product, pg.edition, pg.version])
    dump_file_name = "dump-%s.sql" % key
    if system == "Windows" and pg.version == '10' and os.path.exists(
            os.path.join(tempfile.gettempdir(), dump_file_name)):
        pg.exec_psql(
            'ALTER DOMAIN str_domain2 VALIDATE CONSTRAINT str_domain2_check;',
            '-d regression'
        )


def init_cluster(pg, force_remove=True):
    if system == 'Windows':
        restore_datadir_win(pg)
    else:
        pg.init_cluster(force_remove)
        start(pg)
        pg.load_shared_libraries(restart_service=False)
        stop(pg)
    start(pg)


def backup_datadir_win(pg):
    cmd = 'xcopy /S /E /O /X /I /Q "%s" "%s.bak"' %\
          (pg.get_datadir(), pg.get_datadir())
    subprocess.check_call(cmd, shell=True)


def restore_datadir_win(pg):
    pg.remove_data()
    cmd = 'xcopy /S /E /O /X /I /Q "%s" "%s"' %\
          (pg.get_datadir() + '.bak', pg.get_datadir())
    subprocess.check_call(cmd, shell=True)


@pytest.mark.upgrade
class TestUpgrade():
    system = system

    @pytest.mark.test_upgrade
    def test_upgrade(self, request):
        """
        Scenario:
        1. Install testible version
        2. if route install upgradeble version
        3. Create DB with one table and insert 10 rows
        4. Upgrade by pg_upgrade
        5. Start service
        6.Check that upgrade successfull (select from table)
        :return:
        """
        dist = ""
        if self.system == 'Linux':
            dist = " ".join(platform.linux_distribution()[0:2])
        elif self.system == 'Windows':
            dist = " ".join(platform.win32_ver()[0:2])
        else:
            raise Exception("OS %s is not supported." % self.system)

        version = request.config.getoption('--product_version')
        name = request.config.getoption('--product_name')
        edition = request.config.getoption('--product_edition')
        milestone = request.config.getoption('--product_milestone')
        target = request.config.getoption('--target')
        product_info = " ".join([dist, name, edition, version])
        request.cls.product_info = product_info
        key = "-".join([name, edition, version])
        request.cls.key = key

        print("Running on %s." % target)

        if dist in ['"AstraLinuxSE" 1.5', '"AstraLinuxSE" 1.5.28']:
            print 'AstraLinux not supported (PGPRO-2072)'
            return

        if key not in UPGRADE_ROUTES:
            print 'No routes for upgrade'
            return

        upgrade_route = UPGRADE_ROUTES[key]

        # pylint: disable=no-member
        tag_mark = pytest.allure.label(LabelType.TAG, product_info)
        request.node.add_marker(tag_mark)
        # Install the tested version
        branch = request.config.getoption('--branch')

        pg = install_server(product=name, edition=edition,
                            version=version, milestone=milestone,
                            branch=branch, windows=(self.system == 'Windows'))
        stop(pg)

        if system == 'Windows':
            backup_datadir_win(pg)

        for route in upgrade_route['from']:
            if ('unsupported_platforms' in route
                    and dist in route['unsupported_platforms']):
                continue

            old_name = route['name']
            old_edition = route['edition']
            old_version = route['version']

            key = "-".join([old_name, old_edition, old_version])

            print "Check upgrage from %s" % key

            pgold = install_server(
                product=old_name, edition=old_edition,
                version=old_version, milestone=None,
                branch=None, windows=(self.system == 'Windows')
            )

            generate_db(pgold, pg)
            dumpall(pgold, os.path.join(tempfile.gettempdir(), "%s.sql" % key))
            stop(pgold)
            upgrade(pg, pgold)
            start(pg)
            after_upgrade(pg)
            diff_dbs(key, pg, 'upgrade')
            stop(pg)
            pgold.remove_full()
            init_cluster(pg, True)

        request.cls.pg = pg

    @pytest.mark.test_dump_restore
    def test_dump_restore(self, request):
        """
        Scenario:
        3. if route install upgradeble version
        7. Check that upgrade successfull (select from table)
        :return:
        """
        if self.system == 'Linux':
            dist = " ".join(platform.linux_distribution()[0:2])
        elif self.system == 'Windows':
            dist = "Windows"
        else:
            raise Exception("OS %s is not supported." % self.system)

        product_info = request.cls.product_info
        # pylint: disable=no-member
        tag_mark = pytest.allure.label(LabelType.TAG, product_info)
        request.node.add_marker(tag_mark)

        key = request.cls.key

        print "DEBUG: dump-restore!!! %s" % product_info

        if dist in ['"AstraLinuxSE" 1.5', '"AstraLinuxSE" 1.5.28']:
            print 'AstraLinux not supported (PGPRO-2072)'
            return

        if key not in DUMP_RESTORE_ROUTES:
            print 'No routes for dump-restore'
            return

        dump_restore_route = DUMP_RESTORE_ROUTES[key]

        pg = request.cls.pg

        for route in dump_restore_route['from']:

            if ('unsupported_platforms' in route
                    and dist in route['unsupported_platforms']):
                continue

            old_name = route['name']
            old_edition = route['edition']
            old_version = route['version']

            key = "-".join([old_name, old_edition, old_version])

            print "Check dump-restore from %s" % key

            file_name = os.path.join(tempfile.gettempdir(), "%s.sql" % key)

            if (os.path.isfile(file_name)):
                start(pg)
                pg.exec_psql_file(file_name)
                diff_dbs(key, pg, 'dump-restore')
            else:
                pgold = install_server(
                    product=old_name, edition=old_edition,
                    version=old_version, milestone=None,
                    branch=None, windows=(self.system == 'Windows')
                )

                generate_db(pgold, pg)
                dumpall(pgold, file_name)
                stop(pgold)

                start(pg)
                pg.exec_psql_file(file_name)
                diff_dbs(key, pg, 'dump-restore')
                pgold.remove_full(True)

            stop(pg)
            init_cluster(pg, True)
