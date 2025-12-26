"""
Test Script for EventCascadeGanttVisualizer
===========================================
"""

import os
import json
from finmy.builder.agent_build.visualizer_gantt import EventCascadeGanttVisualizer


def test_gantt():
    """Test the visualizer-gantt."""
    # json_paths = [
    #     r"EXPERIMENT\uTEST\Pipline\build_output_20251222130929900932\FinalEventCascade.json"
    # ]
    json_paths = [
        r"EXPERIMENT\uTEST\Pipline\FinalEventCascade.json",
    ]
    viz = EventCascadeGanttVisualizer()

    for json_path in json_paths:
        if not os.path.exists(json_path):
            print(f"Error: JSON file not found at {json_path}")
            continue

        print(f"Loading data from {json_path}...")
        with open(json_path, "r", encoding="utf-8") as f:
            cascade_data = json.load(f)

        base = os.path.splitext(os.path.basename(json_path))[0]
        out_dir = os.path.dirname(json_path)
        output_path = os.path.join(out_dir, f"{base}_gantt.html")

        print(f"Generating Gantt Chart to {output_path}...")
        viz.plot_cascade(cascade_data, output_path)

        if os.path.exists(output_path):
            print(f"Success: HTML file generated at {output_path}.")
        else:
            print(f"Error: HTML file not found at {output_path}.")


if __name__ == "__main__":
    test_gantt()
