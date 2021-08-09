SET MD=c:\msys32
SET MSYS_HREF="http://dist.l.postgrespro.ru/resources/windows/msys2-base-i686-20200517.tar.xz"
If "%PROCESSOR_ARCHITECTURE%"=="AMD64" ( 
SET MSYS_HREF="http://dist.l.postgrespro.ru/resources/windows/msys2-base-x86_64-20210215.tar.xz"
SET MD=c:\msys64
)

SET PGTD=%cd%

IF EXIST %MD%\NUL GOTO main
:setup
PowerShell -Command "Set-MpPreference -DisableRealtimeMonitoring $true" 2>NUL

rmdir /S /Q %MD% 2>NUL
mkdir %MD%\var\src
for /d %%A in (postgres*) do mklink /D "%MD%\var\src\%%A" "%%~fA"
xcopy *.tar* %MD%\var\src\
xcopy patches %MD%\var\src\patches\ /E

@REM Output bash script contained in this CMD
@for /f "delims=:" %%a in ('findstr -n "^___" %0') do @set "DELIMLINE=%%a"
@for /f "skip=%DELIMLINE% tokens=* eol=_" %%a in ('type %0') do @echo %%a>> %MD%\var\src\make_check.sh

cd /D c:\
@REM Prepare 7-zip for expanding msys
powershell -Command "((new-object net.webclient).DownloadFile('http://dist.l.postgrespro.ru/resources/windows/7za920.zip', '%TEMP%\7z.zip'))"
powershell -Command "$shell = New-Object -ComObject Shell.Application; $zip_src = $shell.NameSpace('%TEMP%\7z.zip'); $zip_dest = $shell.NameSpace('%TEMP%'); $zip_dest.CopyHere($zip_src.Items(), 1044)"
@REM Download and extract msys
powershell -Command "((new-object net.webclient).DownloadFile('%MSYS_HREF%', '%TEMP%\msys.tar.xz'))"
%TEMP%\7za.exe x %TEMP%\msys.tar.xz -so 2>%TEMP%/7z-msys0.log | %TEMP%\7za.exe  x -aoa -si -ttar >%TEMP%/7z-msys1.log 2>&1

@REM First run is performed to setup the environment
%MD%\usr\bin\bash --login -i -c exit >%TEMP%\msys-setup.log 2>&1

@REM Keyring updated manually due to invalid key 4A6129F4E4B84AE46ED7F635628F528CF3053E04 (waiting for a newer msys2- base...)
If "%PROCESSOR_ARCHITECTURE%"=="AMD64" GOTO skip_msys_key
%MD%\usr\bin\bash --login -i -c ^" ^
curl -sS -O https://repo.msys2.org/msys/x86_64/msys2-keyring-1~20210213-2-any.pkg.tar.zst ^&^& ^
pacman --noconfirm -U --config ^<(echo) msys2-keyring-1~20210213-2-any.pkg.tar.zst ^&^& ^
pacman --noconfirm -Sy ^" >%TEMP%\msys-update.log 2>&1

:skip_msys_key
%MD%\usr\bin\bash --login -i -c "pacman --noconfirm -S tar make diffutils patch perl" >>%TEMP%\msys-update.log 2>&1
If NOT "%PROCESSOR_ARCHITECTURE%"=="AMD64" call %MD%\autorebase >>%TEMP%\msys-update.log 2>&1

@REM Grant access to Users (including postgres user) to the whole /var/src contents
icacls %MD%\var\src /grant *S-1-5-32-545:(OI)(CI)F /T >>%TEMP%\icacls.log

@REM Grant access to Users to %PGROOT%/lib/pgxs
mkdir %1\lib\pgxs
icacls %1\lib\pgxs /grant *S-1-5-32-545:(OI)(CI)F /T >>%TEMP%\icacls.log

@REM Grant access to Users to %PGTD%/tmp
icacls %PGTD%\tmp /grant *S-1-5-32-545:(OI)(CI)F /T >>%TEMP%\icacls.log

@REM "Switching log messages language to English (for src/bin/scripts/ tests)"
(echo. & echo lc_messages = 'English_United States.1252') >> %1\share\postgresql.conf.sample

