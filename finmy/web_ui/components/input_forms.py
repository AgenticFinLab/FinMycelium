"""
Input form components for data collection.
"""

import streamlit as st
import pandas as pd
import traceback
from typing import Optional

from finmy.web_ui.utils.validators import parse_keywords


class KeywordInput:
    """Keyword input component."""
    
    @staticmethod
    def render():
        """Render keyword input section."""
        if st.session_state.keywords is not None:
            keywords = st.text_area(
                "Enter relevant keywords or phrases (comma-separated):",
                placeholder=",".join(st.session_state.keywords),
                help="Provide specific terms related to the event case to enhance analysis",
                disabled=st.session_state.is_processing_blocked,
            )
        else:
            keywords = st.text_area(
                "Enter relevant keywords or phrases (comma-separated):",
                placeholder=(
                    "e.g., high-yield investment, guaranteed returns, "
                    "crypto mining scheme, company name, individual names..."
                ),
                help="Provide specific terms related to the event case to enhance analysis",
                disabled=st.session_state.is_processing_blocked,
            )
        
        if keywords:
            st.session_state.keywords = parse_keywords(keywords)


class StructuredDataUpload:
    """Structured data upload component."""
    
    @staticmethod
    def render():
        """Render structured data upload section."""
        if (
            hasattr(st.session_state, "structured_data")
            and st.session_state.structured_data is not None
        ):
            st.info(
                f"📁 File '{st.session_state.uploaded_file_name}' is already uploaded. "
                "Clear existing data to upload a new file."
            )
            
            if st.button(
                "Clear Uploaded Data", disabled=st.session_state.is_processing_blocked
            ):
                st.session_state.structured_data = None
                st.session_state.uploaded_file_name = None
                st.rerun()
            
            st.markdown("First 5 rows of data:")
            st.dataframe(st.session_state.structured_data.head(), width="stretch")
            return
        
        uploaded_file = st.file_uploader(
            "Upload Excel, CSV, or JSON file:",
            type=["xlsx", "csv", "json"],
            help=(
                "Upload structured data files to enhance analysis. "
                "Only one file can be uploaded at a time."
            ),
            disabled=st.session_state.is_processing_blocked,
        )
        
        if uploaded_file:
            try:
                df = StructuredDataUpload._load_file(uploaded_file)
                
                # Validate required columns
                required_columns = ["title", "url"]
                missing_columns = [
                    col for col in required_columns if col not in df.columns
                ]
                
                if missing_columns:
                    st.error(
                        f"❌ Upload failed: The file must contain the following columns: "
                        f"{', '.join(missing_columns)}"
                    )
                    st.info("Please ensure your data includes 'title' and 'url' columns.")
                    return
                
                st.success("✅ File uploaded successfully")
                st.dataframe(df.head(), width="stretch")
                
                st.session_state.structured_data = df
                st.session_state.uploaded_file_name = uploaded_file.name
            except Exception as e:
                traceback.print_exc()
                st.error(f"Error processing file: {e}")
    
    @staticmethod
    def _load_file(uploaded_file) -> pd.DataFrame:
        """Load file based on extension."""
        if uploaded_file.name.endswith(".csv"):
            try:
                return pd.read_csv(uploaded_file, encoding="utf-8")
            except:
                try:
                    return pd.read_csv(uploaded_file, encoding="latin-1")
                except:
                    return pd.read_csv(uploaded_file, encoding="gbk")
        elif uploaded_file.name.endswith(".xlsx"):
            return pd.read_excel(uploaded_file)
        elif uploaded_file.name.endswith(".json"):
            return pd.read_json(uploaded_file)
        else:
            raise ValueError(f"Unsupported file type: {uploaded_file.name}")


class AnalysisControls:
    """Analysis control buttons component."""
    
    @staticmethod
    def render(validate_fn):
        """
        Render analysis control buttons.
        
        Args:
            validate_fn: Function to validate inputs before starting analysis
        """
        if st.button(
            "🚀 Start Reconstructing",
            type="primary",
            width="stretch",
            disabled=st.session_state.is_processing_blocked,
        ):
            if validate_fn():
                st.session_state.analysis_results = None
                st.session_state.is_processing_blocked = True
                return True
            else:
                st.error("Please provide required inputs before starting analysis")
        
        # Status indicator
        if st.session_state.processing_status != "idle":
            AnalysisControls._render_status()
        
        return False
    
    @staticmethod
    def _render_status():
        """Render processing status indicator."""
        status_placeholder = st.empty()
        with status_placeholder.container():
            if st.session_state.processing_status == "processing":
                st.info("🔄 Reconstruction in progress... This may take a few minutes.")
            elif st.session_state.processing_status == "completed":
                st.success(
                    "✅ Reconstruction completed! Please navigate to the **Results** "
                    "page to view the analysis."
                )
            elif st.session_state.processing_status == "error":
                st.error("❌ Reconstruction failed. Please try again.")

