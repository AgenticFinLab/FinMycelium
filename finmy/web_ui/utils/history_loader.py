"""
Utilities for loading historical reconstruction results.
"""

import os
import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime


def scan_history_files(save_folder: str) -> List[Dict[str, str]]:
    """
    Scan for historical result directories.

    Args:
        save_folder: Base folder path where results are saved

    Returns:
        List of dictionaries containing path, name, and time info
    """
    history_files = []

    if not save_folder or not os.path.exists(save_folder):
        logging.warning("Save folder does not exist: %s", save_folder)
        return history_files

    try:
        # Scan all build_output_* directories
        for item in os.listdir(save_folder):
            item_path = os.path.join(save_folder, item)

            # Check if it's a directory and matches the pattern
            if os.path.isdir(item_path) and item.startswith("build_output_"):
                result_file = os.path.join(item_path, "FinalEventCascade.json")

                # Check if result file exists
                if os.path.exists(result_file):
                    # Get modification time
                    mtime = os.path.getmtime(item_path)
                    time_str = datetime.fromtimestamp(mtime).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )

                    history_files.append(
                        {
                            "path": item_path,
                            "name": item,
                            "time": time_str,
                            "timestamp": mtime,
                        }
                    )

        # Sort by modification time, newest first
        history_files.sort(key=lambda x: x["timestamp"], reverse=True)

    except Exception as e:
        logging.error("Error scanning history files: %s", e)

    return history_files


def load_history_result(result_dir_or_file: str) -> Optional[Dict[str, Any]]:
    """
    Load historical result from directory or file path.

    Args:
        result_dir_or_file: Path to the result directory or full file path

    Returns:
        Loaded result dictionary or None if failed
    """
    # If it's a file path, use it directly
    if os.path.isfile(result_dir_or_file):
        result_file = result_dir_or_file
    else:
        # Try to find the result file in the directory
        # First try agent_build format
        result_file = os.path.join(result_dir_or_file, "FinalEventCascade.json")

        # If not found, try to find class_build format files
        if not os.path.exists(result_file):
            try:
                # Look for Class_Build_Event_Cascade_*.json files
                for item in os.listdir(result_dir_or_file):
                    if item.startswith("Class_Build_Event_Cascade_") and item.endswith(
                        ".json"
                    ):
                        result_file = os.path.join(result_dir_or_file, item)
                        break
                else:
                    # If still not found, try just FinalEventCascade.json
                    result_file = os.path.join(
                        result_dir_or_file, "FinalEventCascade.json"
                    )
            except OSError:
                result_file = os.path.join(result_dir_or_file, "FinalEventCascade.json")

    if not os.path.exists(result_file):
        logging.error("Result file not found: %s", result_file)
        return None

    try:
        with open(result_file, "r", encoding="utf-8") as f:
            result_data = json.load(f)

        logging.info("Successfully loaded result from: %s", result_file)
        return result_data

    except Exception as e:
        logging.error("Error loading result file: %s", e)
        return None


def detect_build_mode(result_data: Dict[str, Any]) -> str:
    """
    Detect build mode from result data structure.

    Args:
        result_data: The loaded result dictionary

    Returns:
        Build mode string: "agent_build" or "class_build"
    """
    # Agent build typically has "stages" with nested structure
    if "stages" in result_data and isinstance(result_data["stages"], list):
        # Check if it has the agent build structure
        if result_data["stages"] and isinstance(result_data["stages"][0], dict):
            if "episodes" in result_data["stages"][0]:
                return "agent_build"

    # Default to class_build
    return "class_build"
