#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""qq.py —— 让奶娃能「动手」的小工具（OneBot v11 客户端封装）

用法（默认发给 config.py 里的 OWNER_QQ）：
  python qq.py text "内容"
  python qq.py face 14 [--count 3]
  python qq.py image <本地路径|http(s) url>
  python qq.py record <本地音频路径>
  python qq.py file <本地文件路径> [--name 显示名.docx]
  python qq.py avatar <本地路径|http(s) url>
  python qq.py shot <url> [--width 1280] [--height 800]
  python qq.py sticker [名字]        # 从 E:\mybot\stickers 里挑一张发（不填随机）
  python qq.py laugh                 # 从 E:\mybot\sounds 里挑一段音效当语音发出去
  python qq.py info

发群：任何命令加 --group <群号>；发别人：--to <QQ号>。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "http://127.0.0.1:3000"

# 读配置：路径和 QQ 号全部来自 config.py，换台机器不用改代码
try:
    import config as _C
except Exception:
    _C = None

ROOT = Path(getattr(_C, "ROOT", Path(__file__).resolve().parent))
OWNER = int(getattr(_C, "OWNER_QQ", 0) or 0)
BOT_QQ = str(getattr(_C, "BOT_QQ", ""))
WORKSPACE = Path(getattr(_C, "WORKSPACE", Path.home() / "Documents/deepseek-harness/default-workspace"))
TOKEN_FILE = ROOT / "SnowLuma" / "config" / f"onebot_{BOT_QQ}.json"
BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
]

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def load_token() -> str:
    try:
        data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        return data["networks"]["httpServers"][0]["accessToken"]
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"读不到 OneBot token：{exc}")


def call(action: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{API}/{action}", data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {load_token()}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"status": "failed", "http": exc.code, "body": exc.read().decode("utf-8", "ignore")}
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "error": str(exc)}


def target(args) -> tuple[str, int]:
    if getattr(args, "group", None):
        return "send_group_msg", int(args.group)
    return "send_private_msg", int(args.to or OWNER)


def send_segments(args, segments: list[dict]) -> dict:
    action, peer = target(args)
    key = "group_id" if action == "send_group_msg" else "user_id"
    return call(action, {key: peer, "message": segments})


def seg_face(face_id: int) -> dict:
    return {"type": "face", "data": {"id": str(face_id)}}


def seg_image(src: str) -> dict:
    return {"type": "image", "data": {"file": src}}


def seg_record(src: str) -> dict:
    return {"type": "record", "data": {"file": src}}


def find_browser() -> str | None:
    return next((p for p in BROWSERS if Path(p).exists()), None)


def screenshot(url: str, width: int, height: int) -> Path:
    browser = find_browser()
    if browser is None:
        raise SystemExit("没找到 Edge/Chrome，无法截图")
    out = Path(tempfile.gettempdir()) / f"qq-shot-{int(time.time())}.png"
    cmd = [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
           "--no-sandbox", f"--window-size={width},{height}",
           f"--screenshot={out}", url]
    proc = subprocess.run(cmd, capture_output=True, timeout=60)
    for _ in range(60):
        if out.exists() and out.stat().st_size > 0:
            time.sleep(0.2)
            return out
        time.sleep(0.5)
    raise SystemExit(f"截图失败 rc={proc.returncode} {proc.stderr.decode('utf-8', 'ignore')[:200]}")


STICKER_DIR = ROOT / "stickers"
# 主人发来、被记住的表情放这里（在机器人可写的工作区内）
USER_STICKER_DIR = WORKSPACE / "瑶瑶记忆" / "表情"
SOUND_DIR = ROOT / "sounds"
AUDIO_EXT = (".mp3", ".wav", ".m4a", ".ogg", ".aac", ".amr", ".silk")

NODE_BIN = ROOT / "tools" / "node" / "node.exe"
EDGE_TTS_JS = ROOT / "edge_tts.js"
FFMPEG_BIN = ROOT / "tools" / "node_modules" / "@ffmpeg-installer" / "win32-x64" / "ffmpeg.exe"
# 贝利亚腔：降 4 个半音 + 轻低频 + 微失真 + 短混响（用户试听定稿）
BELIAL_FILTER = ("asetrate=24000*0.7937,aresample=24000,atempo=1.26,"
                 "bass=g=4,treble=g=-2,acrusher=bits=12:mode=log:aa=1,aecho=0.85:0.5:45:0.18")
EDGE_VOICE = "zh-CN-YunjianNeural"


USAGE_FILE = ROOT / "logs" / "sticker-usage.json"


