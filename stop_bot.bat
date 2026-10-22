@echo off
rem ASCII-only on purpose (see start_bot.bat)
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
    python "%~dp0stop_bot.py"
) else (
    echo Python not found.
)
echo.
pause
