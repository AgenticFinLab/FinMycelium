"""
Results page renderer.
"""

import logging
import json
import os

import streamlit as st

from finmy.web_ui.styles import BASE_STYLES, CLASS_BUILD_STYLES
from finmy.web_ui.pages.results.agent_results import AgentResultsRenderer
from finmy.web_ui.pages.results.class_results import ClassResultsRenderer   


class ResultsPage:
    """Results page component."""

    @staticmethod
    def render():
        """Render the results page based on build mode."""

        # try:
        #     builder_dir_path = r"EXPERIMENT/uTEST/Pipline/build_output_20251226153040559838"
        #     with open(os.path.join(builder_dir_path, "FinalEventCascade.json"), "r", encoding="utf-8") as f:
        #          st.session_state.analysis_results = json.load(f)
        #     st.session_state.save_builder_dir_path = builder_dir_path
        # except:
        #     st.error("Error loading reconstruction results. Please check the pipeline output file.")

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
        logging.info(f"type of analysis_results: {type(st.session_state.analysis_results)}")
        AgentResultsRenderer.render(st.session_state.analysis_results)

    @staticmethod
    def _render_class_results():
        """Render class-based results."""
        st.markdown(CLASS_BUILD_STYLES, unsafe_allow_html=True)
        ClassResultsRenderer.render(st.session_state.analysis_results)
