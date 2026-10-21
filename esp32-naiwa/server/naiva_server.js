// 奶娃实体机 · 后端骨架（Node，零额外依赖，复用已装好的 msedge-tts + ffmpeg）
//
// 流程：POST 原始 PCM（16kHz / 16bit / 单声道）
//        → ASR 识别
//        → LLM 回复（DeepSeek API）
//        → TTS（贝利亚腔）+ 转回 16k PCM
//        → 响应体直接是 PCM
//
// 启动：
//   $env:DEEPSEEK_API_KEY = "sk-..."      # 没有也行，会走兜底句子
//   node server/naiva_server.js
//
// 环境变量：
//   PORT            默认 8000
//   DEEPSEEK_API_KEY  没设就走固定回复（方便先验硬件）
//   ASR             stub | iflytek   默认 stub
//   IFlytek 需要：XFYUN_APPID / XFYUN_KEY / XFYUN_SECRET

const http = require("http");
const { execFile } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const { MsEdgeTTS, OUTPUT_FORMAT } = require("E:/mybot/tools/node_modules/msedge-tts/dist/index.js");

const PORT = Number(process.env.PORT || 8000);
const VOICE = "zh-CN-YunjianNeural";
const FFMPEG = "E:\\mybot\\tools\\node_modules\\@ffmpeg-installer\\win32-x64\\ffmpeg.exe";
const BELIAL = "asetrate=24000*0.7937,aresample=24000,atempo=1.26,bass=g=4,treble=g=-2,acrusher=bits=12:mode=log:aa=1,aecho=0.85:0.5:45:0.18";
const PERSONA = `你是奶娃：圆肚子、细四肢、爱笑。说话短，1-2 句，口语，自称"奶娃"或"我"。
正经问题必须答对，不会就说不会，不许编。答话别超过 40 个字，这是语音，长了听不完。`;

// ---------------- ASR ----------------
async function transcribe(pcm) {
  const provider = process.env.ASR || "stub";
  if (provider === "stub") {
    // 先跑通链路用：拿不到识别结果，但流程照走
    return process.env.STUB_TEXT || "你好呀";
  }
  if (provider === "iflytek") {
    // TODO: 讯飞语音听写（https://www.xfyun.cn/doc/asr/voicedictation/API.html）
    // 需要：XFYUN_APPID / XFYUN_KEY / XFYUN_SECRET，签名 + wss 上传 pcm
    throw new Error("iflytek ASR 还没实现，先改 ASR=stub");
  }
  throw new Error("未知 ASR: " + provider);
}

// ---------------- LLM ----------------
async function chat(text) {
  const key = process.env.DEEPSEEK_API_KEY;
  if (!key) {
    return "（没配 API key）奶娃听见你说「" + text.slice(0, 12) + "」了，但脑子还没接上。";
  }
  const body = JSON.stringify({
    model: "deepseek-chat",
    messages: [
      { role: "system", content: PERSONA },
      { role: "user", content: text },
    ],
    max_tokens: 120,
    temperature: 0.8,
  });
  const res = await fetch("https://api.deepseek.com/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Authorization": "Bearer " + key },
    body,
  });
  if (!res.ok) throw new Error("LLM HTTP " + res.status + " " + (await res.text()).slice(0, 200));
  const data = await res.json();
  return (data.choices?.[0]?.message?.content || "").trim() || "嗯。";
}

// ---------------- TTS ----------------
async function synth(text) {
  const tts = new MsEdgeTTS();
  await tts.setMetadata(VOICE, OUTPUT_FORMAT.AUDIO_24KHZ_48KBITRATE_MONO_MP3);
  const { audioStream } = tts.toStream(text);
  const chunks = [];
  const mp3 = await new Promise((resolve, reject) => {
    audioStream.on("data", (c) => chunks.push(c));
    audioStream.on("end", () => resolve(Buffer.concat(chunks)));
    audioStream.on("error", reject);
  });
  if (mp3.length < 2000) throw new Error("TTS 返回空音频");

  const tmpIn = path.join(os.tmpdir(), `naiva-${Date.now()}.mp3`);
  const tmpOut = path.join(os.tmpdir(), `naiva-${Date.now()}.pcm`);
  fs.writeFileSync(tmpIn, mp3);
  await new Promise((resolve, reject) => {
    execFile(FFMPEG, ["-hide_banner", "-loglevel", "error", "-y", "-i", tmpIn,
      "-af", BELIAL, "-ac", "1", "-ar", "16000", "-f", "s16le", tmpOut],
      (err) => (err ? reject(err) : resolve()));
  });
  const pcm = fs.readFileSync(tmpOut);
  fs.unlinkSync(tmpIn);
  fs.unlinkSync(tmpOut);
  return pcm;
}

// ---------------- HTTP ----------------
const server = http.createServer((req, res) => {
  if (req.method === "GET" && req.url === "/ping") {
    res.writeHead(200, { "Content-Type": "text/plain" });
    return res.end("ok");
  }
  if (req.method !== "POST" || req.url !== "/chat") {
    res.writeHead(404);
    return res.end();
  }

  const chunks = [];
  req.on("data", (c) => chunks.push(c));
  req.on("end", async () => {
    const pcm = Buffer.concat(chunks);
    const t0 = Date.now();
    try {
      if (pcm.length < 3200) throw new Error("音频太短（" + pcm.length + " 字节）");
      const text = await transcribe(pcm);
      const reply = await chat(text);
      const out = await synth(reply);
      console.log(`[${new Date().toLocaleTimeString()}] 听:「${text}」说:「${reply}」 ${pcm.length}B→${out.length}B ${Date.now() - t0}ms`);
      res.writeHead(200, { "Content-Type": "application/octet-stream", "Content-Length": out.length });
      res.end(out);
    } catch (err) {
      console.error("[ERR] " + (err && err.message ? err.message : err));
      res.writeHead(500, { "Content-Type": "text/plain" });
      res.end(String(err && err.message ? err.message : err));
    }
  });
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`奶娃后端已启动 http://0.0.0.0:${PORT}  ASR=${process.env.ASR || "stub"}  LLM=${process.env.DEEPSEEK_API_KEY ? "deepseek" : "无 key（兜底句）"}`);
});
