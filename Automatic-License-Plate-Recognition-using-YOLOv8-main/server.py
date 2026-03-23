import cv2
import sqlite3
import torch
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from ultralytics import YOLO
from datetime import datetime
import json

# Initialize FastAPI
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database Setup
DB = "gate.db"
def init_db():
    conn = sqlite3.connect(DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plate TEXT,
            timestamp TEXT,
            risk INTEGER,
            action TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# Load Model
model = YOLO('license_plate_detector.pt')
video_path = './sample.mp4'
seen_plates = set()

def gen_frames():
    cap = cv2.VideoCapture(video_path)
    while True:
        success, frame = cap.read()
        if not success:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0) # Loop video
            continue
        
        # Run Detection every few frames to save CPU
        results = model(frame, verbose=False)[0]
        for box in results.boxes.data.tolist():
            x1, y1, x2, y2, conf, cls = box
            if conf > 0.5:
                # In a real app, you'd perform OCR here. 
                # For this demo, we simulate a detection trigger:
                plate_placeholder = "ABCD1234" if conf > 0.8 else "UNKNOWN"
                
                if plate_placeholder not in seen_plates:
                    process_detection(plate_placeholder)
                    seen_plates.add(plate_placeholder)

                # Draw box on stream
                cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)

        # Encode for Web Stream
        ret, buffer = cv2.imencode('.jpg', cv2.resize(frame, (640, 360)))
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

def process_detection(plate):
    is_auth = plate.upper() == "ABCD1234"
    risk = 0 if is_auth else 85
    action = "GATE OPEN" if is_auth else "GATE HOLD"
    
    conn = sqlite3.connect(DB)
    conn.execute(
        "INSERT INTO logs (plate, timestamp, risk, action) VALUES (?,?,?,?)",
        (plate, datetime.now().strftime("%H:%M:%S"), risk, action)
    )
    conn.commit()
    conn.close()

@app.get("/video_feed")
async def video_feed():
    return StreamingResponse(gen_frames(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/logs")
async def get_logs():
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    # Increased limit to 100 to show more history
    cursor.execute("SELECT plate, timestamp, risk, action FROM logs ORDER BY id DESC LIMIT 100")
    rows = cursor.fetchall()
    conn.close()
    return [{"plate": r[0], "time": r[1], "risk": r[2], "action": r[3]} for r in rows]