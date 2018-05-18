# -*- coding: utf-8 -*-

import platform
import subprocess
import os
import re

import pytest

from allure_commons.types import LabelType
from helpers.pginstall import PgInstall

PRELOAD_LIBRARIES = {
    'standard-10':
        ['auth_delay', 'auto_explain', 'pg_pathman', 'pg_pageprep',
         'plantuner', 'shared_ispell'],
    'ee-10':
        ['auth_delay', 'auto_explain', 'in_memory', 'pg_pageprep',
         'pgpro_scheduler', 'pg_stat_statements', 'plantuner',
         'shared_ispell', 'pg_wait_sampling', 'pg_shardman',
         'pg_pathman'],
    'standard-9.6':
        ['auth_delay', 'auto_explain', 'pg_pathman', 'pg_pageprep',
         'plantuner', 'shared_ispell'],
    'ee-9.6':
        ['auth_delay', 'auto_explain',
         'pgpro_scheduler', 'pg_stat_statements', 'plantuner',
         'shared_ispell', 'pg_wait_sampling', 'pg_pathman'],
    'cert-enterprise-9.6':
        ['auth_delay', 'auto_explain',
         'pgpro_scheduler', 'pg_stat_statements', 'plantuner',
         'shared_ispell', 'pg_wait_sampling', 'pg_pathman'],
    'cert-enterprise-10':
        ['auth_delay', 'auto_explain', 'in_memory', 'pgaudit',
         'pgpro_scheduler', 'pg_stat_statements', 'plantuner',
         'shared_ispell', 'pg_wait_sampling', 'pg_shardman',
         'pg_pathman'],
    '1c-10':
        ['auth_delay', 'auto_explain', 'plantuner'],
}


@pytest.mark.make_check
class TestMakeCheck(object):
    """
    Test that performs 'make installcheck' and 'make check'
    for the installed instance.
    """

    system = platform.system()

    @pytest.mark.test_make_check
    def test_make_check(self, request):
        """
        Scenario:
        1. Install current version
        2. Check that setup successfull

        :return:
        """
        dist = ""
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
        pgid = '%s-%s' % (edition, version)
        # pylint: disable=no-member
        tag_mark = pytest.allure.label(LabelType.TAG, product_info)
        request.node.add_marker(tag_mark)
        branch = request.config.getoption('--branch')

        # Step 1
        pginst = PgInstall(product=name, edition=edition,
                           version=version, milestone=milestone,
                           branch=branch, windows=(self.system == 'Windows'))
        request.cls.pginst = pginst
        pginst.make_check_passed = False
        pginst.setup_repo()
        print("Running on %s." % target)
        pginst.download_source()
        if self.system != 'Windows':
            pginst.install_full()
            pginst.initdb_start()
        else:
            pginst.install_postgres_win(port=55432)
        pginst.exec_psql("ALTER SYSTEM SET shared_preload_libraries = %s" %
                         ','.join(PRELOAD_LIBRARIES[pgid]))
        pginst.exec_psql("ALTER SYSTEM SET max_worker_processes = 16")
        pginst.restart_service()
        cmd = '"%s" --bindir' % os.path.join(pginst.get_default_bin_path(),
                                             'pg_config')
        binpath = subprocess.check_output(cmd, shell=True).strip()
        pg_prefix = re.sub('bin$', '', binpath)
        curpath = os.path.dirname(os.path.abspath(__file__))
        if self.system != 'Windows':
            subprocess.check_call(
                '"%s" "%s"' % (os.path.join(curpath, 'make_installcheck.sh'),
                               pg_prefix),
                shell=True)
            pginst.make_check_passed = True
        else:
            subprocess.check_call(
                '"%s" "%s"' % (os.path.join(curpath, 'make_installcheck.cmd'),
                               pg_prefix),
                shell=True)
            pginst.make_check_passed = True

    @pytest.mark.test_sqlsmith
    def test_sqlsmith(self, request):
        pginst = request.cls.pginst
        if not pginst.make_check_passed:
            print("sqlsmith test skipped (make_check hasn't passed)")
            return
        pginst.exec_psql("CREATE ROLE tester LOGIN PASSWORD 'test'")
        pginst.exec_psql("GRANT ALL ON DATABASE regression TO tester")
        pg_prefix = pginst.get_default_pg_prefix()
        curpath = os.path.dirname(os.path.abspath(__file__))
        if self.system != 'Windows':
            subprocess.check_call(
                '"%s" "%s"' % (os.path.join(curpath, 'sqlsmith.sh'),
                               pg_prefix),
                shell=True)
