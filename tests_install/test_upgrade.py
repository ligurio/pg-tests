import platform

import pytest

import os

from allure_commons.types import LabelType
from helpers.pginstall import PgInstall
import time
import tempfile
import subprocess

system = platform.system()

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
        pg.install_server_only()
        stop(pg)
        pg.init_cluster(True)
    else:
        pg.install_postgres_win()
        pg.client_path_needed = True
        pg.server_path_needed = True
    start(pg)
    return pg


def generate_db(pg):
    pg.exec_psql(
        "CREATE TABLE t(id bigserial, val numeric); "
        "INSERT INTO t (val) (select random() from generate_series(1,10))"
    )

    old_select = pg.exec_psql("SELECT * FROM t ORDER BY id")
    file_name = os.path.join(
        tempfile.gettempdir(),
        "%s-expected.txt" % "-".join([pg.product, pg.edition, pg.version])
    )
    with open(file_name, 'w') as file:
        file.write(old_select)


def check_db(oldKey, pgNew):
    new_select = pgNew.exec_psql("SELECT * FROM t ORDER BY id")
    file_name = os.path.join(tempfile.gettempdir(), "%s-expected.txt" % oldKey)
    with open(file_name, 'r') as file:
        old_select = file.read()
    assert new_select == old_select


def upgrade(pg, pgOld):
    # type: (PgInstall, PgInstall) -> str
    stop(pg)
    stop(pgOld)

    cmd = '%s"%s/pg_upgrade" -d "%s" -b "%s" -D "%s" -B "%s"' % \
          (
              pg.pg_preexec,
              pg.get_default_bin_path(),
              pgOld.get_datadir(),
              pgOld.get_default_bin_path(),
              pg.get_datadir(),
              pg.get_default_bin_path()
          )

    subprocess.check_call(cmd, shell=True, cwd=tempfile.gettempdir())


def dumpall(pg, file):
    cmd = '%s"%s/pg_dumpall" > "%s"' % \
          (
              pg.pg_preexec,
              pg.get_default_bin_path(),
              file
          )
    subprocess.check_call(cmd, shell=True, cwd=tempfile.gettempdir())


def restore(pg, file):
    cmd = '%s"%s/psql" < "%s"' % \
          (
              pg.pg_preexec,
              pg.get_default_bin_path(),
              file
          )
    subprocess.check_call(cmd, shell=True)


def after_upgrade():
    if not system == "Windows":
        subprocess.check_call('sudo -u postgres ./analyze_new_cluster.sh',
                              shell=True, cwd=tempfile.gettempdir())
        subprocess.check_call('./delete_old_cluster.sh',
                              shell=True, cwd=tempfile.gettempdir())
    else:
        subprocess.check_call('analyze_new_cluster.bat',
                              shell=True, cwd=tempfile.gettempdir())
        subprocess.check_call('delete_old_cluster.bat',
                              shell=True, cwd=tempfile.gettempdir())


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

            generate_db(pgold)
            dumpall(pgold, os.path.join(tempfile.gettempdir(), "%s.sql" % key))
            stop(pgold)
            upgrade(pg, pgold)
            start(pg)
            after_upgrade()
            check_db(key, pg)
            stop(pg)
            pgold.remove_full()
            pg.init_cluster(True)

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
                restore(pg, file_name)
                check_db(key, pg)
            else:
                pgold = install_server(
                    product=old_name, edition=old_edition,
                    version=old_version, milestone=None,
                    branch=None, windows=(self.system == 'Windows')
                )

                generate_db(pgold)
                dumpall(pgold, file_name)
                stop(pgold)

                start(pg)
                restore(pg, file_name)
                check_db(key, pg)
                pgold.remove_full(True)

            stop(pg)
            pg.init_cluster(True)