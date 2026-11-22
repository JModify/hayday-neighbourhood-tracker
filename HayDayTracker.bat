@echo off
rem Hay Day Neighbourhood Tracker - double-click to start.
rem Opens the app in its own window with no console. Your data lives in
rem %LOCALAPPDATA%\HayDayTracker, so it is the same wherever you launch this from.
cd /d "%~dp0"

where pyw >nul 2>nul
if %errorlevel%==0 (
    start "" pyw -3 -m hayday_tracker
    exit /b 0
)

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw -m hayday_tracker
    exit /b 0
)

echo Python 3 was not found on this PC.
echo.
echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH"
echo (keep the "tcl/tk and IDLE" option ticked), then double-click this file again.
echo.
pause
