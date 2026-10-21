// 桥接重连：SnowLuma 重启后 qq-bridge 的 WS 不会总自动接上，重发连接配置即可
// 环境变量：DSH_PORT（默认 3080）、DSH_HOME（默认 ~/.dsh）
const http = require("http");
const fs = require("fs");
const path = require("path");
const os = require("os");

const PORT = Number(process.env.DSH_PORT || 3080);
const BINDINGS = path.join(process.env.DSH_HOME || path.join(os.homedir(), ".dsh"),
  "qq-bridge", "bindings.json");

function call(p, method, body) {
  return new Promise((res) => {
    const data = body ? JSON.stringify(body) : null;
    const h = { Origin: "http://127.0.0.1:" + PORT };
    if (data) { h["Content-Type"] = "application/json"; h["Content-Length"] = Buffer.byteLength(data); }
    const r = http.request({ host: "127.0.0.1", port: PORT, path: p, method, headers: h, timeout: 10000 }, (x) => {
      let b = ""; x.on("data", (d) => (b += d));
      x.on("end", () => res({ s: x.statusCode, b }));
    });
    r.on("error", (e) => res({ s: 0, b: e.message }));
    if (data) r.write(data);
    r.end();
  });
}

(async () => {
  let sid = "";
  try { sid = Object.keys(JSON.parse(fs.readFileSync(BINDINGS, "utf8")).sessions)[0] || ""; } catch { /* ignore */ }
  const cfg = await call("/dsh-qq-bridge/state?sessionId=" + sid, "GET");
  let c = {};
  try { c = JSON.parse(cfg.b).connection || {}; } catch { /* ignore */ }
  const r = await call("/dsh-qq-bridge/connection", "POST", {
    wsUrl: c.wsUrl, httpApiUrl: c.httpApiUrl, selfId: c.selfId, autoConnect: true,
  });
  console.log("重连请求: " + r.s);
  await new Promise((x) => setTimeout(x, 2500));
  const st = await call("/dsh-qq-bridge/state?sessionId=" + sid, "GET");
  try {
    const j = JSON.parse(st.b);
    console.log("connected=" + j.connection.connected + " lastError=" + JSON.stringify(j.connection.lastError));
    process.exit(j.connection.connected ? 0 : 1);
  } catch { process.exit(1); }
})();
