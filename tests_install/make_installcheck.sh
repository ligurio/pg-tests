#!/bin/bash

if which apt-get >/dev/null 2>&1; then
    (
    apt-get install -y gcc || true
    apt-get install -y make flex bison perl
    apt-get install -y zlib1g-dev || apt-get install -y zlib-devel
    apt-get install -y libicu-dev || apt-get install -y libicu-devel
    apt-get install -y pkg-config
    apt-get install -y libipc-run-perl || apt-get install -y perl-IPC-Run
    apt-get install -y libio-pty-perl || apt-get install -y perl-IO-Tty || true
    apt-get install -y patch || true
    apt-get install -y perl-devel || true
    apt-get install -y perl-bignum || true
    ) 2>&1
elif which zypper >/dev/null 2>&1; then
    (
    zypper install -y gcc make flex bison perl patch
    zypper install -y --force --force-resolution zlib-devel
    zypper install -y --force --force-resolution libicu-devel
    zypper install -y perl-IPC-Run
    zypper install -y perl-IO-Tty
    ) 2>&1
elif which yum >/dev/null 2>&1; then
    (
    yum install -y gcc make flex bison perl bzip2 zlib-devel libicu-devel patch
    yum install -y perl-devel || true
    yum install -y perl-IPC-Run
    yum install -y perl-IO-Tty || true
    yum install -y perl-Test-Simple perl-Time-HiRes
    yum install -y perl-bignum || true
    ) 2>&1
    # perl-IPC-Run is not present in some distributions (rhel-7, rosa-sx-7...)
fi
if ! perl -e "use IPC::Run"  >/dev/null 2>&1; then
    curl -O http://cpan.metacpan.org/authors/id/T/TO/TODDR/\
IPC-Run-20200505.0.tar.gz && \
    tar fax IPC-Run* && \
    (cd IPC-Run*/ && perl Makefile.PL && make && make install)
fi

if ! perl -e "use IO::Pty"  >/dev/null 2>&1; then
    curl -O https://cpan.metacpan.org/authors/id/T/TO/TODDR/\
IO-Tty-1.15.tar.gz && \
    tar fax IO-Tty* && \
    (cd IO-Tty*/ && perl Makefile.PL && make && make install)
fi

if [ -d ~test/pg-tests ]; then
    chmod 777 ~test/pg-tests
    cd ~test/pg-tests
fi

cd postgres*/
BASEDIR=`pwd`

if grep 'SUSE Linux Enterprise Server' /etc/SuSE-release >/dev/null 2>&1; then #PGPRO-1294
    patch -p0 -i ../patches/SUSE-postgresql-regress.patch
fi

chown -R postgres:postgres .
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
if patch -p1 --dry-run -F 0 -i ../patches/make-installcheck-13.patch >/dev/null 2>&1; then
    echo "Fixing Makefiles v13 for installcheck-world..."
    patch -p1 -i ../patches/make-installcheck-13.patch
    makeecpg=false
fi
if patch -p1 --dry-run -F 0 -i ../patches/make-installcheck-12.patch >/dev/null 2>&1; then
    echo "Fixing Makefiles v12 for installcheck-world..."
    patch -p1 -i ../patches/make-installcheck-12.patch
    makeecpg=false
fi
if patch -p1 --dry-run -F 0 -i ../patches/make-installcheck-11.patch >/dev/null 2>&1; then
    echo "Fixing Makefiles v11 for installcheck-world..."
    patch -p1 -i ../patches/make-installcheck-11.patch
    makeecpg=false
fi
if patch -p1 --dry-run -F 0 -i ../patches/make-installcheck-10.patch >/dev/null 2>&1; then
    echo "Fixing Makefiles v10 for installcheck-world..."
    patch -p1 -i ../patches/make-installcheck-10.patch
    makeecpg=false
fi

# Backpatch 69ae9dcb to version 11 (pgsql-bugs #15349) (uri-regress.c: undefined reference to PQconninfoParse, PQconndefaults)
patch -p1 --dry-run -i ../patches/69ae9dcb.patch >/dev/null 2>&1 && patch -p1 -i ../patches/69ae9dcb.patch

# Enable the installcheck mode for pg_stat_statements testing
sed 's|NO_INSTALLCHECK|# NO_INSTALLCHECK|' -i contrib/pg_stat_statements/Makefile

# Fixing in_memory Makefile (PGPRO-4563)
sed "s|regresscheck-install:.*|regresscheck-install:|" -i contrib/in_memory/Makefile

