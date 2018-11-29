echo %time%: CMD starting
PowerShell -Command "Set-MpPreference -DisableRealtimeMonitoring $true" 2>NUL
sc stop WinDefend 2>NUL

SET MD=c:\msys32\
rmdir /S /Q %MD% 2>NUL
mkdir %MD%\var\src
copy postgres*.tar.bz2 %MD%\var\src\
xcopy patches %MD%\var\src\patches\ /E

@REM Output bash script contained in this CMD
@for /f "delims=:" %%a in ('findstr -n "^___" %0') do @set "DELIMLINE=%%a"
@for /f "skip=%DELIMLINE% tokens=* eol=_" %%a in ('type %0') do @echo %%a>> %MD%\var\src\make_check.sh

cd /D c:\
@REM Prepare 7-zip for expanding msys
powershell -Command "((new-object net.webclient).DownloadFile('https://netcologne.dl.sourceforge.net/project/sevenzip/7-Zip/9.20/7za920.zip', '%TEMP%\7z.zip'))"
powershell -Command "$shell = New-Object -ComObject Shell.Application; $zip_src = $shell.NameSpace('%TEMP%\7z.zip'); $zip_dest = $shell.NameSpace('%TEMP%'); $zip_dest.CopyHere($zip_src.Items(), 1044)"
@REM Download and extract msys
powershell -Command "((new-object net.webclient).DownloadFile('http://repo.msys2.org/distrib/i686/msys2-base-i686-20180531.tar.xz', '%TEMP%\msys.tar.xz'))"
%TEMP%\7za.exe x %TEMP%\msys.tar.xz -so 2>%TEMP%/7z-msys0.log | %TEMP%\7za.exe  x -aoa -si -ttar >%TEMP%/7z-msys1.log 2>&1

@REM First run is performed to setup the environment
%MD%\usr\bin\bash --login -i -c exit >%TEMP%\msys-setup.log 2>&1

@REM Grant access to Users (including postgres user) to src/test/regress/testtablespace/
icacls %MD%\var\src /grant *S-1-5-32-545:(OI)(CI)F /T

%MD%\usr\bin\bash --login -i /var/src/make_check.sh %1
SET LEVEL=%ERRORLEVEL%
echo %time%: CMD finishing
exit /b %LEVEL%

___BASH_SCRIPT___

set -e

echo "`date -Iseconds`: Starting shell... ";
PGPATH=$(echo $1 | sed -e "s@c:[/\\\\]@/c/@i" -e "s@\\\\@/@g");
if file "$PGPATH/bin/postgres.exe" | grep '80386. for MS Windows$'; then
bitness=32; gcc=mingw-w64-i686-gcc; host=i686-w64-mingw32;
else
bitness=64; gcc=mingw-w64-x86_64-gcc; host=x86_64-w64-mingw32;
fi
pacman --noconfirm -S tar make diffutils patch perl $gcc
export PATH="/mingw$bitness/bin:/usr/bin/core_perl:$PGPATH/bin:$PATH"
echo PATH=$PATH
echo PGPORT=$PGPORT
unset PGDATA PGLOCALEDIR
export PGUSER=postgres
cd /var/src
curl -s -O http://cpan.metacpan.org/authors/id/T/TO/TODDR/IPC-Run-0.96.tar.gz
tar fax IPC-Run*
(cd IPC-Run*/ && perl Makefile.PL && make && make install)
echo "Switching log messages language to English (for src/bin/scripts/ tests)"
printf "\nlc_messages = 'English_United States.1252'\n" >> "$PGPATH/share/postgresql.conf.sample"
echo "`date -Iseconds`: Source archive extracting... "
tar fax postgres*.tar.bz2
cd postgres*/
set -o pipefail
echo "`date -Iseconds`: Configuring... "
CFLAGS=" -D WINVER=0x0600 -D _WIN32_WINNT=0x0600" LIBS="-lktmw32" ./configure --enable-tap-tests --host=$host --without-zlib --prefix="$PGPATH" 2>&1 | tee configure.log
pwd
ls -l src/interfaces/ecpg/test/
echo "Fixing ECPG test for installcheck..."
sed -e "s@^ECPG = ../../preproc/ecpg@ECPG = ecpg@" \
    -e "s@^ECPG_TEST_DEPENDENCIES = ../../preproc/ecpg\$(X)@ECPG_TEST_DEPENDENCIES = @" \
    -e "s@^override LDFLAGS := -L../../ecpglib -L../../pgtypeslib @override LDFLAGS := -L'\$(DESTDIR)\$(libdir)/' @" \
    -i src/interfaces/ecpg/test/Makefile.regress
echo "Disabling ECPG test to avoid exception 0xC0000005..."
sed -e "s@^\t\./pg_regress@\techo skipped ./pg_regress@" -i src/interfaces/ecpg/test/Makefile
echo "Disabling dblink test (msys doesn't see Windows processes)..."
sed -e "s@^REGRESS = paths dblink@REGRESS = paths@" -i contrib/dblink/Makefile
echo "Disabling pg_basebackup/030_pg_recvlogical test (PGPRO-1527)"
rm src/bin/pg_basebackup/t/030_pg_recvlogical.pl
echo "Disabling recovery/*logical_decoding test (PGPRO-1527)"
rm src/test/recovery/t/*logical_decoding*.pl
echo "Dirty fix for undefined random()"
sed -e "s@(long) random()@(long) rand()@" -i src/interfaces/libpq/fe-connect.c
echo "Disabling isolation/timeouts test (Fails in pg-tests only with a message: step locktbl timed out after 75 seconds)"
sed -e "s@test: timeouts@#test: timeouts@" -i src/test/isolation/isolation_schedule
echo "`date -Iseconds`: Making native MinGW libs 1"
(cd src/common && make -j4 2>&1 | tee /tmp/make_common.log)
echo "`date -Iseconds`: Making native MinGW libs 2"
(cd src/backend && make -j4 libpostgres.a 2>&1 | tee /tmp/make_libpostgres.log)
echo "`date -Iseconds`: Making ecpg"
make -C src/interfaces/ecpg
echo "Workaround for inability to merge PGPRO-626-ICU"
if [ -f src/test/default_collation/icu/t/001_default_collation.pl ] && ! patch -N --dry-run -R -p1 -i /var/src/patches/win-icu-test.patch ; then patch -p1 -i /var/src/patches/win-icu-test.patch; fi

set +e
echo "`date -Iseconds`: Running installcheck-world"
with_icu=yes make -e installcheck-world 2>&1 | tee /tmp/installcheck.log; exitcode=$?
for df in `find . -name *.diffs`; do echo;echo "    vvvv $df vvvv    "; cat $df; echo "    ^^^^^^^^"; done;
exit $exitcode
