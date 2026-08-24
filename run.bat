@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Luma

REM ------------------------------------------------------------------ REM
REM  Double-click launcher for Luma.                                    REM
REM   - finds Python (py launcher or python.exe)                        REM
REM   - offers to install it with winget if it is missing               REM
REM   - installs what Luma needs the first time only                    REM
REM   - starts Luma                                                     REM
REM ------------------------------------------------------------------ REM

cd /d "%~dp0"

REM --- open in its own window -----------------------------------------
REM  Luma opens maximised in Windows Terminal, which keeps the tab strip
REM  and title bar. That looks slightly busier than focus mode, but it is
REM  what you grab to move the window -- focus mode leaves nothing to drag.
REM
REM    run.bat            maximised, movable       (default)
REM    run.bat --bare     no tabs, no title bar    (cannot be dragged)
REM    run.bat --windowed plain console, no relaunch
REM
REM  F11 toggles full screen at any time, whichever was used.
REM  LUMA_FRAMED stops the relaunch from looping.
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

REM --- locate Python -------------------------------------------------
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

REM --- first run: install what Luma needs -----------------------------
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

REM --- start Luma -----------------------------------------------------
REM  Python and the interface take a moment to load. Put something on the
REM  screen so that moment is not a blank window with a blinking cursor.
cls
echo.
echo      L U M A
echo      -------
echo      Starting...
echo.

%PY% -m luma %*

REM Only pause if something went wrong, so a normal quit closes cleanly.
if errorlevel 1 (
    echo.
    echo   Luma closed unexpectedly. If this keeps happening, look in the
    echo   logs folder next to this file.
    echo.
    pause
)

endlocal
