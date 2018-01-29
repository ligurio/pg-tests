# -*- coding: utf-8 -*-

import platform
import subprocess

import pytest

from allure_commons.types import LabelType
from helpers.pginstall import (setup_repo,
                               get_dev_package_name,
                               get_all_packages_name,
                               install_package,
                               install_postgres_win,
                               install_perl_win,
                               initdb_start,
                               get_default_bin_path,
                               exec_psql,
                               restart_service)


@pytest.mark.dev_usage
class TestDevUsage(object):
    """
    Test that performs 'make installcheck' and 'make check'
    for the installed instance.
    """

    system = platform.system()

    @pytest.mark.test_dev_usage
    def test_dev_usage(self, request):
        """
        Scenario:
        1. Install only -dev package
        2. Try to build PGXS extension

        :return:
        """
        dist = ""
        if self.system == 'Linux':
            dist = " ".join(platform.linux_distribution()[0:2])
        elif self.system == 'Windows':
            dist = 'Windows'
            install_perl_win()
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
        setup_repo(name=name, version=version, edition=edition,
                   milestone=milestone, branch=branch)
        print("Running on %s." % target)
        if self.system != 'Windows':
            package_name = get_dev_package_name(name, edition, version)
            install_package(package_name)
            pg_bin_path = get_default_bin_path(name=name,
                                               version=version,
                                               edition=edition)
            test_script = r"""
set -e
if which apt-get; then
    apt-get install -y gcc || true
    apt-get install -y make
    grep -E '(Debian GNU/Linux 9|"Ubuntu 17.10")' /etc/os-release && \
        apt install -y libdpkg-perl
elif which zypper; then
    zypper install -y gcc make
elif which yum; then
    yum install -y gcc make
fi
cd /tmp/
wget https://codeload.github.com/postgrespro/pg_wait_sampling/\
tar.gz/master -O pg_wait_sampling.tar.gz ||
curl https://codeload.github.com/postgrespro/pg_wait_sampling/\
tar.gz/master -o pg_wait_sampling.tar.gz
tar fax pg_wait_sampling* && \
cd pg_wait_sampling*
export PATH=%s:$PATH
make USE_PGXS=1
make USE_PGXS=1 install
chmod 777 .
""" % (pg_bin_path)
            subprocess.check_call(test_script, shell=True)
            package_name = get_all_packages_name(name, edition, version)
            install_package(package_name)
            initdb_start(name=name, version=version, edition=edition)
            exec_psql('ALTER SYSTEM SET shared_preload_libraries = '
                      'pg_wait_sampling')
            restart_service(name=name, version=version, edition=edition)
            test_script = r"""
cd /tmp/pg_wait_sampling*
sudo -u postgres sh -c "export PATH=%s:$PATH; make USE_PGXS=1 installcheck"
""" % (pg_bin_path)
            subprocess.check_call(test_script, shell=True)
        else:
            install_postgres_win()
        print("OK")
