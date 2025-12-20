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
from sympy import test

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
# from finmy.pipeline import FinmyPipeline
from finmy.builder.class_build.simple_build import ClassLMSimpleBuild



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
        if "keywords" not in st.session_state:
            st.session_state.keywords = None
        if "build_mode" not in st.session_state:
            st.session_state.build_mode = None

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

        st.session_state.build_mode = st.radio(
            "Build Mode",
            options=["class_build", "agent_build"],
            index = 0, 
            help="Choose the build mode for the event reconstruction",
        )

        # Analysis controls
        self.render_analysis_controls()


    def render_keyword_input(self):
        """Render keyword input section with validation and suggestions."""
        # st.subheader("🔤 Keyword Analysis")

        # col1, col2 = st.columns([2, 1])


        if st.session_state.keywords is not None:
            keywords = st.text_area(
                "Enter relevant keywords or phrases (comma-separated):",
                placeholder=st.session_state.keywords,
                help="Provide specific terms related to the fraud case to enhance analysis",
            )
        else:
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
            unified_keywords = keywords.replace('，', ',').replace(";",",").replace("；","")
            
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
                if self.validate_analysis_inputs() and st.session_state.build_mode == "class_build":
                    self.run_analysis()
                elif st.session_state.build_mode == "agent_build":
                    self.render_results_page_agent
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
            results = self.construct_analysis_prompt(inputs)

            # Call AI model
            # response = self.ai_client.chat.completions.create(
            #     model="gpt-4o-mini",
            #     messages=[
            #         {
            #             "role": "developer",
            #             "content": "Always respond in Chinese. You are a financial fraud analysis expert. Provide comprehensive, educational analysis of financial fraud schemes.",
            #         },
            #         {"role": "user", "content": prompt},
            #     ],
            #     temperature=0.7,
            #     max_tokens=2048,
            #     top_p=1,
            #     frequency_penalty=0,
            #     presence_penalty=0,
            #     seed=random.randint(1, 1000000000),
            # )

            # Parse and structure results
            # analysis_text = response.choices[0].message.content
            # print("================ AIHUBMIX RESPONSE ==================")
            # print(analysis_text)
            return results

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
                collector_input = URLCollectorInput(urls=[item["url"]])
                output = parser.run(collector_input)
               
                formatted_item["parsed_content"] = (
                    output.results[0]["content"] if output.results and len(output.results) > 0 else []
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

                    collector_input = URLCollectorInput(urls=[item["url"]])
                    output = parser.run(collector_input)
                
                    formatted_item["parsed_content"] = (
                        output.results[0]["content"] if output.results and len(output.results) > 0 else []
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
                                collector_input = URLCollectorInput(urls=[item["url"]])
                                output = parser.run(collector_input)
                                # print(results)
                                row = row.to_dict()
                                row["parsed_content"] = (
                                    output.results[0]["content"] if output.results and len(output.results) > 0 else []
                                )
                                structure_data_urllink.append(row)
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
        print(All_Text_Content_Count)
        print("============================")





        print("=====================================")
        print("Testing: LM_Build_Flow")
        print("=====================================")
        # output_dir=f"./examples/utest/Collector/test_files/event_output_{timestamp}"
        # pipeline = FinmyPipeline({"output_dir": output_dir})
        # pipeline.lm_build_pipeline_main(raw_texts=All_Text_Content, query_text=main_search_input, key_words=keywords, )

        lm_name = "ARK/doubao-seed-1-6-flash-250828"
        output_file_path = rf"./examples/utest/Collector/test_files/event_cascade_output/EventCascade_{timestamp}.json"
        # Create and run the builder
        builder = ClassLMSimpleBuild(
            lm_name=lm_name,
            all_text_content=All_Text_Content,
            output_file_path=output_file_path,
            query=main_search_input,
            keywords=keywords,
        )  
        try:
            event_cascade = builder.build()
            print(f"Successfully built event cascade: {event_cascade}")
            return event_cascade
        except Exception as e:
            print(f"Error during ClassLMSimpleBuild: {e}")


        # prompt = f"""
        # As a financial fraud analysis expert, analyze the following financial fraud case:
        
        # CASE DESCRIPTION: {main_search_input if main_search_input else 'No natural language description provided'}
        
        # KEYWORDS: {', '.join(keywords) if keywords else 'No keywords provided'}
        
        # STRUCTURED DATA: {structured_data if structured_data else 'Not provided'}
        
        # Please provide a comprehensive analysis including:
        
        # 1. FRAUD PATTERN IDENTIFICATION:
        #    - Main fraud mechanism
        #    - Recruitment methods
        #    - Payment structures
        #    - Exit strategies
        
        # 2. KEY CHARACTERISTICS:
        #    - Promised returns/benefits
        #    - Target victims
        #    - Communication channels
        #    - Trust-building techniques
        
        # 3. TIMELINE ANALYSIS:
        #    - Typical progression stages
        #    - Key milestones
        #    - Duration patterns
        
        # 4. IMPACT ASSESSMENT:
        #    - Financial losses
        #    - Number of victims
        #    - Social consequences
        #    - Legal implications
        
        # 5. RED FLAGS & PREVENTION:
        #    - Warning signs for investors
        #    - Protective measures
        #    - Regulatory considerations
        
        # Provide the analysis in a clear, educational format that helps ordinary people understand how such frauds work and how to avoid them.
        # """

        # return prompt

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

    def render_results_page_1(self):
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




    def render_results_page_agent(self):
        """Render the agent-based event reconstruction results with vertical timeline visualization for nested tulip mania data."""
        st.title("Event Reconstruction - Dutch Tulip Mania (1630s)")

        # Load analysis results
        with open("output/IntegratedEventCascade.json", "r") as f:
            st.session_state.analysis_results = json.load(f)

        st.session_state.processing_status == "completed"
        
        # Check for empty results
        if not st.session_state.analysis_results:
            st.info("No reconstruction results available. Please run an analysis first.")
            if st.button("Go to Reconstruction"):
                st.session_state.current_page = "Analysis"
                st.rerun()
            return
        
        results = st.session_state.analysis_results
        
        # Main container with enhanced custom styling
        with st.container():
            st.markdown("""
            <style>
            /* Base styling */
            .reconstruction-header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                padding: 1.5rem;
                border-radius: 10px;
                color: white;
                margin-bottom: 2rem;
            }
            .section-card {
                background: white;
                padding: 1.5rem;
                border-radius: 10px;
                border-left: 4px solid #667eea;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                margin-bottom: 1rem;
            }
            .subsection-card {
                background: #f8f9fa;
                padding: 1rem;
                border-radius: 8px;
                border-left: 3px solid #764ba2;
                margin-bottom: 0.5rem;
            }
            .metric-badge {
                display: inline-block;
                background: #e3f2fd;
                color: #1976d2;
                padding: 0.25rem 0.75rem;
                border-radius: 20px;
                font-size: 0.875rem;
                margin: 0.25rem;
            }
            .confidence-badge {
                display: inline-block;
                background: #e8f5e9;
                color: #2e7d32;
                padding: 0.25rem 0.75rem;
                border-radius: 20px;
                font-size: 0.875rem;
                margin: 0.25rem;
            }
            
            /* Timeline styling - SIMPLIFIED: Removed the white vertical bar */
            .timeline-container {
                position: relative;
                margin-left: 3.5rem; /* Reduced margin for time labels */
                padding-bottom: 2rem;
            }
            .timeline-line {
                position: absolute;
                left: -1.75rem; /* Adjusted position */
                top: 0;
                bottom: 0;
                width: 4px;
                background: linear-gradient(to bottom, #667eea, #764ba2);
                border-radius: 2px;
            }
            .timeline-item {
                position: relative;
                margin-bottom: 2rem;
                padding-left: 0.5rem; /* Reduced padding */
            }
            .timeline-dot {
                position: absolute;
                left: -2rem; /* Adjusted position */
                top: 0.5rem;
                width: 1.5rem;
                height: 1.5rem;
                border-radius: 50%;
                background: white;
                border: 4px solid #667eea;
                z-index: 1;
            }
            .timeline-dot-stage {
                border-color: #667eea;
                background: #667eea;
            }
            .timeline-dot-episode {
                border-color: #764ba2;
                background: #764ba2;
            }
            .timeline-content {
                background: white;
                padding: 1.5rem;
                border-radius: 8px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                border: 1px solid #e2e8f0; /* Light border instead of left border */
                margin-bottom: 1.5rem;
            }
            
            /* Timeline headers */
            .timeline-stage-header {
                color: #667eea;
                font-weight: bold;
                margin-bottom: 1rem;
                font-size: 1.2rem;
                margin-top: 0;
                padding-top: 0;
                border-bottom: 2px solid #667eea;
                padding-bottom: 0.5rem;
            }
            .timeline-episode-header {
                color: #764ba2;
                font-weight: bold;
                margin-bottom: 1rem;
                font-size: 1.1rem;
                margin-top: 0;
                padding-top: 0;
                border-bottom: 2px solid #764ba2;
                padding-bottom: 0.5rem;
            }
            
            /* FIXED: Time labels positioning - moved further left */
            .timeline-time-label {
                position: absolute;
                left: -5rem; /* Moved further left */
                top: 0.75rem;
                font-size: 0.8rem;
                color: #666;
                white-space: nowrap;
                width: 4.5rem; /* Fixed width */
                text-align: right; /* Right align text */
                font-weight: 600;
            }
            
            /* Evidence styling */
            .evidence-card {
                background: #f5fafe;
                padding: 1rem;
                border-radius: 6px;
                margin: 0.75rem 0;
                font-size: 0.9rem;
            }
            .reasons-list {
                margin-left: 1rem;
                margin-top: 0.5rem;
                font-size: 0.9rem;
                color: #444;
            }
            
            /* Expander styling */
            div[data-testid="stExpander"] > div:first-child {
                background-color: #f8f9fa;
                padding: 0.5rem 1rem;
                border-radius: 8px 8px 0 0;
                border-left: 3px solid #667eea;
            }
            
            /* ENHANCED: Field key styling - make all keys bold with color */
            .field-key {
                font-weight: 700 !important;
                color: #2d3748 !important;
            }
            /* Specific styling for paragraphs with field keys */
            .timeline-content p strong,
            .subsection-card p strong,
            .evidence-card strong {
                font-weight: 700 !important;
                color: #2c5282 !important;
                background-color: #f7fafc;
                padding: 0.1rem 0.3rem;
                border-radius: 3px;
            }
            /* Style for inline field labels */
            .field-label {
                font-weight: 700;
                color: #2c5282;
                background-color: #f7fafc;
                padding: 0.1rem 0.3rem;
                border-radius: 3px;
                margin-right: 0.5rem;
                display: inline-block;
            }
            
            /* Styling for all data fields */
            .data-field {
                margin-bottom: 0.75rem;
            }
            
            /* Responsive adjustments */
            @media (max-width: 768px) {
                .timeline-container {
                    margin-left: 3rem;
                }
                .timeline-time-label {
                    left: -4.5rem;
                    font-size: 0.75rem;
                    width: 4rem;
                }
            }
            
            /* Typography */
            h1 {
                font-size: 1.8rem;
                color: #2d3748;
            }
            h2 {
                font-size: 1.5rem;
                color: #2d3748;
            }
            h3 {
                font-size: 1.3rem;
                color: #2d3748;
            }
            h4 {
                font-size: 1.1rem;
                color: #2d3748;
                margin-top: 0;
                margin-bottom: 1rem;
            }
            h5 {
                font-size: 1rem;
                color: #2d3748;
                margin-top: 0;
                margin-bottom: 1rem;
            }
            h6 {
                font-size: 0.9rem;
                color: #2d3748;
            }
            p, li, span {
                font-size: 0.9rem;
                line-height: 1.6;
            }
            </style>
            """, unsafe_allow_html=True)
            
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
            
            # Render confidence metrics for main attributes
            st.markdown("<div style='margin-bottom: 1rem;'>", unsafe_allow_html=True)
            col1, col2, col3 = st.columns(3)
            with col1:
                title_conf = results.get("title", {}).get("confidence", 0)
                st.markdown(f'<span class="confidence-badge">Title Confidence: {title_conf:.0%}</span>', unsafe_allow_html=True)
            with col2:
                type_conf = results.get("event_type", {}).get("confidence", 0)
                st.markdown(f'<span class="confidence-badge">Event Type Confidence: {type_conf:.0%}</span>', unsafe_allow_html=True)
            with col3:
                # Calculate average confidence for descriptions
                desc_confidences = [d.get("confidence", 0) for d in results.get("descriptions", [])]
                avg_desc_conf = sum(desc_confidences)/len(desc_confidences) if desc_confidences else 0
                st.markdown(f'<span class="confidence-badge">Avg Description Confidence: {avg_desc_conf:.0%}</span>', unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)
            
            # Main timeline rendering with expanders
            
            
            st.markdown('<div class="timeline-container">', unsafe_allow_html=True)
            st.markdown('<div class="timeline-line"></div>', unsafe_allow_html=True)
            
            # Render event-level basic info (expanded by default)
            st.subheader("☀️  Event Basic Information")
            with st.expander("Event Basic Information", expanded=False):
                st.markdown('<div class="timeline-item">', unsafe_allow_html=True)
                st.markdown('<div class="timeline-dot"></div>', unsafe_allow_html=True)
                st.markdown('<div class="timeline-time-label">1630s</div>', unsafe_allow_html=True)
                
                # Event Title Details
                st.markdown("<h4>Event Title</h4>", unsafe_allow_html=True)
                st.markdown(f'<div class="data-field"><span class="field-label">Value:</span> {results.get("title", {}).get("value", "N/A")}</div>', unsafe_allow_html=True)
                st.markdown(f'<span class="confidence-badge">Confidence: {results.get("title", {}).get("confidence", 0):.0%}</span>', unsafe_allow_html=True)
                
                # Title Evidence
                if results.get("title", {}).get("evidence_source_contents"):
                    with st.expander("Title Evidence Source Contents", expanded=False):
                        for evidence in results["title"]["evidence_source_contents"]:
                            st.markdown(f'<div class="evidence-card">• {evidence}</div>', unsafe_allow_html=True)
                
                # Title Reasons
                if results.get("title", {}).get("reasons"):
                    with st.expander("Title Reasons", expanded=False):
                        st.markdown("<ul class='reasons-list'>", unsafe_allow_html=True)
                        for reason in results["title"]["reasons"]:
                            st.markdown(f"<li>{reason}</li>", unsafe_allow_html=True)
                        st.markdown("</ul>", unsafe_allow_html=True)
                
                # Event Type Details
                st.markdown("<h4>Event Type</h4>", unsafe_allow_html=True)
                st.markdown(f'<div class="data-field"><span class="field-label">Value:</span> {results.get("event_type", {}).get("value", "N/A")}</div>', unsafe_allow_html=True)
                st.markdown(f'<span class="confidence-badge">Confidence: {results.get("event_type", {}).get("confidence", 0):.0%}</span>', unsafe_allow_html=True)
                
                # Event Type Evidence
                if results.get("event_type", {}).get("evidence_source_contents"):
                    with st.expander("Event Type Evidence Source Contents", expanded=False):
                        for evidence in results["event_type"]["evidence_source_contents"]:
                            st.markdown(f'<div class="evidence-card">• {evidence}</div>', unsafe_allow_html=True)
                
                # Event Type Reasons
                if results.get("event_type", {}).get("reasons"):
                    with st.expander("Event Type Reasons", expanded=False):
                        st.markdown("<ul class='reasons-list'>", unsafe_allow_html=True)
                        for reason in results["event_type"]["reasons"]:
                            st.markdown(f"<li>{reason}</li>", unsafe_allow_html=True)
                        st.markdown("</ul>", unsafe_allow_html=True)
                
                # Event Descriptions
                st.markdown("<h4>Event Descriptions</h4>", unsafe_allow_html=True)
                for desc in results.get("descriptions", []):
                    st.markdown(f'<div class="data-field"><span class="field-label">Description:</span> {desc.get("value", "N/A")}</div>', unsafe_allow_html=True)
                    st.markdown(f'<span class="confidence-badge">Confidence: {desc.get("confidence", 0):.0%}</span>', unsafe_allow_html=True)
                    
                    # Description Evidence
                    if desc.get("evidence_source_contents"):
                        with st.expander(f"Evidence Source Contents for Description {results['descriptions'].index(desc)+1}", expanded=False):
                            for evidence in desc["evidence_source_contents"]:
                                st.markdown(f'<div class="evidence-card">• {evidence}</div>', unsafe_allow_html=True)
                    
                    # Description Reasons
                    if desc.get("reasons"):
                        with st.expander(f"Reasons for Description {results['descriptions'].index(desc)+1}", expanded=False):
                            st.markdown("<ul class='reasons-list'>", unsafe_allow_html=True)
                            for reason in desc["reasons"]:
                                st.markdown(f"<li>{reason}</li>", unsafe_allow_html=True)
                            st.markdown("</ul>", unsafe_allow_html=True)
                    st.markdown("---", unsafe_allow_html=True)
                
                # Event Time Info
                st.markdown("<h4>Event Time Information</h4>", unsafe_allow_html=True)
                st.markdown(f'<div class="data-field"><span class="field-label">Start Time:</span> {results.get("start_time", {}).get("value", "N/A")}</div>', unsafe_allow_html=True)
                if results.get("start_time", {}).get("reasons"):
                    with st.expander("Start Time Reasons", expanded=False):
                        st.markdown("<ul class='reasons-list'>", unsafe_allow_html=True)
                        for reason in results["start_time"]["reasons"]:
                            st.markdown(f"<li>{reason}</li>", unsafe_allow_html=True)
                        st.markdown("</ul>", unsafe_allow_html=True)
                
                st.markdown(f'<div class="data-field"><span class="field-label">End Time:</span> {results.get("end_time", {}).get("value", "N/A")}</div>', unsafe_allow_html=True)
                if results.get("end_time", {}).get("reasons"):
                    with st.expander("End Time Reasons", expanded=False):
                        st.markdown("<ul class='reasons-list'>", unsafe_allow_html=True)
                        for reason in results["end_time"]["reasons"]:
                            st.markdown(f"<li>{reason}</li>", unsafe_allow_html=True)
                        st.markdown("</ul>", unsafe_allow_html=True)
                
                st.markdown('</div>', unsafe_allow_html=True)


            st.subheader("⏳ Event Timeline (Stages & Episodes)")
            # Render stages and episodes in sequence (collapsed by default)
            stages = results.get("stages", [])
            for stage_idx, stage in enumerate(stages):
                stage_id = stage.get("stage_id", f"Stage {stage_idx+1}")
                stage_name = stage.get("name", {}).get("value", f"Stage {stage_idx+1}")
                stage_conf = stage.get("name", {}).get("confidence", 0)
                
                # Stage expander (collapsed by default)
                with st.expander(f"{stage_id}: {stage_name} (Confidence: {stage_conf:.0%})", expanded=False):
                    st.markdown('<div class="timeline-item">', unsafe_allow_html=True)
                    st.markdown('<div class="timeline-dot timeline-dot-stage"></div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="timeline-time-label">{stage_id}</div>', unsafe_allow_html=True)
                    
                    # Stage header
                    stage_index = stage.get('index_in_event', 0) + 1
                    st.markdown(f"<h4 class='timeline-stage-header'>Stage {stage_index}: {stage_name}</h4>", unsafe_allow_html=True)
                    
                    # Stage Basic Info
                    st.markdown(f'<div class="data-field"><span class="field-label">Stage ID:</span> {stage_id}</div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="data-field"><span class="field-label">Index in Event:</span> {stage.get("index_in_event", 0)}</div>', unsafe_allow_html=True)
                    st.markdown(f'<span class="confidence-badge">Confidence: {stage_conf:.0%}</span>', unsafe_allow_html=True)
                    
                    # Evidence
                    if stage.get("name", {}).get("evidence_source_contents"):
                        with st.expander("Evidence Source Contents", expanded=False):
                            for evidence in stage["name"]["evidence_source_contents"]:
                                st.markdown(f'<div class="evidence-card">• {evidence}</div>', unsafe_allow_html=True)
                    
                    # Reasons
                    if stage.get("name", {}).get("reasons"):
                        with st.expander("Reasons", expanded=False):
                            st.markdown("<ul class='reasons-list'>", unsafe_allow_html=True)
                            for reason in stage["name"]["reasons"]:
                                st.markdown(f"<li>{reason}</li>", unsafe_allow_html=True)
                            st.markdown("</ul>", unsafe_allow_html=True)
                    
                    # Stage Timeframe
                    st.markdown("<h5>Stage Time Information</h5>", unsafe_allow_html=True)
                    start_time = stage.get("start_time", {}).get("value", "Unknown")
                    end_time = stage.get("end_time", {}).get("value", "Unknown")
                    st.markdown(f'<div class="data-field"><span class="field-label">Start Time:</span> {start_time}</div>', unsafe_allow_html=True)
                    if stage.get("start_time", {}).get("reasons"):
                        with st.expander("Stage Start Time Reasons", expanded=False):
                            st.markdown("<ul class='reasons-list'>", unsafe_allow_html=True)
                            for reason in stage["start_time"]["reasons"]:
                                st.markdown(f"<li>{reason}</li>", unsafe_allow_html=True)
                            st.markdown("</ul>", unsafe_allow_html=True)
                    
                    st.markdown(f'<div class="data-field"><span class="field-label">End Time:</span> {end_time}</div>', unsafe_allow_html=True)
                    if stage.get("end_time", {}).get("reasons"):
                        with st.expander("Stage End Time Reasons", expanded=False):
                            st.markdown("<ul class='reasons-list'>", unsafe_allow_html=True)
                            for reason in stage["end_time"]["reasons"]:
                                st.markdown(f"<li>{reason}</li>", unsafe_allow_html=True)
                            st.markdown("</ul>", unsafe_allow_html=True)
                    
                    # Stage Descriptions
                    st.markdown("<h5>Stage Descriptions</h5>", unsafe_allow_html=True)
                    if stage.get("descriptions"):
                        for desc_idx, desc in enumerate(stage.get("descriptions", [])):
                            st.markdown(f'<div class="data-field"><span class="field-label">Description {desc_idx+1}:</span> {desc.get("value", "N/A")}</div>', unsafe_allow_html=True)
                            st.markdown(f'<span class="confidence-badge">Confidence: {desc.get("confidence", 0):.0%}</span>', unsafe_allow_html=True)
                            
                            # Description Evidence
                            if desc.get("evidence_source_contents"):
                                with st.expander(f"Evidence Source Contents for Stage Description {desc_idx+1}", expanded=False):
                                    for evidence in desc["evidence_source_contents"]:
                                        st.markdown(f'<div class="evidence-card">• {evidence}</div>', unsafe_allow_html=True)
                            
                            # Description Reasons
                            if desc.get("reasons"):
                                with st.expander(f"Reasons for Stage Description {desc_idx+1}", expanded=False):
                                    st.markdown("<ul class='reasons-list'>", unsafe_allow_html=True)
                                    for reason in desc["reasons"]:
                                        st.markdown(f"<li>{reason}</li>", unsafe_allow_html=True)
                                    st.markdown("</ul>", unsafe_allow_html=True)
                            st.markdown("---", unsafe_allow_html=True)
                    
                    # Render episodes for this stage (collapsed by default)
                    episodes = stage.get("episodes", [])
                    for episode_idx, episode in enumerate(episodes):
                        episode_id = episode.get("episode_id", f"Episode {episode_idx+1}")
                        episode_name = episode.get("name", {}).get("value", f"Episode {episode_idx+1}")
                        episode_conf = episode.get("name", {}).get("confidence", 0)
                        
                        # Episode expander (collapsed by default)
                        with st.expander(f"{episode_id}: {episode_name} (Confidence: {episode_conf:.0%})", expanded=False):
                            st.markdown('<div class="timeline-item" style="margin-left: 1rem;">', unsafe_allow_html=True)
                            st.markdown('<div class="timeline-dot timeline-dot-episode"></div>', unsafe_allow_html=True)
                            st.markdown(f'<div class="timeline-time-label">{episode_id}</div>', unsafe_allow_html=True)
                            
                            # Episode header
                            episode_index = episode.get('index_in_stage', 0) + 1
                            st.markdown(f"<h5 class='timeline-episode-header'>Episode {episode_index}: {episode_name}</h5>", unsafe_allow_html=True)
                            
                            # Episode Basic Info
                            st.markdown(f'<div class="data-field"><span class="field-label">Episode ID:</span> {episode_id}</div>', unsafe_allow_html=True)
                            st.markdown(f'<div class="data-field"><span class="field-label">Index in Stage:</span> {episode.get("index_in_stage", 0)}</div>', unsafe_allow_html=True)
                            st.markdown(f'<span class="confidence-badge">Confidence: {episode_conf:.0%}</span>', unsafe_allow_html=True)
                            
                            # Evidence
                            if episode.get("name", {}).get("evidence_source_contents"):
                                with st.expander("Evidence Source Contents", expanded=False):
                                    for evidence in episode["name"]["evidence_source_contents"]:
                                        st.markdown(f'<div class="evidence-card">• {evidence}</div>', unsafe_allow_html=True)
                            
                            # Reasons
                            if episode.get("name", {}).get("reasons"):
                                with st.expander("Reasons", expanded=False):
                                    st.markdown("<ul class='reasons-list'>", unsafe_allow_html=True)
                                    for reason in episode["name"]["reasons"]:
                                        st.markdown(f"<li>{reason}</li>", unsafe_allow_html=True)
                                    st.markdown("</ul>", unsafe_allow_html=True)
                            
                            # Episode Timeframe
                            st.markdown("<h6>Episode Time Information</h6>", unsafe_allow_html=True)
                            ep_start = episode.get("start_time", {}).get("value", "Unknown")
                            ep_end = episode.get("end_time", {}).get("value", "Unknown")
                            st.markdown(f'<div class="data-field"><span class="field-label">Start Time:</span> {ep_start}</div>', unsafe_allow_html=True)
                            if episode.get("start_time", {}).get("reasons"):
                                with st.expander("Episode Start Time Reasons", expanded=False):
                                    st.markdown("<ul class='reasons-list'>", unsafe_allow_html=True)
                                    for reason in episode["start_time"]["reasons"]:
                                        st.markdown(f"<li>{reason}</li>", unsafe_allow_html=True)
                                    st.markdown("</ul>", unsafe_allow_html=True)
                            
                            st.markdown(f'<div class="data-field"><span class="field-label">End Time:</span> {ep_end}</div>', unsafe_allow_html=True)
                            if episode.get("end_time", {}).get("reasons"):
                                with st.expander("Episode End Time Reasons", expanded=False):
                                    st.markdown("<ul class='reasons-list'>", unsafe_allow_html=True)
                                    for reason in episode["end_time"]["reasons"]:
                                        st.markdown(f"<li>{reason}</li>", unsafe_allow_html=True)
                                    st.markdown("</ul>", unsafe_allow_html=True)
                            
                            # Episode Descriptions
                            st.markdown("<h6>Episode Descriptions</h6>", unsafe_allow_html=True)
                            if episode.get("descriptions"):
                                for desc_idx, desc in enumerate(episode.get("descriptions", [])):
                                    st.markdown(f'<div class="data-field"><span class="field-label">Description {desc_idx+1}:</span> {desc.get("value", "N/A")}</div>', unsafe_allow_html=True)
                                    st.markdown(f'<span class="confidence-badge">Confidence: {desc.get("confidence", 0):.0%}</span>', unsafe_allow_html=True)
                                    
                                    # Description Evidence
                                    if desc.get("evidence_source_contents"):
                                        with st.expander(f"Evidence Source Contents for Episode Description {desc_idx+1}", expanded=False):
                                            for evidence in desc["evidence_source_contents"]:
                                                st.markdown(f'<div class="evidence-card">• {evidence}</div>', unsafe_allow_html=True)
                                    
                                    # Description Reasons
                                    if desc.get("reasons"):
                                        with st.expander(f"Reasons for Episode Description {desc_idx+1}", expanded=False):
                                            st.markdown("<ul class='reasons-list'>", unsafe_allow_html=True)
                                            for reason in desc["reasons"]:
                                                st.markdown(f"<li>{reason}</li>", unsafe_allow_html=True)
                                            st.markdown("</ul>", unsafe_allow_html=True)
                                    st.markdown("---", unsafe_allow_html=True)
                            
                            # Render Participants
                            st.markdown("<h6>Episode Participants</h6>", unsafe_allow_html=True)
                            if episode.get("participants"):
                                for participant in episode["participants"]:
                                    # st.markdown("<div class='subsection-card'>", unsafe_allow_html=True)
                                    # Participant Basic Info
                                    st.markdown(f'<div class="data-field"><span class="field-label">Participant ID:</span> {participant.get("participant_id", "N/A")}</div>', unsafe_allow_html=True)
                                    
                                    # Participant Name
                                    st.markdown(f'<div class="data-field"><span class="field-label">Name:</span> {participant.get("name", {}).get("value", "N/A")}</div>', unsafe_allow_html=True)
                                    if participant.get("name", {}).get("evidence_source_contents"):
                                        with st.expander(f"Evidence Source Contents for Participant {participant.get('participant_id', 'N/A')} Name", expanded=False):
                                            for evidence in participant["name"]["evidence_source_contents"]:
                                                st.markdown(f'<div class="evidence-card">• {evidence}</div>', unsafe_allow_html=True)
                                    if participant.get("name", {}).get("reasons"):
                                        with st.expander(f"Reasons for Participant {participant.get('participant_id', 'N/A')} Name", expanded=False):
                                            st.markdown("<ul class='reasons-list'>", unsafe_allow_html=True)
                                            for reason in participant["name"]["reasons"]:
                                                st.markdown(f"<li>{reason}</li>", unsafe_allow_html=True)
                                            st.markdown("</ul>", unsafe_allow_html=True)
                                    
                                    # Participant Type
                                    st.markdown(f'<div class="data-field"><span class="field-label">Participant Type:</span> {participant.get("participant_type", {}).get("value", "N/A")}</div>', unsafe_allow_html=True)
                                    if participant.get("participant_type", {}).get("evidence_source_contents"):
                                        with st.expander(f"Evidence Source Contents for Participant {participant.get('participant_id', 'N/A')} Type", expanded=False):
                                            for evidence in participant["participant_type"]["evidence_source_contents"]:
                                                st.markdown(f'<div class="evidence-card">• {evidence}</div>', unsafe_allow_html=True)
                                    if participant.get("participant_type", {}).get("reasons"):
                                        with st.expander(f"Reasons for Participant {participant.get('participant_id', 'N/A')} Type", expanded=False):
                                            st.markdown("<ul class='reasons-list'>", unsafe_allow_html=True)
                                            for reason in participant["participant_type"]["reasons"]:
                                                st.markdown(f"<li>{reason}</li>", unsafe_allow_html=True)
                                            st.markdown("</ul>", unsafe_allow_html=True)
                                    
                                    # Base Role
                                    st.markdown(f'<div class="data-field"><span class="field-label">Base Role:</span> {participant.get("base_role", {}).get("value", "N/A")}</div>', unsafe_allow_html=True)
                                    if participant.get("base_role", {}).get("evidence_source_contents"):
                                        with st.expander(f"Evidence Source Contents for Participant {participant.get('participant_id', 'N/A')} Role", expanded=False):
                                            for evidence in participant["base_role"]["evidence_source_contents"]:
                                                st.markdown(f'<div class="evidence-card">• {evidence}</div>', unsafe_allow_html=True)
                                    if participant.get("base_role", {}).get("reasons"):
                                        with st.expander(f"Reasons for Participant {participant.get('participant_id', 'N/A')} Role", expanded=False):
                                            st.markdown("<ul class='reasons-list'>", unsafe_allow_html=True)
                                            for reason in participant["base_role"]["reasons"]:
                                                st.markdown(f"<li>{reason}</li>", unsafe_allow_html=True)
                                            st.markdown("</ul>", unsafe_allow_html=True)
                                    
                                    # Participant Attributes
                                    if participant.get("attributes"):
                                        with st.expander(f"Attributes for Participant {participant.get('participant_id', 'N/A')}", expanded=False):
                                            for attr_key, attr_value in participant["attributes"].items():
                                                attr_name = attr_key.replace('_', ' ').title()
                                                st.markdown(f'<div class="data-field"><span class="field-label">{attr_name}:</span> {attr_value.get("value", "N/A")}</div>', unsafe_allow_html=True)
                                                if attr_value.get("evidence_source_contents"):
                                                    with st.expander(f"Evidence Source Contents for {attr_name}", expanded=False):
                                                        for evidence in attr_value["evidence_source_contents"]:
                                                            st.markdown(f'<div class="evidence-card">• {evidence}</div>', unsafe_allow_html=True)
                                                if attr_value.get("reasons"):
                                                    with st.expander(f"Reasons for {attr_name}", expanded=False):
                                                        st.markdown("<ul class='reasons-list'>", unsafe_allow_html=True)
                                                        for reason in attr_value["reasons"]:
                                                            st.markdown(f"<li>{reason}</li>", unsafe_allow_html=True)
                                                        st.markdown("</ul>", unsafe_allow_html=True)
                                    
                                    # Participant Actions
                                    if participant.get("actions"):
                                        with st.expander(f"Actions for Participant {participant.get('participant_id', 'N/A')}", expanded=False):
                                            for action in participant["actions"]:
                                                # Action Timestamp
                                                ts_value = action.get('timestamp', {}).get('value', 'Unknown')
                                                st.markdown(f'<div class="data-field"><span class="field-label">Timestamp:</span> {ts_value}</div>', unsafe_allow_html=True)
                                                if action.get("timestamp", {}).get("reasons"):
                                                    with st.expander("Timestamp Reasons", expanded=False):
                                                        st.markdown("<ul class='reasons-list'>", unsafe_allow_html=True)
                                                        for reason in action["timestamp"]["reasons"]:
                                                            st.markdown(f"<li>{reason}</li>", unsafe_allow_html=True)
                                                        st.markdown("</ul>", unsafe_allow_html=True)
                                                
                                                # Action Details
                                                if action.get("details"):
                                                    st.markdown(f'<div class="data-field"><span class="field-label">Action Details:</span></div>', unsafe_allow_html=True)
                                                    for detail in action.get("details", []):
                                                        st.markdown(f"<p>• {detail.get('value', 'N/A')}</p>", unsafe_allow_html=True)
                                                        if detail.get("evidence_source_contents"):
                                                            with st.expander(f"Evidence Source Contents for Action Detail", expanded=False):
                                                                for evidence in detail["evidence_source_contents"]:
                                                                    st.markdown(f'<div class="evidence-card">• {evidence}</div>', unsafe_allow_html=True)
                                                        if detail.get("reasons"):
                                                            with st.expander(f"Reasons for Action Detail", expanded=False):
                                                                st.markdown("<ul class='reasons-list'>", unsafe_allow_html=True)
                                                                for reason in detail["reasons"]:
                                                                    st.markdown(f"<li>{reason}</li>", unsafe_allow_html=True)
                                                                st.markdown("</ul>", unsafe_allow_html=True)
                                                st.markdown("---", unsafe_allow_html=True)
                                    st.markdown("</div>", unsafe_allow_html=True)
                                    st.markdown("---", unsafe_allow_html=True)
                            
                            # Render Participant Relations
                            st.markdown("<h6>Participant Relations</h6>", unsafe_allow_html=True)
                            if episode.get("participant_relations"):
                                for relation in episode["participant_relations"]:
                                    # st.markdown("<div class='subsection-card'>", unsafe_allow_html=True)
                                    st.markdown(f'<div class="data-field"><span class="field-label">From Participant ID:</span> {relation.get("from_participant_id", "N/A")}</div>', unsafe_allow_html=True)
                                    st.markdown(f'<div class="data-field"><span class="field-label">To Participant ID:</span> {relation.get("to_participant_id", "N/A")}</div>', unsafe_allow_html=True)
                                    
                                    # Relation Type
                                    st.markdown(f'<div class="data-field"><span class="field-label">Relation Type:</span> {relation.get("relation_type", {}).get("value", "N/A")}</div>', unsafe_allow_html=True)
                                    if relation.get("relation_type", {}).get("evidence_source_contents"):
                                        with st.expander("Relation Type Evidence", expanded=False):
                                            for evidence in relation["relation_type"]["evidence_source_contents"]:
                                                st.markdown(f'<div class="evidence-card">• {evidence}</div>', unsafe_allow_html=True)
                                    if relation.get("relation_type", {}).get("reasons"):
                                        with st.expander("Relation Type Reasons", expanded=False):
                                            st.markdown("<ul class='reasons-list'>", unsafe_allow_html=True)
                                            for reason in relation["relation_type"]["reasons"]:
                                                st.markdown(f"<li>{reason}</li>", unsafe_allow_html=True)
                                            st.markdown("</ul>", unsafe_allow_html=True)
                                    
                                    # Bidirectional
                                    st.markdown(f'<div class="data-field"><span class="field-label">Is Bidirectional:</span> {relation.get("is_bidirectional", False)}</div>', unsafe_allow_html=True)
                                    
                                    # Relation Time Info
                                    st.markdown(f'<div class="data-field"><span class="field-label">Start Time:</span> {relation.get("start_time", {}).get("value", "N/A")}</div>', unsafe_allow_html=True)
                                    if relation.get("start_time", {}).get("reasons"):
                                        with st.expander("Relation Start Time Reasons", expanded=False):
                                            st.markdown("<ul class='reasons-list'>", unsafe_allow_html=True)
                                            for reason in relation["start_time"]["reasons"]:
                                                st.markdown(f"<li>{reason}</li>", unsafe_allow_html=True)
                                            st.markdown("</ul>", unsafe_allow_html=True)
                                    
                                    st.markdown(f'<div class="data-field"><span class="field-label">End Time:</span> {relation.get("end_time", {}).get("value", "N/A")}</div>', unsafe_allow_html=True)
                                    if relation.get("end_time", {}).get("reasons"):
                                        with st.expander("Relation End Time Reasons", expanded=False):
                                            st.markdown("<ul class='reasons-list'>", unsafe_allow_html=True)
                                            for reason in relation["end_time"]["reasons"]:
                                                st.markdown(f"<li>{reason}</li>", unsafe_allow_html=True)
                                            st.markdown("</ul>", unsafe_allow_html=True)
                                    
                                    # Relation Descriptions
                                    if relation.get("descriptions"):
                                        with st.expander("Relation Descriptions", expanded=False):
                                            for desc in relation["descriptions"]:
                                                st.markdown(f"<p>• {desc.get('value', 'N/A')}</p>", unsafe_allow_html=True)
                                                if desc.get("evidence_source_contents"):
                                                    with st.expander("Description Evidence", expanded=False):
                                                        for evidence in desc["evidence_source_contents"]:
                                                            st.markdown(f'<div class="evidence-card">• {evidence}</div>', unsafe_allow_html=True)
                                                if desc.get("reasons"):
                                                    with st.expander("Description Reasons", expanded=False):
                                                        st.markdown("<ul class='reasons-list'>", unsafe_allow_html=True)
                                                        for reason in desc["reasons"]:
                                                            st.markdown(f"<li>{reason}</li>", unsafe_allow_html=True)
                                                        st.markdown("</ul>", unsafe_allow_html=True)
                                    st.markdown("</div>", unsafe_allow_html=True)
                                    st.markdown("---", unsafe_allow_html=True)
                            
                            # Render Transactions
                            st.markdown("<h6>Episode Transactions</h6>", unsafe_allow_html=True)
                            if episode.get("transactions"):
                                for transaction in episode["transactions"]:
                                    # st.markdown("<div class='subsection-card'>", unsafe_allow_html=True)
                                    # Transaction Timestamp
                                    ts_value = transaction.get('timestamp', {}).get('value', 'Unknown')
                                    st.markdown(f'<div class="data-field"><span class="field-label">Timestamp:</span> {ts_value}</div>', unsafe_allow_html=True)
                                    if transaction.get("timestamp", {}).get("reasons"):
                                        with st.expander("Transaction Timestamp Reasons", expanded=False):
                                            st.markdown("<ul class='reasons-list'>", unsafe_allow_html=True)
                                            for reason in transaction["timestamp"]["reasons"]:
                                                st.markdown(f"<li>{reason}</li>", unsafe_allow_html=True)
                                            st.markdown("</ul>", unsafe_allow_html=True)
                                    
                                    # Transaction Details
                                    if transaction.get("details"):
                                        with st.expander("Transaction Details", expanded=False):
                                            for detail in transaction["details"]:
                                                st.markdown(f"<p>• {detail.get('value', 'N/A')}</p>", unsafe_allow_html=True)
                                                if detail.get("evidence_source_contents"):
                                                    with st.expander("Detail Evidence", expanded=False):
                                                        for evidence in detail["evidence_source_contents"]:
                                                            st.markdown(f'<div class="evidence-card">• {evidence}</div>', unsafe_allow_html=True)
                                                if detail.get("reasons"):
                                                    with st.expander("Detail Reasons", expanded=False):
                                                        st.markdown("<ul class='reasons-list'>", unsafe_allow_html=True)
                                                        for reason in detail["reasons"]:
                                                            st.markdown(f"<li>{reason}</li>", unsafe_allow_html=True)
                                                        st.markdown("</ul>", unsafe_allow_html=True)
                                    
                                    # Transaction Participants
                                    from_id = transaction.get('from_participant_id', {})
                                    if isinstance(from_id, dict):
                                        from_id = from_id.get('value', 'Unknown')
                                    st.markdown(f'<div class="data-field"><span class="field-label">From Participant ID:</span> {from_id}</div>', unsafe_allow_html=True)
                                    if transaction.get("from_participant_id", {}).get("reasons"):
                                        with st.expander("From Participant Reasons", expanded=False):
                                            st.markdown("<ul class='reasons-list'>", unsafe_allow_html=True)
                                            for reason in transaction["from_participant_id"]["reasons"]:
                                                st.markdown(f"<li>{reason}</li>", unsafe_allow_html=True)
                                            st.markdown("</ul>", unsafe_allow_html=True)
                                    
                                    to_id = transaction.get('to_participant_id', {})
                                    if isinstance(to_id, dict):
                                        to_id = to_id.get('value', 'Unknown')
                                    st.markdown(f'<div class="data-field"><span class="field-label">To Participant ID:</span> {to_id}</div>', unsafe_allow_html=True)
                                    if transaction.get("to_participant_id", {}).get("reasons"):
                                        with st.expander("To Participant Reasons", expanded=False):
                                            st.markdown("<ul class='reasons-list'>", unsafe_allow_html=True)
                                            for reason in transaction["to_participant_id"]["reasons"]:
                                                st.markdown(f"<li>{reason}</li>", unsafe_allow_html=True)
                                            st.markdown("</ul>", unsafe_allow_html=True)
                                    
                                    # Transaction Instruments
                                    if transaction.get("instruments") and transaction["instruments"] is not None:
                                        with st.expander("Transaction Instruments", expanded=False):
                                            for instrument in transaction["instruments"]:
                                                if isinstance(instrument, dict):
                                                    st.markdown(f"<p>• {instrument.get('value', 'N/A')}</p>", unsafe_allow_html=True)
                                                    if instrument.get("evidence_source_contents"):
                                                        with st.expander("Instrument Evidence", expanded=False):
                                                            for evidence in instrument["evidence_source_contents"]:
                                                                st.markdown(f'<div class="evidence-card">• {evidence}</div>', unsafe_allow_html=True)
                                                    if instrument.get("reasons"):
                                                        with st.expander("Instrument Reasons", expanded=False):
                                                            st.markdown("<ul class='reasons-list'>", unsafe_allow_html=True)
                                                            for reason in instrument["reasons"]:
                                                                st.markdown(f"<li>{reason}</li>", unsafe_allow_html=True)
                                                            st.markdown("</ul>", unsafe_allow_html=True)
                                                else:
                                                    st.markdown(f"<p>• {instrument}</p>", unsafe_allow_html=True)
                                    st.markdown("</div>", unsafe_allow_html=True)
                                    st.markdown("---", unsafe_allow_html=True)
                            
                            st.markdown('</div>', unsafe_allow_html=True)
                    
                    st.markdown('</div>', unsafe_allow_html=True)
            
            st.markdown('</div>', unsafe_allow_html=True)
            
            # Summary metrics section
            st.markdown("---")
            st.subheader("Reconstruction Summary Metrics")
            
            # Calculate and display summary metrics in card containers
            col1, col2, col3 = st.columns(3)
            
            # Stage metrics
            with col1:
                st.markdown("<div class='section-card'>", unsafe_allow_html=True)
                st.markdown("**Stage Metrics**", unsafe_allow_html=True)
                total_stages = len(stages)
                st.metric("Total Stages", total_stages)
                
                avg_stage_conf = 0
                if stages:
                    avg_stage_conf = sum([s.get("name", {}).get("confidence", 0) for s in stages])/len(stages)
                st.metric("Average Stage Confidence", f"{avg_stage_conf:.0%}")
                st.markdown("</div>", unsafe_allow_html=True)
            
            # Episode metrics
            with col2:
                st.markdown("<div class='section-card'>", unsafe_allow_html=True)
                st.markdown("**Episode Metrics**", unsafe_allow_html=True)
                total_episodes = sum([len(s.get("episodes", [])) for s in stages])
                st.metric("Total Episodes", total_episodes)
                
                all_episodes = []
                for stage in stages:
                    all_episodes.extend(stage.get("episodes", []))
                
                avg_episode_conf = 0
                if all_episodes:
                    avg_episode_conf = sum([e.get("name", {}).get("confidence", 0) for e in all_episodes])/len(all_episodes)
                st.metric("Average Episode Confidence", f"{avg_episode_conf:.0%}")
                st.markdown("</div>", unsafe_allow_html=True)
            
            # Participant metrics
            with col3:
                st.markdown("<div class='section-card'>", unsafe_allow_html=True)
                st.markdown("**Participant Metrics**", unsafe_allow_html=True)
                all_participants = []
                for stage in stages:
                    for episode in stage.get("episodes", []):
                        all_participants.extend(episode.get("participants", []))
                
                # Get unique participants
                unique_participants = 0
                participant_ids = [p.get("participant_id") for p in all_participants if p.get("participant_id")]
                if participant_ids:
                    unique_participants = len(set(participant_ids))
                
                st.metric("Unique Participants", unique_participants)
                
                # Count participant types
                participant_types = {}
                for p in all_participants:
                    p_type = p.get("participant_type", {}).get("value", "unknown")
                    participant_types[p_type] = participant_types.get(p_type, 0) + 1
                st.metric("Participant Types", len(participant_types))
                st.markdown("</div>", unsafe_allow_html=True)
            
            # Export and navigation section
            st.markdown("---")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                if st.button("Export Results", use_container_width=True):
                    # Create download link for JSON
                    json_str = json.dumps(results, indent=2, ensure_ascii=False)
                    file_name = f"{results.get('event_id', 'event_reconstruction')}.json"
                    st.download_button(
                        label="Download JSON",
                        data=json_str,
                        file_name=file_name,
                        mime="application/json",
                        use_container_width=True
                    )
            
            with col2:
                if st.button("Confidence Breakdown", use_container_width=True):
                    # Display confidence breakdown in a card
                    st.markdown("<div class='section-card'>", unsafe_allow_html=True)
                    st.subheader("Confidence Breakdown")
                    
                    # Calculate all confidence metrics
                    title_conf = results.get("title", {}).get("confidence", 0)
                    type_conf = results.get("event_type", {}).get("confidence", 0)
                    desc_confidences = [d.get("confidence", 0) for d in results.get("descriptions", [])]
                    avg_desc_conf = sum(desc_confidences)/len(desc_confidences) if desc_confidences else 0
                    
                    avg_stage_conf = 0
                    if stages:
                        avg_stage_conf = sum([s.get("name", {}).get("confidence", 0) for s in stages])/len(stages)
                    
                    all_episodes = []
                    for stage in stages:
                        all_episodes.extend(stage.get("episodes", []))
                    avg_episode_conf = 0
                    if all_episodes:
                        avg_episode_conf = sum([e.get("name", {}).get("confidence", 0) for e in all_episodes])/len(all_episodes)
                    
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
            
            with col3:
                if st.button("New Reconstruction", use_container_width=True):
                    st.session_state.analysis_results = None
                    st.session_state.current_page = "Analysis"
                    st.rerun()
            
            with col4:
                if st.button("Executive Summary", use_container_width=True):
                    # Generate executive summary in a card
                    st.markdown("<div class='section-card'>", unsafe_allow_html=True)
                    st.subheader("Executive Summary")
                    
                    # Calculate summary metrics
                    total_stages = len(stages)
                    total_episodes = sum([len(s.get("episodes", [])) for s in stages])
                    
                    all_participants = []
                    for stage in stages:
                        for episode in stage.get("episodes", []):
                            all_participants.extend(episode.get("participants", []))
                    participant_ids = [p.get("participant_id") for p in all_participants if p.get("participant_id")]
                    unique_participants = len(set(participant_ids)) if participant_ids else 0
                    
                    # Calculate overall confidence
                    title_conf = results.get("title", {}).get("confidence", 0)
                    type_conf = results.get("event_type", {}).get("confidence", 0)
                    desc_confidences = [d.get("confidence", 0) for d in results.get("descriptions", [])]
                    avg_desc_conf = sum(desc_confidences)/len(desc_confidences) if desc_confidences else 0
                    
                    avg_stage_conf = 0
                    if stages:
                        avg_stage_conf = sum([s.get("name", {}).get("confidence", 0) for s in stages])/len(stages)
                    
                    all_episodes_list = []
                    for stage in stages:
                        all_episodes_list.extend(stage.get("episodes", []))
                    avg_episode_conf = 0
                    if all_episodes_list:
                        avg_episode_conf = sum([e.get("name", {}).get("confidence", 0) for e in all_episodes_list])/len(all_episodes_list)
                    
                    confidence_values = [title_conf, type_conf, avg_desc_conf, avg_stage_conf, avg_episode_conf]
                    valid_confidences = [c for c in confidence_values if c > 0]
                    overall_conf = sum(valid_confidences)/len(valid_confidences) if valid_confidences else 0
                    
                    # Generate summary content
                    summary = f"""
                    ### {results.get('title', {}).get('value', 'Unknown Event')} ({results.get('event_id', 'N/A')})
                    **Event Type:** {results.get('event_type', {}).get('value', 'N/A')}
                    
                    ### Key Overview
                    This event reconstruction details the {results.get('event_type', {}).get('value', 'speculative bubble')} known as {results.get('title', {}).get('value', 'Dutch Tulip Mania')}, which occurred in the 1630s in the Netherlands.
                    
                    ### Key Stages
                    """
                    
                    for stage in stages:
                        stage_name = stage.get('name', {}).get('value', 'N/A')
                        stage_conf = stage.get('name', {}).get('confidence', 0)
                        summary += f"\n- **Stage {stage.get('index_in_event', 0)+1}:** {stage_name} (Confidence: {stage_conf:.0%})"
                    
                    summary += f"""
                    ### Key Findings
                    - <span class='field-label'>Total stages identified:</span> {total_stages}
                    - <span class='field-label'>Total episodes documented:</span> {total_episodes}
                    - <span class='field-label'>Unique participants involved:</span> {unique_participants}
                    - <span class='field-label'>Overall reconstruction confidence:</span> {overall_conf:.0%}
                    
                    ### Critical Observations
                    The reconstruction reveals a classic speculative bubble characterized by:
                    1. Rapid price appreciation of tulip bulbs
                    2. Development of derivative trading (contracts for future delivery)
                    3. Use of bulb notes as a currency substitute
                    4. Legal disputes and settlement failures
                    5. Social and economic disruption
                    """
                    
                    st.markdown(summary, unsafe_allow_html=True)
                    st.markdown("</div>", unsafe_allow_html=True)


    def render_results_page(self):
        """Render the event reconstruction results with dynamic visualization for nested JSON structures."""
        st.title("📋 Event Reconstruction Report")
        
        if not st.session_state.analysis_results:
            st.info("No reconstruction results available. Please run an analysis first.")
            if st.button("Go to Reconstruction"):
                st.session_state.current_page = "Analysis"
                st.rerun()
            return
        
        results = st.session_state.analysis_results
        
        # Main container with custom styling
        with st.container():
            st.markdown("""
            <style>
            .reconstruction-header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                padding: 1.5rem;
                border-radius: 10px;
                color: white;
                margin-bottom: 1rem;
            }
            .section-card {
                background: white;
                padding: 1.5rem;
                border-radius: 10px;
                border-left: 4px solid #667eea;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                margin-bottom: 1rem;
            }
            .subsection-card {
                background: #f8f9fa;
                padding: 1rem;
                border-radius: 8px;
                border-left: 3px solid #764ba2;
                margin-bottom: 0.5rem;
            }
            .metric-badge {
                display: inline-block;
                background: #e3f2fd;
                color: #1976d2;
                padding: 0.25rem 0.75rem;
                border-radius: 20px;
                font-size: 0.875rem;
                margin: 0.25rem;
            }
            .timeline-item {
                border-left: 2px solid #667eea;
                padding-left: 1rem;
                margin-left: 0.5rem;
                margin-bottom: 1rem;
            }
            </style>
            """, unsafe_allow_html=True)
            
            # Reconstruction Overview
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.markdown('<div class="reconstruction-header"><h2>🎯 Event Reconstruction Complete</h2></div>', unsafe_allow_html=True)
            
            with col2:
                st.metric("Status", "RECONSTRUCTED", delta=None)
                if results.get("is_mock_data"):
                    st.warning("Using demonstration data")
            
            # Main rendering function for recursive JSON traversal
            def render_nested_data(data, level=0, parent_key=""):
                """Recursively render nested JSON data with appropriate formatting."""
                
                if isinstance(data, dict):
                    for key, value in data.items():
                        # Create a unique key for expander
                        expander_key = f"{parent_key}_{key}"
                        
                        # Format key name for display
                        display_key = " ".join(word.lower() for word in key.split("_"))
                        
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
                            # Special handling for timeline items
                            if "timeline" in parent_key.lower() or "timeline_of" in parent_key.lower():
                                st.markdown('<div class="timeline-item">', unsafe_allow_html=True)
                                if isinstance(item, str):
                                    st.markdown(f"• {item}")
                                else:
                                    render_nested_data(item, level + 1, f"{parent_key}_item{i}")
                                st.markdown('</div>', unsafe_allow_html=True)
                            else:
                                render_nested_data(item, level + 1, f"{parent_key}_item{i}")
                        else:
                            st.markdown(f"• {item}")
                else:
                    # Simple value
                    if "date" in parent_key.lower() or "year" in parent_key.lower():
                        st.markdown(f'<span class="metric-badge">📅 {data}</span>', unsafe_allow_html=True)
                    elif "amount" in parent_key.lower() or "value" in parent_key.lower():
                        st.markdown(f'<span class="metric-badge">💰 {data}</span>', unsafe_allow_html=True)
                    elif "count" in parent_key.lower() or "number" in parent_key.lower():
                        st.markdown(f'<span class="metric-badge">👥 {data}</span>', unsafe_allow_html=True)
                    else:
                        st.write(data)
            
            # Render the main reconstruction data
            render_nested_data(results)
            
            # Summary metrics section (extract key metrics dynamically)
            st.markdown("---")
            st.subheader("📈 Key Reconstruction Metrics")
            
            # Function to find and display key metrics from nested structure
            def extract_and_display_metrics(data, path=""):
                metric_keywords = ["estimate", "count", "amount", "value", "total", "percentage", "years", "currency"]
                
                if isinstance(data, dict):
                    for key, value in data.items():
                        current_path = f"{path}.{key}" if path else key
                        if any(keyword in key.lower() for keyword in metric_keywords):
                            if isinstance(value, (int, float, str)) and not isinstance(value, bool):
                                # Clean up the key name for display
                                display_name = " ".join(word.capitalize() for word in key.split("_"))
                                col1, col2, col3 = st.columns([2, 2, 1])
                                with col1:
                                    st.markdown(f"**{display_name}**")
                                with col2:
                                    st.info(value)
                                with col3:
                                    # Add appropriate icon
                                    if "percentage" in key.lower():
                                        st.markdown("📊")
                                    elif "currency" in key.lower():
                                        st.markdown("💱")
                                    else:
                                        st.markdown("📈")
                        elif isinstance(value, (dict, list)):
                            extract_and_display_metrics(value, current_path)
            
            # Create metrics in columns
            metrics_col1, metrics_col2, metrics_col3 = st.columns(3)
            
            # Find and organize metrics by category
            def find_metrics_by_category(data, category_keywords):
                metrics = {}
                if isinstance(data, dict):
                    for key, value in data.items():
                        if any(cat in key.lower() for cat in category_keywords):
                            if isinstance(value, (dict, list)):
                                # Recursively search for numeric values
                                def find_nested_values(obj):
                                    found = []
                                    if isinstance(obj, dict):
                                        for k, v in obj.items():
                                            if isinstance(v, (int, float, str)) and not isinstance(v, bool):
                                                found.append((k, v))
                                            elif isinstance(v, (dict, list)):
                                                found.extend(find_nested_values(v))
                                    elif isinstance(obj, list):
                                        for item in obj:
                                            found.extend(find_nested_values(item))
                                    return found
                                nested = find_nested_values(value)
                                if nested:
                                    metrics[key] = nested[:3]  # Limit to top 3
                return metrics
            
            # Extract different types of metrics
            financial_metrics = find_metrics_by_category(results, ["amount", "value", "total", "currency"])
            demographic_metrics = find_metrics_by_category(results, ["count", "victim", "investor"])
            temporal_metrics = find_metrics_by_category(results, ["year", "date", "duration", "timeframe"])
            
            # Display in columns
            with metrics_col1:
                st.markdown("**💰 Financial Metrics**")
                for category, values in financial_metrics.items():
                    with st.expander(f"Financial {category.replace('_', ' ').title()}"):
                        for key, value in values:
                            st.metric(key.replace('_', ' ').title(), str(value))
            
            with metrics_col2:
                st.markdown("**👥 Demographic Impact**")
                for category, values in demographic_metrics.items():
                    with st.expander(f"Demographic {category.replace('_', ' ').title()}"):
                        for key, value in values:
                            st.metric(key.replace('_', ' ').title(), str(value))
            
            with metrics_col3:
                st.markdown("**⏳ Temporal Metrics**")
                for category, values in temporal_metrics.items():
                    with st.expander(f"Temporal {category.replace('_', ' ').title()}"):
                        for key, value in values:
                            st.metric(key.replace('_', ' ').title(), str(value))
            
            # Export and navigation section
            st.markdown("---")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                if st.button("📥 Export as JSON", use_container_width=True):
                    # Create download link for JSON
                    json_str = json.dumps(results, indent=2, ensure_ascii=False)
                    st.download_button(
                        label="Download JSON",
                        data=json_str,
                        file_name="event_reconstruction.json",
                        mime="application/json"
                    )
            
            with col2:
                if st.button("📊 View Timeline", use_container_width=True):
                    # Extract timeline if exists
                    timeline_data = self.extract_timeline_data(results)
                    if timeline_data:
                        self.render_timeline_visualization(timeline_data)
                    else:
                        st.info("No timeline data found in reconstruction")
            
            with col3:
                if st.button("🔄 New Reconstruction", use_container_width=True):
                    st.session_state.analysis_results = None
                    st.session_state.current_page = "Analysis"
                    st.rerun()
            
            with col4:
                if st.button("📋 Executive Summary", use_container_width=True):
                    self.render_executive_summary(results)

    def extract_timeline_data(self, data):
        """Extract timeline data from nested structure."""
        timeline_items = []
        
        def search_for_timeline(obj, path=""):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if "timeline" in key.lower() and isinstance(value, list):
                        timeline_items.extend(value)
                    elif isinstance(value, (dict, list)):
                        search_for_timeline(value, f"{path}.{key}")
            elif isinstance(obj, list):
                for item in obj:
                    search_for_timeline(item, path)
        
        search_for_timeline(data)
        return timeline_items

    def render_timeline_visualization(self, timeline_data):
        """Render a timeline visualization."""
        st.subheader("⏳ Event Timeline")
        
        for i, item in enumerate(timeline_data):
            col1, col2 = st.columns([1, 3])
            with col1:
                st.markdown(f"**Step {i+1}**")
            with col2:
                st.markdown(f'<div class="timeline-item">{item}</div>', unsafe_allow_html=True)

    def render_executive_summary(self, data):
        """Generate and render an executive summary from the reconstruction."""
        st.subheader("📋 Executive Summary")
        
        # Extract key information from metadata
        summary_points = []
        
        def extract_summary_info(obj, path=""):
            if isinstance(obj, dict):
                # Look for key summary information
                summary_keys = ["summary", "overview", "key_findings", "conclusion", "impact"]
                for key in summary_keys:
                    if key in obj and isinstance(obj[key], (str, list)):
                        summary_points.append(obj[key])
                
                # Recursively search for other important info
                for key, value in obj.items():
                    if key in ["name", "title", "description", "result", "outcome"]:
                        if isinstance(value, str) and len(value) < 200:  # Avoid too long strings
                            summary_points.append(f"{key}: {value}")
                    elif isinstance(value, (dict, list)):
                        extract_summary_info(value, f"{path}.{key}")
        
        extract_summary_info(data)
        
        # Display summary points
        for i, point in enumerate(summary_points[:10]):  # Limit to 10 points
            if isinstance(point, list):
                for subpoint in point[:3]:  # Limit nested lists
                    st.markdown(f"- {subpoint}")
            else:
                st.markdown(f"{i+1}. {point}")


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
            if st.session_state.build_mode == "class_build" or st.session_state.build_mode is None:
                self.render_results_page()
            elif st.session_state.build_mode == "agent_build":
                self.render_results_page_agent()
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