@REM Give Built-in users (BU) the same permissions to control PG service as Built-in administrators have (BA)
sc sdset "%2" "D:(A;;CCLCSWRPWPDTLOCRRC;;;SY)(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BU)(A;;CCLCSWLOCRRC;;;IU)(A;;CCLCSWLOCRRC;;;SU)S:(AU;FA;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;WD)"

@REM Add current user to the Remote Management Users group
powershell -Command "$group=(New-Object System.Security.Principal.SecurityIdentifier('S-1-5-32-580')).Translate([System.Security.Principal.NTAccount]).Value.Split('\\')[1]; net localgroup $group %username% /add"

@exit /b 0

:main
echo %time%: Main cmd script starting

%MD%\usr\bin\bash --login -i /var/src/make_check.sh %1 %2 %PGTD%
SET LEVEL=%ERRORLEVEL%
echo %time%: Main cmd script finishing
exit /b %LEVEL%

___BASH_SCRIPT___

set -e
echo "`date -Iseconds`: Starting shell... ";
SN=$2
HD=$3
PGPATH=$(echo $1 | sed -e "s@c:[/\\\\]@/c/@i" -e "s@\\\\@/@g");
if file "$PGPATH/bin/postgres.exe" | grep '80386. for MS Windows$'; then
bitness=32; gcc=mingw-w64-i686-gcc; host=i686-w64-mingw32;
else
bitness=64; gcc=mingw-w64-x86_64-gcc; host=x86_64-w64-mingw32;
fi
pacman --noconfirm -S $gcc
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
BASEDIR=`pwd`

set -o pipefail
pwd

# Enable the installcheck mode for pg_stat_statements testing
if "$PGPATH/bin/psql" -c "SHOW shared_preload_libraries;" | grep "pg_stat_statements" > /dev/null 2>&1; then
    sed 's|NO_INSTALLCHECK|# NO_INSTALLCHECK|' -i contrib/pg_stat_statements/Makefile
fi



disconfopts=""
confopts="python_majorversion=`\"$PYTHONHOME\\python\" -c 'import sys; print(sys.version_info.major)'`"
opts=`"$PGPATH/bin/pg_config" --configure | grep -Eo "'[^']*'|[^' ]*" | sed -e "s/^'//" -e "s/'$//"`
while read -r opt; do
    case "$opt" in --with-*=*) ;; --with-* | --enable-*) opt="${opt/#--/}"; opt="${opt//-/_}" confopts="$confopts $opt=yes ";; esac;
    case "$opt" in --disable-dependency-tracking | --disable-rpath) ;; --disable-*) disconfopts="$disconfopts $opt" ;; esac;
done <<< "$opts";
echo "confopts: $confopts"

# Pass to `./configure` disable-* options, that were passed to configure (if any; namely, --disable-online-upgrade)
echo "`date -Iseconds`: Configuring with options: --enable-tap-tests --host=$host --without-zlib --prefix="$PGPATH" $disconfopts"
CFLAGS=" -D WINVER=0x0600 -D _WIN32_WINNT=0x0600" LIBS="-lktmw32 -ladvapi32" ./configure --enable-tap-tests --host=$host --without-zlib --prefix="$PGPATH" $disconfopts 2>&1 | tee configure.log

