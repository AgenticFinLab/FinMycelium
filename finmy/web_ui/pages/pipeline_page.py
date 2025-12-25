"""
Pipeline/analysis page renderer.
"""

import streamlit as st
import traceback
import datetime

from finmy.web_ui.components.config_uploader import ConfigUploader
from finmy.web_ui.components.input_forms import (
    KeywordInput,
    StructuredDataUpload,
    AnalysisControls,
)
from finmy.web_ui.utils.validators import validate_analysis_inputs
from finmy.web_ui.services.reconstruction_service import ReconstructionService
from finmy.web_ui.state import SessionStateManager
from finmy.web_ui.utils.formatters import format_timestamp


class PipelinePage:
    """Pipeline/analysis page component."""
    
    @staticmethod
    def render():
        """Render the analysis page with event type selection and data input options."""
        # Configuration validation
        config_validated, config = ConfigUploader.render()
        
        if not config_validated:
            return
        
        st.success(f"✅ Using configuration: {st.session_state.config_file_name}")
        
        # Display warning if processing is in progress
        if st.session_state.processing_status == "processing":
            st.warning(
                "⚠️ If reconstruction is in progress, please do not navigate away "
                "from the **Pipeline** page. During this process, clicking on other "
                "menu bars or pages is invalid. Once the processing is complete, you "
                "can click on the **Results** page to view the final results."
            )
            st.info(
                "🛑 You have moved to another page, please refresh the web page to retry."
            )
            
            progress_placeholder = st.empty()
            with progress_placeholder.container():
                st.spinner("🔄 Reconstruction in progress... Please wait.")
            
            st.session_state.is_processing_blocked = True
            return
        else:
            st.session_state.is_processing_blocked = False
        
        # Main input area
        prev_text = st.session_state.get("main_input", "")
        visible_lines = max(prev_text.count("\n") + 1, len(prev_text) // 60 + 1)
        dynamic_height = min(600, max(100, visible_lines * 24))
        
        main_input = st.text_area(
            "Event Description",
            value=prev_text,
            placeholder=(
                "Enter a detailed description of the event case, including key details, "
                "suspicious activities, involved parties, timeline, and any other relevant information..."
            ),
            height="content",
            key=f"main_input_{dynamic_height}",
            help="Provide a comprehensive description for better analysis results",
            disabled=st.session_state.is_processing_blocked,
        )
        
        st.session_state.main_input = main_input
        
        # Input method selection
        input_methods = st.multiselect(
            "Select Additional Input Methods",
            options=["Keywords", "Structured Data"],
            default=["Keywords", "Structured Data"],
            help="Supplement your case description with additional data",
            disabled=st.session_state.is_processing_blocked,
        )
        
        # Keyword input
        if "Keywords" in input_methods:
            KeywordInput.render()
        
        # Structured data upload
        if "Structured Data" in input_methods:
            StructuredDataUpload.render()
        
        st.markdown("---")
        
        # Analysis controls
        should_start = AnalysisControls.render(validate_analysis_inputs)
        
        if should_start:
            PipelinePage._run_analysis()
        
        # Option to reset configuration
        if st.button(
            "Reset Configuration",
            type="secondary",
            disabled=st.session_state.is_processing_blocked,
        ):
            SessionStateManager.reset_config()
            st.rerun()
    
    @staticmethod
    def _run_analysis():
        """Execute the event reconstruction pipeline."""
        # Check if results already exist
        if (
            hasattr(st.session_state, "analysis_results")
            and st.session_state.processing_status == "completed"
        ):
            st.info("Reconstruction already completed. Redirecting to results...")
            st.session_state.current_page = "Results"
            st.rerun()
            return
        
        # Check if processing is already in progress
        if (
            hasattr(st.session_state, "processing_status")
            and st.session_state.processing_status == "processing"
        ):
            st.warning("Reconstruction is already in progress. Please wait...")
            return
        
        # Set processing state
        st.session_state.processing_status = "processing"
        st.session_state.processing_start_time = datetime.datetime.now()
        st.session_state.is_processing_blocked = True
        
        try:
            # Prepare input data
            analysis_inputs = {
                "main_input": st.session_state.get("main_input", ""),
                "keywords": st.session_state.get("keywords", []),
                "structured_data": st.session_state.get("structured_data", None),
            }
            
            # Validate inputs
            if not analysis_inputs["main_input"]:
                st.error("Main input is required")
                st.session_state.processing_status = "error"
                st.session_state.is_processing_blocked = False
                return
            
            # Execute reconstruction
            with st.spinner(
                "🔄 Reconstruction in progress... Please do not navigate away from the "
                "**Pipeline** page. During this process, clicking on other menu bars "
                "or pages is invalid. Once the processing is complete, you can click "
                "on the **Results** page to view the final results."
            ):
                st.write(f"**{format_timestamp()}** - Starting reconstruction...")
                
                # Run reconstruction service
                reconstruction_service = ReconstructionService(st.session_state.config)
                results = reconstruction_service.run_reconstruction(
                    main_input=analysis_inputs["main_input"],
                    keywords=analysis_inputs["keywords"],
                    structured_data=analysis_inputs["structured_data"],
                )
                
                if results:
                    st.session_state.analysis_results = results
                    st.write(f"**{format_timestamp()}** - Reconstruction completed.")
                    st.session_state.processing_status = "completed"
                    st.session_state.is_processing_blocked = False
                    st.session_state.should_redirect = True
                else:
                    st.error("❌ Reconstruction failed. No results returned.")
                    st.session_state.processing_status = "error"
        
        except Exception as e:
            traceback.print_exc()
            st.error(f"❌ Reconstruction failed: {str(e)}")
            st.session_state.processing_status = "error"
        
        finally:
            st.session_state.is_processing_blocked = False
            
            # Execute redirect if flag is set
            if st.session_state.get("should_redirect", False):
                st.session_state.current_page = "Results"
                st.session_state.should_redirect = False
                st.rerun()

