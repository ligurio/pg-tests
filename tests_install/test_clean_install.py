import platform

import pytest

from allure_commons.types import LabelType
from helpers.pginstall import PgInstall


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

        pginst.setup_repo()
        print("Running on %s." % target)
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
