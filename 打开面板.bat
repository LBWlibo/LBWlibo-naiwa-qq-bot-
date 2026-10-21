@echo off
chcp 65001 >nul
title 打开奶娃面板
cd /d "%~dp0"

if not exist "%~dp0current-url.txt" (
    echo 还没生成链接，先双击 start_bot.bat 把机器人拉起来。
    pause
    exit /b 1
)

set /p URL=<"%~dp0current-url.txt"
echo 当前面板地址：
echo %URL%
echo.
echo 正在用默认浏览器打开...
start "" "%URL%"
timeout /t 2 >nul