#Check /etc/localtime exist
[ -f /etc/localtime ] || ln -s /usr/share/zoneinfo/UTC /etc/localtime

set -o pipefail

confopts="python_majorversion=2"
if which python >/dev/null 2>&1; then
    confopts="python_majorversion=`python -c 'import sys; print(sys.version_info.major)'`"
else
    which python3 >/dev/null 2>&1 && confopts="python_majorversion=3"
fi
disconfopts=""
opts=`$1/bin/pg_config --configure | grep -Eo "'[^']*'|[^' ]*" | sed -e "s/^'//" -e "s/'$//"`
while read -r opt; do
    case "$opt" in --with-*=*) ;; --with-* | --enable-*) opt="${opt/#--/}"; opt="${opt//-/_}" confopts="$confopts $opt=yes ";; esac;
    case "$opt" in --disable-dependency-tracking | --disable-rpath) ;; --disable-*) disconfopts="$disconfopts $opt" ;; esac;
done <<< "$opts";

# Pass to `./configure` disable-* options, that were passed to configure (if any; namely, --disable-online-upgrade)
echo "Configuring with options: --enable-tap-tests --without-readline --prefix=$1 $disconfopts $extraoption"
sudo -u postgres ./configure --enable-tap-tests --without-readline --prefix=$1 $disconfopts $extraoption || exit $?

test -f contrib/mchar/mchar.sql.in && make -C contrib/mchar mchar.sql

[ "$makeecpg" = true ] && sudo -u postgres sh -c "make -C src/interfaces/ecpg"

# Pass to `make installcheck` all the options (with-*, enable-*), which were passed to configure
echo "Running: $confopts make -e installcheck-world ..."
sudo -u postgres sh -c "PATH=\"$1/bin:$PATH\" $confopts make -e installcheck-world EXTRA_TESTS=numeric_big 2>&1" | tee /tmp/installcheck.log; exitcode=$?

#TODO: Add pg_repack (stabilize the test)
for comp in orafce plv8 pgpro_stats pgpro_pwr pgpro_controldata pg_filedump pg_portal_modify; do
if [ $exitcode -eq 0 ]; then
    if [ -f ../$comp*.tar* ]; then
        cd ..
        if [ $comp == pg_repack ]; then
            sudo -u postgres mkdir tmp/testts &&
            sudo -u postgres "$1/bin/psql" -c "create tablespace testts location '`pwd`/tmp/testts'"
        fi
        if [ $comp == pgpro_stats ]; then
            # Reconfigure shared_preload_libraries
            spl=`sudo -u postgres "$1/bin/psql" -t -P format=unaligned -c 'SHOW shared_preload_libraries'`
            spl=`echo $spl | sed -E "s/pg_stat_statements,?//"`
            sudo -u postgres "$1/bin/psql" -c "ALTER SYSTEM SET shared_preload_libraries = $spl, $comp"
            service "$2" restart
        fi
        if [ $comp == pgpro_controldata ]; then
            datadir=`sudo -u postgres "$1/bin/psql" -t -P format=unaligned -c 'SHOW data_directory'`
            pgxsdir="`dirname $($1/bin/pg_config --pgxs)`/../.."
            EXTRAVARS="enable_tap_tests=yes PROVE=\"PG_REGRESS=$pgxsdir/src/test/regress/pg_regress prove\" PROVE_FLAGS=\"-I $BASEDIR/src/test/perl\""
        fi
        echo "Performing 'make installcheck' for $comp..."
        tar fax $comp*.tar* &&
        cd $comp*/ && chown -R postgres . &&
        sudo -u postgres sh -c "$EXTRAVARS PATH=\"$1/bin:$PATH\" make -e USE_PGXS=1 installcheck"; exitcode=$?
        cd $BASEDIR
    fi
fi
done

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
echo PGPRO-4563 Disabled: make installcheck-force -C src/test/modules/snapshot_too_old &&
if [ -d src/test/modules/brin ]; then make installcheck -C src/test/modules/brin; fi &&
if [ -d src/test/modules/unsafe_tests ]; then make installcheck -C src/test/modules/unsafe_tests; fi &&
echo PGPRO-4563 Disabled: make installcheck-force -C contrib/test_decoding"
    exitcode=$?
    sudo -u postgres $1/bin/pg_ctl -D tmpdb -w stop
fi
for df in `find .. -name *.diffs`; do echo;echo "    vvvv $df vvvv    "; cat $df; echo "    ^^^^^^^^"; done
exit $exitcode
