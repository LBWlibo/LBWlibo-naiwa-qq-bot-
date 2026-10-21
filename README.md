# 奶娃 QQ 机器人

把 DeepSeek Harness 变成 QQ 上的一个"人"：有人格、有记忆、会发表情、能发语音。

> **个人自用项目**，代码是胶水层——真正的能力来自三个现成组件：
> [SnowLuma](https://github.com/SnowLuma/SnowLuma)（QQ 协议网关）、
> [dsh-plugin-qq-bridge](https://www.npmjs.com/package/dsh-plugin-qq-bridge)（桥接插件）、
> [DeepSeek Harness](https://github.com/deepseek-ai/dsh)（Agent 宿主）。

---

## 它长什么样

```
                        你（QQ 私聊 / 群聊）
                             │
                             ▼
                    ┌─────────────────┐
                    │    SnowLuma     │  注入 QQNT，转成 OneBot v11
                    │  3000 / 3001    │  HTTP + WebSocket
                    └────────┬────────┘
                             │ ws://127.0.0.1:3001
                             ▼
                    ┌─────────────────┐
                    │  dsh-plugin-    │  QQ 消息 ⇄ DSH 会话
                    │  qq-bridge      │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  DSH web :3080  │  人格 / 记忆 / 工具 / 模型
                    └────────┬────────┘
                             │ pwsh 调用
                             ▼
                    ┌─────────────────┐
                    │     qq.py       │  发文字/表情/语音/文件/截图/头像
                    └─────────────────┘
```

## 能做什么

| 能力 | 说明 |
|---|---|
| 人格 | 写在系统提示词里，短句口语、有情绪、反 AI 味，带安全边界 |
| 记忆 | 每天一个 `daily/YYYY-MM-DD.md`，会话第一条消息自动回看最近几天 |
| 梗本 | `梗.md` 存网络流行语，你教的新梗会自动追加 |
| 表情 | 内置表情库 + 你发来的图可"记住"，发图自动轮换避免重复 |
| 语音 | Edge 神经网络语音合成 → ffmpeg 降调做"反派腔"，或直接发预设笑声 |
| 文件 | 用 python-docx / openpyxl 生成 Word/Excel 后发出去 |
| 截图 | Edge headless 截网页，转成图片发送 |
| 守护 | 看门狗每 30 秒体检：端口掉线、轮次卡死、QQ 掉线、桥接断开，各自处置 |
| 一键启动 | `start_bot.bat`：QQ → 等登录 → SnowLuma → 自动挂载 → DSH → 看门狗 |

## 部署前你需要

| 东西 | 说明 |
|---|---|
| Windows 10/11 | 本项目按 Windows 写（用了 tasklist / netstat / PowerShell） |
| **QQNT 9.9.x** | 新版 QQ（Electron 架构）。不是 9.7 那代老 QQ |
| **一个 QQ 小号** | 机器人本体，需要手机扫码登录 |
| Python 3.10+ | 跑启动器和工具脚本 |
| [DeepSeek Harness](https://github.com/deepseek-ai/dsh) | 已安装并能登录（`dsh --version` 有输出） |
| [SnowLuma](https://github.com/SnowLuma/SnowLuma/releases) | 下载 win-x64 完整包（自带 node.exe，约 40MB） |

## 快速开始

### 1. 拿到代码

```bash
git clone https://github.com/LBWlibo/naiwa-qq-bot.git
cd naiwa-qq-bot
```

### 2. 解压 SnowLuma

把 `SnowLuma-v*-win-x64.zip` 解压成：

```
<你放这个项目的目录>\SnowLuma\
  ├─ node.exe
  ├─ index.mjs
  └─ ...
```

### 3. 装桥接插件

```bash
dsh plugin --profile web add dsh-plugin-qq-bridge
```

### 4. 跑配置向导

```bash
python setup.py
```

它会问：机器人 QQ、主人 QQ、部署目录、DSH 工作目录、SnowLuma WebUI 密码、QQ.exe 路径。
**答案只写进本机的 `config.py`，不会上传。**

### 5. 启动

双击 `start_bot.bat`。

第一次会：
1. 启动 QQ（如果没开）
2. **等你扫码登录**
3. 启动 SnowLuma，自动挂载 QQ 进程
4. 启动 DSH web（3080）
5. 启动看门狗

看到四个端口都 `[OK]` 就成功了。

### 6. 绑定会话

打开 `http://127.0.0.1:5099` 完成 SnowLuma 首次登录（改密码，**这个密码要填进 config.py 的 `SNOWLUMA_PASSWORD`**，用于自动恢复）。

然后打开 `current-url.txt` 里的 DSH 面板地址（或双击 `打开面板.bat`）：

1. 新建一个会话
2. 会话里有 `QQ …` 那一行，填 `ws://127.0.0.1:3001`、token（在 `SnowLuma/config/onebot_<机器人QQ>.json` 里）、机器人 QQ
3. 关联联系人 → 填主人 QQ

之后在 QQ 里给它发消息就能收到回复。

## 自动化说明

| 场景 | 系统怎么处理 |
|---|---|
| 开机 | 把 `自动启动.vbs` 复制到启动文件夹（`shell:startup`） |
| QQ 没登录 | 气泡通知你，不乱重启 |
| QQ 已登录但 SnowLuma 没挂上 | 自动登录 WebUI、调用 `/api/processes/<pid>/load` |
| 端口掉了 | 看门狗拉起对应服务 |
| 桥接 WS 断开 | 自动重连 |
| 会话卡死（>150s 无事件） | 重启 DSH 并在 QQ 上通知你 |

**没法自动的**：QQ 的扫码登录。腾讯要求人工验证一次设备。

## 配置项（config.py）

| 字段 | 说明 |
|---|---|
| `BOT_QQ` / `OWNER_QQ` | 机器人号 / 主人号 |
| `ROOT` | 部署目录（SnowLuma、素材都在下面） |
| `WORKSPACE` | DSH 会话的工作目录（记忆、用户表情存这里） |
| `SNOWLUMA_PASSWORD` | SnowLuma WebUI 密码，用于自动挂载 |
| `QQ_EXE` | QQ 客户端路径 |
| `DSH_CMD` | dsh 入口，留空自动找 |
| `DSH_PROFILE` / `DSH_PORT` | 默认 `web` / `3080` |

## 文件说明

```
start_bot.py / .bat      一键启动
stop_bot.py / .bat       停止（不动 QQ）
setup.py                 交互式配置向导
watchdog.py              看门狗：端口 / 卡死 / 桥接 / QQ 掉线
qq.py                    动手能力（OneBot 客户端封装）
snowluma-load.js         自动「加载」QQ 进程（WebUI 那个按钮的 API）
bridge-reconnect.js      桥接重连
edge_tts.js              Edge 语音合成
build-patch.py           生成 DSH profile 配置（人格注入）
persona_v4.py            人格正文
config.example.py        配置模板
stickers/  sounds/       表情与音效素材
esp32-naiwa/             ESP32 实体机方案（固件 + 本地后端）
```

## 改人格

编辑 `persona_v4.py`，然后：

```bash
python build-patch.py
stop_bot.bat
start_bot.bat
```

`build-patch.py` 会自动导出当前 profile、裁掉聊天用不到的工具、把人格写进 `preset-standard`。

## 素材说明

仓库自带 12 张奶蛙表情和一段笑声，**版权属于原作者**，仅供个人学习与技术研究使用。商用或再分发请自行取得授权，或换成你自己的素材（放进 `stickers/`，文件名就是命令里用的名字）。

## 常见问题

**Q：重启后机器人不说话？**
看 `logs/start-<日期>.log`。常见原因是 QQ 没登录（点过"退出登录"），或者 SnowLuma 比 QQ 先起来。本项目已经处理了后者；前者需要你扫码。

**Q：QQ 里发消息没反应，但 SnowLuma 日志里有 `[Event]`？**
桥接断了。双击 `stop_bot.bat` 再 `start_bot.bat`，或等看门狗 30 秒内自动重连。

**Q：它为什么删不了桌面文件？**
沙箱只允许写工作区。这是故意的——它只能通过 DSH 改自己地盘里的文件。

## 免责声明

- SnowLuma 是第三方项目，与腾讯无关；本项目同样无关。
- 使用非官方方式接入 QQ 有**账号风险**，请自行评估，建议用小号。
- 仅供学习与技术研究，请遵守 QQ 用户协议及当地法律。

## License

MIT
