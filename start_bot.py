#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""奶娃 QQ 机器人 · 一键启动

顺序：QQ -> 等登录 -> SnowLuma -> 自动挂载 QQ -> DSH web -> 看门狗

设计要点：
- 已在跑的服务跳过，不重复拉起
- SnowLuma 冷启动不会主动发现已登录的 QQ，所以这里等登录完成再起它，
  起完再调它的内部接口「加载」一次做兜底
- 子进程用 DETACHED_PROCESS，关掉窗口后继续运行
- DSH 的 token 每次重启都变，从它日志里抓出来存到 current-url.txt
"""
from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# ── 读取本机配置（缺了就当作没配，全部走默认/探测）────────────
try:
    import config as C
except Exception:  # noqa: BLE001
    C = None


def cfg(name: str, default=None):
    return getattr(C, name, default) if C else default


ROOT = Path(cfg("ROOT", str(HERE)))
LOGS = ROOT / "logs"
URL_FILE = ROOT / "current-url.txt"

BOT_QQ = str(cfg("BOT_QQ", ""))
BOT_QQ_NUM = int(BOT_QQ) if BOT_QQ.isdigit() else 0
OWNER_QQ = cfg("OWNER_QQ", 0)

TENCENT = Path.home() / "Documents" / "Tencent Files"
QQ_LOGIN_DIR = TENCENT / BOT_QQ / "nt_qq"

SNOW_DIR = ROOT / "SnowLuma"
SNOW_NODE = SNOW_DIR / "node.exe"
SNOW_INDEX = SNOW_DIR / "index.mjs"

DSH_PROFILE = str(cfg("DSH_PROFILE", "web"))
DSH_PORT = int(cfg("DSH_PORT", 3080))

PORTS = {
    "SnowLuma WebUI": 5099,
    "SnowLuma OneBot HTTP": 3000,
    "SnowLuma OneBot WS": 3001,
    "DSH web": DSH_PORT,
}

DETACHED = 0x00000008 | 0x00000200


# ── 基础工具 ─────────────────────────────────────────────────
def log(msg: str) -> None:
    line = f"[{datetime.now():%H:%M:%S}] {msg}"
    print(line, flush=True)
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        with (LOGS / f"start-{datetime.now():%Y%m%d}.log").open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.6)
        return sock.connect_ex((host, port)) == 0


def pids_on_port(port: int) -> list[int]:
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True,
                             encoding="mbcs", errors="ignore", timeout=20).stdout
    except Exception:  # noqa: BLE001
        return []
    pids: set[int] = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0].upper() == "TCP" and parts[3].upper() == "LISTENING":
            if parts[1].rsplit(":", 1)[-1] == str(port):
                try:
                    pids.add(int(parts[4]))
                except ValueError:
                    pass
    return sorted(pids)


def kill_port(port: int) -> None:
    for pid in pids_on_port(port):
        log(f"  清理端口 {port} 上的进程 PID={pid}")
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, timeout=20)


def wait_port(port: int, want_open: bool = True, timeout: float = 90.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_open(port) == want_open:
            return True
        time.sleep(1.0)
    return port_open(port) == want_open


def wait_port_free(port: int, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not port_open(port):
            return True
        time.sleep(0.5)
    return not port_open(port)


def spawn(cmd: list[str], cwd: Path, log_name: str, env: dict | None = None) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    handle = (LOGS / log_name).open("a", encoding="utf-8", errors="replace")
    handle.write(f"\n===== launch {datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
    handle.flush()
    child_env = os.environ.copy()
    if env:
        child_env.update(env)
    subprocess.Popen(cmd, cwd=str(cwd), stdin=subprocess.DEVNULL,
                     stdout=handle, stderr=subprocess.STDOUT, env=child_env,
                     creationflags=DETACHED, close_fds=True)


def process_running(image: str) -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {image}", "/NH"],
                             capture_output=True, text=True, encoding="mbcs",
                             errors="ignore", timeout=20).stdout
        return image.lower() in out.lower()
    except Exception:  # noqa: BLE001
        return False


# ── QQ ───────────────────────────────────────────────────────
def _newest_mtime(root: Path, depth: int = 3) -> float:
    """目录树里最新的文件时间。QQ 登录只改 nt_db/*.db，父目录 mtime 不动。"""
    newest = 0.0
    stack = [(root, 0)]
    while stack:
        d, lvl = stack.pop()
        try:
            for entry in os.scandir(d):
                try:
                    if entry.is_file():
                        newest = max(newest, entry.stat().st_mtime)
                    elif entry.is_dir() and lvl < depth:
                        stack.append((Path(entry.path), lvl + 1))
                except OSError:
                    pass
        except OSError:
            pass
    return newest


def qq_login_fresh(window: int = 900) -> bool:
    try:
        return (time.time() - _newest_mtime(QQ_LOGIN_DIR)) < window
    except Exception:  # noqa: BLE001
        return False


def ensure_qq() -> None:
    if process_running("QQ.exe"):
        log("QQ：已在运行，跳过")
        return
    exe = cfg("QQ_EXE", "")
    if not exe or not Path(exe).exists():
        log("QQ：没配置 QQ_EXE 且未在运行，跳过（请手动打开 QQ）")
        return
    log(f"QQ：启动 {exe}")
    subprocess.Popen([str(exe)], cwd=str(Path(exe).parent),
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, creationflags=DETACHED, close_fds=True)
    for _ in range(60):
        if process_running("QQ.exe"):
            log("QQ：进程已起来")
            return
        time.sleep(1)
    log("QQ：60 秒内没起来")


def wait_qq_login(timeout: int = 240) -> bool:
    log(f"等待 QQ 完成登录（最多 {timeout} 秒）")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if qq_login_fresh():
            log("QQ：检测到登录态")
            return True
        time.sleep(2)
    log("QQ：等待超时，继续往下走")
    return False


# ── SnowLuma ─────────────────────────────────────────────────
def ensure_snowluma(attempt: int = 0) -> bool:
    if port_open(5099):
        if not port_open(3000) or not port_open(3001):
            log("SnowLuma：5099 在跑但还没挂上 QQ，交给自动加载")
        else:
            log("SnowLuma：已在运行，跳过")
        return True
    if attempt:
        log("SnowLuma：清端口后重试")
        kill_port(5099)
        wait_port_free(5099)
    if not (SNOW_NODE.exists() and SNOW_INDEX.exists()):
        log(f"SnowLuma：没找到 {SNOW_NODE} 或 {SNOW_INDEX}")
        return False
    log("SnowLuma：启动")
    spawn([str(SNOW_NODE), str(SNOW_INDEX)], SNOW_DIR, "snowluma.log")
    if wait_port(5099, True, 90):
        log("SnowLuma：5099 就绪")
        return True
    log("SnowLuma：90 秒未就绪")
    return False


def ensure_hooked() -> bool:
    """QQ 已登录但没挂上时，调 SnowLuma 内部接口自动「加载」。"""
    if port_open(3000) and port_open(3001):
        return True
    if not qq_login_fresh():
        return False
    password = str(cfg("SNOWLUMA_PASSWORD", "") or "")
    if not password:
        log("没配置 SnowLuma 密码，跳过自动加载（去 WebUI 手动点一次「加载」）")
        return False

    log("自动加载：调用 SnowLuma 接口挂载 QQ 进程")
    env = os.environ.copy()
    env["SL_PASSWORD"] = password
    env["SL_PORT"] = "5099"
    try:
        proc = subprocess.run([str(SNOW_NODE), str(HERE / "snowluma-load.js")],
                              cwd=str(HERE), env=env, capture_output=True, timeout=90)
        out = (proc.stdout or b"").decode("utf-8", "ignore").strip().replace("\n", " | ")
        log("  结果：" + (out[:200] if out else "无输出"))
    except Exception as exc:  # noqa: BLE001
        log("  调用失败：" + str(exc))
        return False

    for _ in range(30):
        if port_open(3000) and port_open(3001):
            log("自动加载成功：3000/3001 已就绪")
            return True
        time.sleep(1)
    log("自动加载后端口仍未就绪")
    return False


# ── DSH ──────────────────────────────────────────────────────
def find_dsh() -> str:
    exe = str(cfg("DSH_CMD", "") or "")
    if exe and Path(exe).exists():
        return exe
    import shutil
    found = shutil.which("dsh")
    if found:
        return found
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/DeepSeek Harness/resources/runtime/cli/bin/dsh.cmd"
    if local.exists():
        return str(local)
    pf = Path(r"C:\Program Files\DeepSeek Harness/resources/runtime/cli/bin/dsh.cmd")
    if pf.exists():
        return str(pf)
    return ""


def read_url(path: Path, since: int = 0) -> str | None:
    try:
        with path.open("rb") as fh:
            fh.seek(since)
            text = fh.read().decode("utf-8", errors="ignore")
    except OSError:
        return None
    found = re.findall(r"http://127\.0\.0\.1:\d+/\?token=[A-Za-z0-9_\-]+", text)
    return found[-1] if found else None


def save_url(url: str) -> None:
    URL_FILE.write_text(url + "\n", encoding="utf-8")


def ensure_dsh(attempt: int = 0) -> bool:
    dsh_log = LOGS / "dsh-web.log"
    if port_open(DSH_PORT):
        log("DSH：已在运行，跳过")
        url = read_url(dsh_log)
        if url:
            save_url(url)
        return True
    if attempt:
        log("DSH：清端口后重试")
        kill_port(DSH_PORT)
        wait_port_free(DSH_PORT)

    cmd = find_dsh()
    if not cmd:
        log("DSH：没找到 dsh 命令，请装 DeepSeek Harness 或在 config.py 填 DSH_CMD")
        return False

    start_at = dsh_log.stat().st_size if dsh_log.exists() else 0
    log("DSH：启动 " + Path(cmd).name)
    handle = open(dsh_log, "a", encoding="utf-8", errors="replace")
    subprocess.Popen(f'"{cmd}" --profile {DSH_PROFILE} --port {DSH_PORT} --no-open',
                     cwd=str(ROOT), shell=True, stdin=subprocess.DEVNULL,
                     stdout=handle, stderr=subprocess.STDOUT,
                     creationflags=DETACHED, close_fds=True)

    deadline = time.time() + 150
    while time.time() < deadline:
        if port_open(DSH_PORT):
            for _ in range(30):
                url = read_url(dsh_log, start_at)
                if url:
                    save_url(url)
                    log("DSH：就绪")
                    return True
                time.sleep(1)
            return True
        time.sleep(1)
    log("DSH：150 秒未就绪")
    return False


# ── 看门狗 ───────────────────────────────────────────────────
def ensure_watchdog() -> None:
    pid_file = LOGS / "watchdog.pid"
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True,
                             text=True, encoding="mbcs", errors="ignore", timeout=15).stdout
        if str(pid) in out:
            log("看门狗：已在运行，跳过")
            return
    except Exception:  # noqa: BLE001
        pass
    log("看门狗：启动")
    spawn([sys.executable, str(HERE / "watchdog.py")], HERE, "watchdog.out.log")


# ── 主流程 ───────────────────────────────────────────────────
def main() -> int:
    log("=" * 56)
    log("奶娃 QQ 机器人 · 启动")
    log("=" * 56)
    if C is None:
        log("!! 没找到 config.py，很多路径会走默认值；建议先跑 python setup.py")

    ensure_qq()
    wait_qq_login()

    ok_snow = ensure_snowluma()
    if not ok_snow:
        ok_snow = ensure_snowluma(attempt=1)
    if ok_snow and not (port_open(3000) and port_open(3001)):
        ensure_hooked()

    ok_dsh = ensure_dsh()
    if not ok_dsh:
        ok_dsh = ensure_dsh(attempt=1)

    log("-" * 56)
    for name, port in PORTS.items():
        log(f"  {name:<22} {port:<6} {'[OK] 监听中' if port_open(port) else '[--] 未监听'}")
    log("-" * 56)

    url = read_url(LOGS / "dsh-web.log")
    if url:
        save_url(url)
        log("DSH 面板（已存 current-url.txt）：")
        log(url)

    if not (port_open(3000) and port_open(3001)):
        log("3000/3001 没起来 = SnowLuma 还没挂上 QQ")
        log("  自动加载失败时，去 http://127.0.0.1:5099 → 进程注入 → 加载")

    ensure_watchdog()
    log("完成。QQ 里给机器人发消息即可。")
    return 0 if (ok_snow and ok_dsh) else 1


if __name__ == "__main__":
    sys.exit(main())
