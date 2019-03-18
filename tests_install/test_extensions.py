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
            pginst.install_full()
            pginst.initdb_start()
        else:
            pginst.install_postgres_win()

    @pytest.mark.test_pgbadger_prepare
    def test_pgbadger_prepare(self, request):
        pginst = request.cls.pginst
        pginst.exec_psql("ALTER SYSTEM SET log_min_duration_statement = 0")
        pginst.exec_psql("ALTER SYSTEM SET lc_messages = 'C'")
        logcol = pginst.exec_psql_select('SHOW logging_collector')
        if logcol == 'on':
            logdir = pginst.exec_psql_select('SHOW log_directory')
            if not os.path.isabs(logdir):
                datadir = pginst.exec_psql_select('SHOW data_directory')
                logdir = os.path.join(datadir, logdir)
        else:
            request.cls.logdir = None  # PGPRO-2048
            print("Test skipped because logging_collector is disabled.")
            return
        request.cls.logdir = logdir
        pginst.stop_service()
        for lf in os.listdir(logdir):
            os.remove(os.path.join(logdir, lf))
        pginst.start_service()

    @pytest.mark.test_pgbadger
    def test_pgbadger(self, request):
        logdir = request.cls.logdir
        if logdir is None:
            return
        pginst = request.cls.pginst
        if pginst.edition != 'ent':
            print("pg_badger test is only performed with enterprise edition")
            return
        # PGPRO-2225
        if pginst.version == '9.6':
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
            if 'SELECT' not in stats or stats['SELECT'] < 1:
                raise Exception("No SELECT queries catched by pgbadger.")
            if 'INSERT' not in stats or stats['INSERT'] < 1:
                raise Exception("No INSERT queries catched by pgbadger.")
            if 'DDL' not in stats or stats['DDL'] < 1:
                raise Exception("No DDL queries catched by pgbadger.")
            return
        raise Exception('Log files in "%s" are not found.' % logdir)

    @pytest.mark.test_sr_plan
    def test_sr_plan(self, request):
        return
        pginst = request.cls.pginst
        if pginst.edition != 'ent' and pginst.edition != 'std':
            print("sr_plan & pg_stat_statements test is only performed "
                  "with standard and enterprise edition")
            return
        pginst.exec_psql("ALTER SYSTEM SET shared_preload_libraries = "
                         "pg_stat_statements, sr_plan")
        pginst.stop_service()
        pginst.start_service()
        pginst.exec_psql("CREATE EXTENSION pg_stat_statements;")
        pginst.exec_psql("ALTER SYSTEM SET pg_stat_statements.track = 'all'")
        pginst.exec_psql("ALTER SYSTEM SET pg_stat_statements.save = true")
        pginst.stop_service()
        pginst.start_service()
        pginst.exec_psql("SELECT pg_stat_statements_reset()")
        pginst.exec_psql("SELECT 'test string'")
        pgs_count = pginst.exec_psql_select(
            "SELECT COUNT(1) FROM pg_stat_statements")
        if int(pgs_count) == 0:
            raise Exception("No statements recorded in pg_stat_statements "
                            "(due to conflict with sr_plan)")
