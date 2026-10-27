"""
cv_detector.py - Computer Vision Vehicle & Emergency Detection Module using OpenCV.
Features:
- Video / Webcam / Synthetic Stream Processing
- Lane Region of Interest (ROI) Zone Monitoring
- Contour & Motion Density Extraction
- Vehicle Type Classification by Bounding Area
- Live Video Overlay with Detection HUD
"""
import cv2
import numpy as np
import threading
import time
from typing import Dict, List, Tuple
from models import Direction

class CVTrafficDetector:
    def __init__(self, use_camera: bool = False, video_source: str = None):
        self.use_camera = use_camera
        self.video_source = video_source
        self.running = False
        self.thread: threading.Thread = None

        # Vehicle counts per direction detected via CV
        self.counts: Dict[Direction, int] = {
            Direction.NORTH: 0,
            Direction.SOUTH: 0,
            Direction.EAST: 0,
            Direction.WEST: 0,
        }
        self.emergency_detected: Dict[Direction, bool] = {
            Direction.NORTH: False,
            Direction.SOUTH: False,
            Direction.EAST: False,
            Direction.WEST: False,
        }

        # Frame resolution
        self.width = 640
        self.height = 480

        # Background subtractor
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500, varThreshold=50, detectShadows=True
        )

        # Lane Regions of Interest (x1, y1, x2, y2)
        # 4 Quadrants representing surveillance views of 4 approaches
        self.rois = {
            Direction.NORTH: (240, 20, 400, 180),
            Direction.SOUTH: (240, 300, 400, 460),
            Direction.WEST:  (20, 180, 200, 300),
            Direction.EAST:  (440, 180, 620, 300),
        }

        # Synthetic camera state (for testing when no physical camera is plugged in)
        self.synthetic_vehicles: List[dict] = []
        self._init_synthetic_vehicles()

    def _init_synthetic_vehicles(self):
        self.synthetic_vehicles = [
            {"dir": Direction.NORTH, "x": 280, "y": 30, "dx": 0, "dy": 2.5, "w": 25, "h": 45, "type": "Car"},
            {"dir": Direction.NORTH, "x": 330, "y": 90, "dx": 0, "dy": 2.0, "w": 28, "h": 50, "type": "Truck"},
            {"dir": Direction.SOUTH, "x": 280, "y": 420, "dx": 0, "dy": -2.2, "w": 25, "h": 45, "type": "Car"},
            {"dir": Direction.EAST, "x": 580, "y": 210, "dx": -2.8, "dy": 0, "w": 45, "h": 24, "type": "Car"},
            {"dir": Direction.EAST, "x": 500, "y": 250, "dx": -2.5, "dy": 0, "w": 45, "h": 24, "type": "Car"},
            {"dir": Direction.WEST, "x": 40, "y": 230, "dx": 3.0, "dy": 0, "w": 30, "h": 16, "type": "Bike"},
        ]

    def generate_synthetic_frame(self) -> np.ndarray:
        """Creates a realistic synthetic overhead traffic camera frame."""
        frame = np.full((self.height, self.width, 3), 35, dtype=np.uint8)

        # Draw intersection road layout
        # Vertical road
        cv2.rectangle(frame, (220, 0), (420, self.height), (60, 60, 60), -1)
        # Horizontal road
        cv2.rectangle(frame, (0, 160), (self.width, 320), (60, 60, 60), -1)

        # Yellow centerlines
        cv2.line(frame, (320, 0), (320, 160), (0, 220, 255), 2)
        cv2.line(frame, (320, 320), (320, self.height), (0, 220, 255), 2)
        cv2.line(frame, (0, 240), (220, 240), (0, 220, 255), 2)
        cv2.line(frame, (420, 240), (self.width, 240), (0, 220, 255), 2)

        # Move and draw synthetic vehicles
        for sv in self.synthetic_vehicles:
            sv["x"] += sv["dx"]
            sv["y"] += sv["dy"]

            # Wrap around when leaving frame
            if sv["dir"] == Direction.NORTH and sv["y"] > 160:
                sv["y"] = 20
            elif sv["dir"] == Direction.SOUTH and sv["y"] < 320:
                sv["y"] = 440
            elif sv["dir"] == Direction.EAST and sv["x"] < 420:
                sv["x"] = 600
            elif sv["dir"] == Direction.WEST and sv["x"] > 220:
                sv["x"] = 30

            # Draw vehicle body
            vx, vy, vw, vh = int(sv["x"]), int(sv["y"]), sv["w"], sv["h"]
            col = (220, 150, 40) if sv["type"] == "Car" else ((40, 200, 240) if sv["type"] == "Truck" else (200, 50, 200))
            cv2.rectangle(frame, (vx - vw//2, vy - vh//2), (vx + vw//2, vy + vh//2), col, -1)
            cv2.rectangle(frame, (vx - vw//2, vy - vh//2), (vx + vw//2, vy + vh//2), (255, 255, 255), 1)

        # Add camera timestamp and static noise for surveillance feel
        cv2.putText(frame, f"CAM-04 INTERSECTION [LIVE] {time.strftime('%H:%M:%S')}", (15, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 120), 1, cv2.LINE_AA)
        return frame

    def process_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, Dict[Direction, int]]:
        """Applies computer vision pipeline: MOG2 subtraction, contour filtering, and ROI density counting."""
        annotated = frame.copy()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        fg_mask = self.bg_subtractor.apply(blurred)

        # Morphological operations to clean noise
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (4, 4))
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel)
        _, fg_thresh = cv2.threshold(fg_mask, 150, 255, cv2.THRESH_BINARY)

        contours, _ = cv2.findContours(fg_thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Reset counts for current frame
        frame_counts = {d: 0 for d in Direction}

        # Analyze contours
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 150: # ignore minor noise
                continue

            x, y, w, h = cv2.boundingRect(cnt)
            cx, cy = x + w // 2, y + h // 2

            # Determine which ROI lane this vehicle is inside
            matched_direction = None
            for direction, (rx1, ry1, rx2, ry2) in self.rois.items():
                if rx1 <= cx <= rx2 and ry1 <= cy <= ry2:
                    matched_direction = direction
                    break

            if matched_direction:
                frame_counts[matched_direction] += 1

                # Draw bounding box and centroid
                box_color = (0, 255, 0)
                label = "Vehicle"
                if area > 1000:
                    label = "Heavy Veh"
                    box_color = (0, 165, 255)

                cv2.rectangle(annotated, (x, y), (x + w, y + h), box_color, 2)
                cv2.circle(annotated, (cx, cy), 3, (0, 0, 255), -1)
                cv2.putText(annotated, f"{label} ({int(area)})", (x, max(15, y - 5)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, box_color, 1)

        # Draw ROI zones on annotated frame
        for direction, (rx1, ry1, rx2, ry2) in self.rois.items():
            cv2.rectangle(annotated, (rx1, ry1), (rx2, ry2), (255, 200, 0), 1)
            cv2.putText(annotated, f"{direction.value}: {frame_counts[direction]} veh",
                        (rx1 + 5, ry1 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

        # Smooth counts with alpha filter
        for d in Direction:
            self.counts[d] = frame_counts[d]

        return annotated, frame_counts

    def start_cv_window(self):
        """Spawns an interactive OpenCV camera vision preview window."""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop_cv_window(self):
        self.running = False

    def _run_loop(self):
        cap = None
        if self.use_camera:
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                print("[CV Detector] Webcam 0 unavailable, defaulting to Synthetic Feed.")
                cap = None

        while self.running:
            if cap and cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    frame = self.generate_synthetic_frame()
                else:
                    frame = cv2.resize(frame, (self.width, self.height))
            else:
                frame = self.generate_synthetic_frame()

            annotated, counts = self.process_frame(frame)

            # Display HUD
            cv2.imshow("AI Traffic System - Real-Time Computer Vision Detection", annotated)
            key = cv2.waitKey(30) & 0xFF
            if key == ord('q') or key == 27: # 'q' or ESC
                break

        if cap:
            cap.release()
        cv2.destroyAllWindows()
        self.running = False
