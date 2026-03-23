from ultralytics import YOLO
import cv2
import requests
from util import read_license_plate # Ensure util.py is in your folder

license_plate_detector = YOLO('license_plate_detector.pt')
cap = cv2.VideoCapture('./sample.mp4')

seen_plates = set()
frame_count = 0

while cap.isOpened():
    ret, frame = cap.read()
    if not ret: break

    frame_count += 1
    if frame_count % 5 != 0: continue # Process every 5th frame for speed

    img = cv2.resize(frame, (640, 360))
    results = license_plate_detector(img)[0]

    for plate in results.boxes.data.tolist():
        x1, y1, x2, y2, score, _ = plate
        if score < 0.5: continue

        crop = img[int(y1):int(y2), int(x1):int(x2)]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 64, 255, cv2.THRESH_BINARY_INV)

        text, conf = read_license_plate(thresh)

        if text and conf > 0.6 and text not in seen_plates:
            seen_plates.add(text)
            
            # Default risk logic
            risk = 15 if text.startswith("HU") else 85
            
            try:
                requests.post("http://localhost:8000/scan", 
                              json={"plate": text, "risk": risk}, 
                              timeout=0.5)
                print(f"Sent: {text}")
            except:
                print("Server offline")

    cv2.imshow("Gate Vision", img)
    if cv2.waitKey(1) & 0xFF == 27: break

cap.release()
cv2.destroyAllWindows()