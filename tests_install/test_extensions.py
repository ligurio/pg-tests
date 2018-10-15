import os
import platform
import subprocess
import time
import re

import pytest

from allure_commons.types import LabelType
from helpers.pginstall import PgInstall


@pytest.mark.test_extensions
class TestExtensions():

    system = platform.system()

    @pytest.mark.test_extensions_prepare
    def test_extensions_prepare(self, request):
        """
        Scenario:
        1. Install current version

        :return:
        """
        if self.system == 'Linux':
            dist = " ".join(platform.linux_distribution()[0:2])
        elif self.system == 'Windows':
            dist = 'Windows'
        else:
            raise Exception("OS %s is not supported." % self.system)
        version = request.config.getoption('--product_version')
        name = request.config.getoption('--product_name')
        edition = request.config.getoption('--product_edition')
        milestone = request.config.getoption('--product_milestone')
        target = request.config.getoption('--target')
        product_info = " ".join([dist, name, edition, version])
        # pylint: disable=no-member
        tag_mark = pytest.allure.label(LabelType.TAG, product_info)
        request.node.add_marker(tag_mark)
        branch = request.config.getoption('--branch')

        # Step 1
        pginst = PgInstall(product=name, edition=edition,
                           version=version, milestone=milestone,
                           branch=branch, windows=(self.system == 'Windows'))

        request.cls.pginst = pginst
        pginst.setup_repo()
        print("Running on %s." % target)
        if self.system != 'Windows':
            pginst.install_base()
            pginst.initdb_start()
        else:
            pginst.install_postgres_win()

    @pytest.mark.test_pgbadger_prepare
    def test_pgbadger_prepare(self, request):
        pginst = request.cls.pginst
        pginst.exec_psql("ALTER SYSTEM SET log_min_duration_statement = 0")
        pginst.exec_psql("ALTER SYSTEM SET lc_messages = 'C'")
        logdir = pginst.exec_psql_select('SHOW log_directory')
        if not os.path.isabs(logdir):
            datadir = pginst.exec_psql_select('SHOW data_directory')
            logdir = os.path.join(datadir, logdir)
        request.cls.logdir = logdir
        pginst.stop_service()
        time.sleep(5)
        for lf in os.listdir(logdir):
            os.remove(os.path.join(logdir, lf))
        pginst.start_service()
        time.sleep(10)

    @pytest.mark.test_pgbadger
    def test_pgbadger(self, request):
        pginst = request.cls.pginst
        if pginst.edition != 'ent':
            print("pg_badger test is only performed with enterprise edition")
            return
        if pginst.windows:
            print("pg_badger test is not supported on Windows")
            return
        pginst.install_package('pgpro-pgbadger')
        cmd = "pgbadger -V"
        pgbadger_version = subprocess.check_output(cmd, shell=True).strip()
        print(pgbadger_version)
        pginst.exec_psql(
            "CREATE TABLE test (data text)")
        pginst.exec_psql(
            "INSERT INTO test SELECT 'data' FROM generate_series(1, 100);")
        logdir = request.cls.logdir
        pginst.exec_psql("SELECT * FROM test")
        for lf in os.listdir(logdir):
            pgbres = subprocess.check_output(
                'pgbadger --outfile - --extension text --format stderr "%s"' %
                os.path.join(logdir, lf),
                shell=True)
            state = 0
            stats = {}
            for line in pgbres.split('\n'):
                if state != 0:
                    if line.startswith('- '):
                        state = 0
                if state == 0:
                    if line.startswith('- Queries by type -'):
                        state = 1
                elif state == 1:
                    if re.search(r'^Type\s+Count\s+Percentage', line):
                        state = 2
                elif state == 2:
                    tcre = re.search(r'^([^:]+):\s+(\d+)\s', line)
                    if tcre:
                        stats[tcre.group(1)] = int(tcre.group(2))
            print "Query statistics:", stats
            if stats['SELECT'] < 1:
                raise Exception("No SELECT queries catched by pgbadger.")
            if stats['INSERT'] < 1:
                raise Exception("No INSERT queries catched by pgbadger.")
            if stats['DDL'] < 1:
                raise Exception("No DDL queries catched by pgbadger.")
            return
        raise Exception('Log files in "%s" are not found.' % logdir)
