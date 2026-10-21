# -*- coding: utf-8 -*-
"""奶娃 QQ 机器人 · 运行时配置

由 setup.py 交互生成，**不要提交到 git**（已在 .gitignore 里）。
复制本文件为 config.py 后填自己的值也可以。
"""

# ── 两个 QQ 号 ────────────────────────────────────────────────
# 主人号：能给它下命令、能收文件的那个号
OWNER_QQ = 10000
# 机器人号：登录 SnowLuma 的那个小号
BOT_QQ = 10001

# ── 部署位置 ──────────────────────────────────────────────────
# SnowLuma / qq-bridge / stickers / sounds 都在这下面
ROOT = r"E:\mybot"

# 机器人会话的工作目录（DSH 里那个会话的 cwd；记忆和用户表情存在这里）
WORKSPACE = r"C:\Users\you\Documents\deepseek-harness\default-workspace"

# ── SnowLuma ─────────────────────────────────────────────────
# WebUI 密码，用于自动触发「加载 QQ 进程」（就是网页上那个按钮）
SNOWLUMA_PASSWORD = ""

# ── DeepSeek Harness ─────────────────────────────────────────
# dsh 启动入口（.cmd 或 .exe）；留空则自动在 PATH 和默认安装目录里找
DSH_CMD = r""
# 使用的 profile 名字
DSH_PROFILE = "web"
# DSH web 端口
DSH_PORT = 3080
