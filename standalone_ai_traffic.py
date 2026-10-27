"""
standalone_ai_traffic.py - Single-File AI Traffic Signal System & Controller.
Includes:
1. 4-Way Intersection Simulation & Dynamics
2. Dynamic AI Priority Scheduling & Green Time Allocation
3. Emergency Vehicle (Ambulance) Preemption
4. Computer Vision (OpenCV) Vehicle Density Detector
5. Interactive Dark-Themed GUI with Live Telemetry & Control Deck
"""
import sys
import math
import time
import random
import threading
from enum import Enum
from typing import Dict, List, Optional
import tkinter as tk
from tkinter import ttk

# Ensure Windows terminal handles UTF-8 characters
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    import cv2
    import numpy as np
    CV_AVAILABLE = True
except ImportError:
    CV_AVAILABLE = False


# =====================================================================
# 1. MODELS & ENUMS
# =====================================================================

class Direction(Enum):
    NORTH = "North"
    SOUTH = "South"
    EAST = "East"
    WEST = "West"


class LightState(Enum):
    RED = "RED"
    YELLOW = "YELLOW"
    GREEN = "GREEN"


class VehicleType(Enum):
    CAR = ("Car", 1.0, 22, 12, "#38bdf8")
    BUS = ("Bus", 2.2, 40, 15, "#fbbf24")
    TRUCK = ("Truck", 2.0, 36, 14, "#f97316")
    BIKE = ("Motorbike", 0.5, 14, 8, "#a855f7")
    AMBULANCE = ("Ambulance", 10.0, 26, 13, "#ef4444")

    def __init__(self, label, p_weight, length, width, color):
        self.label = label
        self.priority_weight = p_weight
        self.length = length
        self.width = width
        self.color = color


class Vehicle:
    _id_counter = 0

    def __init__(self, direction: Direction, vehicle_type: VehicleType = None):
        Vehicle._id_counter += 1
        self.id = Vehicle._id_counter
        self.direction = direction
        self.vehicle_type = vehicle_type or self._random_type()
        self.pos = 0.0
        self.speed = 0.0
        self.max_speed = 3.5 if self.vehicle_type != VehicleType.AMBULANCE else 5.0
        self.is_emergency = (self.vehicle_type == VehicleType.AMBULANCE)
        self.wait_time = 0.0
        self.is_stopped = False
        self.cleared = False

        r = random.random()
        if self.is_emergency:
            self.turn_intent = "straight" if r < 0.6 else ("left" if r < 0.8 else "right")
        else:
            self.turn_intent = "straight" if r < 0.35 else ("left" if r < 0.68 else "right")

    @staticmethod
    def _random_type():
        types = [VehicleType.CAR, VehicleType.BIKE, VehicleType.BUS, VehicleType.TRUCK, VehicleType.AMBULANCE]
        weights = [0.65, 0.15, 0.10, 0.08, 0.02]
        return random.choices(types, weights=weights)[0]

    def update_wait(self, dt: float):
        if self.is_stopped:
            self.wait_time += dt


# =====================================================================
# 2. AI TRAFFIC CONTROLLER
# =====================================================================

class ControllerMode:
    AI_ADAPTIVE = "AI Adaptive"
    FIXED_CYCLE = "Fixed Timer"


class SignalPhase:
    NORTH = "North (Protected Turn)"
    EAST = "East (Protected Turn)"
    SOUTH = "South (Protected Turn)"
    WEST = "West (Protected Turn)"

    ORDER = [NORTH, EAST, SOUTH, WEST]

    @staticmethod
    def get_direction(phase: str) -> Direction:
        mapping = {
            SignalPhase.NORTH: Direction.NORTH,
            SignalPhase.EAST: Direction.EAST,
            SignalPhase.SOUTH: Direction.SOUTH,
            SignalPhase.WEST: Direction.WEST,
        }
        return mapping.get(phase, Direction.NORTH)

    @staticmethod
    def from_direction(d: Direction) -> str:
        mapping = {
            Direction.NORTH: SignalPhase.NORTH,
            Direction.EAST: SignalPhase.EAST,
            Direction.SOUTH: SignalPhase.SOUTH,
            Direction.WEST: SignalPhase.WEST,
        }
        return mapping[d]

    @staticmethod
    def get_next(phase: str) -> str:
        try:
            idx = SignalPhase.ORDER.index(phase)
            return SignalPhase.ORDER[(idx + 1) % len(SignalPhase.ORDER)]
        except ValueError:
            return SignalPhase.NORTH


