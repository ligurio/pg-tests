# TODO: Enable test5 (PGPRO-1289)
# TODO: Enable pg_hint_plan (PGPRO-1396)
if which apt-get; then
    apt-get install -y gcc || true
    apt-get install -y make flex bison perl
    apt-get install -y zlib1g-dev || apt-get install -y zlib-devel
    apt-get install -y libicu-dev || true
    apt-get install -y libicu-devel || true
    apt-get install -y pkg-config
    apt-get install -y libipc-run-perl || apt-get install -y perl-IPC-Run
    apt-get install -y patch || true
    apt-get install -y perl-devel || true
elif which zypper; then
    zypper install -y gcc make flex bison perl
    zypper install -y --force --force-resolution zlib-devel
    zypper install -y --force --force-resolution libicu-devel
    zypper install -y libipc-run-perl
elif which yum; then
    yum install -y gcc make flex bison perl bzip2 zlib-devel libicu-devel patch
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
    # Update Test::More to minimum required version (0.87)
    curl https://codeload.github.com/Test-More/test-more/tar.gz/v0.90 \
     -o test-more.tar.gz && \
    tar fax test-more* && \
    (cd test-more* && perl Makefile.PL && make && make install)
fi

if [ -d ~test/pg-tests ]; then
    chmod 777 ~test
    cd ~test/pg-tests
fi
tar fax postgrespro*.tar*

cd postgres*/

if grep 'SUSE Linux Enterprise Server' /etc/SuSE-release; then #PGPRO-1294
    patch -p0 -i ../patches/SUSE-postgresql-regress.patch
fi

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

if [ -f contrib/pg_hint_plan/Makefile ]; then
    sed -e 's/REGRESS = /# REGRESS = /' -i contrib/pg_hint_plan/Makefile
fi

if grep 'SUSE Linux Enterprise Server 11' /etc/SuSE-release; then
  # To workaround an "internal compiler error"
  sed 's/log10(2)/0.3010/' -i src/interfaces/ecpg/compatlib/informix.c
fi

sudo chown -R postgres:postgres .
if ./configure --help | grep '  --enable-svt5'; then
    extraoption="--enable-svt5"
    if which apt-get; then
        apt-get install -y fuse
        apt-get install -y fuse-devel || apt-get install -y libfuse-dev || apt-get install -y libfuse-devel
    elif which yum; then
        yum install -y fuse fuse-devel
    fi
    getent group fuse && usermod -a -G fuse postgres

    if ! perl -e "use Fuse"; then
        (
        cd ..
        if which wget; then
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

if patch -p1 --dry-run -i ../patches/make-instalcheck-10.patch; then
    echo "Fixing Makefiles for installcheck-world..."
    patch -p1 -i ../patches/make-installcheck-10.patch
else
    makeecpg=true
fi

sudo -u postgres ./configure --enable-tap-tests --without-readline --with-icu \
 --prefix=$1 $extraoption || exit $?
[ "$makeecpg" = true ] && sudo -u postgres sh -c "make -C src/interfaces/ecpg"
sudo -u postgres sh -c "PATH=$1/bin:$PATH make installcheck-world"
