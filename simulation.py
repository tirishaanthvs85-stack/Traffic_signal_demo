"""
simulation.py - Physics and traffic flow simulation engine for 4-way intersection.
Handles vehicle dynamics, queueing, deceleration at stop lines, and intersection clearance.
"""
import random
import time
from typing import Dict, List, Optional
from models import Direction, LightState, Vehicle, VehicleType
from ai_controller import AITrafficController

class TrafficSimulation:
    STOP_LINE_POS = 300.0        # Position at the stop bar
    INTERSECTION_EXIT_POS = 430.0 # Position where vehicle exits intersection
    TOTAL_LANE_LENGTH = 650.0

    def __init__(self, controller: AITrafficController):
        self.controller = controller
        self.vehicles: Dict[Direction, List[Vehicle]] = {
            Direction.NORTH: [],
            Direction.SOUTH: [],
            Direction.EAST: [],
            Direction.WEST: [],
        }

        # Simulation parameters
        self.sim_time = 0.0
        self.spawn_rate = 1.2   # Average vehicles spawned per second total
        self.sim_speed = 1.0    # Speed multiplier (1x, 2x, etc.)
        self.is_paused = False
        self.last_spawn_time = 0.0
        self.auto_spawn = True

        # Direction-specific spawn weights for creating asymmetric rush hours
        self.direction_weights = {
            Direction.NORTH: 1.0,
            Direction.SOUTH: 1.0,
            Direction.EAST: 0.8,
            Direction.WEST: 0.8,
        }

    def spawn_vehicle(self, direction: Direction, vehicle_type: Optional[VehicleType] = None) -> Optional[Vehicle]:
        """Attempts to spawn a vehicle at the entrance of a lane if space permits."""
        lane = self.vehicles[direction]
        
        # Check if lane entrance is blocked
        if lane:
            closest_to_entrance = min(lane, key=lambda v: v.pos)
            if closest_to_entrance.pos < 45.0: # space required at spawn point
                return None

        v = Vehicle(direction=direction, vehicle_type=vehicle_type)
        v.spawn_time = self.sim_time
        v.pos = 0.0
        v.speed = v.max_speed * 0.7
        lane.append(v)

        if v.is_emergency:
            self.controller.log(f"🚨 Ambulance dispatched into {direction.value} lane!")

        return v

    def spawn_emergency(self, direction: Direction):
        return self.spawn_vehicle(direction, VehicleType.AMBULANCE)

    def trigger_rush_hour(self, direction: Optional[Direction] = None):
        """Bursts vehicles into lanes to simulate rush hour traffic."""
        target_dirs = [direction] if direction else [Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST]
        for d in target_dirs:
            for _ in range(3):
                self.spawn_vehicle(d)

    def update(self, dt: float):
        if self.is_paused:
            return

        effective_dt = dt * self.sim_speed
        self.sim_time += effective_dt

        # 1. Automatic Traffic Spawning
        if self.auto_spawn:
            elapsed = self.sim_time - self.last_spawn_time
            if elapsed >= (1.0 / max(0.2, self.spawn_rate)):
                self.last_spawn_time = self.sim_time
                dirs = list(Direction)
                weights = [self.direction_weights[d] for d in dirs]
                chosen_dir = random.choices(dirs, weights=weights)[0]
                self.spawn_vehicle(chosen_dir)

        # 2. Advance AI Traffic Signal Controller
        # Create queue snapshot of vehicles waiting before stop line
        waiting_queues = {
            d: [v for v in self.vehicles[d] if v.pos <= self.STOP_LINE_POS + 10]
            for d in Direction
        }
        self.controller.update(effective_dt, waiting_queues)

        # 3. Update Vehicle Kinematics and Queuing
        for direction, lane in self.vehicles.items():
            light = self.controller.lights[direction]
            # Sort vehicles by position (frontmost first)
            lane.sort(key=lambda v: v.pos, reverse=True)

            for i, v in enumerate(lane):
                # Target obstacle position ahead
                if i == 0:
                    # Lead vehicle: obstacle is stop line if light is RED or YELLOW and vehicle hasn't crossed
                    if light in (LightState.RED, LightState.YELLOW) and v.pos < self.STOP_LINE_POS:
                        target_stop = self.STOP_LINE_POS
                    else:
                        target_stop = self.TOTAL_LANE_LENGTH
                else:
                    # Following vehicle: obstacle is preceding vehicle's rear
                    prev_v = lane[i - 1]
                    target_stop = prev_v.pos - prev_v.vehicle_type.length - 12.0

                dist_to_target = target_stop - v.pos

                # Simple Intelligent Driver / Deceleration Model
                if dist_to_target > 80.0:
                    # Plenty of space ahead: accelerate
                    v.speed = min(v.max_speed, v.speed + 1.2 * effective_dt)
                    v.is_stopped = False
                elif dist_to_target > 10.0:
                    # Approaching obstacle: decelerate smoothly
                    desired_speed = v.max_speed * (dist_to_target / 80.0)
                    if v.speed > desired_speed:
                        v.speed = max(desired_speed, v.speed - 2.5 * effective_dt)
                    else:
                        v.speed = min(desired_speed, v.speed + 1.0 * effective_dt)
                    v.is_stopped = (v.speed < 0.2)
                else:
                    # Stopped at barrier / back of queue
                    v.speed = 0.0
                    v.is_stopped = True

                # Advance position
                v.pos += v.speed * (effective_dt * 30.0) # scaling for smooth rendering
                v.update_wait(effective_dt)

            # Check for vehicles that cleared the intersection
            cleared_vehicles = [v for v in lane if v.pos >= self.INTERSECTION_EXIT_POS and not v.cleared]
            for cv in cleared_vehicles:
                cv.cleared = True
                self.controller.record_cleared_vehicle(cv)

            # Remove vehicles that moved off screen
            self.vehicles[direction] = [v for v in lane if v.pos < self.TOTAL_LANE_LENGTH]
