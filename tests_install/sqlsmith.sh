set -x
if grep -q 'PRETTY_NAME="ALT Linux 7' /etc/os-release || \
   grep -q 'PRETTY_NAME="Astra Linux (Smolensk 1.5)"' /etc/os-release || \
   grep -q 'cpe:/o:msvsphere:msvsphere:6server' /etc/system-release-cpe; \
then
    echo 'C++11 is not present on this platform. Test skipped.'
    exit 0
fi
if which apt-get; then
    apt-get install -y build-essential pkg-config autoconf
    apt-get install -y autoconf-archive
    apt-get install -y libtool
    apt-get install -y libboost-regex-dev
    apt-get install -y wget
    apt-get install -y gcc-c++
    apt-get install -y boost-regex-devel
    apt-get install -y gcc5-c++
    if grep 'PRETTY_NAME="ALT 8' /etc/os-release; then
        apt-get install -y autoconf_2.60 automake_1.14 libtool_2.4
        if grep 'VERSION_ID=8.2' /etc/os-release; then
          wget http://dist.l.postgrespro.ru/resources/linux/centos-7/\
autoconf-archive-2017.03.21-1.el7.noarch.rpm
          rpm -i autoconf-archive*.noarch.rpm
        fi
    fi
elif which zypper; then
    zypper install -y gcc-c++
    zypper install -y boost-devel
    if grep -q 'PRETTY_NAME="SUSE Linux Enterprise Server 12' /etc/os-release; then
      wget http://download.opensuse.org/distribution/\
openSUSE-stable/repo/oss/noarch/autoconf-archive-2017.09.28-lp152.3.2.noarch.rpm
      rpm -i autoconf-archive*.noarch.rpm
    else
      zypper install -y autoconf autoconf-archive automake
      zypper install -y libboost_regex*
    fi
elif which yum; then
    yum install -y autoconf automake >/dev/null
    yum install -y libtool >/dev/null
    yum install -y gcc-c++ >/dev/null
    yum install -y boost-devel >/dev/null
    yum install -y autoconf-archive >/dev/null || \
    if grep -q '\(Red Hat\|ROSA\) Enterprise Linux \(Server \|Cobalt \|\)release \(7\|8\)'\
     /etc/redhat-release || \
       grep -q 'CentOS Linux release 8.' /etc/redhat-release; then
        yum install -y http://dist.l.postgrespro.ru/resources/linux/centos-7/\
autoconf-archive-2017.03.21-1.el7.noarch.rpm
    fi
fi
export PATH=$1/bin:$PATH
cd ~test/pg-tests
basedir=`pwd`
curl --tlsv1.2 -sS -L https://github.com/jtv/libpqxx/archive/6.1.0.tar.gz \
    -o libpqxx.tar.gz || \
wget https://github.com/jtv/libpqxx/archive/6.1.0.tar.gz -O libpqxx.tar.gz
tar fax libpqxx.tar.gz
cd libpqxx*/
if which python3 >/dev/null 2>&1; then
  sed -e 's|^#! /usr/bin/env python$|#! /usr/bin/env python3|' -i tools/splitconfig tools/*.py # https://github.com/jtv/libpqxx/commit/c6cb952f
fi
autoreconf -fi
CXXFLAGS="-std=c++11" ./configure --prefix=$basedir/libpqxx --disable-documentation && make && make install
cd ~test/pg-tests
curl --tlsv1.2 -sS -L https://github.com/anse1/sqlsmith/archive/2dc83ee8.tar.gz \
    -o ss.tar.gz || \
wget https://github.com/anse1/sqlsmith/archive/2dc83ee8.tar.gz -O ss.tar.gz
tar fax ss.tar.gz
cd sqlsmith*/
sed -e 's|\[m4_esyscmd_s(\[git describe --dirty --tags --always\])\]|1|' -i configure.ac # To do with old autoconf and without git
autoreconf -i
sed -e 's|char conninfo="dbname = postgres";|char conninfo[]="dbname = postgres";|' -i configure # https://github.com/autoconf-archive/autoconf-archive/pull/158
PKG_CONFIG_PATH=$basedir/libpqxx/lib/pkgconfig/:$1/lib/pkgconfig/ \
LIBPQXX_LIBS="-L$1/lib -L$basedir/libpqxx/lib -lpqxx -lpq" ./configure $CONF_OPTIONS || exit 1
[ -f gitrev.h ] || echo "#define GITREV \"1\"" >gitrev.h # To do without git
sed -i -e 's|/\* re-throw to outer loop to recover session. \*/|return 1;|' sqlsmith.cc
make || exit $?
LD_LIBRARY_PATH=$1/lib \
./sqlsmith --max-queries=10000 --dump-all-queries --verbose \
--target="host=localhost dbname=regression user=tester password=test" >../sqlsmith.log 2>&1
result=$?
if [ $result -ne 0 ]; then
  echo "sqlsmith failed (see sqlsmith.log):"
  tail -500 ../sqlsmith.log
  exit $result
fi
