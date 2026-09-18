"""
Smart Attendance System — Flask app
Logic: RFID card_id + Face BOTH must match the SAME student → PRESENT, else ABSENT.

RFID provision (connect hardware later):
  1) Manual entry on /attendance page (for testing without hardware)
  2) REST API: POST /api/rfid_scan  {"card_id": "A1B2C3"}  <- call from ESP32/Arduino/Raspberry Pi
  3) Live polling: GET /api/latest_scan  (frontend auto-fills card field when you tap a card)
  4) Serial bridge: run `python rfid_reader.py --port COM5 --baud 9600` (see that file)

Face provision:
  - Register page uploads face photo + NFC card number
  - Attendance page captures live face via webcam or file upload
"""
import os
import io
import csv
import sqlite3
import base64
import time
from datetime import datetime, date
from flask import Flask, request, render_template, redirect, url_for, flash, jsonify, send_file, send_from_directory, g

import cv2
import numpy as np
from face_utils import extract_face_gray, train_model, verify_face, FACE_SIZE

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Vercel serverless filesystem is read-only except /tmp (ephemeral storage)
IS_VERCEL = bool(os.environ.get("VERCEL"))
DATA_DIR = os.path.join("/tmp", "smart_attendance") if IS_VERCEL else BASE_DIR
DB_PATH = os.path.join(DATA_DIR, "attendance.db")
FACES_DIR = os.path.join(DATA_DIR, "faces")
CAPTURES_DIR = os.path.join(DATA_DIR, "captures")

os.makedirs(FACES_DIR, exist_ok=True)
os.makedirs(CAPTURES_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "smart-attendance-secret-change-me")

# In-memory latest RFID scan (hardware taps land here via /api/rfid_scan)
latest_scan = {"card_id": None, "timestamp": None}

