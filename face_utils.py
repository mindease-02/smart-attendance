"""
face_utils.py - Face detection + recognition using OpenCV LBPH.
No dlib / face_recognition needed. Works with opencv-contrib-python.
"""
import os
import cv2
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "face_model.yml")
LABELS_PATH = os.path.join(BASE_DIR, "face_labels.npy")
FACE_SIZE = (200, 200)
CONFIDENCE_THRESHOLD = 80  # lower = stricter. LBPH: lower distance = better match.

_cascade = None

def get_cascade():
    global _cascade
    if _cascade is None:
        path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        _cascade = cv2.CascadeClassifier(path)
    return _cascade


def extract_face_gray(image_bytes_or_path, from_bytes=False):
    """Detect largest face, return grayscale resized face (200x200) or None."""
    if from_bytes:
        arr = np.frombuffer(image_bytes_or_path, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    else:
        img = cv2.imread(image_bytes_or_path)
    if img is None:
        return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    cascade = get_cascade()
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80))
    if len(faces) == 0:
        # fallback: use whole image center-cropped (helps when photo is already a face close-up)
        h, w = gray.shape
        size = min(h, w)
        y0 = (h - size) // 2
        x0 = (w - size) // 2
        face = gray[y0:y0+size, x0:x0+size]
        return cv2.resize(face, FACE_SIZE)
    # largest face
    x, y, w, h = max(faces, key=lambda b: b[2] * b[3])
    face = gray[y:y+h, x:x+w]
    return cv2.resize(face, FACE_SIZE)


def get_recognizer():
    try:
        return cv2.face.LBPHFaceRecognizer_create()
    except AttributeError:
        raise RuntimeError(
            "cv2.face not found. Install opencv-contrib-python: pip install opencv-contrib-python"
        )


def train_model(faces_dir="static/faces"):
    """
    Retrain LBPH on all registered faces.
    Expects files named like: <student_id>_<anything>.jpg  (grayscale processed faces)
    Returns (num_faces, num_students).
    """
    faces_path = os.path.join(BASE_DIR, faces_dir)
    os.makedirs(faces_path, exist_ok=True)
    X, y = [], []
    for f in os.listdir(faces_path):
        if not f.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        try:
            label = int(f.split("_")[0])
        except ValueError:
            continue
        full = os.path.join(faces_path, f)
        img = cv2.imread(full, cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        img = cv2.resize(img, FACE_SIZE)
        X.append(img)
        y.append(label)
    if not X:
        # remove stale model
        for p in (MODEL_PATH, LABELS_PATH):
            if os.path.exists(p):
                os.remove(p)
        return 0, 0
    rec = get_recognizer()
    rec.train(X, np.array(y))
    rec.write(MODEL_PATH)
    np.save(LABELS_PATH, np.array(sorted(set(y))))
    return len(X), len(set(y))


def predict_face(face_gray):
    """Returns (predicted_label, confidence). Lower confidence = better."""
    if not os.path.exists(MODEL_PATH):
        return None, 999
    rec = get_recognizer()
    rec.read(MODEL_PATH)
    label, conf = rec.predict(cv2.resize(face_gray, FACE_SIZE))
    return int(label), float(conf)


def verify_face(image_bytes, expected_student_id, threshold=CONFIDENCE_THRESHOLD):
    """
    Compare live/captured image bytes against model.
    Returns dict {matched, predicted_id, confidence, threshold, face_found}
    """
    face = extract_face_gray(image_bytes, from_bytes=True)
    if face is None:
        return {"matched": False, "predicted_id": None, "confidence": 999,
                "threshold": threshold, "face_found": False}
    pred_id, conf = predict_face(face)
    matched = (pred_id == int(expected_student_id)) and (conf <= threshold)
    return {"matched": matched, "predicted_id": pred_id, "confidence": round(conf, 2),
            "threshold": threshold, "face_found": True}
