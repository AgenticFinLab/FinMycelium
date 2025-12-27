"""
Event Cascade Gantt Visualization Test Script
=============================================

This script demonstrates and verifies the functionality of the `EventCascadeGanttVisualizer`.
It batch processes a list of predefined JSON files containing Financial Event Cascade data,
generating interactive HTML Gantt charts for each.

Key Features:
- **Batch Processing**: Iterates through multiple experiment output directories.
- **Data Loading**: Reads `FinalEventCascade.json` structure.
- **Visualization**: Uses `EventCascadeGanttVisualizer` to render the timeline,
  participant relationships, and event episodes.
- **Output Verification**: Checks if the HTML file was successfully created.

Usage:
    Run this script directly from the project root or appropriate directory:
    $ python examples/uTEST/Builder/test_viz_gantt.py -c configs/uTEST/builder/agent_build.yml

"""

import os
import json
from finmy.builder.agent_build.visualizer_gantt import EventCascadeGanttVisualizer


def test_gantt():
    """
    Main execution function for testing the Gantt visualizer.

    Steps:
    1. Define list of target JSON file paths.
    2. Initialize the EventCascadeGanttVisualizer.
    3. Iterate through each file:
       - Validate file existence.
       - Load JSON data.
       - Generate HTML Gantt chart in the same directory.
       - Verify output generation.
    """
    # Define the list of input JSON files (Event Cascade outputs from Builder experiments)
    # These paths are relative to the project root.
    json_paths = [
        "EXPERIMENT/uTEST/StepBuilderDemo1/FinalEventCascade.json",
        "EXPERIMENT/uTEST/StepBuilderDemo2/FinalEventCascade.json",
        "EXPERIMENT/uTEST/StepBuilderDemo3/FinalEventCascade.json",
        "EXPERIMENT/uTEST/StepBuilderDemo4/FinalEventCascade.json",
        "EXPERIMENT/uTEST/StepBuilderDemo5/FinalEventCascade.json",
    ]

    # Initialize the visualizer instance
    viz = EventCascadeGanttVisualizer()

    print(f"Starting batch visualization for {len(json_paths)} files...\n")

    for json_path in json_paths:
        # 1. Check if the input file exists
        if not os.path.exists(json_path):
            print(f"[Skipping] File not found: {json_path}")
            continue

        # 2. Load the Event Cascade JSON data
        print(f"Processing: {json_path}")
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                cascade_data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"  [Error] Invalid JSON format in {json_path}: {e}")
            continue
        except Exception as e:
            print(f"  [Error] Could not read file {json_path}: {e}")
            continue

        # 3. Determine output path (same directory as input, suffix _gantt.html)
        base_name = os.path.splitext(os.path.basename(json_path))[0]
        out_dir = os.path.dirname(json_path)
        output_path = os.path.join(out_dir, f"{base_name}_gantt.html")

        # 4. Generate the Gantt Chart
        print(f"  Generating Gantt Chart -> {output_path}")
        try:
            viz.plot_cascade(cascade_data, output_path)
        except Exception as e:
            print(f"  [Error] Visualization failed for {json_path}: {e}")
            continue

        # 5. Verify the output file was created
        if os.path.exists(output_path):
            print(f"  [Success] HTML generated successfully.\n")
        else:
            print(f"  [Failure] HTML file was not created.\n")


if __name__ == "__main__":
    test_gantt()
