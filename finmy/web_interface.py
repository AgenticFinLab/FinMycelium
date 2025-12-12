"""
Web interface for FinMycelium - Financial Fraud Analysis System
Provides a user-friendly interface for analyzing financial fraud cases
through multiple data sources and AI-powered analysis.
"""

import os
import re
import sys
import asyncio
import random
import tempfile
from pathlib import Path
from loguru import logger
import logging
from typing import List, Dict, Any, Optional
import pandas as pd
import datetime
import json


import streamlit as st
from streamlit_input_box import input_box
from streamlit_option_menu import option_menu
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv

from finmy.url_collector.SearchCollector.bocha_search import bochasearch_api
from finmy.url_collector.SearchCollector.baidu_search import baidusearch_api
from finmy.url_collector.MediaCollector.platform_crawler import PlatformCrawler
from finmy.url_collector.url_parser import URLParser
from finmy.pdf_collector.pdf_collector import PDFCollector
from finmy.pdf_collector.base import PDFCollectorInput, PDFCollectorOutput
from finmy.url_collector.url_parser_clean import extract_content_from_parsed_content, extract_content_from_results
from finmy.lm_build_pipeline import lm_build_pipeline_main



# Load environment variables
load_dotenv()

# Import project modules (with fallbacks for missing modules)
try:
    from db_manager import DatabaseManager
except ImportError:
    DatabaseManager = None

try:
    from generic import GenericProcessor
except ImportError:
    GenericProcessor = None


