# -*- coding: utf-8 -*-

import platform
import subprocess

import pytest

from allure_commons.types import LabelType
from helpers.pginstall import PgInstall


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
            pginst.install_server_dev()
            pg_bin_path = pginst.get_default_bin_path()
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
cd pg_wait_sampling*/
export PATH=%s:$PATH
make USE_PGXS=1
make USE_PGXS=1 install
chmod 777 .
""" % (pg_bin_path)
            subprocess.check_call(test_script, shell=True)
            pginst.install_full()
            pginst.initdb_start()
            pginst.exec_psql(
                'ALTER SYSTEM SET shared_preload_libraries = '
                'pg_wait_sampling')
            pginst.restart_service()
            test_script = r"""
cd /tmp/pg_wait_sampling*/
sudo -u postgres sh -c "export PATH=%s:$PATH; make USE_PGXS=1 installcheck"
""" % (pg_bin_path)
            subprocess.check_call(test_script, shell=True)
        else:
            pginst.install_postgres_win()
            pginst.install_perl_win()
        print("OK")
