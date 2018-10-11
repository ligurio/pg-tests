import platform
import subprocess

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
        print("cmd:", pgbadger_version)
