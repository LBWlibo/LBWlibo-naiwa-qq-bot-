#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""watchdog.py —— 机器人看门狗

每 30 秒做一次体检：
1. 四个端口（3000/3001/5099/3080）有没有掉
2. QQ 会话是不是卡在一个没结束的轮次上（常见故障：模型请求挂死，消息全积压）

发现异常就自救：调 start_bot.py 拉起缺的服务；卡死就重启 3080，并在 QQ 上吼一声。

只允许一个实例：pid 文件 + 进程核查。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import zlib
from datetime import datetime
from pathlib import Path

try:
    import compression.zstd as zstd  # Python 3.14+
except Exception:  # noqa: BLE001
    zstd = None

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
try:
    import config as _C
except Exception:
    _C = None


def _cfg(name, default=None):
    return getattr(_C, name, default) if _C else default


ROOT = Path(_cfg("ROOT", str(HERE)))
LOGS = ROOT / "logs"
PID_FILE = LOGS / "watchdog.pid"
STATE_FILE = LOGS / "watchdog-state.json"

DSH_HOME = Path(os.environ.get("DSH_HOME") or (Path.home() / ".dsh"))
BINDINGS = DSH_HOME / "qq-bridge" / "bindings.json"

BOT_QQ = str(_cfg("BOT_QQ", ""))
QQ_LOGIN_DIR = Path.home() / "Documents" / "Tencent Files" / BOT_QQ / "nt_qq"

DSH_PORT = int(_cfg("DSH_PORT", 3080))
PORTS = {5099: "SnowLuma-WebUI", 3000: "OneBot-HTTP", 3001: "OneBot-WS", DSH_PORT: "DSH-web"}


def session_file() -> Path | None:
    """从 bindings.json 找到当前绑定的会话，再去 DSH 会话目录里定位日志。"""
    try:
        import json as _json
        sid = next(iter(_json.loads(BINDINGS.read_text(encoding="utf-8")).get("sessions", {})), "")
    except Exception:
        return None
    if not sid:
        return None
    hits = list((DSH_HOME / "sessions").glob(f"*/{sid}/session.v4.jsonl.zstd"))
    return hits[0] if hits else None
STUCK_SECONDS = 150          # 一个轮次超过这么久没动静就算卡死
CHECK_INTERVAL = 30

DETACHED = 0x08000000 | 0x00000200  # CREATE_NO_WINDOW
NO_WINDOW = 0x08000000

# 所有子进程都不弹控制台窗口（否则每 30 秒闪一次黑框）
_orig_run = subprocess.run


def _quiet_run(*args, **kwargs):
    kwargs.setdefault("creationflags", NO_WINDOW)
    return _orig_run(*args, **kwargs)


subprocess.run = _quiet_run


def _newest_mtime(root: Path, depth: int = 3) -> float:
    newest = 0.0
    stack = [(root, 0)]
    while stack:
        d, lvl = stack.pop()
        try:
            for e in os.scandir(d):
                try:
                    if e.is_file():
                        newest = max(newest, e.stat().st_mtime)
                    elif e.is_dir() and lvl < depth:
                        stack.append((Path(e.path), lvl + 1))
                except OSError:
                    pass
        except OSError:
            pass
    return newest


def qq_login_fresh(window: int = 900) -> bool:
    """登录库里有文件在 window 秒内被写过 = QQ 在线（不能看目录 mtime）。"""
    try:
        return (time.time() - _newest_mtime(QQ_LOGIN_DIR)) < window
    except Exception:
        return False


def log(msg: str) -> None:
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    with (LOGS / "watchdog.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def bridge_connected() -> bool:
    """qq-bridge 的 WS 是否真的连着（SnowLuma 重启后经常假死在这里）"""
    import urllib.request, json as _json
    try:
        sid = ""
        b = BINDINGS.read_text(encoding="utf-8")
        sid = next(iter(_json.loads(b).get("sessions", {})), "")
        url = f"http://127.0.0.1:{DSH_PORT}/dsh-qq-bridge/state?sessionId={sid}"
        req = urllib.request.Request(url, headers={"Origin": f"http://127.0.0.1:{DSH_PORT}"})
        with urllib.request.urlopen(req, timeout=5) as r:
            j = _json.loads(r.read().decode("utf-8"))
        return bool(j.get("connection", {}).get("connected"))
    except Exception:
        return False


def bridge_reconnect() -> None:
    try:
        subprocess.run([sys.executable, str(HERE / "bridge-reconnect.js")] if False else [str(ROOT / "SnowLuma" / "node.exe"), str(HERE / "bridge-reconnect.js")],
                       cwd=str(ROOT), capture_output=True, timeout=40)
    except Exception:
        pass


def try_load_qq() -> bool:
    """轻量补挂：只调 SnowLuma 的 load 接口，不重启任何服务。"""
    pw = str(_cfg("SNOWLUMA_PASSWORD", "") or "")
    node = ROOT / "SnowLuma" / "node.exe"
    script = HERE / "snowluma-load.js"
    if not pw or not node.exists() or not script.exists():
        return False
    env = os.environ.copy()
    env["SL_PASSWORD"] = pw
    env["SL_PORT"] = "5099"
    try:
        subprocess.run([str(node), str(script)], cwd=str(HERE), env=env,
                       capture_output=True, timeout=90)
    except Exception:
        return False
    for _ in range(15):
        if port_open(3000) and port_open(3001):
            return True
        time.sleep(1)
    return False


def toast(title: str, message: str) -> None:
    """Windows 气泡通知（QQ 掉线时提醒用户去扫码）"""
    try:
        subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                          "-File", str(ROOT / "toast.ps1"),
                          "-Title", title, "-Message", message],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, creationflags=DETACHED, close_fds=True)
    except Exception:
        pass


