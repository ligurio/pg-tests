SET MD=c:\msys32

IF EXIST %MD%\NUL GOTO main
:setup
PowerShell -Command "Set-MpPreference -DisableRealtimeMonitoring $true" 2>NUL

rmdir /S /Q %MD% 2>NUL
mkdir %MD%\var\src
for /d %%A in (postgres*) do mklink /D "%MD%\var\src\%%A" "%%~fA"
xcopy patches %MD%\var\src\patches\ /E

@REM Output bash script contained in this CMD
@for /f "delims=:" %%a in ('findstr -n "^___" %0') do @set "DELIMLINE=%%a"
@for /f "skip=%DELIMLINE% tokens=* eol=_" %%a in ('type %0') do @echo %%a>> %MD%\var\src\make_check.sh

cd /D c:\
@REM Prepare 7-zip for expanding msys
powershell -Command "((new-object net.webclient).DownloadFile('https://netcologne.dl.sourceforge.net/project/sevenzip/7-Zip/9.20/7za920.zip', '%TEMP%\7z.zip'))"
powershell -Command "$shell = New-Object -ComObject Shell.Application; $zip_src = $shell.NameSpace('%TEMP%\7z.zip'); $zip_dest = $shell.NameSpace('%TEMP%'); $zip_dest.CopyHere($zip_src.Items(), 1044)"
@REM Download and extract msys
powershell -Command "((new-object net.webclient).DownloadFile('http://dist.l.postgrespro.ru/resources/windows/msys2-base-i686-20180531.tar.xz', '%TEMP%\msys.tar.xz'))"
%TEMP%\7za.exe x %TEMP%\msys.tar.xz -so 2>%TEMP%/7z-msys0.log | %TEMP%\7za.exe  x -aoa -si -ttar >%TEMP%/7z-msys1.log 2>&1

@REM Grant access to Users (including postgres user) to src/test/regress/testtablespace/
icacls %MD%\var\src /grant *S-1-5-32-545:(OI)(CI)F /T

@REM "Switching log messages language to English (for src/bin/scripts/ tests)"
(echo. & echo lc_messages = 'English_United States.1252') >> %1\share\postgresql.conf.sample

@REM Add current user to the Remote Management Users group
powershell -Command "$group=(New-Object System.Security.Principal.SecurityIdentifier('S-1-5-32-580')).Translate([System.Security.Principal.NTAccount]).Value.Split('\\')[1]; net localgroup $group %username% /add"

@REM Exclude current user from the Administrators group
powershell -Command "$group=(New-Object System.Security.Principal.SecurityIdentifier('S-1-5-32-544')).Translate([System.Security.Principal.NTAccount]).Value.Split('\\')[1]; net localgroup $group %username% /delete"
@exit /b 0

:main
echo %time%: Main cmd script starting

@REM First run is performed to setup the environment
%MD%\usr\bin\bash --login -i -c exit >%TEMP%\msys-setup.log 2>&1

%MD%\usr\bin\bash --login -i /var/src/make_check.sh %1
SET LEVEL=%ERRORLEVEL%
echo %time%: Main cmd script finishing
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
export PATH="/mingw$bitness/bin:/usr/bin/core_perl:$PATH:$PGPATH/bin"
echo PATH=$PATH
echo PGPORT=$PGPORT
unset PGDATA PGLOCALEDIR
export PGUSER=postgres
cd /var/src
curl -s -O http://cpan.metacpan.org/authors/id/T/TO/TODDR/IPC-Run-20200505.0.tar.gz
tar fax IPC-Run*
(cd IPC-Run*/ && perl Makefile.PL && make && make install)
echo "`date -Iseconds`: Source archive extracting... "
cd postgres*/
echo 'The source archive buildinfo:'
cat doc/buildinfo.txt

set -o pipefail
echo "`date -Iseconds`: Configuring... "
CFLAGS=" -D WINVER=0x0600 -D _WIN32_WINNT=0x0600" LIBS="-lktmw32" ./configure --enable-tap-tests --host=$host --without-zlib --prefix="$PGPATH" 2>&1 | tee configure.log
pwd

test -f contrib/mchar/mchar.sql.in && make -C contrib/mchar mchar.sql

# Pass to `make installcheck` all the options (with-*, enable-*), that were passed to configure
PYTHONHOME=`TMP= TEMP= powershell -Command "Start-Process -UseNewEnvironment -nonewwindow -wait -FilePath cmd.exe -ArgumentList '/c echo %pythonhome%'"`
confopts="python_majorversion=`$PYTHONHOME/python -c 'import sys; print(sys.version_info.major)'`"
opts=`"$PGPATH/bin/pg_config" --configure | grep -Eo "'[^']*'|[^' ]*" | sed -e "s/^'//" -e "s/'$//"`
while read -r opt;
    do case "$opt" in --with-*=*) ;; --with-* | --enable-*) opt="${opt/#--/}"; opt="${opt//-/_}" confopts="$confopts $opt=yes ";; esac;
done <<< "$opts";
echo "confopts: $confopts"
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
[ -f src/bin/pg_basebackup/t/030_pg_recvlogical.pl ] && rm src/bin/pg_basebackup/t/030_pg_recvlogical.pl
echo "Disabling recovery/*logical_decoding test (PGPRO-1527)"
ls src/test/recovery/t/*logical_decoding*.pl >/dev/null 2>&1 && rm src/test/recovery/t/*logical_decoding*.pl
echo "Dirty fix for undefined random()"
sed -e "s@(long) random()@(long) rand()@" -i src/interfaces/libpq/fe-connect.c
echo "Fix for TZ setting in the MSYS environment (Don't pass timezone environment to non-msys applications)"
[ -f src/bin/pg_controldata/t/002_pg_controldata_legacy.pl ] && patch -p1 -i /var/src/patches/pg_controldata-test-msys.patch
echo "Disabling multimaster tests (PGPRO-1430)"
[ -f contrib/mmts/Makefile ] && sed -e "s@^installcheck@#installcheck@" -i contrib/mmts/Makefile
echo "`date -Iseconds`: Making native MinGW libs 1"
(cd src/common && make 2>&1 | tee /tmp/make_common.log)
echo "`date -Iseconds`: Making native MinGW libs 2"
(cd src/backend && make -j4 libpostgres.a 2>&1 | tee /tmp/make_libpostgres.log)
echo "`date -Iseconds`: Making ecpg"
make -C src/interfaces/ecpg

set +e
echo "`date -Iseconds`: Running $confopts make -e installcheck-world ..."
sh -c "$confopts EXTRA_REGRESS_OPTS='--dlpath=\"$PGPATH/lib\"' make -e installcheck-world EXTRA_TESTS=numeric_big" 2>&1 | gawk '{ print strftime("%H:%M:%S "), $0; fflush() }' | tee /tmp/installcheck.log; exitcode=$?
for df in `find . -name *.diffs`; do echo;echo "    vvvv $df vvvv    "; cat $df; echo "    ^^^^^^^^"; done;
exit $exitcode
