"""
models.py - Core data models and enums for AI Traffic Signal System.
"""
from enum import Enum
import time
import random

class Direction(Enum):
    NORTH = "North"
    SOUTH = "South"
    EAST = "East"
    WEST = "West"

    @property
    def opposite(self):
        opposites = {
            Direction.NORTH: Direction.SOUTH,
            Direction.SOUTH: Direction.NORTH,
            Direction.EAST: Direction.WEST,
            Direction.WEST: Direction.EAST
        }
        return opposites[self]

class LightState(Enum):
    RED = "RED"
    YELLOW = "YELLOW"
    GREEN = "GREEN"

class VehicleType(Enum):
    CAR = ("Car", 1.0, 22, 12, "#38bdf8")       # label, weight, length, width, color
    BUS = ("Bus", 2.2, 40, 15, "#fbbf24")
    TRUCK = ("Truck", 2.0, 36, 14, "#f97316")
    BIKE = ("Motorbike", 0.5, 14, 8, "#a855f7")
    AMBULANCE = ("Ambulance", 10.0, 26, 13, "#ef4444") # high priority

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
        self.spawn_time = time.time()
        self.wait_time = 0.0
        self.speed = 0.0
        self.max_speed = 3.5 if self.vehicle_type != VehicleType.AMBULANCE else 5.0
        self.is_emergency = (self.vehicle_type == VehicleType.AMBULANCE)
        
        # Position along the 1D approach line (0 = far away, stop_line = at traffic light)
        self.pos = 0.0
        self.cleared = False
        self.is_stopped = False

        # Turn intent: 35% straight, 35% right, 30% left
        r = random.random()
        if self.is_emergency:
            self.turn_intent = "straight" if r < 0.6 else ("left" if r < 0.8 else "right")
        else:
            self.turn_intent = "straight" if r < 0.35 else ("left" if r < 0.68 else "right")

    @staticmethod
    def _random_type():
        # Weighted random selection: mostly cars, some bikes, trucks, occasional ambulance
        types = [VehicleType.CAR, VehicleType.BIKE, VehicleType.BUS, VehicleType.TRUCK, VehicleType.AMBULANCE]
        weights = [0.65, 0.15, 0.10, 0.08, 0.02]
        return random.choices(types, weights=weights)[0]

    def update_wait(self, dt: float):
        if self.is_stopped:
            self.wait_time += dt
