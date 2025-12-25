"""
Results page renderer.
"""

import os
import json
import logging
import traceback
import streamlit as st

from finmy.builder.agent_build.visualizer_gantt import EventCascadeGanttVisualizer
from finmy.web_ui.styles import BASE_STYLES, CLASS_BUILD_STYLES

try:
    from finmy.web_ui.pages.results.agent_results import AgentResultsRenderer
    from finmy.web_ui.pages.results.class_results import ClassResultsRenderer
except ImportError as e:
    error_type = type(e).__name__
    error_msg = str(e)
    error_traceback = traceback.format_exc()

    logging.warning("Failed to import results renderers: %s: %s", error_type, error_msg)
    logging.warning("Traceback:\n%s", error_traceback)

    # Fallback if results renderers are not available
    AgentResultsRenderer = None
    ClassResultsRenderer = None


class ResultsPage:
    """Results page component."""

    @staticmethod
    def render():
        """Render the results page based on build mode."""
        if not st.session_state.analysis_results:
            st.info(
                "No reconstruction results available. Please run an analysis first."
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
        if AgentResultsRenderer:
            AgentResultsRenderer.render(st.session_state.analysis_results)
        else:
            st.error("Agent results renderer not available")

    @staticmethod
    def _render_class_results():
        """Render class-based results."""
        st.markdown(CLASS_BUILD_STYLES, unsafe_allow_html=True)
        if ClassResultsRenderer:
            ClassResultsRenderer.render(st.session_state.analysis_results)
        else:
            st.error("Class results renderer not available")
