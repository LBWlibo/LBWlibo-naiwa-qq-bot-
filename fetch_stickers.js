// 每天自动抓几张「奶蛙」表情，去重后存进 stickers 目录
// 环境变量：STICKER_DIR（必填）、STICKER_COUNT（默认 3）、STICKER_KEYWORDS（逗号分隔，可选）
const https = require("https");
const http = require("http");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const DIR = process.env.STICKER_DIR || "";
const COUNT = Math.max(1, Math.min(10, Number(process.env.STICKER_COUNT || 3)));
const KEYWORDS = (process.env.STICKER_KEYWORDS ||
  "奶蛙 表情包,奶蛙 大笑,奶蛙 跳舞,奶家人 表情").split(",").map((s) => s.trim()).filter(Boolean);

if (!DIR) {
  console.error("STICKER_DIR not set");
  process.exit(2);
}
fs.mkdirSync(DIR, { recursive: true });

const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";

function fetchBuf(url, redirects = 0, referer = "") {
  return new Promise((resolve) => {
    const headers = { "User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9" };
    if (referer) headers["Referer"] = referer;
    const mod = url.startsWith("http:") ? http : https;
    const req = mod.get(url, { timeout: 20000, headers }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location && redirects < 4) {
        res.resume();
        return resolve(fetchBuf(new URL(res.headers.location, url).toString(), redirects + 1, referer));
      }
      const chunks = [];
      res.on("data", (c) => chunks.push(c));
      res.on("end", () => resolve({ status: res.statusCode, buf: Buffer.concat(chunks), type: res.headers["content-type"] || "" }));
    });
    req.on("error", () => resolve({ status: 0, buf: Buffer.alloc(0), type: "" }));
    req.on("timeout", () => { req.destroy(); resolve({ status: 0, buf: Buffer.alloc(0), type: "" }); });
  });
}

function decode(s) {
  return s.replace(/&quot;/g, '"').replace(/&amp;/g, "&").replace(/&#39;/g, "'");
}

async function search(q) {
  const r = await fetchBuf("https://www.bing.com/images/search?q=" + encodeURIComponent(q) + "&form=HDRSC2&first=1&count=35");
  if (r.status !== 200) return [];
  const html = decode(r.buf.toString("utf8"));
  const out = [];
  const re = /"murl":"([^"]+)"[\s\S]{0,400}?"turl":"([^"]+)"/g;
  let m;
  while ((m = re.exec(html)) !== null && out.length < 20) out.push({ murl: m[1], turl: m[2] });
  return out;
}


// 读取图片宽高（不解码整张图，只看文件头），用来过滤手机截图这类长条图
function imageSize(buf) {
  try {
    if (buf.slice(0, 8).toString("hex") === "89504e470d0a1a0a") {
      return { w: buf.readUInt32BE(16), h: buf.readUInt32BE(20) };
    }
    if (buf.slice(0, 3).toString("latin1") === "GIF") {
      return { w: buf.readUInt16LE(6), h: buf.readUInt16LE(8) };
    }
    if (buf[0] === 0xff && buf[1] === 0xd8) {
      let i = 2;
      while (i < buf.length - 9) {
        if (buf[i] !== 0xff) { i++; continue; }
        const m = buf[i + 1];
        if (m >= 0xc0 && m <= 0xcf && m !== 0xc4 && m !== 0xc8 && m !== 0xcc) {
          return { h: buf.readUInt16BE(i + 5), w: buf.readUInt16BE(i + 7) };
        }
        i += 2 + buf.readUInt16BE(i + 2);
      }
    }
  } catch { /* ignore */ }
  return null;
}

function looksLikeSticker(buf) {
  const s = imageSize(buf);
  if (!s || !s.w || !s.h) return true;            // 读不出尺寸就放过，交给去重
  if (s.w < 150 || s.h < 150) return false;        // 太小
  const ratio = s.h / s.w;
  if (ratio > 1.45 || ratio < 0.69) return false;  // 竖屏截图/长条图
  return true;
}

function extOf(buf, type) {
  if (buf.slice(0, 3).toString("latin1") === "GIF") return ".gif";
  if (buf[0] === 0xff && buf[1] === 0xd8) return ".jpg";
  if (buf.slice(0, 8).toString("hex") === "89504e470d0a1a0a") return ".png";
  if (buf.slice(0, 4).toString("latin1") === "RIFF") return ".webp";
  const t = type.toLowerCase();
  if (t.includes("png")) return ".png";
  if (t.includes("gif")) return ".gif";
  if (t.includes("webp")) return ".webp";
  return ".jpg";
}

(async () => {
  const existing = new Set();
  for (const f of fs.readdirSync(DIR)) {
    const p = path.join(DIR, f);
    try {
      if (fs.statSync(p).isFile()) existing.add(crypto.createHash("sha256").update(fs.readFileSync(p)).digest("hex"));
    } catch { /* ignore */ }
  }
  console.log("已有表情 " + existing.size + " 张，目标新增 " + COUNT + " 张");

  const day = new Date().toISOString().slice(0, 10).replace(/-/g, "");
  let added = 0;
  const seen = new Set();

  for (const q of KEYWORDS) {
    if (added >= COUNT) break;
    const items = await search(q);
    for (const it of items) {
      if (added >= COUNT) break;
      const src = it.murl.replace(/\\u002f/g, "/");
      if (seen.has(src)) continue;
      seen.add(src);
      if (/mzstatic|9k9k\.com|17yoo\.cn|sinaimg/i.test(src)) continue;

      let got = await fetchBuf(src, 0, "https://www.bing.com/");
      if (!got.buf.length || got.status !== 200) got = await fetchBuf(it.turl, 0, "https://www.bing.com/");
      if (!got.buf.length || got.status !== 200) continue;
      if (got.buf.length < 4000 || got.buf.length > 8 * 1024 * 1024) continue;

      if (!looksLikeSticker(got.buf)) { console.log("  - 跳过（尺寸不像表情）"); continue; }

      const hash = crypto.createHash("sha256").update(got.buf).digest("hex");
      if (existing.has(hash)) continue;
      existing.add(hash);

      added++;
      const name = "auto-" + day + "-" + added + extOf(got.buf, got.type);
      fs.writeFileSync(path.join(DIR, name), got.buf);
      console.log("  + " + name + " " + Math.round(got.buf.length / 1024) + "KB");
    }
  }
  console.log("完成，新增 " + added + " 张");
  process.exit(0);
})();
