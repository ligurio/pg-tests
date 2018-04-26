set -x
if grep 'ALT Linux 6\.' /etc/altlinux-release || \
   grep 'PRETTY_NAME="ALT Linux 7' /etc/os-release || \
   grep 'PRETTY_NAME="Astra Linux (Smolensk 1.5)"' /etc/os-release || \
   grep 'PRETTY_NAME="Debian GNU/Linux 7' /etc/os-release || \
   grep 'PRETTY_NAME="SUSE Linux Enterprise Server 11' /etc/os-release || \
   grep 'GosLinux release 6' /etc/goslinux-release || \
   grep 'ROSA Enterprise Linux Server release 6.6' /etc/system-release || \
   grep 'CentOS release 6.7' /etc/system-release || \
   grep 'cpe:/o:msvsphere:msvsphere:6server' /etc/system-release-cpe; \
then
    echo 'C++11 is not present on this platform. Test skipped.'
    exit 0
fi
if which apt-get; then
    apt-get install -y build-essential pkg-config autoconf
    apt-get install -y autoconf-archive
    apt-get install -y libboost-regex-dev
    if grep 'PRETTY_NAME="Ubuntu 14\.04' /etc/os-release; then
         CONF_OPTIONS="--with-boost-libdir=/usr/lib/x86_64-linux-gnu"
    fi
    if grep 'PRETTY_NAME="ALT 8' /etc/os-release; then
        apt-get install -y gcc5-c++ autoconf_2.60 automake_1.14 \
        boost-regex-devel
    fi
elif which zypper; then
    zypper install -y gcc-c++
    zypper install -y boost-devel
    wget http://download.opensuse.org/distribution/\
openSUSE-stable/repo/oss/suse/noarch/autoconf-archive-2016.03.20-3.3.noarch.rpm
    rpm -i autoconf-archive-2016.03.20-3.3.noarch.rpm
elif which yum; then
    yum install -y autoconf autoconf-archive automake >/dev/null
    yum install -y gcc-c++ >/dev/null
    yum install -y boost-devel >/dev/null

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
export PATH=$1/bin:$PATH
cd ~test/pg-tests
curl --tlsv1.2 -sS -L https://github.com/jtv/libpqxx/archive/6.1.0.tar.gz \
    -o libpqxx.tar.gz || \
wget https://github.com/jtv/libpqxx/archive/6.1.0.tar.gz -O libpqxx.tar.gz
tar fax libpqxx.tar.gz
cd libpqxx*
./configure --disable-documentation && make && make install

cd ~test/pg-tests
curl --tlsv1.2 -sS -L https://github.com/anse1/sqlsmith/archive/master.tar.gz \
    -o ss.tar.gz || \
wget https://github.com/anse1/sqlsmith/archive/master.tar.gz -O ss.tar.gz
tar fax ss.tar.gz
cd sqlsmith*
sed -i -e 's/\$(PQXX_CFLAGS)/\$(LIBPQXX_CFLAGS)/' Makefile.am # https://github.com/anse1/sqlsmith/issues/19
autoreconf -i
sed -i -e 's|/\* re-throw to outer loop to recover session. \*/|return 1;|' sqlsmith.cc
PKG_CONFIG_PATH=/usr/local/lib/pkgconfig/:$1/lib/pkgconfig/ \
LIBPQXX_LIBS="-L$1/lib -lpqxx -lpq" ./configure $CONF_OPTIONS && make
LD_LIBRARY_PATH=$1/lib \
./sqlsmith --max-queries=10000 --dump-all-queries --verbose \
--target="host=localhost dbname=regression user=tester password=test" >../sqlsmith.log 2>&1
