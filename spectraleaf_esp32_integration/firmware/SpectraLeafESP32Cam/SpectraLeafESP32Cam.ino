/*
  SpectraLeaf ESP32-CAM controller

  What this firmware does:
  - Connects to Wi-Fi.
  - Moves a servo/filter wheel to the requested wavelength position.
  - Captures one JPEG with the ESP32 camera.
  - Exposes a small HTTP API used by the PC analysis app.

  API:
    GET /status
    GET /move?band=850
    GET /light?state=on
    GET /light?state=off
    GET /light?state=toggle
    GET /capture?band=850
    GET /capture?band=850&light=auto
    GET /bands

  Default board: AI Thinker ESP32-CAM.
  If your board is different, change the camera pin block below.
*/

#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>
#include <ESP32Servo.h>

// -------------------- Wi-Fi --------------------
// Direct connection mode:
// AP_MODE=true makes the ESP32 create its own Wi-Fi network.
// Connect the PC to AP_SSID, then use http://192.168.4.1 in the desktop app.
// Set AP_MODE=false only if you want the ESP32 to join an existing router.
static const bool AP_MODE = true;
static const char *WIFI_SSID = "YOUR_WIFI_NAME";
static const char *WIFI_PASS = "YOUR_WIFI_PASSWORD";
static const char *AP_SSID = "SpectraLeaf-ESP32";
static const char *AP_PASS = "spectraleaf";

// -------------------- Hardware --------------------
// Servo/filter wheel pin. Pick a pin that is free on your ESP32-CAM board.
// GPIO 12/13/14/15 can be tricky on some boards; test with your wiring.
static const int SERVO_PIN = 13;
static const int SERVO_MIN_US = 500;
static const int SERVO_MAX_US = 2500;
static const int MOVE_SETTLE_MS = 650;

// Optional light/output pins. Set to -1 if unused.
// LIGHT_PIN should drive the transistor gate/base for the box light.
// Change it to the real digital pin you wire to the transistor.
static const int LIGHT_PIN = 14;      // AI Thinker flash LED by default; replace with transistor pin.
static const bool LIGHT_ACTIVE_HIGH = true;
static const int SHUTTER_PIN = -1;   // Optional external shutter/trigger.

struct BandPosition {
  int wavelength;
  int angle;
};

// Adjust these angles to your real filter wheel positions.
BandPosition BANDS[] = {
  {532, 0},
  {556, 30},
  {680, 60},
  {725, 90},
  {850, 120},
  {940, 150},
};
static const int BAND_COUNT = sizeof(BANDS) / sizeof(BANDS[0]);

WebServer server(80);
Servo filterServo;
int currentBand = -1;
uint32_t captureCounter = 0;
bool lightOn = false;

// -------------------- AI Thinker ESP32-CAM pins --------------------
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27

#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

void addCors() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.sendHeader("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  server.sendHeader("Access-Control-Allow-Headers", "Content-Type");
}

void sendJson(int code, const String &json) {
  addCors();
  server.send(code, "application/json", json);
}

void setLight(bool enabled) {
  lightOn = enabled;
  if (LIGHT_PIN < 0) return;
  bool outputHigh = LIGHT_ACTIVE_HIGH ? enabled : !enabled;
  digitalWrite(LIGHT_PIN, outputHigh ? HIGH : LOW);
}

int findBandIndex(int wavelength) {
  for (int i = 0; i < BAND_COUNT; i++) {
    if (BANDS[i].wavelength == wavelength) return i;
  }
  return -1;
}

String bandsJson() {
  String out = "[";
  for (int i = 0; i < BAND_COUNT; i++) {
    if (i) out += ",";
    out += "{\"wavelength\":";
    out += BANDS[i].wavelength;
    out += ",\"angle\":";
    out += BANDS[i].angle;
    out += "}";
  }
  out += "]";
  return out;
}

bool moveToBand(int wavelength, String &error) {
  int index = findBandIndex(wavelength);
  if (index < 0) {
    error = "Unknown band. Use one of: " + bandsJson();
    return false;
  }

  int angle = constrain(BANDS[index].angle, 0, 180);
  filterServo.write(angle);
  currentBand = wavelength;
  delay(MOVE_SETTLE_MS);
  return true;
}

bool initCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_UXGA;
  config.jpeg_quality = 10;
  config.fb_count = 2;
  config.grab_mode = CAMERA_GRAB_LATEST;

  if (!psramFound()) {
    config.frame_size = FRAMESIZE_SVGA;
    config.jpeg_quality = 12;
    config.fb_count = 1;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", err);
    return false;
  }

  sensor_t *sensor = esp_camera_sensor_get();
  if (sensor) {
    // Keep exposure as stable as possible for multispectral comparison.
    sensor->set_brightness(sensor, 0);
    sensor->set_contrast(sensor, 0);
    sensor->set_saturation(sensor, 0);
    sensor->set_gain_ctrl(sensor, 0);
    sensor->set_exposure_ctrl(sensor, 0);
    sensor->set_whitebal(sensor, 0);
    sensor->set_awb_gain(sensor, 0);
    sensor->set_agc_gain(sensor, 8);
    sensor->set_aec_value(sensor, 450);
  }

  return true;
}

void handleRoot() {
  addCors();
  String html = "<!doctype html><html><head><meta charset='utf-8'><title>SpectraLeaf ESP32</title></head><body>";
  html += "<h1>SpectraLeaf ESP32-CAM</h1>";
  html += "<p>Use /capture?band=850, /capture?band=850&light=auto, /move?band=850, /light?state=on, /status or /bands.</p>";
  html += "<p>Current IP: ";
  html += WiFi.localIP().toString();
  html += "</p></body></html>";
  server.send(200, "text/html", html);
}