class AITrafficController:
    def __init__(self, log_callback=None):
        self.mode = ControllerMode.AI_ADAPTIVE
        self.log_callback = log_callback or (lambda msg: None)

        # Timing limits (seconds)
        self.min_green = 6.0
        self.max_green = 28.0
        self.base_green = 7.0
        self.yellow_duration = 3.0
        self.all_red_duration = 1.0
        self.fixed_green_duration = 14.0
        self.starvation_threshold = 28.0

        # State machine - ONLY ONE DIRECTION IS GREEN AT A TIME
        self.active_phase = SignalPhase.NORTH
        self.phase_time_remaining = self.base_green
        self.phase_duration = self.base_green
        self.elapsed_in_phase = 0.0

        # Exactly 1 green signal, all other 3 are red!
        self.lights: Dict[Direction, LightState] = {
            Direction.NORTH: LightState.GREEN,
            Direction.SOUTH: LightState.RED,
            Direction.EAST: LightState.RED,
            Direction.WEST: LightState.RED,
        }

        self.in_transition = False
        self.transition_step = ""
        self.next_phase = SignalPhase.EAST

        self.stats = {
            "vehicles_cleared": 0,
            "total_wait_time": 0.0,
            "emergency_preemptions": 0,
            "switches_count": 0
        }

    def log(self, message: str):
        if self.log_callback:
            self.log_callback(f"[Traffic Controller] {message}")

    def set_mode(self, mode: str):
        self.mode = mode
        self.log(f"Switched controller mode to: {self.mode}")

    def get_phase_directions(self, phase: str) -> List[Direction]:
        return [SignalPhase.get_direction(phase)]

    def calculate_phase_metrics(self, queues: Dict[Direction, List[Vehicle]], phase: str):
        dirs = self.get_phase_directions(phase)
        total_count = sum(len(queues[d]) for d in dirs)
        weighted_density = 0.0
        max_wait = 0.0
        has_emergency = False

        for d in dirs:
            for v in queues[d]:
                weighted_density += v.vehicle_type.priority_weight
                if v.wait_time > max_wait:
                    max_wait = v.wait_time
                if v.is_emergency and v.pos < 300:
                    has_emergency = True

        return {
            "count": total_count,
            "weighted_density": weighted_density,
            "max_wait": max_wait,
            "has_emergency": has_emergency
        }

    def compute_ai_green_time(self, metrics: dict) -> float:
        calculated = self.base_green + (metrics["weighted_density"] * 1.8)
        return max(self.min_green, min(self.max_green, round(calculated, 1)))

    def evaluate_priority_decision(self, queues: Dict[Direction, List[Vehicle]]):
        candidates = [p for p in SignalPhase.ORDER if p != self.active_phase]

        # 1. Emergency Preemption
        for p in candidates:
            m = self.calculate_phase_metrics(queues, p)
            if m["has_emergency"]:
                return p, f"Ambulance Detected on {p} (Emergency Override)"

        # 2. Starvation Safeguard
        for p in candidates:
            m = self.calculate_phase_metrics(queues, p)
            if m["max_wait"] >= self.starvation_threshold and m["count"] > 0:
                return p, f"Starvation safeguard ({p} wait: {m['max_wait']:.1f}s)"

        # 3. Dynamic Backlog Scoring
        best_phase = candidates[0]
        best_score = -1.0
        for p in candidates:
            m = self.calculate_phase_metrics(queues, p)
            score = (m["count"] * 2.0) + (m["weighted_density"] * 2.5) + (m["max_wait"] * 0.6)
            if score > best_score:
                best_score = score
                best_phase = p

        if best_score <= 0.1:
            return SignalPhase.get_next(self.active_phase), "Round-robin sequence (all queues idle)"

        return best_phase, f"Highest Priority Demand ({best_score:.1f} pts)"

    def update(self, dt: float, queues: Dict[Direction, List[Vehicle]]):
        self.phase_time_remaining -= dt
        self.elapsed_in_phase += dt

        # Emergency Preemption during active GREEN
        if not self.in_transition and self.mode == ControllerMode.AI_ADAPTIVE:
            for p in SignalPhase.ORDER:
                if p != self.active_phase:
                    m = self.calculate_phase_metrics(queues, p)
                    if m["has_emergency"]:
                        curr_m = self.calculate_phase_metrics(queues, self.active_phase)
                        if not curr_m["has_emergency"]:
                            self.log(f"🚨 EMERGENCY PREEMPTION: Ambulance in {p}! Switching immediately.")
                            self.stats["emergency_preemptions"] += 1
                            self._begin_transition_to(p)
                            return

            # Early Cutoff
            curr_m = self.calculate_phase_metrics(queues, self.active_phase)
            if self.elapsed_in_phase >= self.min_green and curr_m["count"] == 0:
                has_waiting = any(len(queues[d]) > 0 for d in Direction if d != SignalPhase.get_direction(self.active_phase))
                if has_waiting:
                    self.log(f"⚡ Early Cutoff: Active {self.active_phase} lane empty. Switching early.")
                    target_phase, reason = self.evaluate_priority_decision(queues)
                    self._begin_transition_to(target_phase)
                    return

        if self.phase_time_remaining <= 0:
            self._handle_timer_expiry(queues)

    def _handle_timer_expiry(self, queues: Dict[Direction, List[Vehicle]]):
        if not self.in_transition:
            if self.mode == ControllerMode.AI_ADAPTIVE:
                target_phase, reason = self.evaluate_priority_decision(queues)
                self.log(f"Phase decision: {target_phase} [{reason}]")
            else:
                target_phase = SignalPhase.get_next(self.active_phase)
                self.log(f"Fixed timer cycle: advancing to {target_phase}")

            self._begin_transition_to(target_phase)
        else:
            if self.transition_step == "YELLOW":
                self.transition_step = "ALL_RED"
                self.phase_time_remaining = self.all_red_duration
                self.phase_duration = self.all_red_duration
                for d in Direction:
                    self.lights[d] = LightState.RED
            elif self.transition_step == "ALL_RED":
                self.active_phase = self.next_phase
                self.in_transition = False
                self.transition_step = ""
                self.elapsed_in_phase = 0.0
                self.stats["switches_count"] += 1

                active_dir = SignalPhase.get_direction(self.active_phase)
                if self.mode == ControllerMode.AI_ADAPTIVE:
                    m = self.calculate_phase_metrics(queues, self.active_phase)
                    new_green = self.compute_ai_green_time(m)
                    self.log(f"🚦 GREEN exclusively to {self.active_phase}. Duration: {new_green:.1f}s")
                else:
                    new_green = self.fixed_green_duration
                    self.log(f"🚦 GREEN exclusively to {self.active_phase}. Fixed Duration: {new_green:.1f}s")

                self.phase_duration = new_green
                self.phase_time_remaining = new_green

                for d in Direction:
                    self.lights[d] = LightState.GREEN if d == active_dir else LightState.RED

    def _begin_transition_to(self, next_phase: str):
        self.in_transition = True
        self.next_phase = next_phase
        self.transition_step = "YELLOW"
        self.phase_duration = self.yellow_duration
        self.phase_time_remaining = self.yellow_duration

        active_dir = SignalPhase.get_direction(self.active_phase)
        for d in Direction:
            if d == active_dir:
                self.lights[d] = LightState.YELLOW
            else:
                self.lights[d] = LightState.RED

    def record_cleared_vehicle(self, v: Vehicle):
        self.stats["vehicles_cleared"] += 1
        self.stats["total_wait_time"] += v.wait_time

    def get_avg_wait_time(self) -> float:
        if self.stats["vehicles_cleared"] == 0:
            return 0.0
        return self.stats["total_wait_time"] / self.stats["vehicles_cleared"]


