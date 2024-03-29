import platform
import os
import subprocess

from allure_commons.types import LabelType
from helpers.pginstall import PgInstall
from helpers.utils import get_distro
import allure
import shutil

tempdir = os.path.join(os.path.abspath(os.getcwd()), 'tmp')


class TestCleanInstall():

    system = platform.system()

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

    def test_pg_setup(self, request):
        pginst = request.cls.pginst

        if self.system == 'Windows' or \
                pginst.product != "postgrespro" or \
                pginst.version in ['9.5', '9.6'] or \
                (pginst.version == '9.6' and pginst.edition == '1c'):
            return
        pginst.stop_service()
        os.unlink('/etc/default/postgrespro-%s-%s' %
                  (pginst.alter_edtn, pginst.version))
        dbpath = os.path.join(tempdir, 'db1')
        if os.path.isdir(dbpath):
            shutil.rmtree(dbpath, True)
        pginst.exec_pg_setup('initdb -D "%s"' % dbpath)
        pginst.exec_pg_setup('service start')
        pginst.exec_pg_setup('service status')
        pginst.get_server_version()
        pginst.exec_pg_setup('service stop')
