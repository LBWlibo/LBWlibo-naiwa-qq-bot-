@echo off
chcp 65001 >nul
title 奶娃启动器
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
    python "%~dp0start_bot.py"
) else (
    echo 没找到 python，请先安装 Python 3.10+ 并加入 PATH。
)

echo.
echo 窗口可以关了，机器人在后台继续跑。
pause
