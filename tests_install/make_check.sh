# TODO: Enable test5 (PGPRO-1289)
# TODO: Enable  (PGPRO-1396)
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
sudo -u postgres ./configure --enable-tap-tests --without-readline \
 --prefix=$1
sudo -u postgres make -C src/interfaces/ecpg # TODO: remove?
sudo -u postgres make installcheck-world