def port_open(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def pids_on_port(port: int) -> list[int]:
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True,
                             encoding="mbcs", errors="ignore", timeout=15).stdout
    except Exception:  # noqa: BLE001
        return []
    pids = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0].upper() == "TCP" and parts[3].upper() == "LISTENING":
            if parts[1].rsplit(":", 1)[-1] == str(port):
                try:
                    pids.add(int(parts[4]))
                except ValueError:
                    pass
    return sorted(pids)


def session_state() -> dict | None:
    """返回 {open: bool, last_type, last_age_s, seq}，读不到就 None。"""
    path = session_file()
    if path is None:
        return None
    try:
        stat = path.stat()
    except OSError:
        return None
    age = time.time() - stat.st_mtime
    if zstd is None:
        return {"open": None, "last_type": "?", "last_age_s": age, "seq": -1}

    try:
        head = path.read_bytes()
        raw = zstd.decompress(head).decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        return {"open": None, "last_type": "?", "last_age_s": age, "seq": -1}

    last = None
    turn_open = False
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        last = ev
        if ev.get("type") == "turn/start":
            turn_open = True
        elif ev.get("type") == "turn/end":
            turn_open = False
    return {
        "open": turn_open,
        "last_type": (last or {}).get("type", "?"),
        "last_age_s": age,
        "seq": (last or {}).get("seq", -1),
    }


def notify_owner(text: str) -> None:
    try:
        subprocess.run([sys.executable, str(HERE / "qq.py"), "text", text],
                       cwd=str(ROOT), capture_output=True, timeout=30)
    except Exception:  # noqa: BLE001
        pass


def run_starter() -> None:
    log("→ 调用 start_bot.py 补齐服务")
    subprocess.run([sys.executable, str(HERE / "start_bot.py")],
                   cwd=str(ROOT), capture_output=True, timeout=300)


def restart_dsh(reason: str) -> None:
    log(f"→ 重启 DSH(3080)：{reason}")
    for pid in pids_on_port(3080):
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, timeout=20)
    for _ in range(20):
        if not port_open(3080):
            break
        time.sleep(0.5)
    run_starter()
    time.sleep(5)
    if port_open(3001):
        notify_owner("我刚才卡了一下，已经自己重启好了 😅 你再说一遍？")
    log("→ 重启完成，已通知主人")


def already_running() -> bool:
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    except Exception:  # noqa: BLE001
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True,
                             text=True, encoding="mbcs", errors="ignore", timeout=15).stdout
        return str(pid) in out
    except Exception:  # noqa: BLE001
        return False


def main() -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    if already_running():
        log("已有看门狗在跑，退出")
        return 0
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    log(f"看门狗启动 pid={os.getpid()}，每 {CHECK_INTERVAL}s 体检一次")

    state = {"restarts": 0, "last_restart": 0}
    try:
        last_offline_notice = 0.0
        last_load_try = 0.0
        bridge_fail = 0
        last_bridge_fix = 0.0
        while True:
            down = [p for p in PORTS if not port_open(p)]
            if down:
                only_onebot = set(down) <= {3000, 3001} and port_open(5099)
                if only_onebot:
                    # 只掉 OneBot 端口：SnowLuma 活着。这里不自动重启，
                    # 只在 QQ 没登录时提醒一次（登录后由启动脚本负责挂载）。
                    if not qq_login_fresh() and time.time() - last_offline_notice > 600:
                        last_offline_notice = time.time()
                        log("QQ 掉线：OneBot 端口未监听（5099 正常）。"
                            "需要人工在 QQ 客户端重新登录，登录后会自动恢复。")
                        toast("奶娃掉线了", "QQ 退出登录了，去扫码登录一下；登完会自动恢复")
                    elif qq_login_fresh() and time.time() - last_load_try > 300:
                        last_load_try = time.time()
                        log("QQ 在线但 OneBot 没起来：尝试自动挂载（不重启）")
                        if try_load_qq():
                            log("自动挂载成功")
                        else:
                            log("自动挂载没成功，需要时手动跑一次 start_bot.bat")
                else:
                    log("发现掉线端口：" + ", ".join(f"{p}({PORTS[p]})" for p in down))
                    run_starter()
                    time.sleep(10)
                    still = [p for p in down if not port_open(p)]
                    if still and not (set(still) <= {3000, 3001} and port_open(5099)):
                        log("补齐失败，仍有端口未起：" + ", ".join(map(str, still)))

            if port_open(3000) and port_open(3001) and port_open(3080):
                if bridge_connected():
                    bridge_fail = 0
                else:
                    bridge_fail += 1
                    if bridge_fail >= 2 and time.time() - last_bridge_fix > 180:
                        last_bridge_fix = time.time()
                        log("桥接连续两次断开，尝试重连")
                        bridge_reconnect()
                        if bridge_connected():
                            log("桥接重连成功")
                            bridge_fail = 0

            st = session_state()
            if st and st.get("open") and st.get("last_age_s", 0) > STUCK_SECONDS:
                if time.time() - state["last_restart"] > 300:
                    state["restarts"] += 1
                    state["last_restart"] = time.time()
                    restart_dsh(f"轮次卡死 {int(st['last_age_s'])}s，最后事件 {st['last_type']}")
                    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
                else:
                    log(f"检测到卡死（{int(st['last_age_s'])}s），但 5 分钟内已重启过，跳过")

            time.sleep(CHECK_INTERVAL)
    except KeyboardInterrupt:
        log("收到中断，退出")
    finally:
        try:
            PID_FILE.unlink()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
