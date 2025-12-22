"""
Web interface for FinMycelium - Financial Event Reconstruction System.
Provides a user-friendly interface for reconstructing financial events 
through multiple data sources and AI-powered analysis.
"""

import os
import re
import sys
import json
import yaml
import logging
import datetime
import traceback
from pathlib import Path
from typing import List, Dict, Any, Optional

import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from dotenv import load_dotenv
from loguru import logger
from streamlit_option_menu import option_menu

from lmbase.inference.api_call import LangChainAPIInference, InferInput
from finmy.url_collector.SearchCollector.bocha_search import bochasearch_api
from finmy.url_collector.SearchCollector.baidu_search import baidusearch_api
from finmy.url_collector.MediaCollector.platform_crawler import PlatformCrawler
from finmy.url_collector.base import URLCollectorInput
from finmy.url_collector.url_parser import URLParser
from finmy.pdf_collector.pdf_collector import PDFCollector
from finmy.pdf_collector.base import PDFCollectorInput, PDFCollectorOutput
from finmy.url_collector.url_parser_clean import extract_content_from_parsed_content
from finmy.builder.class_build.prompts.ponzi_scheme import ponzi_scheme_prompt
from finmy.builder.class_build.main_build import ClassEventBuilder
from finmy.builder.agent_build.visualizer import EventCascadeVisualizer
from finmy.pipeline import FinmyPipeline


# Load environment variables
load_dotenv()

# Import project modules with fallbacks
try:
    from db_manager import PDDataBaseManager
except ImportError:
    PDDataBaseManager = None

try:
    from generic import UserQueryInput, RawData, MetaSample, DataSample
except ImportError:
    pass  # Silently ignore if module not available