# =====================================================================
# 3. INTERSECTION SIMULATION ENGINE
# =====================================================================

class TrafficSimulation:
    STOP_LINE_POS = 300.0
    INTERSECTION_EXIT_POS = 430.0
    TOTAL_LANE_LENGTH = 650.0

    def __init__(self, controller: AITrafficController):
        self.controller = controller
        self.vehicles: Dict[Direction, List[Vehicle]] = {d: [] for d in Direction}
        self.sim_time = 0.0
        self.spawn_rate = 1.2
        self.sim_speed = 1.0
        self.is_paused = False
        self.last_spawn_time = 0.0
        self.auto_spawn = True

    def spawn_vehicle(self, direction: Direction, vehicle_type: Optional[VehicleType] = None):
        lane = self.vehicles[direction]
        if lane:
            closest = min(lane, key=lambda v: v.pos)
            if closest.pos < 45.0:
                return None

        v = Vehicle(direction=direction, vehicle_type=vehicle_type)
        v.pos = 0.0
        v.speed = v.max_speed * 0.7
        lane.append(v)
        if v.is_emergency:
            self.controller.log(f"🚨 Ambulance dispatched on {direction.value}!")
        return v

    def spawn_emergency(self, direction: Direction):
        return self.spawn_vehicle(direction, VehicleType.AMBULANCE)

    def trigger_rush_hour(self):
        for d in Direction:
            for _ in range(3):
                self.spawn_vehicle(d)

    def update(self, dt: float):
        if self.is_paused:
            return

        effective_dt = dt * self.sim_speed
        self.sim_time += effective_dt

        # Spawning
        if self.auto_spawn:
            if (self.sim_time - self.last_spawn_time) >= (1.0 / max(0.2, self.spawn_rate)):
                self.last_spawn_time = self.sim_time
                self.spawn_vehicle(random.choice(list(Direction)))

        # Update controller
        waiting_queues = {
            d: [v for v in self.vehicles[d] if v.pos <= self.STOP_LINE_POS + 10]
            for d in Direction
        }
        self.controller.update(effective_dt, waiting_queues)

        # Vehicle kinematics
        for direction, lane in self.vehicles.items():
            light = self.controller.lights[direction]
            lane.sort(key=lambda v: v.pos, reverse=True)

            for i, v in enumerate(lane):
                if i == 0:
                    if light in (LightState.RED, LightState.YELLOW) and v.pos < self.STOP_LINE_POS:
                        target = self.STOP_LINE_POS
                    else:
                        target = self.TOTAL_LANE_LENGTH
                else:
                    prev_v = lane[i - 1]
                    target = prev_v.pos - prev_v.vehicle_type.length - 12.0

                dist = target - v.pos

                if dist > 80.0:
                    v.speed = min(v.max_speed, v.speed + 1.2 * effective_dt)
                    v.is_stopped = False
                elif dist > 10.0:
                    desired = v.max_speed * (dist / 80.0)
                    v.speed = desired
                    v.is_stopped = (v.speed < 0.2)
                else:
                    v.speed = 0.0
                    v.is_stopped = True

                v.pos += v.speed * (effective_dt * 30.0)
                v.update_wait(effective_dt)

            # Intersection clearance
            cleared = [v for v in lane if v.pos >= self.INTERSECTION_EXIT_POS and not v.cleared]
            for cv in cleared:
                cv.cleared = True
                self.controller.record_cleared_vehicle(cv)

            self.vehicles[direction] = [v for v in lane if v.pos < self.TOTAL_LANE_LENGTH]


