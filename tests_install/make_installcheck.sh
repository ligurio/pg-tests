#!/bin/bash

# TODO: Enable test5 (PGPRO-1289)
if which apt-get >/dev/null 2>&1; then
    apt-get install -y gcc || true
    apt-get install -y make flex bison perl
    apt-get install -y zlib1g-dev || apt-get install -y zlib-devel
    apt-get install -y libicu-dev || true
    apt-get install -y libicu-devel || true
    apt-get install -y pkg-config
    apt-get install -y libipc-run-perl || apt-get install -y perl-IPC-Run
    apt-get install -y patch || true
    apt-get install -y perl-devel || true
    apt-get install -y perl-bignum || true
elif which zypper >/dev/null 2>&1; then
    zypper install -y gcc make flex bison perl patch
    zypper install -y --force --force-resolution zlib-devel
    zypper install -y --force --force-resolution libicu-devel
    zypper install -y libipc-run-perl
elif which yum >/dev/null 2>&1; then
    yum install -y gcc make flex bison perl bzip2 zlib-devel libicu-devel patch
    yum install -y perl-devel || true
    yum install -y perl-IPC-Run
    yum install -y perl-Test-Simple perl-Time-HiRes
    # perl-IPC-Run is not present in some distributions (rhel-7, rosa-sx-7...)
fi
if ! perl -e "use IPC::Run"  >/dev/null 2>&1; then
    curl -O http://cpan.metacpan.org/authors/id/T/TO/TODDR/\
IPC-Run-0.96.tar.gz && \
    tar fax IPC-Run* && \
    (cd IPC-Run*/ && perl Makefile.PL && make && make install)
fi

if [ -d ~test/pg-tests ]; then
    chmod 777 ~test
    cd ~test/pg-tests
fi

if grep 'SUSE Linux Enterprise Server 11' /etc/SuSE-release >/dev/null 2>&1; then
    # Update Test::More to minimum required version (0.87)
    tar fax extras/test-more* && \
    (cd test-more*/ && perl Makefile.PL && make && make install)
fi

tar fax postgres*.tar*

cd postgres*/
echo 'The source archive buildinfo:'
cat doc/buildinfo.txt

if grep 'SUSE Linux Enterprise Server' /etc/SuSE-release >/dev/null 2>&1; then #PGPRO-1294
    patch -p0 -i ../patches/SUSE-postgresql-regress.patch
fi

sudo chown -R postgres:postgres .
if ./configure --help | grep '  --enable-svt5'; then
    chown -R postgres:postgres $1
    extraoption="--enable-svt5"
    if which apt-get >/dev/null 2>&1; then
        apt-get install -y fuse
        apt-get install -y fuse-devel || apt-get install -y libfuse-dev || apt-get install -y libfuse-devel
        apt-get install -y libssl-devel
    elif which yum >/dev/null 2>&1; then
        yum install -y fuse fuse-devel
        yum install -y openssl-devel
    elif which zypper >/dev/null 2>&1; then
        zypper install -y fuse fuse-devel
        zypper install -y openssl-devel
        chmod 666 /dev/fuse
    fi
    getent group fuse && usermod -a -G fuse postgres

    if ! perl -e "use Fuse" >/dev/null 2>&1; then
        (
        cd ..
        if which wget >/dev/null 2>&1; then
        wget http://www.cpan.org/authors/id/D/DP/DPATES/Fuse-0.16.tar.gz
        else
        curl -O http://www.cpan.org/authors/id/D/DP/DPATES/Fuse-0.16.tar.gz
        fi
        tar fax Fuse* && \
        cd Fuse*/ && perl Makefile.PL && make && make install
        )
    fi
fi
# PGPRO-1678
sed -s 's|logging_collector = on|# logging_collector = off|' -i `$1/bin/pg_config --sharedir`/postgresql.conf.sample

makeecpg=true
if patch -p1 --dry-run -i ../patches/make-installcheck-11.patch >/dev/null 2>&1; then
    echo "Fixing Makefiles v11 for installcheck-world..."
    patch -p1 -i ../patches/make-installcheck-11.patch
    makeecpg=false
fi
if patch -p1 --dry-run -i ../patches/make-installcheck-10.patch >/dev/null 2>&1; then
    echo "Fixing Makefiles v10 for installcheck-world..."
    patch -p1 -i ../patches/make-installcheck-10.patch
    makeecpg=false
fi

# Backpatch 69ae9dcb to version 11 (pgsql-bugs #15349) (uri-regress.c: undefined reference to PQconninfoParse, PQconndefaults)
patch -p1 --dry-run -i ../patches/69ae9dcb.patch >/dev/null 2>&1 && patch -p1 -i ../patches/69ae9dcb.patch

set -o pipefail
sudo -u postgres ./configure --enable-tap-tests --without-readline --prefix=$1 $extraoption || exit $?

# Pass to `make installcheck` all the options (with-*, enable-*), which were passed to configure
confopts="python_majorversion=2"
opts=`$1/bin/pg_config --configure | grep -Eo "'[^']*'|[^' ]*" | sed -e "s/^'//" -e "s/'$//"`
while read -r opt;
    do case "$opt" in --with-*=*) ;; --with-* | --enable-*) opt="${opt/#--/}"; opt="${opt//-/_}" confopts="$confopts $opt=yes ";; esac;
done <<< "$opts";

[ "$makeecpg" = true ] && sudo -u postgres sh -c "make -C src/interfaces/ecpg"
echo "Running: $confopts make -e installcheck-world ..."
sudo -u postgres sh -c "PATH=\"$1/bin:$PATH\" $confopts make -e installcheck-world EXTRA_TESTS=numeric_big 2>&1" | tee /tmp/installcheck.log; exitcode=$?
if [ $exitcode -eq 0 ]; then
    if [ -f ../plv8*.tar* ]; then
        (
        cd .. &&
        tar fax plv8*.tar* &&
        cd plv8*/ && sudo chown -R postgres . &&
        sudo -u postgres make installcheck; exitcode=$?
        )
    fi
fi
if [ $exitcode -eq 0 ]; then
    # Extra tests
    sudo -u postgres $1/bin/initdb -D tmpdb
    printf "\n
port=25432\n
autovacuum=off\n
old_snapshot_threshold=0\n
max_replication_slots=4\n
wal_level=logical\n
max_prepared_transactions=10\n" >> tmpdb/postgresql.conf
    sudo -u postgres $1/bin/pg_ctl -D tmpdb -l tmpdb.log -w start
    eval `sudo -u postgres $1/bin/initdb -s -D . 2>&1 | grep share_path` &&
    cp src/test/modules/test_pg_dump/test_pg_dump*.{control,sql} $share_path/extension/

    sudo -u postgres sh -c "
export PATH=\"$1/bin:$PATH\" PGPORT=25432;
psql -c 'SHOW data_directory';
make installcheck -C src/interfaces/libpq &&
make installcheck -C src/test/modules/commit_ts &&
make installcheck -C src/test/modules/test_pg_dump &&
make installcheck-force -C src/test/modules/snapshot_too_old &&
if [ -d src/test/modules/brin ]; then make installcheck -C src/test/modules/brin; fi &&
if [ -d src/test/modules/unsafe_tests ]; then make installcheck -C src/test/modules/unsafe_tests; fi &&
make installcheck-force -C contrib/test_decoding"
    exitcode=$?
    sudo -u postgres $1/bin/pg_ctl -D tmpdb -w stop
fi
for df in `find . -name *.diffs`; do echo;echo "    vvvv $df vvvv    "; cat $df; echo "    ^^^^^^^^"; done
exit $exitcode
