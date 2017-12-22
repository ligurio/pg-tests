import os
import platform
import subprocess

import pytest
import settings

from allure_commons.types import LabelType
from helpers.pginstall import setup_repo
from helpers.pginstall import install_package
from helpers.pginstall import install_postgres_win
from helpers.pginstall import get_server_version
from helpers.pginstall import get_psql_version


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
        edtn = ''
        if edition:
            if edition == 'standard':
                edtn = 'std'
            else:
                raise Exception('Edition %s is not supported.')
        print("Running on %s." % target)
        if dist != 'Windows':
            install_package('%s-%s-%s' % (name, edtn, version))
        else:
            install_postgres_win()
        server_version = get_server_version()
        client_version = get_psql_version()
        print("Server version:\n%s\nClient version:\n%s" %
              (server_version, client_version))
        print("OK")
