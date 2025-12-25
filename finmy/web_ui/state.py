"""
Session state management for FinMycelium web interface.
"""

import streamlit as st
from typing import Optional, Dict, Any, List
import pandas as pd


class SessionStateManager:
    """Manages Streamlit session state variables."""
    
    @staticmethod
    def initialize():
        """Initialize all session state variables with default values."""
        defaults = {
            "analysis_results": None,
            "processing_status": "idle",
            "uploaded_files": [],
            "selected_event_type": None,
            "keywords": None,
            "config": None,
            "build_mode": None,
            "is_processing_blocked": False,
            "processing_start_time": None,
            "save_builder_dir_path": None,
            "estimate_time": None,
            "structured_data": None,
            "config_validated": False,
            "config_file_name": None,
            "main_input": "",
            "uploaded_file_name": None,
            "current_page": "Home",
            "should_redirect": False,
        }
        
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value
    
    @staticmethod
    def get(key: str, default: Any = None) -> Any:
        """Get a session state value."""
        return st.session_state.get(key, default)
    
    @staticmethod
    def set(key: str, value: Any):
        """Set a session state value."""
        st.session_state[key] = value
    
    @staticmethod
    def reset_processing():
        """Reset processing-related state."""
        st.session_state.processing_status = "idle"
        st.session_state.is_processing_blocked = False
        st.session_state.processing_start_time = None
    
    @staticmethod
    def reset_config():
        """Reset configuration-related state."""
        st.session_state.config_validated = False
        st.session_state.config = None
        st.session_state.config_file_name = None
        st.session_state.build_mode = None
    
    @staticmethod
    def reset_inputs():
        """Reset input-related state."""
        st.session_state.main_input = ""
        st.session_state.keywords = None
        st.session_state.structured_data = None
        st.session_state.uploaded_file_name = None
    
    @staticmethod
    def reset_all():
        """Reset all state (except current_page)."""
        SessionStateManager.reset_processing()
        SessionStateManager.reset_config()
        SessionStateManager.reset_inputs()
        st.session_state.analysis_results = None
        st.session_state.save_builder_dir_path = None
        st.session_state.estimate_time = None

