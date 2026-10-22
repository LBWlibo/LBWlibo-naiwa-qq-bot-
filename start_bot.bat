@echo off
rem ASCII-only on purpose: cmd parses .bat with the OEM codepage and
rem non-ASCII bytes break the script when launched from wscript.
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
    python "%~dp0start_bot.py"
) else (
    echo Python not found. Install Python 3.10+ and add it to PATH.
)

echo.
echo Done. You can close this window; the bot keeps running in background.
pause
