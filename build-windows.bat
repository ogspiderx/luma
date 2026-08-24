@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo   Building Luma for Windows
echo   -------------------------
echo.

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY (
    echo   Python is not installed.
    echo   Get it from https://www.python.org/downloads/
    echo   During setup, tick "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)

echo   [1/4] Installing what the build needs...
%PY% -m pip install --upgrade pip --quiet --disable-pip-version-check
%PY% -m pip install --quiet --disable-pip-version-check -r requirements.txt pyinstaller
if errorlevel 1 (
    echo   Could not install the build dependencies.
    pause
    exit /b 1
)

echo   [2/4] Building the application...
%PY% -m PyInstaller --noconfirm --clean packaging\pyinstaller\luma.spec
if errorlevel 1 (
    echo   The build failed.
    pause
    exit /b 1
)

echo   [3/4] Packaging the portable folder...
powershell -NoProfile -Command ^
  "$v = (python -c 'from luma import __version__; print(__version__)').Trim(); Compress-Archive -Force -Path 'dist/Luma/*' -DestinationPath \"dist/Luma-$v-portable-windows.zip\""

echo   [4/4] Building the installer...
set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
    echo.
    echo   Inno Setup 6 is not installed, so the installer was skipped.
    echo   The portable build is ready in the dist folder.
    echo   To build the installer too, get Inno Setup from:
    echo       https://jrsoftware.org/isdl.php
    echo   then run this file again.
    echo.
    pause
    exit /b 0
)
"%ISCC%" "packaging\windows\luma.iss"

echo.
echo   Done. Look in the dist folder:
echo     dist\Luma\Luma.exe                    the portable build
echo     dist\Luma-*-portable-windows.zip      the portable build, zipped
echo     dist\installer\Luma-Setup-*.exe       the installer
echo.
pause