def _load_usage() -> dict:
    try:
        import json as _json
        return _json.loads(USAGE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_usage(data: dict) -> None:
    try:
        import json as _json
        USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        USAGE_FILE.write_text(_json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _all_stickers() -> list[Path]:
    files = []
    for root in (STICKER_DIR, USER_STICKER_DIR):
        if root.exists():
            files.extend(sorted(p for p in root.iterdir()
                                if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp")))
    return files


def pick_sticker(name: str = "") -> Path:
    """挑图：指定名字就尽量给，但避免和上一张重复；不指定就给最久没用的那张。"""
    import time as _time
    files = _all_stickers()
    if not files:
        raise SystemExit("表情目录里没有图片")
    usage = _load_usage()
    last = usage.get("_last", "")

    chosen = None
    if name:
        hit = [p for p in files if name.lower() in p.stem.lower()]
        if not hit:
            raise SystemExit("没有这张表情，现有：" + "、".join(p.stem for p in files))
        chosen = hit[0]
        # 和上一张撞了，就换一张最久没用的，避免连着重复
        if chosen.name == last and len(files) > 1:
            others = [p for p in files if p.name != last]
            others.sort(key=lambda p: usage.get(p.name, 0))
            chosen = others[0]
    else:
        fresh = [p for p in files if p.name != last]
        pool = fresh if fresh else files
        pool.sort(key=lambda p: usage.get(p.name, 0))
        chosen = pool[0]

    usage[chosen.name] = _time.time()
    usage["_last"] = chosen.name
    _save_usage(usage)
    return chosen


def speak(text: str, voice: str = EDGE_VOICE) -> Path:
    """Edge 在线合成 -> 降调成贝利亚腔 -> 返回音频路径。断网时抛 SystemExit。"""
    if not NODE_BIN.exists() or not EDGE_TTS_JS.exists():
        raise SystemExit("语音组件缺失：node 或 edge_tts.js 不在")
    raw = Path(tempfile.gettempdir()) / f"qq-tts-{int(time.time())}.mp3"
    out = Path(tempfile.gettempdir()) / f"qq-belial-{int(time.time())}.mp3"
    proc = subprocess.run([str(NODE_BIN), str(EDGE_TTS_JS), text, str(raw), voice],
                          capture_output=True, timeout=45)
    if not raw.exists() or raw.stat().st_size < 2000:
        raise SystemExit("语音合成失败（多半是断网）：" + proc.stderr.decode("utf-8", "ignore")[:120])
    if FFMPEG_BIN.exists():
        subprocess.run([str(FFMPEG_BIN), "-hide_banner", "-loglevel", "error", "-y",
                        "-i", str(raw), "-af", BELIAL_FILTER, "-ac", "1", "-ar", "24000",
                        str(out)], capture_output=True, timeout=60)
    return out if out.exists() else raw


def pick_sound() -> Path:
    if not SOUND_DIR.exists():
        raise SystemExit(f"音效目录不存在：{SOUND_DIR}")
    files = sorted([p for p in SOUND_DIR.iterdir() if p.suffix.lower() in AUDIO_EXT])
    if not files:
        raise SystemExit("音效目录里还没有音频，先往里放一段吧")
    import random
    return random.choice(files)


def main() -> int:
    ap = argparse.ArgumentParser(description="奶娃的 QQ 工具箱")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--to", type=int, default=OWNER, help="私聊对象 QQ 号")
        p.add_argument("--group", type=int, default=0, help="发到群")

    p = sub.add_parser("text"); p.add_argument("content"); common(p)
    p = sub.add_parser("face"); p.add_argument("face_id", type=int); p.add_argument("--count", type=int, default=1); common(p)
    p = sub.add_parser("image"); p.add_argument("src"); common(p)
    p = sub.add_parser("record"); p.add_argument("src"); common(p)
    p = sub.add_parser("file"); p.add_argument("src"); p.add_argument("--name", default=""); common(p)
    p = sub.add_parser("avatar"); p.add_argument("src")
    p = sub.add_parser("shot"); p.add_argument("url"); p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=800); common(p)
    p = sub.add_parser("sticker"); p.add_argument("name", nargs="?", default=""); common(p)
    p = sub.add_parser("laugh"); common(p)
    p = sub.add_parser("speak"); p.add_argument("text"); p.add_argument("--voice", default=EDGE_VOICE); common(p)
    sub.add_parser("info")

    args = ap.parse_args()

    if args.cmd == "info":
        print(json.dumps({"login": call("get_login_info", {}),
                          "status": call("get_status", {})}, ensure_ascii=False))
        return 0

    if args.cmd == "text":
        result = send_segments(args, [{"type": "text", "data": {"text": args.content}}])
    elif args.cmd == "face":
        segs = [seg_face(args.face_id) for _ in range(max(1, args.count))]
        result = send_segments(args, segs)
    elif args.cmd == "image":
        result = send_segments(args, [seg_image(args.src)])
    elif args.cmd == "record":
        result = send_segments(args, [seg_record(args.src)])
    elif args.cmd == "file":
        action = "upload_group_file" if args.group else "upload_private_file"
        key = "group_id" if args.group else "user_id"
        peer = args.group or (args.to or OWNER)
        result = call(action, {key: peer, "file": str(Path(args.src).resolve()),
                               "name": args.name or Path(args.src).name})
    elif args.cmd == "avatar":
        result = call("set_qq_avatar", {"file": args.src})
    elif args.cmd == "shot":
        png = screenshot(args.url, args.width, args.height)
        result = send_segments(args, [seg_image(str(png))])
    elif args.cmd == "sticker":
        png = pick_sticker(args.name)
        result = send_segments(args, [seg_image(str(png))])
    elif args.cmd == "laugh":
        clip = pick_sound()
        result = send_segments(args, [seg_record(str(clip))])
    elif args.cmd == "speak":
        clip = speak(args.text, args.voice)
        result = send_segments(args, [seg_record(str(clip))])
    else:
        return 2

    print(json.dumps(result, ensure_ascii=False))
    return 0 if str(result.get("status", "")).lower() in ("ok", "async") else 1


if __name__ == "__main__":
    sys.exit(main())
