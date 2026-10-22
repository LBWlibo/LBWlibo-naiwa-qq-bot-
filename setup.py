# -*- coding: utf-8 -*-
"""奶娃 QQ 机器人 · 交互式配置向导

跑一次，把 QQ 号、部署路径、SnowLuma 密码写进 config.py。
之后再双击 start_bot.bat 就能启动。

    python setup.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT_DIR = Path(__file__).resolve().parent
CONFIG = ROOT_DIR / "config.py"


def ask(prompt: str, default: str = "") -> str:
    hint = f"（默认 {default}）" if default else ""
    try:
        val = input(f"{prompt}{hint}: ").strip()
    except EOFError:
        val = ""
    return val or default


def ask_yes(prompt: str, default: bool = True) -> bool:
    d = "Y/n" if default else "y/N"
    v = ask(f"{prompt} [{d}]", "y" if default else "n").lower()
    return v.startswith("y")


def find_dsh() -> str:
    """找 dsh 入口：PATH -> 常见安装位置。"""
    exe = shutil.which("dsh")
    if exe:
        return exe
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/DeepSeek Harness/resources/runtime/cli/bin/dsh.cmd",
        Path(r"C:\Program Files\DeepSeek Harness\resources\runtime\cli\bin\dsh.cmd"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return ""


def find_qq() -> str:
    for p in [r"E:\QQ.exe", r"C:\Program Files\Tencent\QQNT\QQ.exe",
              r"C:\Program Files (x86)\Tencent\QQNT\QQ.exe",
              os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tencent\QQNT\QQ.exe"),
              os.path.expandvars(r"%LOCALAPPDATA%\Tencent\QQNT\QQ.exe")]:
        if Path(p).exists():
            return p
    return ""


def install_autostart(root: Path) -> bool:
    """在「启动」文件夹放一个快捷方式，登录时用 wscript 隐藏启动。"""
    startup = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup"
    if not startup.exists():
        return False
    lnk = startup / "naiwa-bot.lnk"
    vbs = root / "自动启动.vbs"
    ps_lines = [
        "$ws = New-Object -ComObject WScript.Shell",
        f'$s = $ws.CreateShortcut("{lnk}")',
        '$s.TargetPath = "C:\\Windows\\System32\\wscript.exe"',
        '$s.Arguments = \'"' + str(vbs) + '"\'',
        f'$s.WorkingDirectory = "{root}"',
        "$s.WindowStyle = 7",
        "$s.Save()",
    ]
    script = Path(os.environ.get("TEMP", ".")) / "naiwa_autostart.ps1"
    script.write_text("\r\n".join(ps_lines), encoding="utf-8-sig")
    try:
        subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                       capture_output=True, timeout=60, creationflags=0x08000000)
        return lnk.exists()
    except Exception:
        return False


def main() -> int:
    print("=" * 56)
    print("奶娃 QQ 机器人 · 配置向导")
    print("=" * 56)
    print("回车用默认值。所有值只写进本机 config.py，不会上传。\n")

    bot_qq = ask("机器人 QQ（登录 SnowLuma 的小号）")
    if not bot_qq.isdigit():
        print("× 机器人 QQ 必须是数字")
        return 1
    owner_qq = ask("主人 QQ（你自己，能下命令的那个号）")
    if not owner_qq.isdigit():
        print("× 主人 QQ 必须是数字")
        return 1

    root = ask("部署目录（SnowLuma / 素材 放这里）", str(ROOT_DIR))
    workspace = ask("DSH 会话的工作目录（记忆存这里）",
                    str(Path.home() / "Documents/deepseek-harness/default-workspace"))

    print("\nSnowLuma 的 WebUI 密码（可选，填了能在 QQ 掉线后自动恢复）")
    password = ask("WebUI 密码", "")

    qq_exe = ask("QQ 客户端路径（自动登录用）", find_qq())
    dsh_cmd = ask("DSH 启动入口（.cmd 或 .exe）", find_dsh())

    content = f'''# -*- coding: utf-8 -*-
"""本机配置（不进仓库，由 setup.py 生成）"""

OWNER_QQ = {owner_qq}
BOT_QQ = {bot_qq}

ROOT = r"{root}"
WORKSPACE = r"{workspace}"

SNOWLUMA_PASSWORD = {password!r}

QQ_EXE = r"{qq_exe}"

DSH_CMD = r"{dsh_cmd}"
DSH_PROFILE = "web"
DSH_PORT = 3080
'''
    CONFIG.write_text(content, encoding="utf-8")
    print(f"\n✓ 已写入 {CONFIG}")

    # 目录检查
    rootp = Path(root)
    for sub in ("SnowLuma", "stickers", "sounds", "logs", "qq-bridge"):
        (rootp / sub).mkdir(parents=True, exist_ok=True)
    print(f"✓ 目录已就绪：{rootp}")

    missing = []
    if not (rootp / "SnowLuma" / "index.mjs").exists():
        missing.append("SnowLuma 还没解压到 " + str(rootp / "SnowLuma"))
    if not dsh_cmd:
        missing.append("没找到 dsh 命令，请手动填 DSH_CMD")
    if not qq_exe:
        missing.append("没找到 QQ.exe，请手动填 QQ_EXE")

    if missing:
        print("\n还需要处理：")
        for m in missing:
            print("  · " + m)
    if ask_yes("\n要设置开机自启吗（登录后自动启动机器人）？", True):
        if install_autostart(rootp):
            print("✓ 已加入启动文件夹")
        else:
            print("× 自启设置失败，可手动把 自动启动.vbs 的快捷方式放进 shell:startup")

    print("\n下一步：")
    print("  1. 把 SnowLuma 的 win-x64 包解压到 " + str(rootp / "SnowLuma"))
    print("  2. 装桥接插件：dsh plugin --profile web add dsh-plugin-qq-bridge")
    print("  3. 双击 start_bot.bat")
    return 0


if __name__ == "__main__":
    sys.exit(main())