test -f contrib/mchar/mchar.sql.in && make -C contrib/mchar mchar.sql
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
sed -e "s@(uint32) random()@(uint32) rand()@" -i src/interfaces/libpq/fe-connect.c
echo "Fix for TZ setting in the MSYS environment (Don't pass timezone environment to non-msys applications)"
[ -f src/bin/pg_controldata/t/002_pg_controldata_legacy.pl ] && patch -p1 -i /var/src/patches/pg_controldata-test-msys.patch
echo "Fix for authentication test in the MSYS environment (PGPRO-5085)"
[ -f src/test/authentication/t/004_profile.pl ] && patch -p1 -i /var/src/patches/fix-password-policies-tests.patch || true
echo "Fix for pg_dump test with password policies"
[ -f src/bin/pg_dump/t/002_pg_dump.pl ] && patch -p1 -i /var/src/patches/fix-pg_dump_passoword-policies-tests.patch || true
echo "Disabling multimaster tests (PGPRO-1430)"
[ -f contrib/mmts/Makefile ] && sed -e "s@^installcheck@#installcheck@" -i contrib/mmts/Makefile
echo "`date -Iseconds`: Making native MinGW libs 1"
(cd src/common && make 2>&1 | tee /tmp/make_common.log)
echo "`date -Iseconds`: Making native MinGW libs 2"
(cd src/backend && make -j4 libpostgres.a 2>&1 | tee /tmp/make_libpostgres.log)
echo "`date -Iseconds`: Making ecpg"
make -C src/interfaces/ecpg
echo "`date -Iseconds`: Making pg_regress"
make -C src/test/regress
# Bandaid for PGPRO-5331
# Needed after b961bdfe: PQprint() doesn't work when /c/Progra~1/Postgr~1/13/bin/libpq.dll is used
echo "`date -Iseconds`: Making pg_isolation_regress"
make -C src/test/isolation
cp src/interfaces/libpq/libpq.dll src/test/isolation/

echo "Preparing pgxs/ for tests"
mkdir -p "$1/lib/pgxs/src/makefiles"
mkdir -p "$1/lib/pgxs/src/test/regress"
cp src/makefiles/pgxs.mk "$1/lib/pgxs/src/makefiles/"
cp src/Makefile.global src/Makefile.shlib src/Makefile.port "$1/lib/pgxs/src/"
cp src/test/regress/pg_regress.exe "$1/lib/pgxs/src/test/regress/"

set +e
# Pass to `make installcheck` all the options (with-*, enable-*), that were passed to configure
echo "`date -Iseconds`: Running $confopts make -e installcheck-world ..."
sh -c "$confopts EXTRA_REGRESS_OPTS='--dlpath=\"$PGPATH/lib\"' make -e installcheck-world EXTRA_TESTS=numeric_big" 2>&1 | gawk '{ print strftime("%H:%M:%S "), $0; fflush() }' | tee /tmp/installcheck.log; exitcode=$?

# TODO: Add orafce pg_filedump pg_repack
# TODO: Enable the pgpro_pwr test again (after defeating "Permission denied")
for comp in plv8 pgpro_stats pgpro_controldata pg_portal_modify; do
if [ $exitcode -eq 0 ]; then
    if [ -f ../$comp*.tar* ]; then
        cd ..
        if [ $comp == pg_repack ]; then
            mkdir "$HD/tmp/testts" &&
            "$PGPATH/bin/psql" -c "create tablespace testts location '$HD/tmp/testts'"
        fi
        if [ $comp == pgpro_stats ]; then
            # Reconfigure shared_preload_libraries
            spl=`"$PGPATH/bin/psql" -t -P format=unaligned -c 'SHOW shared_preload_libraries'`
            spl=`echo $spl | sed -E "s/pg_stat_statements,?//"`
            "$PGPATH/bin/psql" -c "ALTER SYSTEM SET shared_preload_libraries = $spl, $comp"
            powershell -Command "Restart-Service '$2'"
        fi
        if [ $comp == pgpro_controldata ]; then
            export PATH="$PGPATH/../../PostgresPro/pgpro_controldata:$PATH"
            EXTRAVARS="enable_tap_tests=yes PROVE=\"PG_REGRESS=$PGPATH/lib/pgxs/src/test/regress/pg_regress prove\" PROVE_FLAGS=\"-I $BASEDIR/src/test/perl\""
        fi
        echo "Performing 'make installcheck' for $comp..."
        tar fax $comp*.tar* &&
        cd $comp*/ &&
        sh -c "$EXTRAVARS make -e USE_PGXS=1 installcheck"; exitcode=$?
        cd $BASEDIR
    fi
fi
done

for df in `find . /var/src -name *.diffs`; do echo;echo "    vvvv $df vvvv    "; cat $df; echo "    ^^^^^^^^"; done;
exit $exitcode
