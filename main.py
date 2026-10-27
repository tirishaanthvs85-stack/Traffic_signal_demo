"""
main.py - Entry point for the AI Smart Traffic Signal System.
Supports GUI Mode and Headless Benchmark Evaluation Mode.
"""
import sys
import argparse
import tkinter as tk

# Ensure Windows stdout handles UTF-8 characters gracefully
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from models import Direction, VehicleType
from ai_controller import AITrafficController, ControllerMode
from simulation import TrafficSimulation

def run_benchmark(duration_seconds: int = 120):
    """Headless automated benchmark comparing Fixed-Timer vs AI-Adaptive controller."""
    print("=" * 65)
    print(f"[BENCHMARK] RUNNING AI vs FIXED-TIMER TRAFFIC SIMULATION ({duration_seconds}s)")
    print("=" * 65)

    results = {}
    for mode in [ControllerMode.FIXED_CYCLE, ControllerMode.AI_ADAPTIVE]:
        print(f"\nEvaluating Mode: [{mode}]...")
        ctrl = AITrafficController()
        ctrl.set_mode(mode)
        sim = TrafficSimulation(ctrl)
        sim.auto_spawn = True
        sim.spawn_rate = 1.4

        dt = 0.05
        steps = int(duration_seconds / dt)

        # Inject an emergency vehicle midway to evaluate preemption response
        emergency_step = int(steps * 0.4)

        for step in range(steps):
            if step == emergency_step:
                sim.spawn_emergency(Direction.NORTH)
            sim.update(dt)

        cleared = ctrl.stats["vehicles_cleared"]
        avg_wait = ctrl.get_avg_wait_time()
        preemptions = ctrl.stats["emergency_preemptions"]
        switches = ctrl.stats["switches_count"]

        results[mode] = {
            "cleared": cleared,
            "avg_wait": avg_wait,
            "preemptions": preemptions,
            "switches": switches
        }
        print(f"  ➜ Vehicles Cleared     : {cleared}")
        print(f"  ➜ Average Waiting Time : {avg_wait:.2f} s")
        print(f"  ➜ Phase Switches       : {switches}")
        print(f"  ➜ Emergency Preemptions: {preemptions}")

    fixed_wait = results[ControllerMode.FIXED_CYCLE]["avg_wait"]
    ai_wait = results[ControllerMode.AI_ADAPTIVE]["avg_wait"]
    fixed_clear = results[ControllerMode.FIXED_CYCLE]["cleared"]
    ai_clear = results[ControllerMode.AI_ADAPTIVE]["cleared"]

    wait_reduction = ((fixed_wait - ai_wait) / fixed_wait) * 100 if fixed_wait > 0 else 0
    throughput_increase = ((ai_clear - fixed_clear) / fixed_clear) * 100 if fixed_clear > 0 else 0

    print("\n" + "=" * 65)
    print("📊 BENCHMARK COMPARISON SUMMARY:")
    print(f"  - Average Wait Reduction by AI   : {wait_reduction:+.1f}%")
    print(f"  - Throughput Improvement by AI   : {throughput_increase:+.1f}%")
    print("=" * 65)

def main():
    parser = argparse.ArgumentParser(description="AI Traffic Signal System")
    parser.add_argument("--benchmark", action="store_true", help="Run automated headless evaluation benchmark")
    parser.add_argument("--duration", type=int, default=120, help="Benchmark duration in seconds")
    args = parser.parse_args()

    if args.benchmark:
        run_benchmark(args.duration)
    else:
        from gui import TrafficSystemGUI
        root = tk.Tk()
        app = TrafficSystemGUI(root)
        root.mainloop()

if __name__ == "__main__":
    main()
