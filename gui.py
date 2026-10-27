"""
gui.py - Interactive Tkinter GUI for AI Traffic Signal System.
Features:
- High-fidelity 2D Intersection Simulation Canvas with Smooth Animation
- Real-time Traffic Lights with Glow and Timers
- Vehicle Rendering with Headlights and Flashing Ambulance Sirens
- AI Adaptive vs Fixed Timer Mode Comparison Dashboard
- Live Queue & Wait Time Visualizations
- Interactive Vehicle & Emergency Spawning
- Live Decision Log Terminal
- Computer Vision Window launcher
"""
import tkinter as tk
from tkinter import ttk, messagebox
import time
import math
from models import Direction, LightState, VehicleType, Vehicle
from ai_controller import AITrafficController, ControllerMode, SignalPhase
from simulation import TrafficSimulation
from cv_detector import CVTrafficDetector

class TrafficSystemGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("AI Smart Traffic Signal System & Adaptive Controller")
        self.root.geometry("1240x800")
        self.root.configure(bg="#0b0f19")
        self.root.minsize(1100, 750)

        # Initialize Core Controller & Simulation
        self.controller = AITrafficController(log_callback=self._log_event)
        self.simulation = TrafficSimulation(self.controller)
        self.cv_detector = CVTrafficDetector(use_camera=False)

        # Animation state
        self.last_frame_time = time.time()
        self.flashing_tick = 0

        self._setup_styles()
        self._build_ui()
        self._start_animation_loop()

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#0b0f19")
        style.configure("Card.TFrame", background="#1e293b", relief="flat")
        style.configure("TLabel", background="#1e293b", foreground="#f8fafc", font=("Segoe UI", 9))
        style.configure("Header.TLabel", background="#1e293b", foreground="#38bdf8", font=("Segoe UI", 11, "bold"))
        style.configure("TButton", font=("Segoe UI", 9, "bold"), padding=5)
        style.configure("Primary.TButton", background="#0284c7", foreground="#ffffff")

    def _build_ui(self):
        # Main Layout: Left Canvas (Intersection), Right Panel (Dashboard & Controls)
        main_container = tk.Frame(self.root, bg="#0b0f19")
        main_container.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        # Left: Simulation Canvas Container
        left_frame = tk.Frame(main_container, bg="#0f172a", bd=1, relief=tk.SOLID)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 10))

        # Title bar above canvas
        canvas_header = tk.Frame(left_frame, bg="#1e293b", height=38)
        canvas_header.pack(fill=tk.X)
        tk.Label(
            canvas_header,
            text="🚦 REAL-TIME INTERSECTION SIMULATION (4-WAY DUAL ARTERIAL)",
            bg="#1e293b",
            fg="#38bdf8",
            font=("Segoe UI", 10, "bold")
        ).pack(side=tk.LEFT, padx=12, pady=8)

        # Canvas (700 x 700)
        self.canvas_size = 700
        self.canvas = tk.Canvas(
            left_frame,
            width=self.canvas_size,
            height=self.canvas_size,
            bg="#0f172a",
            highlightthickness=0
        )
        self.canvas.pack(padx=5, pady=5)

        # Right: Dashboard & Command Controls (Scrollable)
        right_container = tk.Frame(main_container, bg="#0b0f19", width=490)
        right_container.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self._build_dashboard(right_container)

    def _build_dashboard(self, parent):
        # 1. System Status Card
        status_card = tk.LabelFrame(
            parent, text=" ⚡ SYSTEM CONTROL & STATUS ",
            bg="#131d31", fg="#38bdf8", font=("Segoe UI", 10, "bold"), bd=1
        )
        status_card.pack(fill=tk.X, pady=(0, 8))

        row1 = tk.Frame(status_card, bg="#131d31")
        row1.pack(fill=tk.X, padx=10, pady=5)

        tk.Label(row1, text="Active Phase:", bg="#131d31", fg="#94a3b8", font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self.lbl_phase = tk.Label(row1, text="North - South", bg="#131d31", fg="#10b981", font=("Segoe UI", 11, "bold"))
        self.lbl_phase.pack(side=tk.LEFT, padx=6)

        self.lbl_mode_badge = tk.Label(
            row1, text="AI ADAPTIVE", bg="#0284c7", fg="#ffffff",
            font=("Segoe UI", 8, "bold"), padx=8, pady=2
        )
        self.lbl_mode_badge.pack(side=tk.RIGHT)

        row2 = tk.Frame(status_card, bg="#131d31")
        row2.pack(fill=tk.X, padx=10, pady=3)

        tk.Label(row2, text="Phase Time Remaining:", bg="#131d31", fg="#94a3b8").pack(side=tk.LEFT)
        self.lbl_timer = tk.Label(row2, text="15.0s", bg="#131d31", fg="#fbbf24", font=("Segoe UI", 12, "bold"))
        self.lbl_timer.pack(side=tk.LEFT, padx=6)

        # Mode Toggle Buttons
        btn_mode_frame = tk.Frame(status_card, bg="#131d31")
        btn_mode_frame.pack(fill=tk.X, padx=10, pady=6)

        self.btn_ai_mode = tk.Button(
            btn_mode_frame, text="🤖 AI Adaptive Mode",
            bg="#0284c7", fg="white", font=("Segoe UI", 9, "bold"),
            command=lambda: self._set_controller_mode(ControllerMode.AI_ADAPTIVE)
        )
        self.btn_ai_mode.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        self.btn_fixed_mode = tk.Button(
            btn_mode_frame, text="⏱️ Fixed Timer (20s)",
            bg="#334155", fg="white", font=("Segoe UI", 9),
            command=lambda: self._set_controller_mode(ControllerMode.FIXED_CYCLE)
        )
        self.btn_fixed_mode.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        # 2. Performance Metrics Card
        metrics_card = tk.LabelFrame(
            parent, text=" 📊 REAL-TIME METRICS & COMPARISON ",
            bg="#131d31", fg="#38bdf8", font=("Segoe UI", 10, "bold"), bd=1
        )
        metrics_card.pack(fill=tk.X, pady=(0, 8))

        m_grid = tk.Frame(metrics_card, bg="#131d31")
        m_grid.pack(fill=tk.X, padx=8, pady=6)

        # Metric Tiles
        self.metric_widgets = {}
        metrics_def = [
            ("Vehicles Cleared", "0", "#38bdf8", 0, 0),
            ("Avg Waiting Time", "0.0s", "#fbbf24", 0, 1),
            ("Emergency Preemptions", "0", "#ef4444", 1, 0),
            ("AI Delay Saved", "+0.0%", "#10b981", 1, 1),
        ]
        for label, default_val, col, r, c in metrics_def:
            box = tk.Frame(m_grid, bg="#1e293b", padx=8, pady=5)
            box.grid(row=r, column=c, padx=4, pady=4, sticky="nsew")
            m_grid.columnconfigure(c, weight=1)
            tk.Label(box, text=label, bg="#1e293b", fg="#94a3b8", font=("Segoe UI", 8)).pack(anchor="w")
            lbl_val = tk.Label(box, text=default_val, bg="#1e293b", fg=col, font=("Segoe UI", 12, "bold"))
            lbl_val.pack(anchor="w")
            self.metric_widgets[label] = lbl_val

        # 3. Live Lane Queue & Density
        lane_card = tk.LabelFrame(
            parent, text=" 🚘 LANE QUEUE & DENSITY MONITOR ",
            bg="#131d31", fg="#38bdf8", font=("Segoe UI", 10, "bold"), bd=1
        )
        lane_card.pack(fill=tk.X, pady=(0, 8))

        self.lane_labels = {}
        lane_frame = tk.Frame(lane_card, bg="#131d31")
        lane_frame.pack(fill=tk.X, padx=8, pady=6)

        for i, d in enumerate(Direction):
            l_box = tk.Frame(lane_frame, bg="#1e293b", padx=6, pady=4)
            l_box.grid(row=0, column=i, padx=3, sticky="nsew")
            lane_frame.columnconfigure(i, weight=1)
            tk.Label(l_box, text=d.value, bg="#1e293b", fg="#e2e8f0", font=("Segoe UI", 8, "bold")).pack()
            l_val = tk.Label(l_box, text="0 veh", bg="#1e293b", fg="#38bdf8", font=("Segoe UI", 10, "bold"))
            l_val.pack()
            self.lane_labels[d] = l_val

        # 4. Interactive Spawner & Emergency Dispatch
        spawn_card = tk.LabelFrame(
            parent, text=" 🎮 INTERACTIVE TESTING & DISPATCH ",
            bg="#131d31", fg="#38bdf8", font=("Segoe UI", 10, "bold"), bd=1
        )
        spawn_card.pack(fill=tk.X, pady=(0, 8))

        s_row1 = tk.Frame(spawn_card, bg="#131d31")
        s_row1.pack(fill=tk.X, padx=8, pady=3)

        tk.Label(s_row1, text="Spawn Car:", bg="#131d31", fg="#94a3b8", font=("Segoe UI", 8)).pack(side=tk.LEFT)
        for d in Direction:
            btn = tk.Button(
                s_row1, text=d.value[:1], width=3, bg="#334155", fg="white",
                font=("Segoe UI", 8, "bold"),
                command=lambda dir=d: self.simulation.spawn_vehicle(dir)
            )
            btn.pack(side=tk.LEFT, padx=2)

        btn_all = tk.Button(
            s_row1, text="+ All", bg="#0369a1", fg="white", font=("Segoe UI", 8, "bold"),
            command=lambda: [self.simulation.spawn_vehicle(d) for d in Direction]
        )
        btn_all.pack(side=tk.LEFT, padx=4)

        btn_rush = tk.Button(
            s_row1, text="⚡ Rush Hour", bg="#d97706", fg="white", font=("Segoe UI", 8, "bold"),
            command=lambda: self.simulation.trigger_rush_hour()
        )
        btn_rush.pack(side=tk.RIGHT, padx=2)

        s_row2 = tk.Frame(spawn_card, bg="#131d31")
        s_row2.pack(fill=tk.X, padx=8, pady=3)

        tk.Label(s_row2, text="🚑 Dispatch Ambulance (Emergency):", bg="#131d31", fg="#f87171", font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT)
        for d in Direction:
            btn_amb = tk.Button(
                s_row2, text=f"{d.value[:1]}", width=3, bg="#991b1b", fg="white",
                font=("Segoe UI", 8, "bold"),
                command=lambda dir=d: self.simulation.spawn_emergency(dir)
            )
            btn_amb.pack(side=tk.LEFT, padx=2)

        # Simulation settings: Speed, Auto-spawn, CV Window
        sim_ctrl = tk.Frame(spawn_card, bg="#131d31")
        sim_ctrl.pack(fill=tk.X, padx=8, pady=5)

        self.btn_pause = tk.Button(
            sim_ctrl, text="⏸️ Pause", bg="#475569", fg="white", font=("Segoe UI", 8, "bold"),
            command=self._toggle_pause
        )
        self.btn_pause.pack(side=tk.LEFT, padx=2)

        self.btn_cv = tk.Button(
            sim_ctrl, text="📷 Open CV Camera Window", bg="#059669", fg="white", font=("Segoe UI", 8, "bold"),
            command=self._toggle_cv_window
        )
        self.btn_cv.pack(side=tk.RIGHT, padx=2)

        # Speed slider
        tk.Label(sim_ctrl, text="Speed:", bg="#131d31", fg="#94a3b8", font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(6, 2))
        self.slider_speed = tk.Scale(
            sim_ctrl, from_=1.0, to=3.0, resolution=0.5, orient=tk.HORIZONTAL,
            bg="#131d31", fg="#38bdf8", highlightthickness=0, length=70,
            command=lambda val: setattr(self.simulation, "sim_speed", float(val))
        )
        self.slider_speed.set(1.0)
        self.slider_speed.pack(side=tk.LEFT)

        # 5. Live AI Decision & Log Box
        log_card = tk.LabelFrame(
            parent, text=" 📜 AI DECISION ENGINE LOGS ",
            bg="#131d31", fg="#38bdf8", font=("Segoe UI", 10, "bold"), bd=1
        )
        log_card.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(
            log_card, bg="#0a0f1d", fg="#a5f3fc", font=("Consolas", 8),
            height=7, bd=0, highlightthickness=0
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

    def _set_controller_mode(self, mode: str):
        self.controller.set_mode(mode)
        if mode == ControllerMode.AI_ADAPTIVE:
            self.lbl_mode_badge.config(text="AI ADAPTIVE", bg="#0284c7")
            self.btn_ai_mode.config(bg="#0284c7")
            self.btn_fixed_mode.config(bg="#334155")
        else:
            self.lbl_mode_badge.config(text="FIXED TIMER", bg="#64748b")
            self.btn_ai_mode.config(bg="#334155")
            self.btn_fixed_mode.config(bg="#0284c7")

    def _toggle_pause(self):
        self.simulation.is_paused = not self.simulation.is_paused
        self.btn_pause.config(text="▶️ Resume" if self.simulation.is_paused else "⏸️ Pause")

    def _toggle_cv_window(self):
        if not self.cv_detector.running:
            self.cv_detector.start_cv_window()
            self.btn_cv.config(text="❌ Close CV Window", bg="#dc2626")
        else:
            self.cv_detector.stop_cv_window()
            self.btn_cv.config(text="📷 Open CV Camera Window", bg="#059669")

    def _log_event(self, message: str):
        timestamp = time.strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}\n"
        if hasattr(self, "log_text"):
            self.log_text.insert(tk.END, formatted)
            self.log_text.see(tk.END)

    def _start_animation_loop(self):
        self._update_simulation()

    def _update_simulation(self):
        now = time.time()
        dt = min(0.1, now - self.last_frame_time)
        self.last_frame_time = now
        self.flashing_tick += 1

        # Advance physics and AI state
        self.simulation.update(dt)

        # Draw Intersection Scene
        self._render_scene()

        # Update HUD Metrics
        self._render_hud()

        # Loop at ~40-60 FPS (16-25ms)
        self.root.after(20, self._update_simulation)

    def _render_hud(self):
        # Update Phase and remaining timer
        self.lbl_phase.config(text=self.controller.active_phase)
        rem = max(0.0, self.controller.phase_time_remaining)
        self.lbl_timer.config(text=f"{rem:.1f}s")

        # Metric widgets
        stats = self.controller.stats
        cleared = stats["vehicles_cleared"]
        avg_wait = self.controller.get_avg_wait_time()
        preemptions = stats["emergency_preemptions"]

        self.metric_widgets["Vehicles Cleared"].config(text=str(cleared))
        self.metric_widgets["Avg Waiting Time"].config(text=f"{avg_wait:.1f}s")
        self.metric_widgets["Emergency Preemptions"].config(text=str(preemptions))

        # Efficiency calculation comparison
        # In a fixed 20s cycle with no dynamic green or early cutoff, average wait is typically 18-24s
        benchmark_wait = 20.0
        if avg_wait > 0:
            saved = max(0.0, ((benchmark_wait - avg_wait) / benchmark_wait) * 100)
            self.metric_widgets["AI Delay Saved"].config(text=f"+{saved:.1f}%" if self.controller.mode == ControllerMode.AI_ADAPTIVE else "Baseline")
        else:
            self.metric_widgets["AI Delay Saved"].config(text="--")

        # Queue count per lane
        for d in Direction:
            cnt = len([v for v in self.simulation.vehicles[d] if v.pos <= self.simulation.STOP_LINE_POS + 10])
            self.lane_labels[d].config(text=f"{cnt} veh")

    def _render_scene(self):
        self.canvas.delete("all")
        c_size = self.canvas_size
        center = c_size // 2
        road_w = 140
        half_w = road_w // 2

        # 1. Background Grass / City Pavement
        self.canvas.create_rectangle(0, 0, c_size, c_size, fill="#0f172a", outline="")

        # 2. Roads (Asphalt: #1e293b)
        # Vertical corridor (North - South)
        self.canvas.create_rectangle(center - half_w, 0, center + half_w, c_size, fill="#1e293b", outline="")
        # Horizontal corridor (East - West)
        self.canvas.create_rectangle(0, center - half_w, c_size, center + half_w, fill="#1e293b", outline="")
        # Center Intersection Box
        self.canvas.create_rectangle(center - half_w, center - half_w, center + half_w, center + half_w, fill="#243048", outline="")

        # 3. Yellow Double Median Lines
        # North
        self.canvas.create_line(center - 2, 0, center - 2, center - half_w - 30, fill="#f59e0b", width=2)
        self.canvas.create_line(center + 2, 0, center + 2, center - half_w - 30, fill="#f59e0b", width=2)
        # South
        self.canvas.create_line(center - 2, center + half_w + 30, center - 2, c_size, fill="#f59e0b", width=2)
        self.canvas.create_line(center + 2, center + half_w + 30, center + 2, c_size, fill="#f59e0b", width=2)
        # West
        self.canvas.create_line(0, center - 2, center - half_w - 30, center - 2, fill="#f59e0b", width=2)
        self.canvas.create_line(0, center + 2, center - half_w - 30, center + 2, fill="#f59e0b", width=2)
        # East
        self.canvas.create_line(center + half_w + 30, center - 2, c_size, center - 2, fill="#f59e0b", width=2)
        self.canvas.create_line(center + half_w + 30, center + 2, c_size, center + 2, fill="#f59e0b", width=2)

        # 4. White Solid Stop Lines & Crosswalks
        # North Stop Line (y = center - half_w - 15)
        n_stop_y = center - half_w - 15
        self.canvas.create_line(center - half_w, n_stop_y, center, n_stop_y, fill="#ffffff", width=4)
        # North Crosswalk stripes
        for x_step in range(center - half_w + 5, center + half_w, 14):
            self.canvas.create_rectangle(x_step, center - half_w - 12, x_step + 8, center - half_w - 2, fill="#e2e8f0", outline="")

        # South Stop Line (y = center + half_w + 15)
        s_stop_y = center + half_w + 15
        self.canvas.create_line(center, s_stop_y, center + half_w, s_stop_y, fill="#ffffff", width=4)
        # South Crosswalk stripes
        for x_step in range(center - half_w + 5, center + half_w, 14):
            self.canvas.create_rectangle(x_step, center + half_w + 2, x_step + 8, center + half_w + 12, fill="#e2e8f0", outline="")

        # West Stop Line (x = center - half_w - 15)
        w_stop_x = center - half_w - 15
        self.canvas.create_line(w_stop_x, center, w_stop_x, center + half_w, fill="#ffffff", width=4)
        # West Crosswalk stripes
        for y_step in range(center - half_w + 5, center + half_w, 14):
            self.canvas.create_rectangle(center - half_w - 12, y_step, center - half_w - 2, y_step + 8, fill="#e2e8f0", outline="")

        # East Stop Line (x = center + half_w + 15)
        e_stop_x = center + half_w + 15
        self.canvas.create_line(e_stop_x, center - half_w, e_stop_x, center, fill="#ffffff", width=4)
        # East Crosswalk stripes
        for y_step in range(center - half_w + 5, center + half_w, 14):
            self.canvas.create_rectangle(center + half_w + 2, y_step, center + half_w + 12, y_step + 8, fill="#e2e8f0", outline="")

        # Lane Direction Arrows on road
        self._draw_road_indicators(center, half_w)

        # 5. Render Vehicles
        for direction, lane in self.simulation.vehicles.items():
            for v in lane:
                self._draw_vehicle(v, center, half_w)

        # 6. Render Traffic Lights Heads with Glow and Digital Countdowns
        self._draw_traffic_lights(center, half_w)

    def _draw_road_indicators(self, center, half_w):
        # Draw lane turn arrows (↰ ↑ ↱) indicating protected left, right and straight movements
        self.canvas.create_text(center - 35, center - half_w - 38, text="↰ ↑ ↱", fill="#94a3b8", font=("Segoe UI", 9, "bold"))
        self.canvas.create_text(center + 35, center + half_w + 38, text="↰ ↑ ↱", fill="#94a3b8", font=("Segoe UI", 9, "bold"))
        self.canvas.create_text(center - half_w - 38, center + 35, text="↰\n↑\n↱", fill="#94a3b8", font=("Segoe UI", 8, "bold"))
        self.canvas.create_text(center + half_w + 38, center - 35, text="↰\n↑\n↱", fill="#94a3b8", font=("Segoe UI", 8, "bold"))

        # Faint dashed turn guide arcs in junction box
        self.canvas.create_arc(center - half_w, center - half_w, center - half_w + 70, center - half_w + 70,
                               start=0, extent=90, style="arc", outline="#0284c7", dash=(3, 5))
        self.canvas.create_arc(center + half_w - 210, center - half_w, center + half_w, center - half_w + 210,
                               start=90, extent=90, style="arc", outline="#0284c7", dash=(3, 5))

    def _map_vehicle_coords(self, v: Vehicle, center: int, half_w: int):
        """Converts 1D distance `pos` along lane approach to (cx, cy, heading_angle) with smooth left/right turning."""
        stop_line_dist = 265.0 # Screen distance from spawn (10) to stop line
        scale = stop_line_dist / self.simulation.STOP_LINE_POS
        pos = v.pos * scale
        c = center
        turn = getattr(v, "turn_intent", "straight")

        rx = -half_w // 2 # -35
        ry = pos - c
        r_head = 90

        if turn == "straight":
            rx = -half_w // 2
            ry = pos - c
            r_head = 90
        elif turn == "right":
            if pos <= 265:
                rx = -35
                ry = pos - c
                r_head = 90
            elif pos < 335:
                t = (pos - 265) / 70.0
                rx = -70 + 35 * math.cos(t * math.pi / 2)
                ry = -70 + 35 * math.sin(t * math.pi / 2)
                r_head = 90 + int(t * 90)
            else:
                rx = -70 - (pos - 335)
                ry = -35
                r_head = 180
        elif turn == "left":
            if pos <= 265:
                rx = -35
                ry = pos - c
                r_head = 90
            elif pos < 405:
                t = (pos - 265) / 140.0
                rx = 70 - 105 * math.cos(t * math.pi / 2)
                ry = -70 + 105 * math.sin(t * math.pi / 2)
                r_head = 90 - int(t * 90)
            else:
                rx = 70 + (pos - 405)
                ry = 35
                r_head = 0

        # Rotate reference coordinates into direction
        if v.direction == Direction.NORTH:
            cx = c + rx
            cy = c + ry
            heading = r_head
        elif v.direction == Direction.EAST:
            cx = c - ry
            cy = c + rx
            heading = (r_head + 90) % 360
        elif v.direction == Direction.SOUTH:
            cx = c - rx
            cy = c - ry
            heading = (r_head + 180) % 360
        else: # WEST
            cx = c + ry
            cy = c - rx
            heading = (r_head + 270) % 360

        return cx, cy, heading

    def _draw_vehicle(self, v: Vehicle, center: int, half_w: int):
        cx, cy, heading = self._map_vehicle_coords(v, center, half_w)
        length = v.vehicle_type.length
        width = v.vehicle_type.width
        color = v.vehicle_type.color

        # Bounding box corners according to heading (0: East, 90: South, 180: West, 270: North)
        if heading in (90, 270):
            x1, y1 = cx - width//2, cy - length//2
            x2, y2 = cx + width//2, cy + length//2
        else:
            x1, y1 = cx - length//2, cy - width//2
            x2, y2 = cx + length//2, cy + width//2

        # Draw vehicle shadow
        self.canvas.create_rectangle(x1+2, y1+2, x2+2, y2+2, fill="#070a12", outline="")

        # Draw vehicle chassis
        self.canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline="#ffffff", width=1)

        # Turn indicator symbol on roof
        turn = getattr(v, "turn_intent", "straight")
        turn_sym = "↰" if turn == "left" else ("↱" if turn == "right" else "↑")
        self.canvas.create_text(cx, cy, text=turn_sym, fill="#ffffff", font=("Segoe UI", 7, "bold"))

        # Flashing turn blinker
        is_blink = (self.flashing_tick // 4) % 2 == 0
        if is_blink and turn != "straight" and v.pos < 360:
            blinker_x = x1 if turn == "left" else x2
            self.canvas.create_oval(blinker_x - 3, cy - 3, blinker_x + 3, cy + 3, fill="#f59e0b", outline="")

        # Emergency Ambulance Siren Flashing
        if v.is_emergency:
            siren_col = "#ef4444" if (self.flashing_tick // 4) % 2 == 0 else "#38bdf8"
            self.canvas.create_oval(cx - 4, cy - 4, cx + 4, cy + 4, fill=siren_col, outline="#ffffff")
            self.canvas.create_oval(cx - 10, cy - 10, cx + 10, cy + 10, outline=siren_col, width=1)

    def _draw_traffic_lights(self, center: int, half_w: int):
        """Draws 4 traffic light signal heads at the 4 intersection corners."""
        light_configs = {
            Direction.NORTH: (center - half_w - 38, center - half_w - 75),
            Direction.SOUTH: (center + half_w + 14, center + half_w + 25),
            Direction.WEST:  (center - half_w - 75, center + half_w + 14),
            Direction.EAST:  (center + half_w + 25, center - half_w - 38),
        }

        rem_text = f"{int(math.ceil(max(0, self.controller.phase_time_remaining)))}"

        for direction, (bx, by) in light_configs.items():
            curr_state = self.controller.lights[direction]

            # Signal Head Box
            box_w, box_h = 24, 52
            self.canvas.create_rectangle(bx, by, bx + box_w, by + box_h, fill="#111827", outline="#475569", width=2)

            # Colors for 3 lamps (RED, YELLOW, GREEN)
            red_fill = "#ef4444" if curr_state == LightState.RED else "#371414"
            yel_fill = "#eab308" if curr_state == LightState.YELLOW else "#3a2e0b"
            grn_fill = "#22c55e" if curr_state == LightState.GREEN else "#0b2e16"

            # Draw Red Lamp
            self.canvas.create_oval(bx + 4, by + 4, bx + 20, by + 18, fill=red_fill, outline="")
            # Draw Yellow Lamp
            self.canvas.create_oval(bx + 4, by + 19, bx + 20, by + 33, fill=yel_fill, outline="")
            # Draw Green Lamp
            self.canvas.create_oval(bx + 4, by + 34, bx + 20, by + 48, fill=grn_fill, outline="")

            # Glow effect on active lamp
            if curr_state == LightState.RED:
                self.canvas.create_oval(bx + 1, by + 1, bx + 23, by + 21, outline="#ef4444", width=2)
            elif curr_state == LightState.YELLOW:
                self.canvas.create_oval(bx + 1, by + 16, bx + 23, by + 36, outline="#eab308", width=2)
            elif curr_state == LightState.GREEN:
                self.canvas.create_oval(bx + 1, by + 31, bx + 23, by + 51, outline="#22c55e", width=2)

            # Timer badge
            self.canvas.create_text(
                bx + box_w//2, by - 8,
                text=rem_text,
                fill="#38bdf8",
                font=("Consolas", 8, "bold")
            )
