"""
Test Script for EventCascadeGanttVisualizer
===========================================
"""

import os
import json
from finmy.builder.agent_build.visualizer_gantt import EventCascadeGanttVisualizer


def test_gantt():
    # Define Input Data Path (Same as test_viz.py)
    json_path = "EXPERIMENT/uTEST/StepBuilderDemo1/FinalEventCascade.json"

    if not os.path.exists(json_path):
        print(f"Error: JSON file not found at {json_path}")
        return

    print(f"Loading data from {json_path}...")
    with open(json_path, "r", encoding="utf-8") as f:
        cascade_data = json.load(f)

    viz = EventCascadeGanttVisualizer()
    base = os.path.splitext(os.path.basename(json_path))[0]
    out_dir = os.path.dirname(json_path)
    output_path = os.path.join(out_dir, f"{base}_gantt.html")

    print(f"Generating Gantt Chart to {output_path}...")
    viz.plot_cascade(cascade_data, output_path)

    if os.path.exists(output_path):
        print("Success: HTML file generated.")
    else:
        print("Error: HTML file not found.")


if __name__ == "__main__":
    test_gantt()
