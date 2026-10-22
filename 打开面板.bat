@echo off
rem ASCII-only on purpose (see start_bot.bat)
cd /d "%~dp0"

if not exist "%~dp0current-url.txt" (
    echo Panel URL not generated yet. Run start_bot.bat first.
    pause
    exit /b 1
)

set /p URL=<"%~dp0current-url.txt"
echo Current panel URL:
echo %URL%
echo.
start "" "%URL%"
timeout /t 2 >nul
