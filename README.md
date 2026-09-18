# 🎓 Smart Attendance System — Face ID + RFID

Marks **Present** only when **RFID card + Face match the SAME student**, else **Absent**.

## Features
- 📝 Register student: Name + Roll No + **NFC/RFID card number** + **face photo upload**
- 📡 RFID provision (connect hardware later):
  - Manual card entry (testing)
  - `POST /api/rfid_scan {"card_id": "..."}` — call from ESP32 / Arduino / Raspberry Pi
  - `GET /api/latest_scan` — frontend auto-fill polling
  - `python rfid_reader.py` — USB serial bridge for RC522/Arduino readers
  - `arduino_rfid_example.ino` — ESP32 + MFRC522 sample code
- 📷 Face capture via webcam or file upload, matched with OpenCV LBPH (no dlib needed)
- 📊 Dashboard, logs, CSV export, SQLite storage

## Run

```bash
cd smart_attendance_system
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5001

## Usage
1. **Register** → enter name, roll no, NFC card number, upload clear front face photo.
2. **Mark Attendance** → scan/type card ID → capture face → Verify.
   - Card + face same person → `Present ✅`
   - Unknown card / face mismatch / no face → `Absent ❌` with reason logged.

## Connect RFID Reader Later
**Option A — ESP32 + RC522:** upload `arduino_rfid_example.ino` (set WiFi + server IP). Each tap POSTs UID to server; attendance page auto-fills it.

**Option B — Arduino + RC522 over USB:** flash Arduino to `Serial.println(cardUID)`, then:
```bash
python rfid_reader.py --port /dev/ttyUSB0 --baud 9600
# Mac example: --port /dev/cu.usbserial-0001 | Windows: --port COM5
```

**Option C — USB keyboard-wedge reader:**
```bash
python rfid_reader.py --keyboard
```

**Option D — any device / test manually:**
```bash
curl -X POST http://127.0.0.1:5001/api/rfid_scan -H "Content-Type: application/json" -d '{"card_id":"A1B2C3"}'
```

## Files
| File | Purpose |
|---|---|
| `app.py` | Flask website + APIs |
| `face_utils.py` | Face detect/recognize (LBPH) |
| `rfid_reader.py` | Serial/keyboard → API bridge |
| `arduino_rfid_example.ino` | ESP32 firmware |
| `templates/` `static/` | Web UI |
| `attendance.db` | SQLite (auto-created) |

## Notes
- Face model: OpenCV LBPH, threshold 80 (tune `CONFIDENCE_THRESHOLD` in `face_utils.py`). Use good lighting + front face for best accuracy.
- Register each student's card UID exactly as the reader sends it (case-sensitive — use uppercase, no spaces).
