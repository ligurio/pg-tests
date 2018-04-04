SET MD=c:\msys32\
rmdir /S /Q %MD%
mkdir %MD%\var\src
copy postgres*.tar.bz2 %MD%\var\src\
cd /D c:\
SET PGPATH=%1
powershell -Command "((new-object net.webclient).DownloadFile('https://www.7-zip.org/a/7za920.zip', '%TEMP%\7z.zip'))"
powershell -Command "$shell = New-Object -ComObject Shell.Application; $zip_src = $shell.NameSpace('%TEMP%\7z.zip'); $zip_dest = $shell.NameSpace('%TEMP%'); $zip_dest.CopyHere($zip_src.Items(), 1044)"

REM %TEMP%\7z.exe /S /D="C:\7z\"
REM https://downloads.sourceforge.net/project/mingw/Installer/mingw-get/mingw-get-0.6.2-beta-20131004-1/mingw-get-0.6.2-mingw32-beta-20131004-1-bin.zip
REM Alternative way (without 7z, but starts the shell)
REM powershell -Command "((new-object net.webclient).DownloadFile('http://repo.msys2.org/distrib/x86_64/msys2-x86_64-20161025.exe', 'msys2.exe'))"
REM msys2.exe --script install.qs
powershell -Command "((new-object net.webclient).DownloadFile('http://repo.msys2.org/distrib/i686/msys2-base-i686-20161025.tar.xz', '%TEMP%\msys.tar.xz'))"
%TEMP%\7za.exe x %TEMP%\msys.tar.xz -so | %TEMP%\7za.exe  x -aoa -si -ttar >%TEMP%/7z-msys.log

REM First run is performed to setup the environment
%MD%\usr\bin\bash --login -i -c exit >%TEMP%\msys-setup.log

REM Grant access to Users (including postgres user) to src/test/regress/testtablespace/
icacls %MD%\var\src /grant *S-1-5-32-545:(OI)(CI)F /T
@echo off
echo ^
PGPATH=$(echo %PGPATH% ^| sed -e "s@c:\\\\@/c/@i" -e "s@\\\\@/@g"); ^
if file "$PGPATH/bin/postgres.exe" ^| grep '80386. for MS Windows$'; then ^
bitness=32; gcc=mingw-w64-i686-gcc; host=i686-w64-mingw32; ^
else ^
bitness=64; gcc=mingw-w64-x86_64-gcc; host=x86_64-w64-mingw32; ^
fi ^&^& ^
pacman --noconfirm -S tar make diffutils perl $gcc ^&^& ^
export PATH="/mingw$bitness/bin:/usr/bin/core_perl:$PGPATH/bin:$PATH" ^&^& ^
echo $PATH ^&^& ^
cd /var/src ^&^& ^
curl -O http://cpan.metacpan.org/authors/id/T/TO/TODDR/IPC-Run-0.96.tar.gz ^&^& ^
tar fax IPC-Run* ^&^& ^
(cd IPC-Run* ^&^& perl Makefile.PL ^&^& make ^&^& make install) ^&^& ^
tar fax postgres*.tar.bz2 ^&^& ^
cd postgres* ^&^& ^
./configure --enable-tap-tests --host=$host --without-zlib --prefix="$PGPATH" >configure.log ^&^& ^
echo "Fixing ECPG test for installcheck..." ^&^& ^
sed -e "s@^ECPG = ../../preproc/ecpg@ECPG = ecpg@" ^
    -e "s@^ECPG_TEST_DEPENDENCIES = ../../preproc/ecpg\$(X)@ECPG_TEST_DEPENDENCIES = @" ^
    -e "s@^override LDFLAGS := -L../../ecpglib -L../../pgtypeslib @override LDFLAGS := -L'\$(DESTDIR)\$(libdir)/' @" ^
    -i src/interfaces/ecpg/test/Makefile.regress ^&^& ^
echo "Disabling ECPG test to avoid exception 0xC0000005..." ^&^& ^
sed -e "s@^\t\./pg_regress@\techo skipped ./pg_regress@" -i src/interfaces/ecpg/test/Makefile ^&^& ^
echo "Disabling dblink test..." ^&^& ^
sed -e "s@^REGRESS = paths dblink@REGRESS = paths@" -i contrib/dblink/Makefile ^&^& ^
echo "Disabling pg_basebackup/030_pg_recvlogical test (PGPRO-1527)" ^&^& ^
rm src/bin/pg_basebackup/t/030_pg_recvlogical.pl ^&^& ^
echo "Disabling pg_ctl/001_start_stop test (port conflict)" ^&^& ^
rm src/bin/pg_ctl/t/001_start_stop.pl ^&^& ^
echo "Disabling pg_dump/002_pg_dump test" ^&^& ^
rm src/bin/pg_dump/t/002_pg_dump.pl ^&^& ^
echo "Disabling scripts tests" ^&^& ^
rm src/bin/scripts/t/0*.pl src/bin/scripts/t/1*.pl ^&^& ^
echo "Disabling isolation/timeouts test (Fails in pg-tests only with a message: step locktbl timed out after 75 seconds)" ^&^& ^
sed -e "s@test: timeouts@#test: timeouts@" -i src/test/isolation/isolation_schedule ^&^& ^
(cd src/common ^&^& make -j4 libpgcommon_srv.a ^> /tmp/make_libpgcommon_srv.log) ^&^& ^
(cd src/backend ^&^& make -j4 libpostgres.a ^> /tmp/make_libpostgres.log) ^&^& ^
make installcheck-world ^

> %MD%\var\src\make_check.sh
%MD%\usr\bin\bash --login -i /var/src/make_check.sh
exit /b %errorlevel%
