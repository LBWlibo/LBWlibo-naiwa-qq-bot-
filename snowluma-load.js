// 自动「加载」QQ 进程：登录 SnowLuma WebUI -> 找 QQ 进程 -> POST load
// 环境变量：SL_PASSWORD（必填）、SL_PORT（默认 5099）
const http = require("http");

const PASSWORD = process.env.SL_PASSWORD || "";
const HOST = "127.0.0.1";
const PORT = Number(process.env.SL_PORT || 5099);

function req(method, path, body, token) {
  return new Promise((resolve) => {
    const data = body ? JSON.stringify(body) : null;
    const headers = { "Content-Type": "application/json" };
    if (token) headers["Authorization"] = "Bearer " + token;
    if (data) headers["Content-Length"] = Buffer.byteLength(data);
    const r = http.request({ host: HOST, port: PORT, path, method, headers, timeout: 15000 }, (res) => {
      let b = "";
      res.on("data", (d) => (b += d));
      res.on("end", () => resolve({ status: res.statusCode, body: b }));
    });
    r.on("error", (e) => resolve({ status: 0, body: e.message }));
    r.on("timeout", () => { r.destroy(); resolve({ status: 0, body: "timeout" }); });
    if (data) r.write(data);
    r.end();
  });
}

(async () => {
  const login = await req("POST", "/api/login", { password: PASSWORD });
  let token = "";
  try { token = JSON.parse(login.body).token || ""; } catch { /* ignore */ }
  if (!token) { console.log("LOGIN_FAIL " + login.status + " " + login.body.slice(0, 80)); process.exit(2); }
  console.log("登录成功");

  const procs = await req("GET", "/api/processes", null, token);
  let list = [];
  try { list = JSON.parse(procs.body).list || []; } catch { /* ignore */ }
  console.log("QQ 进程数: " + list.length);
  for (const p of list) console.log("  pid=" + p.pid + " status=" + p.status + " loggedIn=" + p.loggedIn);
  if (!list.length) { console.log("没有可加载的进程"); process.exit(3); }

  const need = list.filter((p) => p.status !== "online" && p.status !== "loaded");
  if (!need.length) { console.log("已经在线，无需加载"); process.exit(0); }

  for (const p of need) {
    const load = await req("POST", `/api/processes/${p.pid}/load`, {}, token);
    console.log("load pid=" + p.pid + " -> " + load.status + " " + load.body.slice(0, 120));
  }
  process.exit(0);
})();
