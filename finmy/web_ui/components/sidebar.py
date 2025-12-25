"""
Sidebar component for navigation.
"""

import streamlit as st
from streamlit_option_menu import option_menu


class Sidebar:
    """Sidebar navigation component."""
    
    @staticmethod
    def render():
        """Render the sidebar with navigation and system information."""
        with st.sidebar:
            st.title("🕵️ FinMycelium")
            st.markdown("---")
            
            # Navigation menu
            menu_options = ["Home", "Pipeline", "Results", "About"]
            
            selected = option_menu(
                menu_title="Navigation",
                options=menu_options,
                icons=["house", "search", "bar-chart", "info-circle"],
                menu_icon="cast",
                default_index=0,
            )
            
            st.session_state.current_page = selected
            
            # Display warning if trying to navigate away during processing
            if st.session_state.get("processing_status") == "processing":
                st.warning(
                    "⚠️ Do not switch pages while Reconstruction is in progress. "
                    "Please refresh the webpage and try again now."
                )
                st.info(
                    "Navigation to other pages is temporarily disabled until processing completes."
                )
            
            st.markdown("---")
            st.caption("FinMycelium v1.0")
            st.caption("Copyright © 2025 AgenticFin Lab")

