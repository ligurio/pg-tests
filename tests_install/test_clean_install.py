import platform

import pytest
import settings

from allure_commons.types import LabelType
from helpers.pginstall import (setup_repo,
                               get_base_package_name,
                               install_package,
                               initdb_start,
                               install_postgres_win,
                               get_server_version,
                               get_psql_version,
                               get_server_package_name)


@pytest.mark.clean_install
class TestCleanInstall():

    os = ""

    @pytest.mark.test_clean_install
    def test_clean_install(self, request):
        """
        Scenario:
        1. Install current version
        2. Check that setup successfull (select version)

        :return:
        """
        dist = ""
        self.os = platform.system()
        if self.os == 'Linux':
            dist = " ".join(platform.linux_distribution()[0:2])
        elif self.os == 'Windows':
            dist = 'Windows'
        else:
            raise Exception("OS %s is not supported." % self.os)
        version = request.config.getoption('--product_version')
        name = request.config.getoption('--product_name')
        edition = request.config.getoption('--product_edition')
        build = request.config.getoption('--product_build')
        milestone = request.config.getoption('--product_milestone')
        target = request.config.getoption('--target')
        product_info = " ".join([dist, name, edition, version])
        # pylint: disable=no-member
        tag_mark = pytest.allure.label(LabelType.TAG, product_info)
        request.node.add_marker(tag_mark)
        branch = request.config.getoption('--branch')

        # Step 1
        setup_repo(name=name, version=version, edition=edition,
                   milestone=milestone, branch=branch)
        print("Running on %s." % target)
        if dist != 'Windows':
            package_name = get_base_package_name(name, edition, version)
            install_package(package_name)
            initdb_start(name=name, version=version, edition=edition)
        else:
            install_postgres_win()
        server_version = get_server_version()
        client_version = get_psql_version()
        print("Server version:\n%s\nClient version:\n%s" %
              (server_version, client_version))
        print("OK")
