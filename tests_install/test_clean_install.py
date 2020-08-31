import platform
import os
import subprocess

import pytest

from allure_commons.types import LabelType
from helpers.pginstall import PgInstall
from helpers.utils import get_distro
import allure


@pytest.mark.clean_install
class TestCleanInstall():

    system = platform.system()

    @pytest.mark.test_clean_install
    def test_clean_install(self, request):
        """
        Scenario:
        1. Install current version
        2. Check that setup successfull (select version)

        :return:
        """
        if self.system == 'Linux':
            dist = " ".join(get_distro()[0:2])
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
        tag_mark = allure.label(LabelType.TAG, product_info)
        request.node.add_marker(tag_mark)
        branch = request.config.getoption('--branch')

        # Step 1
        pginst = PgInstall(product=name, edition=edition,
                           version=version, milestone=milestone,
                           branch=branch, windows=(self.system == 'Windows'))

        request.cls.pginst = pginst
        pginst.setup_repo()
        print("Running on %s." % target)
        print("Minor product version is: %s\n" %
              pginst.get_product_minor_version())
        if self.system != 'Windows':
            pginst.install_base()
            pginst.initdb_start()
        else:
            pginst.install_postgres_win()
        server_version = pginst.get_server_version()
        client_version = pginst.get_psql_version()
        print("Server version:\n%s\nClient version:\n%s" %
              (server_version, client_version))
        print("OK")

    @pytest.mark.test_full_remove
    def test_pg_setup(self, request):
        pginst = request.cls.pginst

        def exec_pg_setup(options=''):
            cmd = '"%spg-setup" %s' % \
                (
                    pginst.get_client_bin_path(),
                    options
                )
            return subprocess.check_output(cmd, shell=True)

        if self.system == 'Windows' or \
                pginst.product != "postgrespro" or \
                pginst.version in ['9.5', '9.6'] or \
                (pginst.version == '9.6' and pginst.edition == '1c'):
            return
        pginst.stop_service()
        os.unlink('/etc/default/postgrespro-%s-%s' %
                  (pginst.alter_edtn, pginst.version))
        exec_pg_setup('initdb -D /tmp/db1')
        exec_pg_setup('service start')
        exec_pg_setup('service status')
        pginst.get_server_version()
        exec_pg_setup('service stop')
