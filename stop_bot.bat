@echo off
chcp 65001 >nul
title 奶娃停止器
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
    python "%~dp0stop_bot.py"
) else (
    echo 没找到 python。
)
echo.
pause
