@echo off
rem Same as HayDayTracker.bat but keeps a console window open so any start-up error is visible.
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -m hayday_tracker
) else (
    python -m hayday_tracker
)
echo.
echo The tracker has closed. Press any key to close this window.
pause >nul