# ---------- DB ----------
def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            roll_no TEXT UNIQUE NOT NULL,
            card_id TEXT UNIQUE NOT NULL,
            face_image TEXT,
            created_at TEXT
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            name_attempt TEXT,
            card_id_scanned TEXT,
            status TEXT NOT NULL,
            reason TEXT,
            face_confidence REAL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY(student_id) REFERENCES students(id)
        )
    """)
    db.commit()
    db.close()

init_db()

# ---------- Helpers ----------
def save_registered_face(file_storage, student_id):
    """Detect face from uploaded file, save processed gray face as <id>_*.jpg, retrain model."""
    data = file_storage.read()
    arr = np.frombuffer(data, np.uint8)
    # save original for reference
    orig_path = os.path.join(FACES_DIR, f"{student_id}_orig.jpg")
    with open(orig_path, "wb") as f:
        f.write(data)
    face = extract_face_gray(data, from_bytes=True)
    if face is None:
        os.remove(orig_path) if os.path.exists(orig_path) else None
        return None
    proc_path = os.path.join(FACES_DIR, f"{student_id}_face.jpg")
    cv2.imwrite(proc_path, face)
    if os.path.exists(orig_path):
        os.remove(orig_path)
    train_model(FACES_DIR)
    return proc_path

# ---------- Pages ----------
@app.route("/")
def index():
    db = get_db()
    total_students = db.execute("SELECT COUNT(*) c FROM students").fetchone()["c"]
    today = date.today().isoformat()
    present_today = db.execute(
        "SELECT COUNT(*) c FROM attendance WHERE status='Present' AND date(timestamp)=date(?)", (today,)).fetchone()["c"]
    db.close()
    return render_template("home.html", total=total_students, present=present_today)

@app.route("/dashboard")
def dashboard():
    db = get_db()
    total_students = db.execute("SELECT COUNT(*) c FROM students").fetchone()["c"]
    today = date.today().isoformat()
    present_today = db.execute(
        "SELECT COUNT(*) c FROM attendance WHERE status='Present' AND date(timestamp)=date(?)", (today,)).fetchone()["c"]
    absent_today = db.execute(
        "SELECT COUNT(*) c FROM attendance WHERE status='Absent' AND date(timestamp)=date(?)", (today,)).fetchone()["c"]
    recent = db.execute(
        "SELECT a.*, s.name as student_name, s.roll_no FROM attendance a "
        "LEFT JOIN students s ON s.id=a.student_id ORDER BY a.id DESC LIMIT 10").fetchall()
    db.close()
    return render_template("dashboard.html", total=total_students, present=present_today,
                           absent=absent_today, recent=recent)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        roll_no = request.form.get("roll_no", "").strip()
        card_id = request.form.get("card_id", "").strip()
        face_file = request.files.get("face_image")
        if not name or not roll_no or not card_id or not face_file or face_file.filename == "":
            flash("All fields required: Name, Roll No, NFC Card Number, Face photo.", "danger")
            return redirect(url_for("register"))
        db = get_db()
        try:
            cur = db.execute(
                "INSERT INTO students (name, roll_no, card_id, created_at) VALUES (?,?,?,?)",
                (name, roll_no, card_id, datetime.now().isoformat(timespec="seconds")))
            db.commit()
            sid = cur.lastrowid
        except sqlite3.IntegrityError:
            db.close()
            flash("Roll No or Card ID already registered. Use unique values.", "danger")
            return redirect(url_for("register"))
        db.close()
        saved = save_registered_face(face_file, sid)
        if saved is None:
            # rollback student if no face found
            db = get_db()
            db.execute("DELETE FROM students WHERE id=?", (sid,))
            db.commit(); db.close()
            flash("No face detected in uploaded photo. Upload a clear front-face photo.", "danger")
            return redirect(url_for("register"))
        # store face path
        db = get_db()
        db.execute("UPDATE students SET face_image=? WHERE id=?", (os.path.basename(saved), sid))
        db.commit(); db.close()
        flash(f"Student {name} registered! Face + NFC card linked.", "success")
        return redirect(url_for("students"))
    return render_template("register.html")

@app.route("/students")
def students():
    db = get_db()
    rows = db.execute("SELECT * FROM students ORDER BY id DESC").fetchall()
    db.close()
    return render_template("students.html", students=rows)

@app.route("/face_img/<filename>")
def face_img(filename):
    """Serve registered face images (lives in /tmp on Vercel, static locally)."""
    return send_from_directory(FACES_DIR, filename)

@app.route("/debug_env")
def debug_env():
    e = request.environ
    out = {k: e.get(k) for k in ("PATH_INFO", "SCRIPT_NAME", "REQUEST_URI", "RAW_URI", "QUERY_STRING", "HTTP_X_VERCEL_REWRITE", "HTTP_X_VERCEL_ID")}
    out["vercel_headers"] = {k: v for k, v in request.headers.items() if "vercel" in k.lower() or "rewrite" in k.lower()}
    return jsonify(out)

@app.route("/student/delete/<int:sid>", methods=["POST"])
def delete_student(sid):
    db = get_db()
    db.execute("DELETE FROM students WHERE id=?", (sid,))
    db.commit(); db.close()
    # remove face files
    for f in os.listdir(FACES_DIR):
        if f.startswith(f"{sid}_"):
            try: os.remove(os.path.join(FACES_DIR, f))
            except OSError: pass
    train_model(FACES_DIR)
    flash("Student deleted.", "info")
    return redirect(url_for("students"))

@app.route("/attendance")
def attendance_page():
    return render_template("attendance.html", latest=latest_scan)

@app.route("/logs")
def logs():
    db = get_db()
    rows = db.execute(
        "SELECT a.*, s.name as student_name, s.roll_no FROM attendance a "
        "LEFT JOIN students s ON s.id=a.student_id ORDER BY a.id DESC LIMIT 200").fetchall()
    db.close()
    return render_template("logs.html", logs=rows)

@app.route("/export_csv")
def export_csv():
    db = get_db()
    rows = db.execute(
        "SELECT a.timestamp, s.name, s.roll_no, a.card_id_scanned, a.status, a.reason, a.face_confidence "
        "FROM attendance a LEFT JOIN students s ON s.id=a.student_id ORDER BY a.id DESC").fetchall()
    db.close()
    path = os.path.join(BASE_DIR, "attendance_export.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "name", "roll_no", "card_scanned", "status", "reason", "face_confidence"])
        w.writerows([tuple(r) for r in rows])
    return send_file(path, as_attachment=True)

# ---------- Core: mark attendance (Face + RFID must match) ----------
@app.route("/mark_attendance", methods=["POST"])
def mark_attendance():
    """
    Expects: card_id (text) + face_image (file upload OR base64 webcam snapshot in 'face_data').
    Rule: card must belong to a student AND live face must match THAT SAME student → Present.
    Otherwise → Absent (with reason).
    """
    card_id = request.form.get("card_id", "").strip()
    if not card_id:
        # also accept JSON
        j = request.get_json(silent=True) or {}
        card_id = str(j.get("card_id", "")).strip()

    # get face bytes
    face_bytes = None
    if "face_image" in request.files and request.files["face_image"].filename:
        face_bytes = request.files["face_image"].read()
    elif request.form.get("face_data"):
        b64 = request.form.get("face_data")
        if "," in b64:
            b64 = b64.split(",", 1)[1]
        try:
            face_bytes = base64.b64decode(b64)
        except Exception:
            face_bytes = None

    ts = datetime.now().isoformat(timespec="seconds")
    db = get_db()
    student = db.execute("SELECT * FROM students WHERE card_id=?", (card_id,)).fetchone() if card_id else None

    def log_absent(sid, name_attempt, reason, conf=None):
        db.execute(
            "INSERT INTO attendance (student_id, name_attempt, card_id_scanned, status, reason, face_confidence, timestamp)"
            " VALUES (?,?,?,?,?,?,?)",
            (sid, name_attempt, card_id, "Absent", reason, conf, ts))
        db.commit()

    if not card_id:
        db.close()
        return jsonify({"status": "Absent", "reason": "No RFID card ID provided."}), 400
    if student is None:
        log_absent(None, "Unknown", f"Card {card_id} not registered.")
        db.close()
        return jsonify({"status": "Absent", "reason": f"Card {card_id} not registered. Please register first."})
    if not face_bytes:
        log_absent(student["id"], student["name"], "No face image provided.")
        db.close()
        return jsonify({"status": "Absent", "reason": "No face image provided."})

    # save capture for audit
    cap_name = f"cap_{student['id']}_{int(time.time())}.jpg"
    try:
        with open(os.path.join(CAPTURES_DIR, cap_name), "wb") as f:
            f.write(face_bytes)
    except OSError:
        pass

    result = verify_face(face_bytes, student["id"])
    if not result["face_found"]:
        log_absent(student["id"], student["name"], "No face detected in captured image.", result["confidence"])
        db.close()
        return jsonify({"status": "Absent", "reason": "No face detected. Look at camera and retry.",
                        "student": student["name"], "confidence": result["confidence"]})
    if result["matched"]:
        db.execute(
            "INSERT INTO attendance (student_id, name_attempt, card_id_scanned, status, reason, face_confidence, timestamp)"
            " VALUES (?,?,?,?,?,?,?)",
            (student["id"], student["name"], card_id, "Present",
             f"RFID + Face matched (conf {result['confidence']})", result["confidence"], ts))
        db.commit(); db.close()
        return jsonify({"status": "Present",
                        "reason": f"RFID + Face matched for {student['name']}.",
                        "student": student["name"], "roll_no": student["roll_no"],
                        "confidence": result["confidence"]})
    else:
        log_absent(student["id"], student["name"],
                   f"Face mismatch: card belongs to {student['name']} but face matched ID {result['predicted_id']} (conf {result['confidence']}).",
                   result["confidence"])
        db.close()
        return jsonify({"status": "Absent",
                        "reason": f"Face NOT matched for card holder {student['name']}. Marked Absent.",
                        "student": student["name"], "confidence": result["confidence"],
                        "predicted_id": result["predicted_id"]})

# ---------- RFID hardware APIs ----------
@app.route("/api/rfid_scan", methods=["POST"])
def api_rfid_scan():
    """
    Hardware (ESP32 / Arduino / Pi) calls this when a card is tapped:
      POST /api/rfid_scan  Content-Type: application/json  {"card_id": "A1B2C3"}
    """
    data = request.get_json(force=True, silent=True) or {}
    card_id = str(data.get("card_id", "")).strip()
    if not card_id:
        return jsonify({"ok": False, "error": "card_id required"}), 400
    latest_scan["card_id"] = card_id
    latest_scan["timestamp"] = datetime.now().isoformat(timespec="seconds")
    db = get_db()
    s = db.execute("SELECT name, roll_no FROM students WHERE card_id=?", (card_id,)).fetchone()
    db.close()
    return jsonify({"ok": True, "card_id": card_id,
                    "known": s is not None,
                    "student": dict(s) if s else None,
                    "message": f"Card {card_id} received. Now capture face."})

@app.route("/api/latest_scan")
def api_latest_scan():
    return jsonify(latest_scan)

@app.route("/api/students")
def api_students():
    db = get_db()
    rows = db.execute("SELECT id, name, roll_no, card_id FROM students").fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

if __name__ == "__main__":
    print("Smart Attendance running at http://127.0.0.1:5001")
    print("RFID hardware endpoint: POST /api/rfid_scan {\"card_id\": \"...\"}")
    app.run(host="0.0.0.0", port=5001, debug=True)
