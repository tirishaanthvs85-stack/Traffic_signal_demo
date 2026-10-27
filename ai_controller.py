"""
ai_controller.py - Intelligent Traffic Signal Controller.
Implements Dynamic Green Timing, Queue-Based Priority Scheduling,
Emergency Vehicle Preemption, and Comparison with Fixed-Time Controllers.
"""
import time
from typing import Dict, List, Callable, Optional
from models import Direction, LightState, Vehicle, VehicleType

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
    def __init__(self, log_callback: Optional[Callable[[str], None]] = None):
        self.mode = ControllerMode.AI_ADAPTIVE
        self.log_callback = log_callback or (lambda msg: None)

        # Timing constraints (in seconds)
        self.min_green = 6.0
        self.max_green = 28.0
        self.base_green = 7.0
        self.yellow_duration = 3.0
        self.all_red_duration = 1.0
        self.fixed_green_duration = 14.0
        self.starvation_threshold = 28.0 # max wait before forced switch

        # State - ONLY ONE DIRECTION IS GREEN AT A TIME
        self.active_phase = SignalPhase.NORTH
        self.state_step = LightState.GREEN # Current phase light state
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

        # Transition control
        self.in_transition = False
        self.transition_step = "" # "YELLOW", "ALL_RED"
        self.next_phase = SignalPhase.EAST

        # Emergency override tracking
        self.emergency_override_active = False
        self.emergency_target_phase: Optional[str] = None

        # Statistics
        self.stats = {
            "vehicles_cleared": 0,
            "total_wait_time": 0.0,
            "max_queue_seen": 0,
            "emergency_preemptions": 0,
            "switches_count": 0,
            "cleared_history": []
        }

    def set_mode(self, mode: str):
        old_mode = self.mode
        self.mode = mode
        self.log(f"Switched controller mode: {old_mode} ➜ {self.mode}")
        if mode == ControllerMode.FIXED_CYCLE:
            self.phase_duration = self.fixed_green_duration
            self.phase_time_remaining = min(self.phase_time_remaining, self.fixed_green_duration)

    def log(self, message: str):
        if self.log_callback:
            self.log_callback(f"[Traffic Controller] {message}")

    def get_phase_directions(self, phase: str) -> List[Direction]:
        return [SignalPhase.get_direction(phase)]

    def calculate_phase_metrics(self, queues: Dict[Direction, List[Vehicle]], phase: str):
        """Calculates queue count, weighted density, max wait time, and emergency vehicle presence for single approach."""
        d = SignalPhase.get_direction(phase)
        lane = queues.get(d, [])
        total_count = len(lane)
        weighted_density = 0.0
        max_wait = 0.0
        has_emergency = False

        for v in lane:
            weighted_density += v.vehicle_type.priority_weight
            if v.wait_time > max_wait:
                max_wait = v.wait_time
            if v.is_emergency and v.pos < 300: # approaching or waiting
                has_emergency = True

        return {
            "count": total_count,
            "weighted_density": weighted_density,
            "max_wait": max_wait,
            "has_emergency": has_emergency
        }

    def compute_ai_green_time(self, metrics: dict) -> float:
        """Dynamically allocates green light duration for the single approach based on backlog."""
        count = metrics["count"]
        weighted_density = metrics["weighted_density"]
        calculated = self.base_green + (weighted_density * 2.0)
        optimal_green = max(self.min_green, min(self.max_green, round(calculated, 1)))
        return optimal_green

    def evaluate_priority_decision(self, queues: Dict[Direction, List[Vehicle]]):
        """
        Decides which single direction gets GREEN next among the 3 waiting directions:
        1. Emergency Vehicle Preemption (Ambulances)
        2. Starvation Safeguard (>28s wait)
        3. Dynamic Weighted Demand Score
        """
        candidates = [p for p in SignalPhase.ORDER if p != self.active_phase]

        # 1. Emergency Preemption
        for p in candidates:
            m = self.calculate_phase_metrics(queues, p)
            if m["has_emergency"]:
                return p, f"Ambulance Detected on {p} (Emergency Override)"

        # 2. Starvation Prevention
        for p in candidates:
            m = self.calculate_phase_metrics(queues, p)
            if m["max_wait"] >= self.starvation_threshold and m["count"] > 0:
                return p, f"Starvation safeguard triggered ({p} wait: {m['max_wait']:.1f}s)"

        # 3. Dynamic Score Comparison
        best_phase = candidates[0]
        best_score = -1.0
        reasons = []

        for p in candidates:
            m = self.calculate_phase_metrics(queues, p)
            score = (m["count"] * 2.0) + (m["weighted_density"] * 2.5) + (m["max_wait"] * 0.6)
            reasons.append(f"{p[:5]}:{score:.1f}")
            if score > best_score:
                best_score = score
                best_phase = p

        if best_score <= 0.1:
            # All queues empty, proceed round-robin
            next_seq = SignalPhase.get_next(self.active_phase)
            return next_seq, "Round-robin sequence (all queues idle)"

        return best_phase, f"Highest Priority Demand [{', '.join(reasons)}]"

    def update(self, dt: float, queues: Dict[Direction, List[Vehicle]]):
        """Advances traffic light state machine by dt seconds."""
        self.phase_time_remaining -= dt
        self.elapsed_in_phase += dt

        # Check for immediate emergency preemption while in GREEN
        if not self.in_transition and self.mode == ControllerMode.AI_ADAPTIVE:
            for p in SignalPhase.ORDER:
                if p != self.active_phase:
                    m = self.calculate_phase_metrics(queues, p)
                    if m["has_emergency"]:
                        curr_m = self.calculate_phase_metrics(queues, self.active_phase)
                        if not curr_m["has_emergency"]:
                            self.log(f"🚨 EMERGENCY PREEMPTION! Ambulance on {p}. Switching signals immediately.")
                            self.stats["emergency_preemptions"] += 1
                            self._begin_transition_to(p, is_emergency=True)
                            return

            # Early Cutoff: If current single phase is empty and other approaches are waiting
            curr_metrics = self.calculate_phase_metrics(queues, self.active_phase)
            if self.elapsed_in_phase >= self.min_green and curr_metrics["count"] == 0:
                has_waiting = any(len(queues[d]) > 0 for d in Direction if d != SignalPhase.get_direction(self.active_phase))
                if has_waiting:
                    self.log(f"⚡ Early Cutoff: Active {self.active_phase} lane empty. Switching early to serve waiting traffic.")
                    target_phase, reason = self.evaluate_priority_decision(queues)
                    self._begin_transition_to(target_phase)
                    return

        # Regular timer countdown check
        if self.phase_time_remaining <= 0:
            self._handle_timer_expiry(queues)

    def _handle_timer_expiry(self, queues: Dict[Direction, List[Vehicle]]):
        if not self.in_transition:
            if self.mode == ControllerMode.AI_ADAPTIVE:
                target_phase, reason = self.evaluate_priority_decision(queues)
                self.log(f"Phase decision: {target_phase} chosen. Reason: {reason}")
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
                    metrics = self.calculate_phase_metrics(queues, self.active_phase)
                    new_green = self.compute_ai_green_time(metrics)
                    self.log(f"🚦 GREEN granted exclusively to {self.active_phase}. Duration: {new_green:.1f}s (Queue: {metrics['count']})")
                else:
                    new_green = self.fixed_green_duration
                    self.log(f"🚦 GREEN granted exclusively to {self.active_phase}. Fixed Duration: {new_green:.1f}s")

                self.phase_duration = new_green
                self.phase_time_remaining = new_green

                # Exactly one direction is GREEN; all other 3 are RED!
                for d in Direction:
                    self.lights[d] = LightState.GREEN if d == active_dir else LightState.RED

    def _begin_transition_to(self, next_phase: str, is_emergency: bool = False):
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

    def record_cleared_vehicle(self, vehicle: Vehicle):
        self.stats["vehicles_cleared"] += 1
        self.stats["total_wait_time"] += vehicle.wait_time
        self.stats["cleared_history"].append({
            "type": vehicle.vehicle_type.label,
            "wait_time": vehicle.wait_time,
            "direction": vehicle.direction.value,
            "is_emergency": vehicle.is_emergency
        })

    def get_avg_wait_time(self) -> float:
        if self.stats["vehicles_cleared"] == 0:
            return 0.0
        return self.stats["total_wait_time"] / self.stats["vehicles_cleared"]
