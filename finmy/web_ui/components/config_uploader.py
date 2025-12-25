"""
Configuration file uploader component.
"""

import streamlit as st
import yaml
import traceback
import logging
from typing import Dict, Any, Optional, Tuple

from finmy.web_ui.utils.validators import validate_config


class ConfigUploader:
    """Component for uploading and validating configuration files."""
    
    @staticmethod
    def render() -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Render configuration upload section.
        
        Returns:
            Tuple of (is_validated, config_dict)
        """
        if "config_validated" not in st.session_state:
            st.session_state.config_validated = False
            st.session_state.config = None
        
        if not st.session_state.config_validated:
            st.title("Configuration Setup")
            st.markdown(
                "Please select and validate your configuration file before proceeding with reconstruction."
            )
            
            st.subheader("📁 Select Configuration File")
            config_file_path = st.file_uploader(
                "Upload YAML Configuration File",
                type=["yml", "yaml"],
                help="Select a valid YAML configuration file",
            )
            
            if config_file_path is not None:
                try:
                    config_content = config_file_path.read().decode("utf-8")
                    
                    st.subheader("📋 Configuration Preview")
                    with st.expander("View Configuration Details", expanded=True):
                        st.code(config_content, language="yaml")
                    
                    config_data = yaml.safe_load(config_content)
                    validation_passed, validation_errors = validate_config(config_data)
                    
                    if validation_passed:
                        st.success("✅ Configuration validation successful!")
                        
                        col1, col2, col3 = st.columns([1, 2, 1])
                        with col2:
                            if st.button(
                                "Confirm Configuration",
                                type="primary",
                                use_container_width=True,
                            ):
                                st.session_state.config = config_data
                                st.session_state.processing_status = "idle"
                                
                                # Determine build mode
                                builder_type = config_data["builder_config"]["builder_type"]
                                if builder_type == "AgentEventBuilder":
                                    st.session_state.build_mode = "agent_build"
                                elif builder_type == "ClassEventBuilder":
                                    st.session_state.build_mode = "class_build"
                                
                                st.session_state.config_validated = True
                                st.session_state.config_file_name = config_file_path.name
                                st.rerun()
                    else:
                        st.error("❌ Configuration validation failed:")
                        for error in validation_errors:
                            st.error(f"- {error}")
                        st.warning(
                            "Please upload a valid configuration file with all required sections."
                        )
                except Exception as e:
                    error_type = type(e).__name__
                    error_msg = str(e)
                    error_traceback = traceback.format_exc()
                    
                    logging.error("Error processing configuration file: %s: %s", error_type, error_msg)
                    logging.error("Traceback:\n%s", error_traceback)
                    traceback.print_exc()
                    
                    st.error(f"❌ Error processing configuration: {error_type}: {error_msg}")
                    st.info("Please ensure the file is properly formatted YAML.")
            
            if config_file_path is None:
                st.info("Please upload a configuration file to proceed.")
                st.stop()
                return False, None
        
        return st.session_state.config_validated, st.session_state.config

