# -*- coding: utf-8 -*-
"""把奶娃人格写进 DSH 的 web profile（生成 cordis.patch.yml）

做四件事：
1. 用 dsh 导出当前 profile 的完整配置（打补丁前的基准）
2. 取 preset-standard 那一段，裁掉聊天用不到的工具行
3. 把 persona 行换成 persona_v4.py 里的人格（QQ 号从 config.py 注入）
4. 写入 ~/.dsh/profiles/<profile>/cordis.patch.yml

改人格只需要改 persona_v4.py，然后重跑本脚本 + 重启 DSH。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

try:
    import config as C
except Exception:  # noqa: BLE001
    C = None


def cfg(name, default=None):
    return getattr(C, name, default) if C else default


ROOT = Path(cfg("ROOT", str(HERE)))
PROFILE = str(cfg("DSH_PROFILE", "web"))
DSH_HOME = Path(os.environ.get("DSH_HOME") or (Path.home() / ".dsh"))
PATCH = DSH_HOME / "profiles" / PROFILE / "cordis.patch.yml"
DUMP = ROOT / "logs" / "web-config.yml"

# 聊天用不到的工具行：一律不挂载
DROP = {
    "tool-jobs", "tool-schedule", "skill-filesystem", "tool-skill",
    "command-goal", "tool-goal", "planning", "plan-mode",
    "delegation", "tool-subagent-control", "tool-subagent-list-agents",
    "tool-subagent", "tool-subagent-fork",
    "workflow-ptc", "tool-workflow", "tool-ask-user", "tool-todo",
    "present", "tool-plugin-manager", "tool-plugin-market",
    "agent-instructions",
}

from persona_v4 import PERSONA as _PERSONA

OWNER = str(cfg("OWNER_QQ", "10000"))
PERSONA = [x.replace("{OWNER_QQ}", OWNER) for x in _PERSONA]


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
    return ""


def main() -> int:
    dsh = find_dsh()
    if not dsh:
        print("没找到 dsh，无法导出 profile 配置")
        return 1

    DUMP.parent.mkdir(parents=True, exist_ok=True)
    print("导出 profile 配置 ...")
    with DUMP.open("w", encoding="utf-8", errors="replace") as fh:
        subprocess.run([dsh, "--profile", PROFILE, "--dump-config"], stdout=fh,
                       stderr=subprocess.STDOUT, timeout=180)

    raw = DUMP.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8", errors="ignore")
    lines = text.splitlines()

    start = next(i for i, l in enumerate(lines) if l.strip() == "- id: preset-standard")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("- id: ")), len(lines))
    block = lines[start:end]

    plugins_at = next(i for i, l in enumerate(block) if l.strip() == "plugins:")
    header = block[: plugins_at + 1]

    rows: list[list[str]] = []
    for line in block[plugins_at + 1:]:
        if line.strip().startswith("- id: "):
            rows.append([line])
        elif rows:
            rows[-1].append(line)

    kept = [r for r in rows if r[0].strip().split(": ", 1)[1] not in DROP]

    out: list[str] = list(header)
    for row in kept:
        rid = row[0].strip().split(": ", 1)[1]
        if rid == "persona":
            out.append("      - id: persona")
            out.append("        name: '@deepseek-ai/dsh-persona'")
            out.append("        config:")
            out.append("          prefix: |-")
            for para in PERSONA:
                out.append(("            " + para) if para else "")
            continue
        out.extend(row)

    while len(out) > 1 and out[-1].strip() == "":
        out.pop()

    head = """# 由 build-patch.py 生成，别手改（改了重跑会覆盖）
# 这个文件覆盖 web profile 的 standard preset：人格 + 裁剪后的工具集
- id: ui-settings-general
  name: "@deepseek-ai/dsh-client-ui-settings-general"
  config:
    welcomeNoticeVersion: 2026-09-28.1
- id: agent-default-model
  name: "@deepseek-ai/dsh-agent-default-model"
  config:
    provider: deepseek-account
    model: deepseek-flash
    reasoningEffort: low
- id: sandbox-policy
  name: "@deepseek-ai/dsh-sandbox-policy"
  config:
    mode: workspace-write
    workspaceRoot: !!js process.cwd()
- id: approval
  name: "@deepseek-ai/dsh-user-approval"
  config:
    policy: never
"""

    PATCH.parent.mkdir(parents=True, exist_ok=True)
    PATCH.write_text(head + "\n" + "\n".join(out) + "\n", encoding="utf-8")
    print(f"✓ 已写入 {PATCH}")
    print(f"  工具行 {len(kept)} 个，人格 {len(PERSONA)} 段")
    print("  重启 DSH 生效：stop_bot.bat -> start_bot.bat")
    return 0


if __name__ == "__main__":
    sys.exit(main())
