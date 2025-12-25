"""
Main entry point for FinMycelium web interface.
Refactored version with modular architecture.
"""

import streamlit as st
import traceback

from finmy.web_ui.state import SessionStateManager
from finmy.web_ui.components.sidebar import Sidebar
from finmy.web_ui.pages.home_page import HomePage
from finmy.web_ui.pages.pipeline_page import PipelinePage
from finmy.web_ui.pages.results_page import ResultsPage
from finmy.web_ui.pages.about_page import AboutPage


class FinMyceliumWebInterface:
    """
    Main web interface class for FinMycelium financial event reconstruction system.
    Refactored with modular architecture for better maintainability.
    """
    
    def __init__(self):
        """Initialize the web interface with configuration and state management."""
        self.setup_page_config()
        SessionStateManager.initialize()
    
    def setup_page_config(self):
        """Configure Streamlit page settings for optimal user experience."""
        st.set_page_config(
            page_title="FinMycelium - Financial Event Reconstruction System",
            page_icon="🕵️",
            layout="wide",
            initial_sidebar_state="expanded",
            menu_items={
                "Get Help": None,
                "Report a bug": None,
                "About": None,
            },
        )
    
    def run(self):
        """Main run method that handles routing and page rendering."""
        # Render sidebar
        Sidebar.render()
        
        # Get current page
        current_page = st.session_state.get("current_page", "Home")
        
        # Force Pipeline page if processing
        if st.session_state.get("processing_status") == "processing":
            current_page = "Pipeline"
            st.session_state.current_page = current_page
        
        # Route to appropriate page
        try:
            if current_page == "Home":
                HomePage.render()
            elif current_page == "Pipeline":
                PipelinePage.render()
            elif current_page == "Results":
                if st.session_state.get("processing_status") != "processing":
                    build_mode = st.session_state.get("build_mode")
                    if build_mode == "class_build" or build_mode is None:
                        ResultsPage.render()
                    elif build_mode == "agent_build":
                        ResultsPage.render()
                    else:
                        ResultsPage.render()
            elif current_page == "About":
                AboutPage.render()
        except Exception as e:
            traceback.print_exc()
            st.error(f"Error rendering page: {e}")
            st.info("Please refresh the page and try again.")


def main():
    """Main entry point for the FinMycelium web interface."""
    try:
        app = FinMyceliumWebInterface()
        app.run()
    except Exception as e:
        traceback.print_exc()
        st.error(f"Application error: {e}")
        st.info("Please refresh the page and try again.")


if __name__ == "__main__":
    main()

