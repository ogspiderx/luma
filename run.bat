@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Luma

cd /d "%~dp0"

set "LUMA_WTMODE=--maximized"
if /i "%~1"=="--bare" set "LUMA_WTMODE=--focus --maximized"

if not defined LUMA_FRAMED if /i not "%~1"=="--windowed" (
    where wt.exe >nul 2>&1
    if not errorlevel 1 (
        set "LUMA_FRAMED=1"
        start "" wt.exe %LUMA_WTMODE% cmd /c "%~f0"
        exit /b 0
    )
)

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
    where python >nul 2>&1 && set "PY=python"
)

if not defined PY (
    echo.
    echo   Luma needs Python, and it is not installed yet.
    echo.
    where winget >nul 2>&1
    if errorlevel 1 (
        echo   Please install Python from:
        echo       https://www.python.org/downloads/
        echo.
        echo   During setup, tick "Add python.exe to PATH".
        echo   Then run this file again.
        echo.
        pause
        exit /b 1
    )
    echo   Installing it now. This takes a couple of minutes.
    echo.
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    echo.
    echo   Python is installed. Please close this window and open Luma again
    echo   so Windows picks up the change.
    echo.
    pause
    exit /b 0
)

if not exist ".installed" (
    echo.
    echo   Setting up Luma for the first time. This happens once.
    echo.
    %PY% -m pip install --quiet --disable-pip-version-check -r requirements.txt
    if errorlevel 1 (
        echo.
        echo   Setup did not finish. Please check your internet connection
        echo   and run this file again.
        echo.
        pause
        exit /b 1
    )
    echo done > ".installed"
    echo   Ready.
    echo.
)

cls
echo.
echo      L U M A
echo      -------
echo      Starting...
echo.

%PY% -m luma %*

if errorlevel 1 (
    echo.
    echo   Luma closed unexpectedly. If this keeps happening, look in the
    echo   logs folder next to this file.
    echo.
    pause
)

endlocal
