// ESP32 + MFRC522 RFID -> Flask attendance server
// Install in Arduino IDE: MFRC522 library + ArduinoJson (or just plain POST below, no JSON lib needed)
// Wiring (ESP32):
//   RC522 SDA  -> GPIO 21 | SCK -> GPIO 18 | MOSI -> GPIO 23 | MISO -> GPIO 19 | RST -> GPIO 22 | 3.3V -> 3.3V | GND -> GND
// Update WIFI_SSID, WIFI_PASS, SERVER_URL then upload. Tap a card -> card UID posted to /api/rfid_scan.

#include <WiFi.h>
#include <HTTPClient.h>
#include <SPI.h>
#include <MFRC522.h>

#define RST_PIN 22
#define SS_PIN  21
const char* WIFI_SSID = "YOUR_WIFI";
const char* WIFI_PASS = "YOUR_PASSWORD";
const char* SERVER_URL = "http://192.168.1.50:5000/api/rfid_scan"; // Flask PC IP

MFRC522 rfid(SS_PIN, RST_PIN);

String uidToString() {
  String s = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) s += "0";
    s += String(rfid.uid.uidByte[i], HEX);
  }
  s.toUpperCase();
  return s;
}

void setup() {
  Serial.begin(115200);
  SPI.begin();
  rfid.PCD_Init();
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Connecting WiFi");
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.println("\nConnected! Tap RFID cards.");
}

void loop() {
  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) { delay(50); return; }
  String cardId = uidToString();
  Serial.println("Card: " + cardId);
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(SERVER_URL);
    http.addHeader("Content-Type", "application/json");
    String body = "{\"card_id\":\"" + cardId + "\"}";
    int code = http.POST(body);
    Serial.printf("POST %d %s\n", code, http.getString().c_str());
    http.end();
  }
  rfid.PICC_HaltA();
  delay(1000); // debounce
}
