// 奶娃实体机 · ESP32-S3 固件骨架
//
// 阶段 1（先跑这个）：按住按钮录音 3 秒 → 存 PSRAM → 松手后原样播放
// 阶段 2+：把 WAV 用 HTTP POST 到后端，收 PCM 边收边播
//
// 板子：ESP32-S3-DevKitC-1 N16R8（必须带 PSRAM）
// 库：ESP32 Arduino Core 3.x（自带 ESP_I2S.h）
//
// 接线见 README.md

#include <WiFi.h>
#include <HTTPClient.h>
#include "ESP_I2S.h"

// ---------- 引脚 ----------
#define PIN_MIC_WS    4
#define PIN_MIC_SCK   5
#define PIN_MIC_SD    6
#define PIN_SPK_LRC   15
#define PIN_SPK_BCLK  16
#define PIN_SPK_DIN   17
#define PIN_BUTTON    18

// ---------- 音频参数 ----------
#define SAMPLE_RATE   16000
#define RECORD_SECONDS 3
#define MAX_SAMPLES   (SAMPLE_RATE * RECORD_SECONDS)
#define MAX_BYTES     (MAX_SAMPLES * 2)   // 16bit mono

// ---------- WiFi / 后端 ----------
const char* WIFI_SSID = "你的WiFi名";
const char* WIFI_PASS = "你的WiFi密码";
const char* SERVER_URL = "http://192.168.1.100:8000/chat";  // 阶段 2 改成电脑 IP

I2SClass I2S_MIC;
I2SClass I2S_SPK;

int16_t* recBuf = nullptr;
size_t   recLen = 0;

// ============ 录制 ============
bool recordAudio() {
  if (recBuf == nullptr) {
    // 必须放 PSRAM，否则内部 RAM 装不下 3 秒
    recBuf = (int16_t*)heap_caps_malloc(MAX_BYTES, MALLOC_CAP_SPIRAM);
    if (recBuf == nullptr) {
      Serial.println("[ERR] PSRAM 分配失败，检查板子是否是 N16R8");
      return false;
    }
  }

  Serial.println("[REC] 开始录音");
  recLen = 0;
  uint32_t start = millis();

  while (millis() - start < RECORD_SECONDS * 1000) {
    size_t got = I2S_MIC.readBytes((char*)(recBuf + recLen), 512 * 2);
    recLen += got / 2;
    if (recLen >= MAX_SAMPLES) break;
  }
  recLen = min(recLen, (size_t)MAX_SAMPLES);
  Serial.printf("[REC] 结束，采样点 %u\n", (unsigned)recLen);
  return recLen > SAMPLE_RATE / 2;   // 少于 0.5 秒算失败
}

// ============ 播放（PCM 裸数据） ============
void playPcm(const uint8_t* data, size_t len) {
  I2S_SPK.write(data, len);
}

// ============ 播放本地录音（阶段 1 验收） ============
void playRecorded() {
  Serial.println("[PLAY] 回放");
  playPcm((const uint8_t*)recBuf, recLen * 2);
}

// ============ 上传并播放（阶段 2+） ============
void sendAndPlay() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[ERR] WiFi 未连接");
    return;
  }

  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/octet-stream");
  http.setTimeout(20000);

  int code = http.POST((uint8_t*)recBuf, recLen * 2);
  Serial.printf("[NET] HTTP %d\n", code);

  if (code == 200) {
    WiFiClient* stream = http.getStreamPtr();
    // 后端返回 16kHz/16bit/mono 裸 PCM，直接喂给 I2S
    uint8_t buf[1024];
    int total = 0;
    while (http.connected()) {
      size_t avail = stream->available();
      if (avail) {
        size_t n = stream->readBytes(buf, min(avail, sizeof(buf)));
        I2S_SPK.write(buf, n);
        total += n;
      } else {
        if (http.getSize() > 0 && total >= http.getSize()) break;
        delay(2);
      }
    }
    Serial.printf("[NET] 收到 %d 字节\n", total);
  }
  http.end();
}

// ============ 初始化 ============
void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("\n=== naiwa boot ===");

  pinMode(PIN_BUTTON, INPUT_PULLUP);

  // 麦克风：I2S0，只收
  I2S_MIC.setPins(PIN_MIC_SCK, PIN_MIC_WS, -1, PIN_MIC_SD);
  if (!I2S_MIC.begin(I2S_MODE_STD, SAMPLE_RATE, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO)) {
    Serial.println("[ERR] 麦克风 I2S 初始化失败");
  }

  // 功放：I2S1，只发
  I2S_SPK.setPins(PIN_SPK_BCLK, PIN_SPK_LRC, -1, PIN_SPK_DIN);
  if (!I2S_SPK.begin(I2S_MODE_STD, SAMPLE_RATE, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO)) {
    Serial.println("[ERR] 功放 I2S 初始化失败");
  }

  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("[WIFI] 连接中");
  for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) {
    delay(500);
    Serial.print(".");
  }
  Serial.println(WiFi.status() == WL_CONNECTED ? " OK" : " 失败（阶段1可以不用）");

  Serial.println("按按钮开始录音");
}

void loop() {
  static bool lastPressed = false;
  bool pressed = digitalRead(PIN_BUTTON) == LOW;

  if (pressed && !lastPressed) {
    if (recordAudio()) {
      // 阶段 1：先回放验证麦克风
      // playRecorded();
      // 阶段 2：改为上传
      sendAndPlay();
    }
  }
  lastPressed = pressed;
  delay(20);
}
