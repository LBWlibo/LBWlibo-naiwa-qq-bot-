#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""yaoyao QQ 机器人停止器：关掉 DSH(3080) 和 SnowLuma(5099/3000/3001)。QQ 不动。"""
import subprocess
import sys
from pathlib import Path

PORTS = {5099: "SnowLuma WebUI", 3000: "SnowLuma HTTP", 3001: "SnowLuma WS", 3080: "DSH web"}


def pids_on_port(port: int) -> list[int]:
    pids: set[int] = set()
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True,
                             encoding="mbcs", errors="ignore", timeout=20).stdout
    except Exception:
        return []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0].upper() == "TCP" and parts[3].upper() == "LISTENING":
            if parts[1].rsplit(":", 1)[-1] == str(port):
                try:
                    pids.add(int(parts[4]))
                except ValueError:
                    pass
    return sorted(pids)


def stop_watchdog() -> None:
    """先停看门狗，否则它会把刚停掉的服务又拉起来。"""
    pid_file = Path(r"E:\mybot\logs\watchdog.pid")
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except Exception:  # noqa: BLE001
        return
    print(f"停止看门狗 (PID {pid})")
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, timeout=20)
    try:
        pid_file.unlink()
    except OSError:
        pass


def main() -> int:
    stop_watchdog()
    for port, name in PORTS.items():
        for pid in pids_on_port(port):
            print(f"停止 {name} (端口 {port}, PID {pid})")
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                           capture_output=True, timeout=20)
    print("已停止。QQ 没动。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
