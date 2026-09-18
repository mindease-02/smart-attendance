"""
rfid_reader.py — Serial bridge between a physical RFID reader and the Flask website.

Use when you connect your RFID reader afterwards:
  1) Connect reader via USB (Arduino + RC522, ESP32, or USB RFID keyboard-wedge reader).
  2) Run:  python rfid_reader.py --port COM5 --baud 9600 --server http://127.0.0.1:5001
     (on Mac/Linux port looks like /dev/ttyUSB0 or /dev/cu.usbserial-XXXX)
  3) Every card tap is POSTed to /api/rfid_scan, and the attendance page auto-fills it.

For USB readers that type the card number + Enter (keyboard wedge), use:
  python rfid_reader.py --keyboard --server http://127.0.0.1:5001
  then just tap cards while this script runs (typed input is forwarded).
"""
import argparse
import sys
import time
import json

try:
    import requests
except ImportError:
    print("Install requests: pip install requests")
    sys.exit(1)


def send_scan(server, card_id):
    card_id = str(card_id).strip()
    if not card_id:
        return
    try:
        r = requests.post(f"{server.rstrip('/')}/api/rfid_scan", json={"card_id": card_id}, timeout=5)
        print(f"[RFID] {card_id} -> {r.status_code} {r.text}")
    except Exception as e:
        print(f"[RFID] {card_id} FAILED: {e}")


def serial_mode(port, baud, server):
    try:
        import serial
    except ImportError:
        print("Install pyserial: pip install pyserial")
        sys.exit(1)
    print(f"Listening on serial {port} @ {baud} -> {server}")
    ser = serial.Serial(port, baud, timeout=1)
    time.sleep(2)
    buf = ""
    while True:
        try:
            if ser.in_waiting:
                chunk = ser.read(ser.in_waiting).decode(errors="ignore")
                buf += chunk
                # card IDs usually end with newline
                while "\n" in buf or "\r" in buf:
                    for sep in ("\r\n", "\n", "\r"):
                        if sep in buf:
                            line, buf = buf.split(sep, 1)
                            line = line.strip()
                            if line:
                                send_scan(server, line)
                            break
            else:
                time.sleep(0.05)
        except KeyboardInterrupt:
            print("\nStopped.")
            break


def keyboard_mode(server):
    print(f"Keyboard-wedge mode -> {server}. Tap RFID cards (type + Enter). Ctrl+C to stop.")
    try:
        while True:
            line = input().strip()
            if line:
                send_scan(server, line)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM5", help="Serial port, e.g. COM5 or /dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--server", default="http://127.0.0.1:5001")
    ap.add_argument("--keyboard", action="store_true", help="Use keyboard-wedge mode instead of serial")
    args = ap.parse_args()
    if args.keyboard:
        keyboard_mode(args.server)
    else:
        serial_mode(args.port, args.baud, args.server)