class FinMyceliumWebInterface:
    """
    Main web interface class for FinMycelium financial event reconstruction system.
    Handles user interactions, data processing, and result visualization.
    """

    def __init__(self):
        """Initialize the web interface with configuration and state management."""
        self.setup_page_config()
        self.initialize_session_state()

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
        
        # Hide default Streamlit UI elements
        hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            .stDeployButton {display: none;}
            </style>
        """
        st.markdown(hide_st_style, unsafe_allow_html=True)

    def initialize_session_state(self):
        """Initialize session state variables for maintaining state across interactions."""
        # Core analysis state
        if "save_dir" not in st.session_state:
            st.session_state.save_dir = None
        if "analysis_results" not in st.session_state:
            st.session_state.analysis_results = None
        if "processing_status" not in st.session_state:
            st.session_state.processing_status = "idle"
        if "should_redirect" not in st.session_state:
            st.session_state.should_redirect = False
            
        # Configuration state
        if "config_validated" not in st.session_state:
            st.session_state.config_validated = False
        if "config" not in st.session_state:
            st.session_state.config = None
        if "config_file_name" not in st.session_state:
            st.session_state.config_file_name = None
        if "build_mode" not in st.session_state:
            st.session_state.build_mode = None
            
        # Input data state
        if "main_input" not in st.session_state:
            st.session_state.main_input = ""
        if "keywords" not in st.session_state:
            st.session_state.keywords = None
        if "structured_data" not in st.session_state:
            st.session_state.structured_data = None
        if "uploaded_file_name" not in st.session_state:
            st.session_state.uploaded_file_name = None
            
        # Navigation state
        if "current_page" not in st.session_state:
            st.session_state.current_page = "Home"

    def render_sidebar(self):
        """Render the sidebar with navigation and system information."""
        with st.sidebar:
            st.title("🕵️ FinMycelium")
            st.markdown("---")

            # Navigation menu
            selected = option_menu(
                menu_title="Navigation",
                options=["Home", "Pipeline", "Results", "About"],
                icons=["house", "search", "bar-chart", "info-circle"],
                menu_icon="cast",
                default_index=0,
            )

            st.session_state.current_page = selected

            st.markdown("---")
            st.caption("FinMycelium v1.0")
            st.caption("Copyright © 2025 AgenticFin Lab")

    def render_home_page(self):
        """Render the home page with system overview and quick start options."""
        st.title("Welcome to FinMycelium")
        st.markdown(
            """
            ### Comprehensive Financial Event Reconstruction Platform
            
            FinMycelium helps you analyze and understand financial event schemes 
            through advanced AI-powered analysis of multiple data sources.
            """
        )

        # Features overview
        col1, col2, col3 = st.columns(3)

        with col1:
            st.subheader("🔍 Multi-Source Analysis")
            st.markdown(
                """
                - Web content collection
                - Document processing (PDF/Word)
                - Social media monitoring
                - Structured data analysis
                """
            )

        with col2:
            st.subheader("🤖 AI-Powered Insights")
            st.markdown(
                """
                - Event type recognition
                - Timeline reconstruction
                - Impact assessment
                - Educational insights
                """
            )

        with col3:
            st.subheader("📊 Comprehensive Reporting")
            st.markdown(
                """
                - Visual analytics
                - Key findings summary
                - Risk assessment
                - Prevention recommendations
                """
            )

        st.markdown("---")

        # Quick start section
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            st.subheader("Get Started")
            st.markdown(
                """
                **Start your analysis in 3 simple steps:**
                1. **Input** the event related information you want to analyze
                2. **Provide** data through keywords or structured file
                3. **Analyze** with our AI-powered event reconstruction system
                """
            )

    def render_analysis_page(self):
        """
        Render the analysis page with event type selection and data input options.
        Includes configuration file validation before proceeding to analysis inputs.
        """
        
        # Display configuration section if not yet validated
        if not st.session_state.config_validated:
            self.render_configuration_section()
            return  # Stop here until configuration is validated
        
        # Only proceed to analysis inputs after configuration is validated
        st.success(f"✅ Using configuration: {st.session_state.config_file_name}")
        
        # Display the main analysis interface
        prev_text = st.session_state.get("main_input", "")
        visible_lines = max(prev_text.count("\n") + 1, len(prev_text) // 60 + 1)
        dynamic_height = min(600, max(100, visible_lines * 24))
        
        main_input = st.text_area(
            "Event Description",
            value=prev_text,
            placeholder="Enter a detailed description of the event case, including key details, suspicious activities, involved parties, timeline, and any other relevant information...",
            height="content",
            key=f"main_input_{dynamic_height}",
            help="Provide a comprehensive description for better analysis results",
        )
        
        st.session_state.main_input = main_input
        
        # Input method selection
        input_methods = st.multiselect(
            "Select Additional Input Methods",
            options=["Keywords", "Structured Data"],
            default=["Keywords", "Structured Data"],
            help="Supplement your case description with additional data",
        )
        
        # Keyword input
        if "Keywords" in input_methods:
            self.render_keyword_input()
        
        # Structured data upload
        if "Structured Data" in input_methods:
            self.render_structured_data_upload()
        
        st.markdown("---")
        
        # Analysis controls
        self.render_analysis_controls()
        
        # Option to reset configuration
        if st.button("Reset Configuration", type="secondary"):
            self.reset_configuration()

    def render_configuration_section(self):
        """Render configuration file upload and validation section."""
        st.title("Configuration Setup")
        st.markdown("Please select and validate your configuration file before proceeding with reconstruction.")
        
        # Configuration file selection
        st.subheader("📁 Select Configuration File")
        config_file_path = st.file_uploader(
            "Upload YAML Configuration File",
            type=["yml", "yaml"],
            help="Select a valid YAML configuration file"
        )
        
        # Configuration display and validation
        if config_file_path is not None:
            try:
                # Read and parse YAML configuration
                config_content = config_file_path.read().decode("utf-8")
                
                # Display configuration for user review
                st.subheader("📋 Configuration Preview")
                with st.expander("View Configuration Details", expanded=True):
                    st.code(config_content, language="yaml")
                
                # Parse and validate configuration
                config_data = yaml.safe_load(config_content)
                
                # Basic validation checks
                validation_passed = True
                validation_errors = []
                
                # Check for required sections
                required_sections = ["lm_type", "lm_name", "inference_config", "generation_config", 
                                     "db_config", "output_dir", "url_collector_config", "pdf_collector_config", 
                                     "summarizer_config", "matcher_config", "builder_config"]
                
                for section in required_sections:
                    if section not in config_data:
                        validation_passed = False
                        validation_errors.append(f"Missing required section: {section}")

                if "lm_name" in config_data:
                    if not isinstance(config_data["lm_name"], str):
                        validation_passed = False
                        validation_errors.append("lm_name must be a string")
                
                # Display validation results
                if validation_passed:
                    st.success("✅ Configuration validation successful!")
                    
                    # User confirmation
                    col1, col2, col3 = st.columns([1, 2, 1])
                    with col2:
                        if st.button("Confirm Configuration", type="primary", use_container_width=True):
                            # Store validated configuration in session state
                            st.session_state.config = config_data
                            
                            # Determine build mode
                            builder_type = config_data.get("builder_config", {}).get("builder_type", "")
                            if builder_type == "AgentEventBuilder":
                                st.session_state.build_mode = "agent_build"
                            elif builder_type == "ClassEventBuilder":
                                st.session_state.build_mode = "class_build"
                            else:
                                st.session_state.build_mode = "class_build"  # Default
                            
                            st.session_state.config_validated = True
                            st.session_state.config_file_name = config_file_path.name
                            
                            # Clear file uploader and reload page
                            st.rerun()
                else:
                    st.error("❌ Configuration validation failed:")
                    for error in validation_errors:
                        st.error(f"- {error}")
                    
                    st.warning("Please upload a valid configuration file with all required sections.")
                    
            except yaml.YAMLError as e:
                st.error(f"❌ Invalid YAML format: {str(e)}")
                st.info("Please check your YAML syntax and try again.")
            except Exception as e:
                st.error(f"❌ Error processing configuration: {str(e)}")
                st.info("Please ensure the file is properly formatted.")
        
        # Exit if no configuration is selected
        if config_file_path is None:
            st.info("Please upload a configuration file to proceed.")
            st.stop()

    def render_keyword_input(self):
        """Render keyword input section with validation and suggestions."""
        if st.session_state.keywords is not None:
            keywords = st.text_area(
                "Enter relevant keywords or phrases (comma-separated):",
                placeholder=",".join(st.session_state.keywords),
                help="Provide specific terms related to the event case to enhance analysis",
            ) 
        else:
            keywords = st.text_area(
                "Enter relevant keywords or phrases (comma-separated):",
                placeholder="e.g., high-yield investment, guaranteed returns, crypto mining scheme, company name, individual names...",
                help="Provide specific terms related to the event case to enhance analysis",
            )

        # Process keyword input with flexible delimiter handling
        if keywords:  
            # Normalize full-width Chinese commas to standard commas
            unified_keywords = keywords.replace('，', ',').replace(";",",").replace("；","")
            
            # Split on commas/spaces (supports multiple consecutive delimiters)
            keyword_list = re.split(r'[,|\s]+', unified_keywords)
            
            # Clean up keywords (strip whitespace + remove empty strings)
            st.session_state.keywords = [
                k.strip() for k in keyword_list if k.strip()
            ]

    def render_structured_data_upload(self):
        """Render structured data upload with format validation."""
        # Check if a file is already uploaded
        if (
            hasattr(st.session_state, "structured_data")
            and st.session_state.structured_data is not None
        ):
            st.info(
                f"📁 File '{st.session_state.uploaded_file_name}' is already uploaded. Clear existing data to upload a new file."
            )

            if st.button("Clear Uploaded Data"):
                st.session_state.structured_data = None
                st.session_state.uploaded_file_name = None
                st.rerun()
            st.markdown("First 5 rows of data:")
            st.dataframe(st.session_state.structured_data.head(), width="stretch")
            return

        uploaded_file = st.file_uploader(
            "Upload Excel, CSV, or JSON file:",
            type=["xlsx", "csv", "json"],
            help="Upload structured data files to enhance analysis. Only one file can be uploaded at a time.",
        )

        if uploaded_file:
            try:
                if uploaded_file.name.endswith(".csv"):
                    try:
                        df = pd.read_csv(uploaded_file, encoding="utf-8")
                    except:
                        try:
                            df = pd.read_csv(uploaded_file, encoding="latin-1")
                        except:
                            df = pd.read_csv(uploaded_file, encoding="gbk")
                elif uploaded_file.name.endswith(".xlsx"):
                    df = pd.read_excel(uploaded_file)
                elif uploaded_file.name.endswith(".json"):
                    df = pd.read_json(uploaded_file)

                # Validate required columns
                required_columns = ["title", "url"]
                missing_columns = [
                    col for col in required_columns if col not in df.columns
                ]

                if missing_columns:
                    st.error(
                        f"❌ Upload failed: The file must contain the following columns: {', '.join(missing_columns)}"
                    )
                    st.info(
                        "Please ensure your data includes 'title' and 'url' columns."
                    )
                    return

                st.success("✅ File uploaded successfully")
                st.dataframe(df.head(), width="stretch")

                st.session_state.structured_data = df
                st.session_state.uploaded_file_name = uploaded_file.name

            except Exception as e:
                st.error(f"Error processing file: {e}")

    def render_analysis_controls(self):
        """Render analysis control buttons and status indicators."""
        if st.button("🚀 Start Reconstructing", type="primary", width="stretch"):
            if self.validate_analysis_inputs():
                # Clear previous results and start processing
                st.session_state.analysis_results = None
                self.run_analysis()
            else:
                st.error("Please provide required inputs before starting analysis")

        # Status indicator
        if st.session_state.processing_status != "idle":
            status_placeholder = st.empty()
            with status_placeholder.container():
                if st.session_state.processing_status == "processing":
                    st.info("🔄 Reconstruction in progress... This may take a few minutes.")
                elif st.session_state.processing_status == "completed":
                    st.success("✅ Reconstruction completed!")
                elif st.session_state.processing_status == "error":
                    st.error("❌ Reconstruction failed. Please try again.")

    def validate_analysis_inputs(self) -> bool:
        """Validate that required inputs are provided for analysis."""
        has_natural_language = (
            hasattr(st.session_state, "main_input") and st.session_state.main_input
        )
        has_keywords = (
            hasattr(st.session_state, "keywords") and st.session_state.keywords
        )
        has_structured_data = (
            hasattr(st.session_state, "structured_data")
            and st.session_state.structured_data is not None
        )

        if not has_natural_language and not has_keywords and not has_structured_data:
            st.error(
                "Please provide at least one data source for analysis (natural language description, keywords, or structured data file)"
            )
            return False

        return True

    def reset_configuration(self):
        """Reset configuration and clear related session state."""
        st.session_state.config_validated = False
        st.session_state.config = None
        st.session_state.config_file_name = None
        st.session_state.build_mode = None
        st.rerun()

    def run_analysis(self):
        """Execute the event reconstruction pipeline with provided inputs."""
        # Check if processing is already in progress
        if hasattr(st.session_state, 'processing_status') and st.session_state.processing_status == "processing":
            st.warning("Reconstruction is already in progress. Please wait...")
            return
        
        # Check if configuration is available (critical check)
        if not st.session_state.config:
            st.error("Configuration is missing. Please reset and reconfigure.")
            st.session_state.processing_status = "error"
            return
        
        # Set processing status
        st.session_state.processing_status = "processing"
        
        try:
            # Use st.spinner for progress indication
            with st.spinner("🔄 Reconstruction in progress... This may take a few minutes."):
                # Prepare input data
                analysis_inputs = {
                    "main_input": st.session_state.get("main_input", ""),
                    "keywords": st.session_state.get("keywords", []),
                    "structured_data": st.session_state.get("structured_data", None),
                }
                
                # Add input validation
                if not analysis_inputs["main_input"]:
                    st.error("Main input is required")
                    st.session_state.processing_status = "error"
                    return
                
                # Execute reconstruction
                results = self.perform_ai_analysis(analysis_inputs)
                
                if results:
                    # Store results
                    st.session_state.analysis_results = results
                    st.session_state.processing_status = "completed"
                    
                    # Set flag for page navigation
                    st.session_state.should_redirect = True
                else:
                    st.error("❌ Reconstruction failed. No results returned.")
                    st.session_state.processing_status = "error"
                    
        except Exception as e:
            st.error(f"❌ Reconstruction failed: {str(e)}")
            st.session_state.processing_status = "error"
            
        finally:
            # Execute redirect if flag is set
            if st.session_state.get('should_redirect', False):
                st.session_state.current_page = "Results"
                # Clear the flag
                st.session_state.should_redirect = False
                st.rerun()

    def perform_ai_analysis(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform AI-powered event reconstruction using the provided inputs.

        Args:
            inputs: Dictionary containing natural language description and data sources

        Returns:
            Dictionary containing analysis results
        """
        try:
            # Construct analysis prompt
            results = self.event_reconstruction(inputs)
            return results
        except Exception as e:
            st.error(f"AI analysis error: {e}")
            return None

    def event_reconstruction(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the complete event reconstruction pipeline."""
        main_search_input = inputs["main_input"]
        keywords = inputs["keywords"]
        search_query_content = main_search_input + " \n\nkeywords: " + " ".join(keywords)

        # Initialize URL parser
        parser = URLParser(delay=2.0, use_selenium_fallback=True, selenium_wait_time=5)
  
        pipeline_output = f"pipeline_output_{datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        save_dir = os.path.join(st.session_state.config["output_dir"],pipeline_output)
        st.session_state.save_dir = save_dir

        os.makedirs(save_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

        # Collect data from various sources
        all_text_content = []
        
        # 1. Bocha Search results
        try:
            logging.info("Collecting data from Bocha Search...")
            bocha_search_results = bochasearch_api(
                search_query_content, summary=True, count=10
            )
            
            formatted_bocha_search_results_content = []
            for item in bocha_search_results["data"]["webPages"]["value"]:
                formatted_item = {
                    "title": item["name"],
                    "url": item["url"],
                    "search_query_content": search_query_content,
                    "keywords": ",".join(keywords),
                    "snippet": item["snippet"],
                    "content": item["summary"],
                    "sitename": item["siteName"],
                    "datepublished": item["datePublished"],
                }
                
                # Parse URL content
                collector_input = URLCollectorInput(urls=[item["url"]])
                output = parser.run(collector_input)
                formatted_item["parsed_content"] = (
                    output.results[0]["content"] if output.results and len(output.results) > 0 else []
                )
                
                # Format content for analysis
                item_content = ""
                item_content += "Title:\n"
                item_content += item["name"] + "\n\n"
                item_content += "Sitename:\n"
                item_content += item["siteName"] + "\n\n"
                item_content += "Content:\n"
                item_content += item["summary"] + "\n\n\n"
                item_content += "Parsed Content:\n"
                item_content += extract_content_from_parsed_content(formatted_item["parsed_content"]) + "\n\n\n"
                
                formatted_bocha_search_results_content.append(item_content)

            # Save results
            filepath = os.path.join(
                save_dir, f"formatted_bocha_search_results_{timestamp}.json"
            )
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(
                    bocha_search_results, f, ensure_ascii=False, indent=4
                )
                
            all_text_content.extend(formatted_bocha_search_results_content)
            
        except Exception as e:
            logging.error(f"Bocha Search error: {e}")

        # 2. Baidu Search results
        try:
            logging.info("Collecting data from Baidu Search...")
            baidu_search_results = baidusearch_api(search_query_content)
            formatted_baidu_search_results_content = []
            
            if "references" in baidu_search_results:
                for item in baidu_search_results["references"]:
                    formatted_item = {
                        "title": item["title"],
                        "url": item["url"],
                        "search_query_content": search_query_content,
                        "keywords": ",".join(keywords),
                        "snippet": item["snippet"],
                        "content": item["content"],
                        "sitename": item["website"],
                        "datepublished": item["date"],
                    }

                    # Parse URL content
                    collector_input = URLCollectorInput(urls=[item["url"]])
                    output = parser.run(collector_input)
                    formatted_item["parsed_content"] = (
                        output.results[0]["content"] if output.results and len(output.results) > 0 else []
                    )

                    # Format content for analysis
                    item_content = ""
                    item_content += "Title:\n"
                    item_content += item["title"] + "\n\n"
                    item_content += "Sitename:\n"
                    item_content += item["website"] + "\n\n"
                    item_content += "Content:\n"
                    item_content += item["content"] + "\n\n\n"
                    item_content += "Parsed Content:\n"
                    item_content += extract_content_from_parsed_content(formatted_item["parsed_content"]) + "\n\n\n"
                    
                    formatted_baidu_search_results_content.append(item_content)

            # Save results
            filepath = os.path.join(
                save_dir, f"formatted_baidu_search_results_{timestamp}.json"
            )
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(
                    baidu_search_results, f, ensure_ascii=False, indent=4
                )
                
            all_text_content.extend(formatted_baidu_search_results_content)
            
        except Exception as e:
            logging.error(f"Baidu Search error: {e}")

        # 3. Process structured data
        try:
            if st.session_state.structured_data is not None:
                logging.info("Processing structured data...")
                structure_data_urllink_content = []
                structure_data_filepath_content = []
                
                for index, row in st.session_state.structured_data.iterrows():
                    try:
                        title = row["title"] if row["title"] else "No Title"
                        url = row["url"] if row["url"] else "No URL"
                        
                        if isinstance(url, str):
                            if url.startswith(("http://", "https://", "www.")):
                                # Process web URL
                                collector_input = URLCollectorInput(urls=[url])
                                output = parser.run(collector_input)
                                row_dict = row.to_dict()
                                row_dict["parsed_content"] = (
                                    output.results[0]["content"] if output.results and len(output.results) > 0 else []
                                )
                                
                                # Format content
                                item_content = ""
                                item_content += "title:\n"
                                item_content += title + "\n\n"
                                item_content += "content:\n"
                                item_content += extract_content_from_parsed_content(row_dict["parsed_content"])
                                structure_data_urllink_content.append(item_content)
                                
                            else:
                                # Process local PDF file
                                if os.path.exists(url) and url.lower().endswith(".pdf"):
                                    config = st.session_state.config["pdf_collector_config"]
                                    pdf_collector_input = PDFCollectorInput(
                                        input_pdf_path=url,
                                        keywords=keywords,
                                    )
                                    
                                    parser_instance = PDFCollector(config)
                                    collect_results = parser_instance.collect(pdf_collector_input)
                                    filter_results = parser_instance.filter(pdf_collector_input, collect_results)
                                    
                                    # Format content
                                    item_content = ""
                                    if collect_results.records and collect_results.records[0]:
                                        record = collect_results.records[0]
                                        if hasattr(record, 'Location') and record.Location:
                                            try:
                                                with open(record.Location, "r", encoding="utf-8") as f:
                                                    item_content += "title:\n"
                                                    item_content += title + "\n\n"
                                                    item_content += "content:\n"
                                                    item_content += f.read()
                                                structure_data_filepath_content.append(item_content)
                                            except Exception as e:
                                                logging.error(f"Error reading PDF content: {e}")
                    except Exception as e:
                        logging.error(f"Error processing structured data row {index}: {e}")
                
                all_text_content.extend(structure_data_urllink_content)
                all_text_content.extend(structure_data_filepath_content)
                
        except Exception as e:
            logging.error(f"Structured data processing error: {e}")

        # 4. Run the reconstruction pipeline
        try:
            logging.info("Running reconstruction pipeline...")
            
            # Limit content size to avoid token limits
            all_text_content_limit = []
            total_chars = 0
            max_chars = 100000  # Limit to 100k characters
            
            for item in all_text_content:
                item_chars = len(item)
                if total_chars + item_chars <= max_chars:
                    all_text_content_limit.append(item)
                    total_chars += item_chars
                else:
                    break
            
            logging.info(f"Processing {len(all_text_content_limit)} items ({total_chars} characters)")
            
            # Initialize and run pipeline
            pipeline = FinmyPipeline(st.session_state.config)
            pipeline_result = pipeline.lm_build_pipeline_with_contents(
                contents=all_text_content_limit,
                query_text=main_search_input,
                key_words=keywords,
            )
            
            # Save all collected content for debugging
            all_text_content_filepath = os.path.join(
                save_dir, f"All_Text_Content_{timestamp}.json"
            )
            with open(all_text_content_filepath, "w", encoding="utf-8") as f:
                json.dump(all_text_content_limit, f, ensure_ascii=False, indent=4)
            
            # Process pipeline result
            if pipeline_result:
                if isinstance(pipeline_result, dict):
                    return pipeline_result
                elif hasattr(pipeline_result, 'result'):
                    return pipeline_result.result
                else:
                    logging.warning(f"Unexpected pipeline_result type: {type(pipeline_result)}")
                    return pipeline_result
            else:
                logging.error("Pipeline returned no results")
                return None
                
        except Exception as e:
            logging.error(f"Pipeline execution error: {e}")
            traceback.print_exc()
            return None

    def render_results_page_agent(self):
        """Render the agent-based event reconstruction results with timeline visualization."""
        st.title("📋 Event Reconstruction Report")
        
        # try:
        #     with open(r"EXPERIMENT\xxxxxxxx\FinalEventCascade.json", "r", encoding="utf-8") as f:
        #         st.session_state.analysis_results = json.load(f)
        # except:
        #     st.error("Error loading reconstruction results. Please check the pipeline output file.")

        # Check for empty results
        if not st.session_state.analysis_results:
            st.info("No reconstruction results available. Please run an analysis first.")
            if st.button("Go to Reconstruction"):
                st.session_state.current_page = "Pipeline"
                st.rerun()
            return
        
        results = st.session_state.analysis_results
        
        # Generate timeline visualization
        try:
            logging.info("Generating timeline visualization...")
            viz = EventCascadeVisualizer()
            viz_output_path = os.path.join(st.session_state.save_dir, "timeline.png")
            viz.plot_cascade(results, viz_output_path)
            
            if os.path.exists(viz_output_path):
                st.image(viz_output_path, caption="Event Timeline Visualization")
            else:
                st.warning("Timeline visualization could not be generated.")
        except Exception as e:
            logging.error(f"Timeline generation error: {e}")
            st.warning("Could not generate timeline visualization.")

        # Main container with custom styling
        with st.container():
            # Reconstruction Overview
            col1, col2 = st.columns([3, 1])
            
            with col1:
                event_title = results.get("title", {}).get("value", "Event Reconstruction")
                st.markdown(
                    f'<div class="reconstruction-header"><h2>{event_title} Complete</h2></div>',
                    unsafe_allow_html=True
                )
            
            with col2:
                st.metric("Event ID", results.get("event_id", "N/A"), delta=None)
                st.metric("Event Type", results.get("event_type", {}).get("value", "N/A"), delta=None)
                if results.get("is_mock_data"):
                    st.warning("Using demonstration data")
            
            # Event Basic Information
            st.subheader("☀️ Event Basic Information")
            with st.expander("Event Basic Information", expanded=False):
                # Event Title
                st.markdown("<h4>Event Title</h4>", unsafe_allow_html=True)
                st.markdown(f'<div class="data-field"><span class="field-label">Value:</span> {results.get("title", {}).get("value", "N/A")}</div>', unsafe_allow_html=True)
                
                # Event Type
                st.markdown("<h4>Event Type</h4>", unsafe_allow_html=True)
                st.markdown(f'<div class="data-field"><span class="field-label">Value:</span> {results.get("event_type", {}).get("value", "N/A")}</div>', unsafe_allow_html=True)
                
                # Event Descriptions
                st.markdown("<h4>Event Descriptions</h4>", unsafe_allow_html=True)
                for desc in results.get("descriptions", []):
                    st.markdown(f'<div class="data-field"><span class="field-label">Description:</span> {desc.get("value", "N/A")}</div>', unsafe_allow_html=True)
            
            # Event Timeline (Stages & Episodes)
            st.subheader("⏳ Event Timeline (Stages & Episodes)")
            stages = results.get("stages", [])
            
            for stage_idx, stage in enumerate(stages):
                stage_name = stage.get("name", {}).get("value", f"Stage {stage_idx+1}")
                stage_conf = stage.get("name", {}).get("confidence", 0)
                
                with st.expander(f"Stage {stage_idx+1}: {stage_name} (Confidence: {stage_conf:.0%})", expanded=False):
                    # Stage Basic Info
                    st.markdown(f'<div class="data-field"><span class="field-label">Stage ID:</span> {stage.get("stage_id", "N/A")}</div>', unsafe_allow_html=True)
                    
                    # Stage Timeframe
                    start_time = stage.get("start_time", {}).get("value", "Unknown")
                    end_time = stage.get("end_time", {}).get("value", "Unknown")
                    st.markdown(f'<div class="data-field"><span class="field-label">Start Time:</span> {start_time}</div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="data-field"><span class="field-label">End Time:</span> {end_time}</div>', unsafe_allow_html=True)
                    
                    # Render episodes for this stage
                    episodes = stage.get("episodes", [])
                    for episode_idx, episode in enumerate(episodes):
                        episode_name = episode.get("name", {}).get("value", f"Episode {episode_idx+1}")
                        episode_conf = episode.get("name", {}).get("confidence", 0)
                        
                        with st.expander(f"Episode {episode_idx+1}: {episode_name} (Confidence: {episode_conf:.0%})", expanded=False):
                            # Episode Basic Info
                            st.markdown(f'<div class="data-field"><span class="field-label">Episode ID:</span> {episode.get("episode_id", "N/A")}</div>', unsafe_allow_html=True)
                            
                            # Episode Timeframe
                            ep_start = episode.get("start_time", {}).get("value", "Unknown")
                            ep_end = episode.get("end_time", {}).get("value", "Unknown")
                            st.markdown(f'<div class="data-field"><span class="field-label">Start Time:</span> {ep_start}</div>', unsafe_allow_html=True)
                            st.markdown(f'<div class="data-field"><span class="field-label">End Time:</span> {ep_end}</div>', unsafe_allow_html=True)

            # Export and navigation section
            st.markdown("---")
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("📥 Export as JSON", use_container_width=True):
                    json_str = json.dumps(results, indent=2, ensure_ascii=False)
                    file_name = f"{results.get('event_id', 'event_reconstruction')}.json"
                    st.download_button(
                        label="📥 Download JSON",
                        data=json_str,
                        file_name=file_name,
                        mime="application/json",
                        use_container_width=True
                    )
            
            with col2:
                if st.button("📊 View Confidence Breakdown", use_container_width=True):
                    self.render_confidence_breakdown(results)

    def render_results_page_class(self):
        """Render the class-based event reconstruction results."""
        st.title("📋 Event Reconstruction Report")
        
        if not st.session_state.analysis_results:
            st.info("No reconstruction results available. Please run an analysis first.")
            if st.button("Go to Reconstruction"):
                st.session_state.current_page = "Pipeline"
                st.rerun()
            return
        
        results = st.session_state.analysis_results
        
        # Main container with custom styling
        with st.container():
            # Reconstruction Overview
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.markdown('<div class="reconstruction-header"><h2>🎯 Event Reconstruction Complete</h2></div>', unsafe_allow_html=True)
            
            with col2:
                st.metric("Status", "RECONSTRUCTED", delta=None)
                if results.get("is_mock_data"):
                    st.warning("Using demonstration data")
            
            # Recursively render nested data
            def render_nested_data(data, level=0, parent_key=""):
                if isinstance(data, dict):
                    for key, value in data.items():
                        expander_key = f"{parent_key}_{key}"
                        display_key = " ".join(word.capitalize() for word in key.split("_"))
                        
                        if isinstance(value, (dict, list)) and value:
                            if level == 0:  # Top-level sections
                                with st.expander(f"### 📊 {display_key}", expanded=True):
                                    render_nested_data(value, level + 1, expander_key)
                            elif level == 1:  # Second-level sections
                                st.markdown(f'<div class="section-card"><h4>{display_key}</h4></div>', unsafe_allow_html=True)
                                render_nested_data(value, level + 1, expander_key)
                            else:  # Nested levels
                                with st.expander(f"**{display_key}**"):
                                    render_nested_data(value, level + 1, expander_key)
                        else:
                            # Render leaf nodes
                            if level <= 1:
                                col1, col2 = st.columns([1, 2])
                                with col1:
                                    st.markdown(f"**{display_key}:**")
                                with col2:
                                    st.write(value if value else "N/A")
                            else:
                                st.markdown(f"- **{display_key}:** {value}")
                                
                elif isinstance(data, list):
                    for i, item in enumerate(data):
                        if isinstance(item, (dict, list)):
                            render_nested_data(item, level + 1, f"{parent_key}_item{i}")
                        else:
                            st.markdown(f"• {item}")
                else:
                    st.write(data)
            
            # Render the main reconstruction data
            render_nested_data(results)
            
            # Export section
            st.markdown("---")
            if st.button("📥 Export as JSON", use_container_width=True):
                json_str = json.dumps(results, indent=2, ensure_ascii=False)
                st.download_button(
                    label="Download JSON",
                    data=json_str,
                    file_name="event_reconstruction.json",
                    mime="application/json"
                )

    def render_confidence_breakdown(self, results):
        """Render confidence breakdown for agent-based results."""
        st.markdown("<div class='section-card'>", unsafe_allow_html=True)
        st.subheader("📊 Confidence Breakdown")
        
        # Calculate confidence metrics
        title_conf = results.get("title", {}).get("confidence", 0)
        type_conf = results.get("event_type", {}).get("confidence", 0)
        
        desc_confidences = [d.get("confidence", 0) for d in results.get("descriptions", [])]
        avg_desc_conf = sum(desc_confidences)/len(desc_confidences) if desc_confidences else 0
        
        stages = results.get("stages", [])
        avg_stage_conf = 0
        if stages:
            avg_stage_conf = sum([s.get("name", {}).get("confidence", 0) for s in stages])/len(stages)
        
        all_episodes = []
        for stage in stages:
            all_episodes.extend(stage.get("episodes", []))
        avg_episode_conf = 0
        if all_episodes:
            avg_episode_conf = sum([e.get("name", {}).get("confidence", 0) for e in all_episodes])/len(all_episodes)
        
        # Display confidence metrics
        conf_data = {
            "Title": title_conf,
            "Event Type": type_conf,
            "Average Description": avg_desc_conf,
            "Average Stage": avg_stage_conf,
            "Average Episode": avg_episode_conf
        }
        
        for key, value in conf_data.items():
            st.progress(value)
            st.markdown(f'<div class="data-field"><span class="field-label">{key}:</span> {value:.0%}</div>', unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True)

    def render_about_page(self):
        """Render the about page with system information and usage guidelines."""
        st.title("About FinMycelium")

        st.markdown(
            """
            ### Financial Event Reconstruction and Education Platform
            
            FinMycelium is an advanced AI-powered system designed to analyze financial event 
            and provide comprehensive educational insights to help protect consumers and investors.
            """
        )

        st.markdown("---")

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("System Capabilities")
            st.markdown(
                """
                - **Multi-source Data Analysis**: Process keywords, documents, and structured data
                - **AI-Powered Pattern Recognition**: Identify event mechanisms and characteristics
                - **Comprehensive Reporting**: Generate detailed analysis with risk assessments
                - **Educational Content**: Provide prevention tips and warning signs
                - **User-Friendly Interface**: Intuitive workflow for all user levels
                """
            )

        with col2:
            st.subheader("Methodology")
            st.markdown(
                """
                - **Data Collection**: Aggregate information from multiple sources
                - **Pattern Analysis**: Identify common event characteristics
                - **Risk Assessment**: Evaluate potential impacts and warning signs
                - **Educational Synthesis**: Create understandable prevention guidance
                - **Continuous Learning**: Adapt to new event patterns and techniques
                """
            )

        st.markdown("---")

        st.subheader("Usage Guidelines")
        st.markdown(
            """
            - **For Educational Purposes**: This tool is designed for educational and research purposes
            - **Consult Professionals**: Always consult licensed financial advisors for investment decisions
            - **Verify Information**: Cross-check findings with official regulatory sources
            - **Report Suspected Event**: Report potential event to relevant authorities
            - **Continuous Learning**: Financial event patterns evolve constantly - stay informed
            """
        )

        st.markdown("---")

        st.caption(
            """
            FinMycelium v1.0 | Financial Event Reconstruction System | 
            For educational and research purposes only.
            """
        )

    def run(self):
        """Main method to run the web interface application."""
        self.render_sidebar()

        current_page = st.session_state.get("current_page", "Home")

        if current_page == "Home":
            self.render_home_page()
        elif current_page == "Pipeline":
            self.render_analysis_page()
        elif current_page == "Results":
            # Check if we have valid configuration before rendering results
            if not st.session_state.config:
                st.error("Configuration is missing. Please return to Pipeline page and reconfigure.")
                if st.button("Return to Pipeline"):
                    st.session_state.current_page = "Pipeline"
                    st.rerun()
                return
                
            if st.session_state.build_mode == "agent_build":
                self.render_results_page_agent()
            else:  # Default to class_build
                self.render_results_page_class()
        elif current_page == "About":
            self.render_about_page()


def main():
    """Main entry point for the FinMycelium web interface."""
    try:
        app = FinMyceliumWebInterface()
        app.run()
    except Exception as e:
        st.error(f"Application error: {e}")
        st.info("Please refresh the page and try again.")


if __name__ == "__main__":
    main()