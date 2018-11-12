echo %time%: CMD starting
PowerShell -Command "Set-MpPreference -DisableRealtimeMonitoring $true" 2>NUL

SET MD=c:\msys64
rmdir /S /Q %MD% 2>NUL
SET CWD=%cd%
cd /D c:\
SET PGSRC=%1
SET PGPATH=%2
powershell -Command "((new-object net.webclient).DownloadFile('https://netcologne.dl.sourceforge.net/project/sevenzip/7-Zip/9.20/7za920.zip', '%TEMP%\7z.zip'))"
powershell -Command "$shell = New-Object -ComObject Shell.Application; $zip_src = $shell.NameSpace('%TEMP%\7z.zip'); $zip_dest = $shell.NameSpace('%TEMP%'); $zip_dest.CopyHere($zip_src.Items(), 1044)"

powershell -Command "((new-object net.webclient).DownloadFile('http://repo.msys2.org/distrib/x86_64/msys2-base-x86_64-20180531.tar.xz', '%TEMP%\msys.tar.xz'))"
%TEMP%\7za.exe x %TEMP%\msys.tar.xz -so 2>%TEMP%/7z-msys0.log | %TEMP%\7za.exe  x -aoa -si -ttar >%TEMP%/7z-msys1.log 2>&1

REM First run is performed to setup the environment
rmdir %MD%\tmp
mklink %MD%\tmp c:\tmp
%MD%\usr\bin\bash --login -i -c exit >%TEMP%\msys-setup.log 2>&1

@echo off
echo ^
echo "`date -Iseconds`: Starting shell... "; ^
PGPATH=$(echo %PGPATH% ^| sed -e "s@c:[/\\\\]@/c/@i" -e "s@\\\\@/@g"); ^
PGSRC=$(echo %PGSRC% ^| sed -e "s@c:[/\\\\]@/c/@i" -e "s@\\\\@/@g"); ^
CWD=$(echo %CWD% ^| sed -e "s@c:[/\\\\]@/c/@i" -e "s@\\\\@/@g"); ^
cd "$CWD" ^&^& ^
bitness=64; gcc=mingw-w64-x86_64-gcc; host=x86_64-w64-mingw32; ^
pacman --noconfirm -S tar make diffutils perl mingw-w64-x86_64-gcc patch ^&^& ^
echo "`date -Iseconds`: Extracting source from $PGSRC..." ^&^& ^
tar fax "$PGSRC" ^&^& ^
cd postgres*/ ^&^& ^
echo export PATH=\"/mingw64/bin:/usr/bin/core_perl:$PGPATH/bin:$PATH\" ^> setenv.sh ^&^& ^
source setenv.sh ^&^& ^
set -o pipefail ^&^& ^
echo "`date -Iseconds`: Configuring... " ^&^& ^
./configure --host=$host --without-zlib --prefix="$PGPATH" 2^>^&1 ^| tee configure.log ^

> %MD%\tmp\make_check.sh
%MD%\usr\bin\bash --login -i /tmp/make_check.sh

SET LEVEL=%ERRORLEVEL%
echo %time%: CMD finishing
exit /b %LEVEL%