class FinMyceliumWebInterface:
    """
    Main web interface class for FinMycelium financial fraud analysis system.
    Handles user interactions, data processing, and result visualization.
    """

    def __init__(self):
        """Initialize the web interface with configuration and state management."""
        self.setup_page_config()
        self.initialize_session_state()
        self.ai_client = None
        self.setup_ai_client()

    def setup_page_config(self):
        """Configure Streamlit page settings for optimal user experience."""
        st.set_page_config(
            page_title="FinMycelium - Financial Fraud Analysis",
            page_icon="🕵️",
            layout="wide",
            initial_sidebar_state="expanded",
            menu_items={
                "Get Help": None,
                "Report a bug": None,
                "About": None,
            },
        )
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
        if "analysis_results" not in st.session_state:
            st.session_state.analysis_results = None
        if "processing_status" not in st.session_state:
            st.session_state.processing_status = "idle"
        if "uploaded_files" not in st.session_state:
            st.session_state.uploaded_files = []
        if "selected_fraud_type" not in st.session_state:
            st.session_state.selected_fraud_type = None

    def setup_ai_client(self):
        """Initialize AI client with configuration from environment variables."""
        try:
            self.ai_client = OpenAI(
                base_url="https://aihubmix.com/v1",
                api_key=os.getenv("AIHUBMIX_API_KEY"),
            )
        except Exception as e:
            st.error(f"Failed to initialize AI client: {e}")
            self.ai_client = None

    def render_sidebar(self):
        """Render the sidebar with navigation and system information."""
        with st.sidebar:
            st.title("🕵️ FinMycelium")
            st.markdown("---")

            # Navigation menu
            selected = option_menu(
                menu_title="Navigation",
                options=["Home", "Analysis", "Results", "About"],
                icons=["house", "search", "bar-chart", "info-circle"],
                menu_icon="cast",
                default_index=0,
            )

            st.session_state.current_page = selected

            # System status
            st.markdown("---")
            st.subheader("System Status")

            # Module availability status
            modules_status = {
                "AI Analysis": self.ai_client is not None,
                "Database Manager": DatabaseManager is not None,
                "Generic Processor": GenericProcessor is not None,
            }

            for module, available in modules_status.items():
                status_icon = "✅" if available else "🔄"
                st.write(f"{status_icon} {module}")

            st.markdown("---")
            st.caption("FinMycelium v1.0")
            st.caption("Copyright © 2025 AgenticFin Lab")

    def render_home_page(self):
        """Render the home page with system overview and quick start options."""
        st.title("Welcome to FinMycelium")
        st.markdown(
            """
        ### Comprehensive Financial Fraud Analysis Platform
        
        FinMycelium helps you analyze and understand financial fraud schemes 
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
            - Fraud pattern recognition
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

        # col1, col2 = st.columns([2, 1])

        col1, col2, col3 = st.columns([1, 1, 1])

        with col2:
            # Quick start section
            st.subheader("Get Started")
            st.markdown(
                """
            **Start your analysis in 3 simple steps:**
            1. **Input** the event related information you want to analyze
            2. **Provide** data through keywords or structured file
            3. **Analyze** with our AI-powered fraud detection system
            """
            )

        # with col2:
        #     if st.button("Start Analysis", type="primary", width='stretch'):
        #         st.session_state.current_page = "Analysis"
        #         st.rerun()

    def render_analysis_page(self):
        """
        Render the analysis page with fraud type selection and data input options.
        """
        # st.title("Financial Fraud Analysis")
        # st.markdown("Provide details about the fraud case you want to analyze.")

        # Natural language input box
        # st.subheader("🔍 Event Description")
        prev_text = st.session_state.get("main_input", "")
        visible_lines = max(prev_text.count("\n") + 1, len(prev_text) // 60 + 1)
        dynamic_height = min(600, max(100, visible_lines * 24))

        # need: from streamlit_input_box import input_box
        # docs: https://pypi.org/project/streamlit-input-box/
        # main_input = input_box(
        #     min_lines=1,  # min
        #     max_lines=5,  # max
        #     just_once=False,  #
        #     key=None,
        # )

        main_input = st.text_area(
            "Event Description",
            value=prev_text,
            placeholder="Enter a detailed description of the fraud case, including key details, suspicious activities, involved parties, timeline, and any other relevant information...",
            height="content",
            key=f"main_input_{dynamic_height}",
            help="Provide a comprehensive description for better analysis results",
        )

        st.session_state.main_input = main_input

        if main_input:
            st.session_state.main_input = main_input

        # st.markdown("---")

        # Data input methods
        # st.subheader("Data Input Methods")
        # st.markdown(
        #     "Provide additional data through keywords or structured data files:"
        # )

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

    def render_keyword_input(self):
        """Render keyword input section with validation and suggestions."""
        # st.subheader("🔤 Keyword Analysis")

        # col1, col2 = st.columns([2, 1])

        # with col1:
        keywords = st.text_area(
            "Enter relevant keywords or phrases (comma-separated):",
            placeholder="e.g., high-yield investment, guaranteed returns, crypto mining scheme, company name, individual names...",
            help="Provide specific terms related to the fraud case to enhance analysis",
        )

        # with col2:
        #     st.markdown("**Keyword Tips:**")
        #     st.markdown(
        #         """
        #     - Company/Project names
        #     - Promised returns
        #     - Investment methods
        #     - Key individuals
        #     - Platform names
        #     - Suspicious activities
        #     """
        #     )

        # Process keyword input with flexible delimiter handling
        if keywords:  # Check if input string is not empty
            # Step 1: Normalize full-width Chinese commas to standard commas
            unified_keywords = keywords.replace('，', ',')
            
            # Step 2: Split on commas/spaces (supports multiple consecutive delimiters)
            # Regex pattern matches one or more commas (,) OR whitespace characters (\s)
            keyword_list = re.split(r'[,|\s]+', unified_keywords)
            
            # Step 3: Clean up keywords (strip whitespace + remove empty strings)
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
        col1, col2, col3 = st.columns([1, 1, 1])

        with col2:
            if st.button("🚀 Start Analysis", type="primary", width="stretch"):
                if self.validate_analysis_inputs():
                    self.run_analysis()
                else:
                    st.error("Please provide required inputs before starting analysis")

        # Status indicator
        if st.session_state.processing_status != "idle":
            status_placeholder = st.empty()
            with status_placeholder.container():
                if st.session_state.processing_status == "processing":
                    st.info("🔄 Analysis in progress... This may take a few minutes.")

                elif st.session_state.processing_status == "completed":
                    st.success("✅ Analysis completed! ")
                elif st.session_state.processing_status == "error":
                    st.error("❌ Analysis failed. Please try again.")

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

    def run_analysis(self):
        """Execute the fraud analysis pipeline with provided inputs."""
        st.session_state.processing_status = "processing"

        #
        with st.status(
            "🔄 Analysis in progress... This may take a few minutes.", state="running"
        ) as status:
            try:
                #
                analysis_inputs = {
                    "main_input": getattr(st.session_state, "main_input", ""),
                    "keywords": getattr(st.session_state, "keywords", []),
                    "structured_data": getattr(
                        st.session_state, "structured_data", None
                    ),
                }

                #
                st.write("Processing data...")
                results = self.perform_ai_analysis(analysis_inputs)

                #
                status.update(label="✅ Analysis completed!", state="complete")

                #
                st.session_state.analysis_results = results
                st.session_state.processing_status = "completed"

                #
                st.session_state.current_page = "Results"
                st.success("Redirecting to results...")
                st.rerun()

            except Exception as e:
                status.update(label=f"❌ Analysis failed: {e}", state="error")
                st.session_state.processing_status = "error"

    def perform_ai_analysis(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform AI-powered fraud analysis using the provided inputs.

        Args:
            inputs: Dictionary containing natural language description and data sources

        Returns:
            Dictionary containing analysis results
        """
        if not self.ai_client:
            return self.get_mock_analysis_results(inputs)

        try:
            # Construct analysis prompt
            prompt = self.construct_analysis_prompt(inputs)

            # Call AI model
            response = self.ai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "developer",
                        "content": "Always respond in Chinese. You are a financial fraud analysis expert. Provide comprehensive, educational analysis of financial fraud schemes.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=2048,
                top_p=1,
                frequency_penalty=0,
                presence_penalty=0,
                seed=random.randint(1, 1000000000),
            )

            # Parse and structure results
            analysis_text = response.choices[0].message.content
            print("================ AIHUBMIX RESPONSE ==================")
            print(analysis_text)
            return self.parse_analysis_results(analysis_text, inputs)

        except Exception as e:
            st.error(f"AI analysis error: {e}")
            return self.get_mock_analysis_results(inputs)

    def construct_analysis_prompt(self, inputs: Dict[str, Any]) -> str:
        """Construct detailed prompt for fraud analysis."""
        main_search_input = inputs["main_input"]
        keywords = inputs["keywords"]
        structured_data = inputs["structured_data"] is not None
        search_query_content=main_search_input+" \n\nkeywords: "+" ".join(keywords)

        # main_search_input -> summarizer -> refined description and keywords

        # keywords -> MediaCollector (Get media info) -> filter -> clean data
        # Test Platform Crawler Manager
        # There is still something wrong currently
        # try:
        #     print("=====================================")
        #     print("Testing: PlatformCrawler")
        #     print("=====================================")
        #     platformcrawler = PlatformCrawler()
        #     result = platformcrawler.run_crawler("wb", keywords, max_notes=5)
        #     logger.info(f"Test result: {result}")
        #     logger.info("Platform Crawler Manager test completed!")
        # except:
        #     print("PlatformCrawler: Error!")

        # keywords -> SearchCollector+url_parser (Get web info) -> filter -> clean data
        # Bocha Search API test
        parser = URLParser(delay=2.0, use_selenium_fallback=True, selenium_wait_time=5)
        save_dir = r"examples/utest/Collector/test_files"
        os.makedirs(save_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")


        print("=====================================")
        print("Testing: Bocha Search")
        print("=====================================")
        formatted_bocha_search_results_content=[]
        try:
            
            
            bocha_search_results = bochasearch_api(
                search_query_content, summary=True, count=10
            )
            # Print the search results to console for verification
            formatted_bocha_search_results = []
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
                results = parser.parse_urls([item["url"]])
                # print(results)
                formatted_item["parsed_content"] = (
                    results[0]["content"] if results else []
                )
                formatted_bocha_search_results.append(formatted_item)

            filepath = os.path.join(
                save_dir, f"formatted_bocha_search_results_{timestamp}.json"
            )
            
            
            for item in formatted_bocha_search_results:
                item_content = ""
                item_content += "Title:\n"
                item_content += item["title"]+"\n\n"
                item_content += "Sitename:\n"
                item_content += item["sitename"]+"\n\n"
                item_content += "Content:\n"
                item_content += item["content"]+"\n\n\n"
                item_content += "Parsed Content:\n"
                item_content += extract_content_from_parsed_content(item["parsed_content"])+"\n\n\n"
                               
                formatted_bocha_search_results_content.append(item_content)


            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(
                    formatted_bocha_search_results, f, ensure_ascii=False, indent=4
                )
            # print(formatted_bocha_search_results)
        except:
            print("Bocha Search: Error!")


        print("=====================================")
        print("Testing: Baidu Search")
        print("=====================================")
        formatted_baidu_search_results_content=[]
        try:
            
            baidu_search_results = baidusearch_api(search_query_content)
            formatted_baidu_search_results = []
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
                    results = parser.parse_urls([item["url"]])
                    # print(results)
                    formatted_item["parsed_content"] = (
                        results[0]["content"] if results else []
                    )
                    formatted_baidu_search_results.append(formatted_item)
            # Print the search results to console for verification
            
            for item in formatted_baidu_search_results:
                item_content = ""
                item_content += "Title:\n"
                item_content += item["title"]+"\n\n"
                item_content += "Sitename:\n"
                item_content += item["sitename"]+"\n\n"
                item_content += "Content:\n"
                item_content += item["content"]+"\n\n\n"
                item_content += "Parsed Content:\n"
                item_content += extract_content_from_parsed_content(item["parsed_content"])+"\n\n\n"
                               
                formatted_baidu_search_results_content.append(item_content)


            filepath = os.path.join(
                save_dir, f"formatted_baidu_search_results_{timestamp}.json"
            )
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(
                    formatted_baidu_search_results, f, ensure_ascii=False, indent=4
                )
            # print(formatted_baidu_search_results)
        except:
            print("Baidu Search: Error!")



        # structured_data 
        print("=====================================")
        print("Testing: structure data processing")
        print("=====================================")
        structure_data_urllink = []
        structure_data_filepath = []
        structure_data_urllink_content=[]
        structure_data_filepath_content=[]
        try:  
            if st.session_state.structured_data is not None:
                parser = URLParser(
                delay=2.0, use_selenium_fallback=True, selenium_wait_time=5
                )
                output_dir = f"./examples/utest/Collector/test_files/pdfcollector_output_{timestamp}"
                for index, row in st.session_state.structured_data.iterrows():
                    try:
                        title = row["title"] if row["title"] else "No Title"
                        url = row["url"] if row["url"] else "No URL"
                        # Check if URL is a web link or local file path
                        if isinstance(url, str):
                            # Web URL detection (basic check)
                            if url.startswith(("http://", "https://", "www.")):
                                # Process web URL
                                # Repla ce with web URL processing logic
                                results = parser.parse_urls([url])
                                # print(results)
                                row = row.to_dict()
                                row["parsed_content"] = (
                                    results[0]["content"] if results else []
                                )
                                structure_data_urllink.append(row.to_dict())
                            else:
                                # Assume local file path

                                if os.path.exists(url) and url.lower().endswith(".pdf"):

                                    print("Processing local PDF file:", url)

                                    # Here we need to write code to handle parameter input

                                    
                                    batch_size = 200
                                    language = "ch"
                                    check_pdf_limits = True

                                    config = {
                                        # The directory to store output files
                                        "output_dir": output_dir,
                                        # The batch size for processing pdfs (max: 200)
                                        "batch_size": batch_size,
                                        # The language code for the document (e.g., "en" for English)
                                        "language": language,
                                        # Whether to check PDF size and page limits
                                        "check_pdf_limits": check_pdf_limits,
                                        # Path to the .env file for loading environment variables
                                        "env_file": ".env",
                                    }

                                    # Create PDFCollectorInput object with keywords from command line or test keywords

                                    keywords = keywords if keywords else []
                                    pdf_collector_input = PDFCollectorInput(
                                        # input_dir=args.input_dir,
                                        input_pdf_path=url,
                                        keywords=keywords,
                                    )

                                    # Initialize PDFCollector
                                    parser_instance = PDFCollector(config)

                                    # Run the main processing function
                                    logging.info("  - Starting PDF processing...")
                            
                                    # Collect the parsed and filtered results
                                    collect_results = parser_instance.collect(pdf_collector_input)
                                    filter_results = parser_instance.filter(pdf_collector_input,collect_results)

                                    # Print final results summary
                                    logging.info(
                                        "  - Total PDFs parsed results after filtering: %d",
                                        len(collect_results.records),
                                    )
                                    
                                    row["parsed_content"] = (
                                        collect_results.records[0].__dict__ if collect_results.records[0] else {}
                                    )
                                    structure_data_filepath.append(row.to_dict())
                        else:
                            st.warning(
                                f"Row {index}: URL is not a string format. Skipping processing."
                            )
                    except:
                        logging.info(
                            "Processing error: %s",
                            row["url"] if row["url"] else "No URL Provided",
                        )

                

                print("===== Structured Data URL Link =====")
                # print(structure_data_urllink)
                print("=====================================")
                filepath = os.path.join(
                    save_dir, f"structure_data_urllink_{timestamp}.json"
                )    
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(structure_data_urllink, f, ensure_ascii=False, indent=4)
                
                for item in structure_data_urllink:
                    item_content = ""
                    item_content += "title:\n"
                    item_content += item["title"] if item["title"] else "No Title"
                    item_content += "\n\n"
                    item_content += "content:\n"
                    item_content += extract_content_from_parsed_content(item["parsed_content"])
                    structure_data_urllink_content.append(item_content)


                print("===== Structured Data Filepath =====")
                # print(structure_data_filepath)
                print("=====================================")
                filepath = os.path.join(
                    save_dir, f"structured_data_filepath_{timestamp}.json"
                )    
                print(structure_data_filepath)
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(structure_data_filepath, f, ensure_ascii=False, indent=4)
                
                for item in structure_data_filepath:
                    item_content=""
                    if(item["parsed_content"]["Location"]):
                        with open(item["parsed_content"]["Location"],"r",encoding="utf-8") as f:
                            item_content += "title:\n"
                            item_content += item["title"] if item["title"] else "No Title"
                            item_content += "\n\n"
                            item_content += "content:\n"
                            item_content += f.read()
                            # print(item_content)
                        structure_data_filepath_content.append(item_content)

        
        except:
            print("There is something wrong with structured data processing!")

        # info_to_analyze = cleaned and filtered data from above steps
        
        All_Text_Content = formatted_bocha_search_results_content +formatted_baidu_search_results_content + structure_data_urllink_content + structure_data_filepath_content
        All_Text_Content_filepath = os.path.join(
                    save_dir, f"All_Text_Content_{timestamp}.json"
                )    
        with open(All_Text_Content_filepath, "w", encoding="utf-8") as f:
                    json.dump(All_Text_Content, f, ensure_ascii=False, indent=4)
        print("============================")
        print("=========All_Text_Content==========")
        print("============================")
        print(All_Text_Content)
        print("============================")
        
        print("Length of All_Text_Content List")
        print(len(All_Text_Content))
        
        print("Length of All_Text_Content String:")
        All_Text_Content_Count=0
        for item in All_Text_Content:
            All_Text_Content_Count+=len(item)
        print("============================")



        print("=====================================")
        print("Testing: LM_Build_Flow")
        print("=====================================")
        lm_build_pipeline_main(raw_texts=All_Text_Content, query_text=main_search_input, key_words=keywords, output_dir=f"./examples/utest/Collector/test_files/event_output_{timestamp}")


        prompt = f"""
        As a financial fraud analysis expert, analyze the following financial fraud case:
        
        CASE DESCRIPTION: {main_search_input if main_search_input else 'No natural language description provided'}
        
        KEYWORDS: {', '.join(keywords) if keywords else 'No keywords provided'}
        
        STRUCTURED DATA: {structured_data if structured_data else 'Not provided'}
        
        Please provide a comprehensive analysis including:
        
        1. FRAUD PATTERN IDENTIFICATION:
           - Main fraud mechanism
           - Recruitment methods
           - Payment structures
           - Exit strategies
        
        2. KEY CHARACTERISTICS:
           - Promised returns/benefits
           - Target victims
           - Communication channels
           - Trust-building techniques
        
        3. TIMELINE ANALYSIS:
           - Typical progression stages
           - Key milestones
           - Duration patterns
        
        4. IMPACT ASSESSMENT:
           - Financial losses
           - Number of victims
           - Social consequences
           - Legal implications
        
        5. RED FLAGS & PREVENTION:
           - Warning signs for investors
           - Protective measures
           - Regulatory considerations
        
        Provide the analysis in a clear, educational format that helps ordinary people understand how such frauds work and how to avoid them.
        """

        return prompt

    def parse_analysis_results(
        self, analysis_text: str, inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Parse AI response into structured results format."""
        return {
            "summary": analysis_text,
            "key_findings": self.extract_key_findings(analysis_text),
            "risk_factors": self.extract_risk_factors(analysis_text),
            "prevention_tips": self.extract_prevention_tips(analysis_text),
            "analysis_timestamp": pd.Timestamp.now().isoformat(),
        }

    def extract_key_findings(self, analysis: str) -> List[str]:
        """Extract key findings from analysis text."""
        # Simplified extraction - in practice, use more sophisticated NLP
        sentences = [s.strip() for s in analysis.split(".") if s.strip()]
        return sentences[:5]  # Return first 5 sentences as key findings

    def extract_risk_factors(self, analysis: str) -> List[str]:
        """Extract risk factors from analysis text."""
        risk_indicators = [
            "high return",
            "guaranteed",
            "risk",
            "warning",
            "red flag",
            "suspicious",
        ]
        sentences = [
            s.strip()
            for s in analysis.split(".")
            if any(indicator in s.lower() for indicator in risk_indicators)
        ]
        return sentences[:3]

    def extract_prevention_tips(self, analysis: str) -> List[str]:
        """Extract prevention tips from analysis text."""
        prevention_indicators = [
            "prevent",
            "avoid",
            "protect",
            "check",
            "verify",
            "due diligence",
        ]
        sentences = [
            s.strip()
            for s in analysis.split(".")
            if any(indicator in s.lower() for indicator in prevention_indicators)
        ]
        return (
            sentences[:3]
            if sentences
            else [
                "Always verify investment opportunities with regulatory authorities",
                "Be skeptical of guaranteed high returns",
                "Consult with financial advisors before making significant investments",
            ]
        )

    def get_mock_analysis_results(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Provide mock analysis results when AI service is unavailable."""
        return {
            "summary": "This is a mock analysis based on the provided inputs. In a real scenario, this would contain comprehensive AI-generated insights about the fraud pattern, mechanisms, and prevention strategies.",
            "key_findings": [
                "Mock finding 1: Analysis of described fraud characteristics",
                "Mock finding 2: Common patterns identified in similar cases",
                "Mock finding 3: Potential financial impact assessment",
            ],
            "risk_factors": [
                "High promised returns with low risk claims",
                "Lack of regulatory compliance indicators",
                "Pressure tactics for quick investment decisions",
            ],
            "prevention_tips": [
                "Verify all investment opportunities with financial regulators",
                "Be cautious of guaranteed high returns",
                "Consult independent financial advisors before investing",
            ],
            "analysis_timestamp": pd.Timestamp.now().isoformat(),
            "is_mock_data": True,
        }

    def render_results_page(self):
        """Render the results page with comprehensive analysis visualization."""
        st.title("Analysis Results")

        if not st.session_state.analysis_results:
            st.info("No analysis results available. Please run an analysis first.")
            if st.button("Go to Analysis"):
                st.session_state.current_page = "Analysis"
                st.rerun()
            return

        results = st.session_state.analysis_results

        # Results overview
        col1, col2 = st.columns([2, 1])

        with col1:
            st.subheader("Fraud Analysis Results")

        with col2:
            st.metric("Analysis Status", "Completed")
            if results.get("is_mock_data"):
                st.warning("Using demonstration data")

        st.markdown("---")

        # Key findings
        # st.subheader("🔍 Key Findings")
        # for i, finding in enumerate(results["key_findings"], 1):
        #     st.markdown(f"{i}. {finding}")

        st.markdown("---")

        # Detailed analysis
        st.subheader("📊 Detailed Analysis")
        with st.expander("View Complete Analysis", expanded=True):
            st.write(results["summary"])

        # Risk factors and prevention
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("⚠️ Risk Factors")
            for risk in results["risk_factors"]:
                st.markdown(f"• {risk}")

        with col2:
            st.subheader("🛡️ Prevention Tips")
            for tip in results["prevention_tips"]:
                st.markdown(f"• {tip}")

        st.markdown("---")

        # Educational insights
        st.subheader("🎓 Educational Insights")
        self.render_educational_insights(results)

        # Action buttons
        col1, col2, col3 = st.columns(3)
        with col2:
            if st.button("🔄 New Analysis", width="stretch"):
                st.session_state.analysis_results = None
                st.session_state.current_page = "Analysis"
                st.rerun()

    def render_educational_insights(self, results: Dict[str, Any]):
        """Render educational insights section with fraud-specific information."""
        st.info(
            """
        **General Fraud Prevention Tips:**
        - Verify all investment opportunities with relevant authorities
        - Be cautious of unsolicited investment offers
        - Understand that high returns typically involve high risks
        - Don't invest in anything you don't fully understand
        - Seek independent financial advice before investing
        - Research the background of companies and individuals
        - Be wary of pressure to invest quickly
        """
        )

    def render_about_page(self):
        """Render the about page with system information and usage guidelines."""
        st.title("About FinMycelium")

        st.markdown(
            """
        ### Financial Fraud Analysis and Education Platform
        
        FinMycelium is an advanced AI-powered system designed to analyze financial fraud schemes 
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
            - **AI-Powered Pattern Recognition**: Identify fraud mechanisms and characteristics
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
            - **Pattern Analysis**: Identify common fraud characteristics
            - **Risk Assessment**: Evaluate potential impacts and warning signs
            - **Educational Synthesis**: Create understandable prevention guidance
            - **Continuous Learning**: Adapt to new fraud patterns and techniques
            """
            )

        st.markdown("---")

        st.subheader("Usage Guidelines")
        st.markdown(
            """
        - **For Educational Purposes**: This tool is designed for educational and research purposes
        - **Consult Professionals**: Always consult licensed financial advisors for investment decisions
        - **Verify Information**: Cross-check findings with official regulatory sources
        - **Report Suspected Fraud**: Report potential fraud to relevant authorities
        - **Continuous Learning**: Financial fraud patterns evolve constantly - stay informed
        """
        )

        st.markdown("---")

        st.caption(
            """
        FinMycelium v1.0 | Financial Fraud Analysis System | 
        For educational and research purposes only.
        """
        )

    def run(self):
        """Main method to run the web interface application."""
        self.render_sidebar()

        current_page = st.session_state.get("current_page", "Home")

        if current_page == "Home":
            self.render_home_page()
        elif current_page == "Analysis":
            self.render_analysis_page()
        elif current_page == "Results":
            self.render_results_page()
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