# =====================================================================
# 4. COMPUTER VISION VEHICLE DETECTOR (OPENCV)
# =====================================================================

class CVTrafficDetector:
    def __init__(self):
        self.running = False
        self.thread = None

    def start_window(self):
        if not CV_AVAILABLE:
            print("[CV Detector] OpenCV (cv2) or NumPy is not installed.")
            return
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop_window(self):
        self.running = False

    def _loop(self):
        w, h = 640, 480
        subtractor = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=50, detectShadows=True)
        rois = {
            "North": (240, 20, 400, 180),
            "South": (240, 300, 400, 460),
            "West":  (20, 180, 200, 300),
            "East":  (440, 180, 620, 300),
        }
        svs = [
            {"x": 280, "y": 40, "dy": 2.5, "w": 24, "h": 40},
            {"x": 580, "y": 210, "dx": -2.8, "w": 40, "h": 22},
            {"x": 40, "y": 250, "dx": 3.0, "w": 36, "h": 22},
        ]

        while self.running:
            frame = np.full((h, w, 3), 35, dtype=np.uint8)
            cv2.rectangle(frame, (220, 0), (420, h), (60, 60, 60), -1)
            cv2.rectangle(frame, (0, 160), (w, 320), (60, 60, 60), -1)
            cv2.line(frame, (320, 0), (320, h), (0, 220, 255), 2)
            cv2.line(frame, (0, 240), (w, 240), (0, 220, 255), 2)

            for s in svs:
                s["x"] += s.get("dx", 0)
                s["y"] += s.get("dy", 0)
                if s["y"] > 160: s["y"] = 20
                if s["x"] < 420 and "dx" in s and s["dx"] < 0: s["x"] = 600
                if s["x"] > 220 and "dx" in s and s["dx"] > 0: s["x"] = 30
                cv2.rectangle(frame, (int(s["x"]), int(s["y"])), (int(s["x"]+s["w"]), int(s["y"]+s["h"])), (220, 150, 40), -1)

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            mask = subtractor.apply(gray)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            counts = {k: 0 for k in rois}
            for cnt in contours:
                if cv2.contourArea(cnt) < 150:
                    continue
                x, y, bw, bh = cv2.boundingRect(cnt)
                cx, cy = x + bw // 2, y + bh // 2
                for lane, (rx1, ry1, rx2, ry2) in rois.items():
                    if rx1 <= cx <= rx2 and ry1 <= cy <= ry2:
                        counts[lane] += 1
                        cv2.rectangle(frame, (x, y), (x + bw, y + bh), (0, 255, 0), 2)

            for lane, (rx1, ry1, rx2, ry2) in rois.items():
                cv2.rectangle(frame, (rx1, ry1), (rx2, ry2), (255, 200, 0), 1)
                cv2.putText(frame, f"{lane}: {counts[lane]} veh", (rx1 + 5, ry1 + 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

            cv2.putText(frame, f"AI SURVEILLANCE FEED [ONLINE] {time.strftime('%H:%M:%S')}", (15, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 120), 1)

            cv2.imshow("AI Traffic System - Computer Vision Camera", frame)
            if (cv2.waitKey(30) & 0xFF) in (ord('q'), 27):
                break

        cv2.destroyAllWindows()
        self.running = False


# =====================================================================
# 5. USER INTERFACE (TKINTER)
# =====================================================================

class TrafficSystemGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("AI Smart Traffic Signal System & Adaptive Controller")
        self.root.geometry("1240x800")
        self.root.configure(bg="#0b0f19")

        self.controller = AITrafficController(log_callback=self._log_event)
        self.simulation = TrafficSimulation(self.controller)
        self.cv = CVTrafficDetector()

        self.last_time = time.time()
        self.flash_tick = 0

        self._build_ui()
        self._loop()

    def _build_ui(self):
        container = tk.Frame(self.root, bg="#0b0f19")
        container.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        # Simulation Canvas Left
        left = tk.Frame(container, bg="#0f172a", bd=1, relief=tk.SOLID)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 10))

        header = tk.Frame(left, bg="#1e293b", height=38)
        header.pack(fill=tk.X)
        tk.Label(header, text="🚦 4-WAY ADAPTIVE INTERSECTION SIMULATION", bg="#1e293b", fg="#38bdf8", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT, padx=12, pady=8)

        self.canvas_size = 700
        self.canvas = tk.Canvas(left, width=self.canvas_size, height=self.canvas_size, bg="#0f172a", highlightthickness=0)
        self.canvas.pack(padx=5, pady=5)

        # Right Dashboard
        right = tk.Frame(container, bg="#0b0f19", width=490)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # 1. Status Card
        card1 = tk.LabelFrame(right, text=" ⚡ STATUS & CONTROL ", bg="#131d31", fg="#38bdf8", font=("Segoe UI", 10, "bold"), bd=1)
        card1.pack(fill=tk.X, pady=(0, 8))

        r1 = tk.Frame(card1, bg="#131d31")
        r1.pack(fill=tk.X, padx=10, pady=5)
        tk.Label(r1, text="Active Phase:", bg="#131d31", fg="#94a3b8").pack(side=tk.LEFT)
        self.lbl_phase = tk.Label(r1, text="North - South", bg="#131d31", fg="#10b981", font=("Segoe UI", 11, "bold"))
        self.lbl_phase.pack(side=tk.LEFT, padx=6)

        self.lbl_mode_badge = tk.Label(r1, text="AI ADAPTIVE", bg="#0284c7", fg="white", font=("Segoe UI", 8, "bold"), padx=8, pady=2)
        self.lbl_mode_badge.pack(side=tk.RIGHT)

        r2 = tk.Frame(card1, bg="#131d31")
        r2.pack(fill=tk.X, padx=10, pady=3)
        tk.Label(r2, text="Time Remaining:", bg="#131d31", fg="#94a3b8").pack(side=tk.LEFT)
        self.lbl_timer = tk.Label(r2, text="12.0s", bg="#131d31", fg="#fbbf24", font=("Segoe UI", 12, "bold"))
        self.lbl_timer.pack(side=tk.LEFT, padx=6)

        btns = tk.Frame(card1, bg="#131d31")
        btns.pack(fill=tk.X, padx=10, pady=6)
        self.btn_ai = tk.Button(btns, text="🤖 AI Adaptive Mode", bg="#0284c7", fg="white", font=("Segoe UI", 9, "bold"),
                                command=lambda: self._set_mode(ControllerMode.AI_ADAPTIVE))
        self.btn_ai.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        self.btn_fix = tk.Button(btns, text="⏱️ Fixed Timer (20s)", bg="#334155", fg="white", font=("Segoe UI", 9),
                                 command=lambda: self._set_mode(ControllerMode.FIXED_CYCLE))
        self.btn_fix.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        # 2. Metrics Card
        card2 = tk.LabelFrame(right, text=" 📊 METRICS & COMPARISON ", bg="#131d31", fg="#38bdf8", font=("Segoe UI", 10, "bold"), bd=1)
        card2.pack(fill=tk.X, pady=(0, 8))

        m_grid = tk.Frame(card2, bg="#131d31")
        m_grid.pack(fill=tk.X, padx=8, pady=6)
        self.metric_labels = {}
        for idx, (title, col) in enumerate([("Vehicles Cleared", "#38bdf8"), ("Avg Waiting Time", "#fbbf24"),
                                            ("Emergency Preemptions", "#ef4444"), ("AI Delay Saved", "#10b981")]):
            box = tk.Frame(m_grid, bg="#1e293b", padx=8, pady=5)
            box.grid(row=idx//2, column=idx%2, padx=4, pady=4, sticky="nsew")
            m_grid.columnconfigure(idx%2, weight=1)
            tk.Label(box, text=title, bg="#1e293b", fg="#94a3b8", font=("Segoe UI", 8)).pack(anchor="w")
            lbl = tk.Label(box, text="0", bg="#1e293b", fg=col, font=("Segoe UI", 12, "bold"))
            lbl.pack(anchor="w")
            self.metric_labels[title] = lbl

        # 3. Lane Density
        card3 = tk.LabelFrame(right, text=" 🚘 LANE QUEUE MONITOR ", bg="#131d31", fg="#38bdf8", font=("Segoe UI", 10, "bold"), bd=1)
        card3.pack(fill=tk.X, pady=(0, 8))
        l_row = tk.Frame(card3, bg="#131d31")
        l_row.pack(fill=tk.X, padx=8, pady=6)
        self.lane_lbls = {}
        for i, d in enumerate(Direction):
            bx = tk.Frame(l_row, bg="#1e293b", padx=6, pady=4)
            bx.grid(row=0, column=i, padx=3, sticky="nsew")
            l_row.columnconfigure(i, weight=1)
            tk.Label(bx, text=d.value, bg="#1e293b", fg="#e2e8f0", font=("Segoe UI", 8, "bold")).pack()
            l_v = tk.Label(bx, text="0 veh", bg="#1e293b", fg="#38bdf8", font=("Segoe UI", 10, "bold"))
            l_v.pack()
            self.lane_lbls[d] = l_v

        # 4. Spawner Controls
        card4 = tk.LabelFrame(right, text=" 🎮 INTERACTIVE TESTING & DISPATCH ", bg="#131d31", fg="#38bdf8", font=("Segoe UI", 10, "bold"), bd=1)
        card4.pack(fill=tk.X, pady=(0, 8))

        sr1 = tk.Frame(card4, bg="#131d31")
        sr1.pack(fill=tk.X, padx=8, pady=3)
        tk.Label(sr1, text="Spawn Car:", bg="#131d31", fg="#94a3b8", font=("Segoe UI", 8)).pack(side=tk.LEFT)
        for d in Direction:
            tk.Button(sr1, text=d.value[0], width=3, bg="#334155", fg="white", font=("Segoe UI", 8, "bold"),
                      command=lambda dir=d: self.simulation.spawn_vehicle(dir)).pack(side=tk.LEFT, padx=2)
        tk.Button(sr1, text="+ All", bg="#0369a1", fg="white", font=("Segoe UI", 8, "bold"),
                  command=lambda: [self.simulation.spawn_vehicle(d) for d in Direction]).pack(side=tk.LEFT, padx=4)
        tk.Button(sr1, text="⚡ Rush Hour", bg="#d97706", fg="white", font=("Segoe UI", 8, "bold"),
                  command=self.simulation.trigger_rush_hour).pack(side=tk.RIGHT, padx=2)

        sr2 = tk.Frame(card4, bg="#131d31")
        sr2.pack(fill=tk.X, padx=8, pady=3)
        tk.Label(sr2, text="🚑 Dispatch Ambulance:", bg="#131d31", fg="#f87171", font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT)
        for d in Direction:
            tk.Button(sr2, text=d.value[0], width=3, bg="#991b1b", fg="white", font=("Segoe UI", 8, "bold"),
                      command=lambda dir=d: self.simulation.spawn_emergency(dir)).pack(side=tk.LEFT, padx=2)

        sim_c = tk.Frame(card4, bg="#131d31")
        sim_c.pack(fill=tk.X, padx=8, pady=5)
        self.btn_pause = tk.Button(sim_c, text="⏸️ Pause", bg="#475569", fg="white", font=("Segoe UI", 8, "bold"), command=self._toggle_pause)
        self.btn_pause.pack(side=tk.LEFT, padx=2)
        self.btn_cv = tk.Button(sim_c, text="📷 CV Camera Window", bg="#059669", fg="white", font=("Segoe UI", 8, "bold"), command=self._toggle_cv)
        self.btn_cv.pack(side=tk.RIGHT, padx=2)

        # 5. Logs
        card5 = tk.LabelFrame(right, text=" 📜 AI DECISION ENGINE LOGS ", bg="#131d31", fg="#38bdf8", font=("Segoe UI", 10, "bold"), bd=1)
        card5.pack(fill=tk.BOTH, expand=True)
        self.log_text = tk.Text(card5, bg="#0a0f1d", fg="#a5f3fc", font=("Consolas", 8), height=7, bd=0)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

    def _set_mode(self, mode: str):
        self.controller.set_mode(mode)
        if mode == ControllerMode.AI_ADAPTIVE:
            self.lbl_mode_badge.config(text="AI ADAPTIVE", bg="#0284c7")
            self.btn_ai.config(bg="#0284c7")
            self.btn_fix.config(bg="#334155")
        else:
            self.lbl_mode_badge.config(text="FIXED TIMER", bg="#64748b")
            self.btn_ai.config(bg="#334155")
            self.btn_fix.config(bg="#0284c7")

    def _toggle_pause(self):
        self.simulation.is_paused = not self.simulation.is_paused
        self.btn_pause.config(text="▶️ Resume" if self.simulation.is_paused else "⏸️ Pause")

    def _toggle_cv(self):
        if not self.cv.running:
            self.cv.start_window()
            self.btn_cv.config(text="❌ Close CV Window", bg="#dc2626")
        else:
            self.cv.stop_window()
            self.btn_cv.config(text="📷 CV Camera Window", bg="#059669")

    def _log_event(self, msg: str):
        if hasattr(self, "log_text"):
            self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {msg}\n")
            self.log_text.see(tk.END)

    def _loop(self):
        now = time.time()
        dt = min(0.1, now - self.last_time)
        self.last_time = now
        self.flash_tick += 1

        self.simulation.update(dt)
        self._render()
        self.root.after(20, self._loop)

    def _render(self):
        # Update text labels
        self.lbl_phase.config(text=self.controller.active_phase)
        self.lbl_timer.config(text=f"{max(0.0, self.controller.phase_time_remaining):.1f}s")
        cleared = self.controller.stats["vehicles_cleared"]
        avg_wait = self.controller.get_avg_wait_time()
        self.metric_labels["Vehicles Cleared"].config(text=str(cleared))
        self.metric_labels["Avg Waiting Time"].config(text=f"{avg_wait:.1f}s")
        self.metric_labels["Emergency Preemptions"].config(text=str(self.controller.stats["emergency_preemptions"]))

        if avg_wait > 0 and self.controller.mode == ControllerMode.AI_ADAPTIVE:
            saved = max(0.0, ((20.0 - avg_wait) / 20.0) * 100)
            self.metric_labels["AI Delay Saved"].config(text=f"+{saved:.1f}%")
        else:
            self.metric_labels["AI Delay Saved"].config(text="--")

        for d in Direction:
            cnt = len([v for v in self.simulation.vehicles[d] if v.pos <= self.simulation.STOP_LINE_POS + 10])
            self.lane_lbls[d].config(text=f"{cnt} veh")

        # Draw intersection
        self.canvas.delete("all")
        c = self.canvas_size // 2
        rw = 140
        hw = rw // 2

        self.canvas.create_rectangle(0, 0, self.canvas_size, self.canvas_size, fill="#0f172a", outline="")
        self.canvas.create_rectangle(c - hw, 0, c + hw, self.canvas_size, fill="#1e293b", outline="")
        self.canvas.create_rectangle(0, c - hw, self.canvas_size, c + hw, fill="#1e293b", outline="")
        self.canvas.create_rectangle(c - hw, c - hw, c + hw, c + hw, fill="#243048", outline="")

        # Yellow centerlines
        self.canvas.create_line(c, 0, c, c - hw - 30, fill="#f59e0b", width=2)
        self.canvas.create_line(c, c + hw + 30, c, self.canvas_size, fill="#f59e0b", width=2)
        self.canvas.create_line(0, c, c - hw - 30, c, fill="#f59e0b", width=2)
        self.canvas.create_line(c + hw + 30, c, self.canvas_size, c, fill="#f59e0b", width=2)

        # Stop lines & Crosswalks
        self.canvas.create_line(c - hw, c - hw - 15, c, c - hw - 15, fill="#ffffff", width=4)
        self.canvas.create_line(c, c + hw + 15, c + hw, c + hw + 15, fill="#ffffff", width=4)
        self.canvas.create_line(c - hw - 15, c, c - hw - 15, c + hw, fill="#ffffff", width=4)
        self.canvas.create_line(c + hw + 15, c - hw, c + hw + 15, c, fill="#ffffff", width=4)

        # Vehicles with smooth left/right turning
        scale = 265.0 / self.simulation.STOP_LINE_POS
        for d, lane in self.simulation.vehicles.items():
            for v in lane:
                pos = v.pos * scale
                turn = getattr(v, "turn_intent", "straight")
                rx = -hw // 2
                ry = pos - c
                r_head = 90

                if turn == "straight":
                    rx, ry, r_head = -hw // 2, pos - c, 90
                elif turn == "right":
                    if pos <= 265:
                        rx, ry, r_head = -35, pos - c, 90
                    elif pos < 335:
                        t = (pos - 265) / 70.0
                        rx = -70 + 35 * math.cos(t * math.pi / 2)
                        ry = -70 + 35 * math.sin(t * math.pi / 2)
                        r_head = 90 + int(t * 90)
                    else:
                        rx, ry, r_head = -70 - (pos - 335), -35, 180
                elif turn == "left":
                    if pos <= 265:
                        rx, ry, r_head = -35, pos - c, 90
                    elif pos < 405:
                        t = (pos - 265) / 140.0
                        rx = 70 - 105 * math.cos(t * math.pi / 2)
                        ry = -70 + 105 * math.sin(t * math.pi / 2)
                        r_head = 90 - int(t * 90)
                    else:
                        rx, ry, r_head = 70 + (pos - 405), 35, 0

                if d == Direction.NORTH:
                    vx, vy, heading = c + rx, c + ry, r_head
                elif d == Direction.EAST:
                    vx, vy, heading = c - ry, c + rx, (r_head + 90) % 360
                elif d == Direction.SOUTH:
                    vx, vy, heading = c - rx, c - ry, (r_head + 180) % 360
                else: # WEST
                    vx, vy, heading = c + ry, c - rx, (r_head + 270) % 360

                L, W = v.vehicle_type.length, v.vehicle_type.width
                if heading in (90, 270):
                    x1, y1, x2, y2 = vx - W//2, vy - L//2, vx + W//2, vy + L//2
                else:
                    x1, y1, x2, y2 = vx - L//2, vy - W//2, vx + L//2, vy + W//2

                self.canvas.create_rectangle(x1, y1, x2, y2, fill=v.vehicle_type.color, outline="#ffffff", width=1)
                
                # Turn symbol on roof
                tsym = "↰" if turn == "left" else ("↱" if turn == "right" else "↑")
                self.canvas.create_text(vx, vy, text=tsym, fill="#ffffff", font=("Segoe UI", 7, "bold"))

                if v.is_emergency:
                    col = "#ef4444" if (self.flash_tick // 4) % 2 == 0 else "#38bdf8"
                    self.canvas.create_oval(vx - 4, vy - 4, vx + 4, vy + 4, fill=col, outline="#ffffff")

        # Traffic Lights
        light_pos = {
            Direction.NORTH: (c - hw - 38, c - hw - 75),
            Direction.SOUTH: (c + hw + 14, c + hw + 25),
            Direction.WEST:  (c - hw - 75, c + hw + 14),
            Direction.EAST:  (c + hw + 25, c - hw - 38),
        }
        for d, (bx, by) in light_pos.items():
            st = self.controller.lights[d]
            self.canvas.create_rectangle(bx, by, bx + 24, by + 52, fill="#111827", outline="#475569", width=2)
            self.canvas.create_oval(bx + 4, by + 4, bx + 20, by + 18, fill="#ef4444" if st == LightState.RED else "#371414")
            self.canvas.create_oval(bx + 4, by + 19, bx + 20, by + 33, fill="#eab308" if st == LightState.YELLOW else "#3a2e0b")
            self.canvas.create_oval(bx + 4, by + 34, bx + 20, by + 48, fill="#22c55e" if st == LightState.GREEN else "#0b2e16")


# =====================================================================
# 6. ENTRY POINT
# =====================================================================

if __name__ == "__main__":
    root = tk.Tk()
    app = TrafficSystemGUI(root)
    root.mainloop()