void handleStatus() {
  String json = "{";
  json += "\"ok\":true,";
  json += "\"ip\":\"" + WiFi.localIP().toString() + "\",";
  json += "\"current_band\":" + String(currentBand) + ",";
  json += "\"light_on\":";
  json += lightOn ? "true," : "false,";
  json += "\"light_pin\":" + String(LIGHT_PIN) + ",";
  json += "\"capture_counter\":" + String(captureCounter) + ",";
  json += "\"bands\":" + bandsJson();
  json += "}";
  sendJson(200, json);
}

void handleBands() {
  sendJson(200, bandsJson());
}

void handleMove() {
  if (!server.hasArg("band")) {
    sendJson(400, "{\"ok\":false,\"error\":\"Missing band query parameter\"}");
    return;
  }

  int band = server.arg("band").toInt();
  String error;
  if (!moveToBand(band, error)) {
    sendJson(400, "{\"ok\":false,\"error\":\"" + error + "\"}");
    return;
  }

  sendJson(200, "{\"ok\":true,\"band\":" + String(band) + "}");
}

void handleLight() {
  if (!server.hasArg("state")) {
    sendJson(400, "{\"ok\":false,\"error\":\"Missing state query parameter. Use on, off, or toggle.\"}");
    return;
  }

  String state = server.arg("state");
  state.toLowerCase();
  if (state == "on" || state == "1" || state == "true") {
    setLight(true);
  } else if (state == "off" || state == "0" || state == "false") {
    setLight(false);
  } else if (state == "toggle") {
    setLight(!lightOn);
  } else {
    sendJson(400, "{\"ok\":false,\"error\":\"Unknown light state. Use on, off, or toggle.\"}");
    return;
  }

  sendJson(200, "{\"ok\":true,\"light_on\":" + String(lightOn ? "true" : "false") + ",\"light_pin\":" + String(LIGHT_PIN) + "}");
}

void handleCapture() {
  if (!server.hasArg("band")) {
    sendJson(400, "{\"ok\":false,\"error\":\"Missing band query parameter\"}");
    return;
  }

  int band = server.arg("band").toInt();
  String error;
  if (!moveToBand(band, error)) {
    sendJson(400, "{\"ok\":false,\"error\":\"" + error + "\"}");
    return;
  }

  String lightMode = server.hasArg("light") ? server.arg("light") : "auto";
  lightMode.toLowerCase();
  bool previousLightState = lightOn;
  if (lightMode == "auto" || lightMode == "on") {
    setLight(true);
  } else if (lightMode == "off") {
    setLight(false);
  }

  if (SHUTTER_PIN >= 0) {
    digitalWrite(SHUTTER_PIN, HIGH);
    delay(80);
    digitalWrite(SHUTTER_PIN, LOW);
  }

  delay(80);
  camera_fb_t *fb = esp_camera_fb_get();
  if (lightMode == "auto") {
    setLight(previousLightState);
  }

  if (!fb) {
    sendJson(500, "{\"ok\":false,\"error\":\"Camera capture failed\"}");
    return;
  }

  captureCounter++;
  addCors();
  server.sendHeader("X-SpectraLeaf-Band", String(band));
  server.sendHeader("X-SpectraLeaf-Capture", String(captureCounter));
  server.sendHeader("Cache-Control", "no-store");
  server.setContentLength(fb->len);
  server.send(200, "image/jpeg", "");
  WiFiClient client = server.client();
  client.write(fb->buf, fb->len);
  esp_camera_fb_return(fb);
}

void handleOptions() {
  addCors();
  server.send(204);
}

void setupWifi() {
  if (AP_MODE) {
    WiFi.mode(WIFI_AP);
    WiFi.softAP(AP_SSID, AP_PASS);
    Serial.print("AP IP: ");
    Serial.println(WiFi.softAPIP());
    return;
  }

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Connecting to Wi-Fi");
  uint32_t started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < 20000) {
    Serial.print(".");
    delay(400);
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("Wi-Fi IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("Wi-Fi failed; starting fallback AP.");
    WiFi.mode(WIFI_AP);
    WiFi.softAP(AP_SSID, AP_PASS);
    Serial.print("AP IP: ");
    Serial.println(WiFi.softAPIP());
  }
}

void setup() {
  Serial.begin(115200);
  Serial.println();
  Serial.println("Starting SpectraLeaf ESP32-CAM");

  if (LIGHT_PIN >= 0) {
    pinMode(LIGHT_PIN, OUTPUT);
    setLight(false);
  }
  if (SHUTTER_PIN >= 0) {
    pinMode(SHUTTER_PIN, OUTPUT);
    digitalWrite(SHUTTER_PIN, LOW);
  }

  filterServo.setPeriodHertz(50);
  filterServo.attach(SERVO_PIN, SERVO_MIN_US, SERVO_MAX_US);
  filterServo.write(BANDS[0].angle);
  currentBand = BANDS[0].wavelength;
  delay(MOVE_SETTLE_MS);

  setupWifi();
  initCamera();

  server.on("/", HTTP_GET, handleRoot);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/bands", HTTP_GET, handleBands);
  server.on("/move", HTTP_GET, handleMove);
  server.on("/light", HTTP_GET, handleLight);
  server.on("/capture", HTTP_GET, handleCapture);
  server.onNotFound([]() {
    if (server.method() == HTTP_OPTIONS) {
      handleOptions();
    } else {
      sendJson(404, "{\"ok\":false,\"error\":\"Not found\"}");
    }
  });
  server.begin();
  Serial.println("HTTP server ready.");
}

void loop() {
  server.handleClient();
}
