# -*- coding: utf-8 -*-

import platform
import subprocess

import pytest

from allure_commons.types import LabelType
from helpers.pginstall import PgInstall

PRELOAD_LIBRARIES = {
    'standard-10':
        ['auth_delay', 'auto_explain', 'pg_pathman', 'plantuner',
         'shared_ispell'],
    'ee-10':
        ['auth_delay', 'auto_explain', 'in_memory',
         'pgpro_scheduler', 'pg_stat_statements', 'plantuner',
         'shared_ispell', 'pg_wait_sampling', 'pg_shardman',
         'pg_pathman'],
    'ee-9.6':
        ['auth_delay', 'auto_explain',
         'pgpro_scheduler', 'pg_stat_statements', 'plantuner',
         'shared_ispell', 'pg_wait_sampling', 'pg_pathman'],
    'cert-enterprise-9.6':
        ['auth_delay', 'auto_explain',
         'pgpro_scheduler', 'pg_stat_statements', 'plantuner',
         'shared_ispell', 'pg_wait_sampling', 'pg_pathman'],
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
        pginst.setup_repo()
        print("Running on %s." % target)
        if self.system != 'Windows':
            pginst.install_full()
            pginst.initdb_start()
            pginst.exec_psql("ALTER SYSTEM SET shared_preload_libraries = %s" %
                             ','.join(PRELOAD_LIBRARIES[pgid]))
            pginst.restart_service()
            pginst.download_source()
            pg_prefix = pginst.get_default_pg_prefix()
# TODO: Enable test5 (PGPRO-1289)
            test_script = r"""
if which apt-get; then
    apt-get install -y gcc || true
    apt-get install -y make flex bison perl
    apt-get install -y zlib1g-dev || apt-get install -y zlib-devel
    apt-get install -y libipc-run-perl || apt-get install -y perl-IPC-Run
    apt-get install -y perl-devel || true
elif which zypper; then
    zypper install -y gcc make flex bison perl
    zypper install -y --force --force-resolution zlib-devel
    zypper install -y libipc-run-perl
elif which yum; then
    yum install -y gcc make flex bison perl bzip2 zlib-devel
    yum install -y perl-devel || true
    yum install -y perl-IPC-Run perl-Test-Simple perl-Time-HiRes
    # perl-IPC-Run is not present in some distributions (rhel-7, rosa-sx-7...)
fi
if ! perl -e "use IPC::Run"; then
    curl -O http://cpan.metacpan.org/authors/id/T/TO/TODDR/\
IPC-Run-0.96.tar.gz && \
    tar fax IPC-Run* && \
    (cd IPC-Run* && perl Makefile.PL && make && make install)
fi

if grep 'SUSE Linux Enterprise Server 11' /etc/SuSE-release; then
    # Update Test::More to minimum required version (0.82)
    curl https://codeload.github.com/Test-More/test-more/tar.gz/v0.82 \
     -o test-more.tar.gz && \
    tar fax test-more* && \
    (cd test-more* && perl Makefile.PL && make && make install)
fi

chmod 777 ~test
cd ~test/pg-tests
tar fax postgrespro*.tar*

cd postgres*/

# vvv test5 Fails
if [ -d src/interfaces/ecpg/test/connect ]; then
    rm src/interfaces/ecpg/test/connect/test5*
    sed -e 's/\(\s*test5\s\+test5\)/#\1/' \
     -i src/interfaces/ecpg/test/connect/Makefile
    [ -f src/interfaces/ecpg/test/ecpg_schedule_tcp ] && \
    sed -e 's/test:\s\+connect\/test5//' \
     -i src/interfaces/ecpg/test/ecpg_schedule_tcp
    sed -e 's/test:\s\+connect\/test5//' \
     -i src/interfaces/ecpg/test/ecpg_schedule
fi
# ^^^ test5 Fails

if grep 'SUSE Linux Enterprise Server 11' /etc/SuSE-release; then
  # To workaround an "internal compiler error"
  sed 's/log10(2)/0.3010/' -i src/interfaces/ecpg/compatlib/informix.c
fi

sudo chown -R postgres:postgres .
sudo -u postgres ./configure --enable-tap-tests --without-readline \
 --prefix=%s
sudo -u postgres make -C src/interfaces/ecpg # TODO: remove?
sudo -u postgres make installcheck-world
""" % (pg_prefix)
            subprocess.check_call(test_script, shell=True)
        else:
            pginst.install_perl_win()
            pginst.install_postgres_win()

    @pytest.mark.test_sqlsmith
    def test_sqlsmith(self, request):
        pginst = request.cls.pginst
        pginst.exec_psql("CREATE ROLE tester LOGIN PASSWORD 'test'")
        pginst.exec_psql("GRANT ALL ON DATABASE regression TO tester")
        pg_prefix = pginst.get_default_pg_prefix()
        if self.system != 'Windows':
            test_script = r"""
set -x
if grep 'ALT Linux 6\.' /etc/altlinux-release || \
   grep 'PRETTY_NAME="ALT Linux 7' /etc/os-release || \
   grep 'PRETTY_NAME="Astra Linux (Smolensk 1.5)"' /etc/os-release || \
   grep 'PRETTY_NAME="Debian GNU/Linux 7' /etc/os-release || \
   grep 'GosLinux release 6' /etc/goslinux-release || \
   grep 'PRETTY_NAME="SUSE Linux Enterprise Server 11' /etc/os-release || \
   grep 'cpe:/o:msvsphere:msvsphere:6server' /etc/system-release-cpe; \
then
    echo 'C++11 is not present on this platform. Test skipped.'
    exit 0
fi
if which apt-get; then
    apt-get install -y build-essential autoconf autoconf-archive pkg-config
    apt-get install -y libboost-regex-dev
    if grep 'PRETTY_NAME="Ubuntu 14\.04' /etc/os-release; then
         CONF_OPTIONS="--with-boost-libdir=/usr/lib/x86_64-linux-gnu"
    fi
elif which zypper; then
    zypper install -y gcc-c++
    zypper install -y boost-devel
    wget https://download.opensuse.org/repositories/devel:/tools:/building/\
SLE_12_SP1/noarch/autoconf-archive-2017.09.28-44.1.noarch.rpm
    rpm -i autoconf-archive-2017.09.28-44.1.noarch.rpm
elif which yum; then
    yum install -y autoconf autoconf-archive automake
    yum install -y gcc-c++
    yum install -y boost-devel

    if grep '\(Red Hat\|ROSA\) Enterprise Linux Server release 6' \
        /etc/redhat-release; then
        wget -qO- http://people.redhat.com/bkabrda/scl_python27.repo >> \
            /etc/yum.repos.d/scl.repo
        yum install -y python27

        yum install -y \
            http://mirror.centos.org/centos/6/sclo/x86_64/rh/devtoolset-3/\
devtoolset-3-gcc-c++-4.9.2-6.2.el6.x86_64.rpm \
            http://mirror.centos.org/centos/6/sclo/x86_64/rh/devtoolset-3/\
devtoolset-3-gcc-4.9.2-6.2.el6.x86_64.rpm \
            http://mirror.centos.org/centos/6/sclo/x86_64/rh/devtoolset-3/\
devtoolset-3-runtime-3.1-12.el6.x86_64.rpm \
            http://mirror.centos.org/centos/6/sclo/x86_64/rh/devtoolset-3/\
devtoolset-3-libstdc++-devel-4.9.2-6.2.el6.x86_64.rpm \
            http://mirror.centos.org/centos/6/sclo/x86_64/rh/devtoolset-3/\
devtoolset-3-binutils-2.24-18.el6.x86_64.rpm

        source /opt/rh/devtoolset-3/enable
        source /opt/rh/python27/enable
        yum install -y http://mirrors.isu.net.sa/pub/fedora/fedora-epel/\
6/x86_64/autoconf-archive-2012.09.08-1.el6.noarch.rpm
    fi

    if grep '\(Red Hat\|ROSA\) Enterprise Linux \(Server\|Cobalt\) release 7'\
     /etc/redhat-release; then
        yum install -y http://mirror.centos.org/centos/\
7/os/x86_64/Packages/autoconf-archive-2017.03.21-1.el7.noarch.rpm
    fi

    if grep 'CentOS release 6.7' /etc/redhat-release; then
        yum install -y centos-release-scl
        yum install -y devtoolset-3-toolchain python27
        source /opt/rh/devtoolset-3/enable
        ln -s /usr/local/bin/python2.7 /usr/local/bin/python
        export PATH=/usr/local/bin:$PATH
        yum install -y http://mirrors.isu.net.sa/pub/fedora/fedora-epel/\
6/x86_64/autoconf-archive-2012.09.08-1.el6.noarch.rpm
    fi
fi
cd ~test/pg-tests
curl --tlsv1.2 -sS -L https://github.com/jtv/libpqxx/archive/6.1.0.tar.gz \
    -o libpqxx.tar.gz || \
wget https://github.com/jtv/libpqxx/archive/6.1.0.tar.gz -O libpqxx.tar.gz
tar fax libpqxx.tar.gz
cd libpqxx*
PATH={0}/bin:$PATH ./configure --disable-documentation && make && make install

cd ~test/pg-tests
curl --tlsv1.2 -sS -L https://github.com/anse1/sqlsmith/archive/v1.0.tar.gz \
    -o sqlsmith.tar.gz || \
wget https://github.com/anse1/sqlsmith/archive/v1.0.tar.gz -O sqlsmith.tar.gz
tar fax sqlsmith.tar.gz
cd sqlsmith*
autoreconf -i
PKG_CONFIG_PATH=/usr/local/lib/pkgconfig/:{0}/lib/pkgconfig/ \
LIBPQXX_LIBS="-L{0}/lib -lpqxx -lpq" ./configure $CONF_OPTIONS && make
LD_LIBRARY_PATH={0}/lib \
./sqlsmith --max-queries=10000 --verbose \
--target="host=localhost dbname=regression user=tester password=test"
""".format(pg_prefix)
            subprocess.check_call(test_script, shell=True)
