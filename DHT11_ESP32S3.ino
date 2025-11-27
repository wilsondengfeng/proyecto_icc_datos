#include <WiFi.h>
#include <WebServer.h>
#include <HTTPClient.h>
#include <DHTesp.h>
#include <ESP32Servo.h>

// Credenciales WiFi (ajusta a tu red)
const char* WIFI_SSID = "Deng";
const char* WIFI_PASS = "12345678";
// Endpoint en tu EC2 (ajusta puerto según gunicorn)
const char* SERVER_URL = "http://44.222.106.109:8000/api";
// Si en Flask dejaste API_TOKEN vacío, deja esto vacío
const char* API_TOKEN = "";

// Pines
const int DHT_PIN = 1;       // GPIO1: senal del DHT11
const int LED1_PIN = 2;      // GPIO2: LED 1
const int LED2_PIN = 42;     // GPIO42: LED 2
const int SERVO_PIN = 41;    // GPIO41: servo puerta (SG90)
const int PIR_PIN = 40;      // GPIO40: sensor movimiento SR501

const int DOOR_CLOSED_ANGLE = 0;
const int DOOR_OPEN_ANGLE = 90;

Servo doorServo;
bool doorOpen = false;

DHTesp dht;
WebServer server(80);

unsigned long lastPost = 0;
const unsigned long postIntervalMs = 5000;  // cada 5s

void sendCors() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.sendHeader("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  server.sendHeader("Access-Control-Allow-Headers", "Content-Type");
}

void handleOptions() {
  sendCors();
  server.send(204);
}

void handleRoot() {
  sendCors();
  server.send(200, "text/plain", "ESP32-S3 listo");
}

void handleLed(int pin, bool turnOn) {
  digitalWrite(pin, turnOn ? HIGH : LOW);
  sendCors();
  String body = String("{\"pin\":") + pin + ",\"on\":" + (turnOn ? "true" : "false") + "}";
  server.send(200, "application/json", body);
}

void handleSensor() {
  TempAndHumidity data = dht.getTempAndHumidity();
  sendCors();

  if (isnan(data.temperature) || isnan(data.humidity)) {
    server.send(500, "application/json", "{\"error\":\"sensor\"}");
    return;
  }

  char payload[96];
  snprintf(payload, sizeof(payload), "{\"temp\":%.2f,\"hum\":%.2f}", data.temperature, data.humidity);
  server.send(200, "application/json", payload);
}

void sendTelemetry(float temp, float hum) {
  if (WiFi.status() != WL_CONNECTED) return;
  HTTPClient http;
  WiFiClient client;
  bool motion = digitalRead(PIR_PIN) == HIGH;
  bool led1On = digitalRead(LED1_PIN) == HIGH;
  bool led2On = digitalRead(LED2_PIN) == HIGH;
  bool doorState = doorOpen;
  int doorAngle = doorState ? DOOR_OPEN_ANGLE : DOOR_CLOSED_ANGLE;
  http.begin(client, SERVER_URL);
  http.addHeader("Content-Type", "application/json");
  if (strlen(API_TOKEN) > 0) {
    http.addHeader("X-API-Key", API_TOKEN);
  }
  String body = String("{\"temp\":") + String(temp, 2) +
                ",\"hum\":" + String(hum, 2) +
                ",\"motion\":" + (motion ? "true" : "false") +
                ",\"led1\":" + (led1On ? "true" : "false") +
                ",\"led2\":" + (led2On ? "true" : "false") +
                ",\"door_open\":" + (doorState ? "true" : "false") +
                ",\"door_angle\":" + doorAngle +
                ",\"device\":\"esp32-1\"}";
  int code = http.POST(body);
  // Serial.printf("POST telemetria -> HTTP %d\n", code);
  http.end();
}

void handlePir() {
  sendCors();
  bool motion = digitalRead(PIR_PIN) == HIGH;
  server.send(200, "application/json", motion ? "{\"motion\":true}" : "{\"motion\":false}");
}

void setDoor(bool open) {
  doorOpen = open;
  doorServo.write(open ? DOOR_OPEN_ANGLE : DOOR_CLOSED_ANGLE);
  sendCors();
  String body = String("{\"open\":") + (open ? "true" : "false") + "}";
  server.send(200, "application/json", body);
}

void setupRoutes() {
  server.on("/", HTTP_GET, handleRoot);

  // DHT11
  server.on("/sensor", HTTP_GET, handleSensor);
  server.on("/sensor", HTTP_OPTIONS, handleOptions);

  // PIR
  server.on("/pir", HTTP_GET, handlePir);
  server.on("/pir", HTTP_OPTIONS, handleOptions);

  // LED GPIO2
  server.on("/led/2/on", HTTP_POST, [] { handleLed(LED1_PIN, true); });
  server.on("/led/2/off", HTTP_POST, [] { handleLed(LED1_PIN, false); });
  server.on("/led/2/on", HTTP_OPTIONS, handleOptions);
  server.on("/led/2/off", HTTP_OPTIONS, handleOptions);

  // LED GPIO42
  server.on("/led/42/on", HTTP_POST, [] { handleLed(LED2_PIN, true); });
  server.on("/led/42/off", HTTP_POST, [] { handleLed(LED2_PIN, false); });
  server.on("/led/42/on", HTTP_OPTIONS, handleOptions);
  server.on("/led/42/off", HTTP_OPTIONS, handleOptions);

  // Servo puerta
  server.on("/door/open", HTTP_POST, [] { setDoor(true); });
  server.on("/door/close", HTTP_POST, [] { setDoor(false); });
  server.on("/door/open", HTTP_OPTIONS, handleOptions);
  server.on("/door/close", HTTP_OPTIONS, handleOptions);
}

void setup() {
  Serial.begin(115200);

  pinMode(LED1_PIN, OUTPUT);
  pinMode(LED2_PIN, OUTPUT);
  digitalWrite(LED1_PIN, LOW);
  digitalWrite(LED2_PIN, LOW);
  pinMode(PIR_PIN, INPUT);

  // Timers para servo en ESP32-S3
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  ESP32PWM::allocateTimer(2);
  ESP32PWM::allocateTimer(3);
  doorServo.setPeriodHertz(50);
  doorServo.attach(SERVO_PIN, 500, 2400);
  doorServo.write(DOOR_CLOSED_ANGLE);

  dht.setup(DHT_PIN, DHTesp::DHT11);

  Serial.printf("Conectando a WiFi: %s\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  unsigned long startAttempt = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startAttempt < 15000) {
    delay(250);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("WiFi conectado. IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("No se pudo conectar a WiFi.");
  }

  setupRoutes();
  server.begin();
  Serial.println("Servidor HTTP iniciado en puerto 80.");
}

void loop() {
  server.handleClient();

  unsigned long now = millis();
  if (now - lastPost >= postIntervalMs) {
    lastPost = now;
    TempAndHumidity data = dht.getTempAndHumidity();
    if (!isnan(data.temperature) && !isnan(data.humidity)) {
      sendTelemetry(data.temperature, data.humidity);
    }
  }
}
