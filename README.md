# 🚦 AI Smart Traffic Signal System

An adaptive, intelligent traffic signal management and control system built in Python. It replaces static, rigid timer cycles with real-time dynamic queue sensing, computer vision vehicle detection, and priority-weighted signal scheduling with emergency vehicle preemption.

---

## 🌟 Key Features

1. **Dynamic Green Time Allocation**:
   - Calculates the optimal green light duration dynamically based on real-time vehicle density and queue length:
     $$\text{Duration} = \text{clamp}(T_{base} + \text{Density} \times 1.8\text{s},\, T_{min},\, T_{max})$$
   - Prevents empty road idling by executing **early cutoff** when waiting queues clear.

2. **Priority Scoring & Starvation Safeguard**:
   - Computes weighted lane urgency incorporating queue count, vehicle types (buses, trucks, cars, bikes), and elapsed waiting time:
     $$\text{Score} = (\text{Count} \times 1.5) + (\text{Weight} \times 2.0) + (\text{MaxWait} \times 0.4)$$
   - Automatically prioritizes starved lanes if maximum wait exceeds threshold.

3. **Emergency Vehicle Preemption (Ambulances)**:
   - When an ambulance or emergency vehicle is detected on a red corridor, the system immediately cuts the active green, cycles a safe yellow, and opens the intersection corridor for the emergency vehicle.

4. **Computer Vision Vehicle Detector (`cv2`)**:
   - OpenCV MOG2 background subtractor and contour bounding box tracking with lane Region of Interest (ROI) zones.
   - Includes real-time simulated surveillance feed and support for live webcams.

5. **Visual Control Deck & Simulation**:
   - Dark-themed 60 FPS Tkinter GUI displaying the 4-way intersection, vehicle kinematics, glowing traffic signal heads, live telemetry, and AI decision logs.

---

## 📁 Project Architecture

```
ai_traffic_system/
│
├── main.py                    # Application entry point (GUI & Benchmark modes)
├── gui.py                     # Tkinter 4-way intersection UI & telemetry deck
├── ai_controller.py           # Adaptive AI scheduling & state machine
├── simulation.py              # Physics, car-following, and spawning engine
├── cv_detector.py             # OpenCV vehicle & ROI zone detection
├── models.py                  # Direction, LightState, Vehicle data classes
├── standalone_ai_traffic.py   # Complete all-in-one single-file version
├── run.bat                    # One-click Windows runner
└── README.md                  # System documentation
```

---

## 🚀 How to Run

### 1. Launch Interactive GUI (Recommended)
```bash
python main.py
```
*(Or double-click `run.bat`)*

### 2. Run Automated AI vs Fixed-Timer Benchmark
Compare throughput and wait times over an automated headless test:
```bash
python main.py --benchmark --duration 60
```

### 3. Run Single-File Standalone Version
```bash
python standalone_ai_traffic.py
```

---

## 📊 Benchmark Results

| Metric | Traditional Fixed Timer (20s) | AI Adaptive Controller | Improvement |
| :--- | :--- | :--- | :--- |
| **Average Wait Time** | 2.22s | 1.20s | **-45.7% Wait Reduction** |
| **Vehicles Cleared** | 19 | 21 | **+10.5% Throughput** |
| **Emergency Preemptions** | 0 (Ignored) | Handled (Instant Green) | **100% Preempted** |
