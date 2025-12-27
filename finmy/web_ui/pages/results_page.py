"""
Results page renderer.
"""

import json
import logging
import os

import streamlit as st

from finmy.web_ui.styles import BASE_STYLES, CLASS_BUILD_STYLES
from finmy.web_ui.pages.results.agent_results import AgentResultsRenderer
from finmy.web_ui.pages.results.class_results import ClassResultsRenderer
from finmy.web_ui.utils.history_loader import (
    load_history_result,
    detect_build_mode,
)


class ResultsPage:
    """Results page component."""

    @staticmethod
    def render():
        """Render the results page based on build mode."""

        # Render history file selector
        ResultsPage._render_history_file_selector()

        if not st.session_state.analysis_results:
            st.info(
                "No reconstruction results available. Please run an analysis first or load a historical result."
            )
            if st.button("Go to Reconstruction"):
                st.session_state.current_page = "Pipeline"
                st.rerun()
            return

        build_mode = st.session_state.get("build_mode")

        if build_mode == "agent_build":
            ResultsPage._render_agent_results()
        elif build_mode == "class_build" or build_mode is None:
            ResultsPage._render_class_results()
        else:
            st.error(f"Unknown build mode: {build_mode}")

    @staticmethod
    def _render_agent_results():
        """Render agent-based results."""
        st.markdown(BASE_STYLES, unsafe_allow_html=True)
        logging.info(
            "type of analysis_results: %s", type(st.session_state.analysis_results)
        )
        AgentResultsRenderer.render(st.session_state.analysis_results)

    @staticmethod
    def _render_class_results():
        """Render class-based results."""
        st.markdown(CLASS_BUILD_STYLES, unsafe_allow_html=True)
        ClassResultsRenderer.render(st.session_state.analysis_results)

    @staticmethod
    def _render_history_file_selector():
        """Render file selector for loading historical results."""
        st.markdown("### 📁 Load Historical Results")

        result_file_path = st.text_input(
            "Enter result file path:",
            value=st.session_state.get("last_result_file_path", ""),
            key="result_file_path_input",
            help=(
                "Enter the full path to result file:\n"
                "- Agent Build: FinalEventCascade.json\n"
                "- Class Build: Class_Build_Event_Cascade_*.json\n"
                "Or enter the directory path containing the result file"
            ),
        )

        if st.button("📂 Load Result", key="load_from_path_btn"):
            if result_file_path:
                if os.path.exists(result_file_path):
                    # Check if it's a valid result file or directory
                    is_valid_file = result_file_path.endswith(".json") and (
                        "FinalEventCascade.json" in result_file_path
                        or "Class_Build_Event_Cascade_" in result_file_path
                    )
                    is_valid_dir = os.path.isdir(result_file_path)

                    if is_valid_file or is_valid_dir:
                        ResultsPage._load_history_result(result_file_path)
                        st.session_state.last_result_file_path = result_file_path
                        st.rerun()
                    else:
                        st.error(
                            "❌ Please provide a valid result file path or directory.\n"
                            "Supported files: FinalEventCascade.json or Class_Build_Event_Cascade_*.json"
                        )
                else:
                    st.error(f"❌ Path not found: {result_file_path}")
            else:
                st.warning("Please enter a file path.")

        st.markdown("---")

    @staticmethod
    def _load_history_result(result_path: str):
        """Load historical result from file path or directory."""
        try:
            result_data = load_history_result(result_path)

            if result_data:
                st.session_state.analysis_results = result_data

                # Set save_builder_dir_path to the directory containing the file
                if os.path.isfile(result_path):
                    st.session_state.save_builder_dir_path = os.path.dirname(
                        result_path
                    )
                else:
                    st.session_state.save_builder_dir_path = result_path

                # Detect build mode from result structure
                build_mode = detect_build_mode(result_data)
                st.session_state.build_mode = build_mode

                file_name = os.path.basename(result_path)
                if os.path.isdir(result_path):
                    # Find the actual file name
                    for item in os.listdir(result_path):
                        if item.endswith(".json") and (
                            "FinalEventCascade" in item
                            or "Class_Build_Event_Cascade_" in item
                        ):
                            file_name = item
                            break

                st.success(
                    f"✅ Successfully loaded result: {file_name} (Build Mode: {build_mode})"
                )
                logging.info(
                    "Loaded historical result from: %s, build_mode: %s",
                    result_path,
                    build_mode,
                )
            else:
                st.error(
                    "❌ Failed to load result. The file may be corrupted or invalid."
                )

        except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
            error_msg = str(e)
            logging.error("Error loading history result: %s", error_msg)
            st.error(f"❌ Error loading result: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            logging.error("Unexpected error loading history result: %s", error_msg)
            st.error(f"❌ Unexpected error: {error_msg}")
