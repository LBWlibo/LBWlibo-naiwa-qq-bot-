// 用微软 Edge 在线语音合成（免费、无需 key）生成中文男声
// 用法：node edge_tts.js "文字" 输出路径 [voice]
const { MsEdgeTTS, OUTPUT_FORMAT } = require("E:/mybot/tools/node_modules/msedge-tts/dist/index.js");
const fs = require("fs");

const [text, out, voice] = process.argv.slice(2);
if (!text || !out) {
  console.error("usage: node edge_tts.js <text> <out.mp3> [voice]");
  process.exit(2);
}

const watchdog = setTimeout(() => {
  console.error("ERR timeout");
  process.exit(1);
}, 30000);

(async () => {
  const tts = new MsEdgeTTS();
  await tts.setMetadata(voice || "zh-CN-YunjianNeural", OUTPUT_FORMAT.AUDIO_24KHZ_48KBITRATE_MONO_MP3);
  const { audioStream } = tts.toStream(text);
  const chunks = [];
  audioStream.on("data", (c) => chunks.push(c));
  audioStream.on("end", () => {
    const buf = Buffer.concat(chunks);
    if (buf.length < 2000) {
      console.error("ERR empty audio");
      process.exit(1);
    }
    fs.writeFileSync(out, buf);
    clearTimeout(watchdog);
    console.log("ok " + Math.round(buf.length / 1024) + "KB");
    process.exit(0);
  });
  audioStream.on("error", (e) => {
    console.error("ERR " + e.message);
    process.exit(1);
  });
})().catch((e) => {
  console.error("ERR " + (e && e.message ? e.message : e));
  process.exit(1);
});
