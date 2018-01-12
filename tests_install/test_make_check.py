# -*- coding: utf-8 -*-

import platform
import subprocess

import pytest

from allure_commons.types import LabelType
from helpers.pginstall import (setup_repo,
                               install_package,
                               install_postgres_win,
                               install_perl_win,
                               download_source,
                               exec_psql,
                               restart_service)

PRELOAD_LIBRARIES = {
    'standard':
        ['auth_delay', 'auto_explain', 'pg_pathman', 'plantuner',
         'shared_ispell'],
    'ee':
        ['auth_delay', 'auto_explain', 'in_memory', 'pg_pathman',
         'pgpro_scheduler', 'plantuner', 'shared_ispell'],
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
        edtn = ''
        if edition:
            if edition == 'standard':
                edtn = 'std'
            elif edition == 'ee':
                edtn = 'ent'
            else:
                raise Exception('Edition %s is not supported.' % edition)
        print("Running on %s." % target)
        if self.system != 'Windows':
            install_package('%s-%s-%s*' % (name, edtn, version))
            exec_psql("ALTER SYSTEM SET shared_preload_libraries = %s" %
                      ','.join(PRELOAD_LIBRARIES[edition]))
            restart_service(name=name, version=version, edition=edition)
            download_source(name=name, version=version, edition=edition,
                            milestone=milestone, branch=branch)
# TODO: Enable test5 (PGPRO-1289)
# TODO: Don't update tzdata on mssphere (PGPRO-1293)
            test_script = r"""
if which apt-get; then
    apt-get install -y gcc || true
    apt-get install -y make flex bison perl
    apt-get install -y zlib1g-dev || apt-get install -y zlib-devel
    apt-get install -y libipc-run-perl || apt-get install -y perl-IPC-Run
    apt-get install -y perl-devel || true
elif which zypper; then
    zypper install -y gcc make flex bison perl zlib1g-dev
    zypper install -y libipc-run-perl
elif which yum; then
    yum install -y gcc make flex bison perl bzip2 zlib-devel
    yum install -y perl-devel || true
    yum install -y perl-IPC-Run perl-Test-Simple perl-Time-HiRes
    # perl-IPC-Run is not present in some distributions (rhel-7, rosa-sx-7...)
    if ! perl -e "use IPC::Run"; then
        curl -O https://cpan.metacpan.org/authors/id/T/TO/TODDR/\
IPC-Run-0.96.tar.gz &&
        tar fax IPC-Run*
        (cd IPC-Run*; perl Makefile.PL && make && make install)
    fi
fi
# timestamptz fails on msvsphere due to old tzdata
if [ "`cat /etc/msvsphere-release`" = "МСВСфера Сервер release 6.3" ]; then
    curl -O http://mirror.centos.org/centos/6/os/x86_64/Packages/\
tzdata-2016j-1.el6.noarch.rpm
    yum install -y tzdata-*.rpm
fi

chmod 777 ~test
cd ~test/pg-tests
tar fax postgrespro*.tar*

cd postgres*/

# vvv test5 Fails
rm src/interfaces/ecpg/test/connect/test5*
sed -e 's/\(\s*test5\s\+test5\)/#\1/' \
 -i src/interfaces/ecpg/test/connect/Makefile
sed -e 's/test:\s\+connect\/test5//' \
 -i src/interfaces/ecpg/test/ecpg_schedule_tcp
sed -e 's/test:\s\+connect\/test5//' \
 -i src/interfaces/ecpg/test/ecpg_schedule
# ^^^ test5 Fails

PREFIX=$(readlink -f `pg_config --bindir`/..)
sudo chown -R postgres:postgres .
sudo -u postgres ./configure --enable-tap-tests --without-readline \
 --prefix=$PREFIX
sudo -u postgres make -C src/interfaces/ecpg # TODO: remove?
sudo -u postgres make installcheck-world
"""
            subprocess.check_call(test_script, shell=True)
        else:
            install_postgres_win()
        print("OK")
