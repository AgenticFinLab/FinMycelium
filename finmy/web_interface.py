"""
Web interface for FinMycelium - Financial Fraud Analysis System
Provides a user-friendly interface for analyzing financial fraud cases
through multiple data sources and AI-powered analysis.
"""

import os
import sys
import asyncio
import random
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional

import streamlit as st
from streamlit_option_menu import option_menu
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

# Load environment variables
load_dotenv(project_root / '.env')

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
        self.setup_ai_client()
        
    def setup_page_config(self):
        """Configure Streamlit page settings for optimal user experience."""
        st.set_page_config(
            page_title="FinMycelium - Financial Fraud Analysis",
            page_icon="🕵️",
            layout="wide",
            initial_sidebar_state="expanded"
        )
        
    def initialize_session_state(self):
        """Initialize session state variables for maintaining state across interactions."""
        if 'analysis_results' not in st.session_state:
            st.session_state.analysis_results = None
        if 'processing_status' not in st.session_state:
            st.session_state.processing_status = 'idle'
        if 'uploaded_files' not in st.session_state:
            st.session_state.uploaded_files = []
        if 'selected_fraud_type' not in st.session_state:
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
                "Database Manager": DatabaseManager is not None,
                "Generic Processor": GenericProcessor is not None,
                "AI Analysis": self.ai_client is not None
            }
            
            for module, available in modules_status.items():
                status_icon = "✅" if available else "🔄"
                st.write(f"{status_icon} {module}")
                
            st.markdown("---")
            st.caption("Financial Fraud Analysis System v1.0")
            
    def render_home_page(self):
        """Render the home page with system overview and quick start options."""
        st.title("Welcome to FinMycelium")
        st.markdown("""
        ### Comprehensive Financial Fraud Analysis Platform
        
        FinMycelium helps you analyze and understand financial fraud schemes 
        through advanced AI-powered analysis of multiple data sources.
        """)
        
        # Features overview
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.subheader("🔍 Multi-Source Analysis")
            st.markdown("""
            - Web content collection
            - Document processing (PDF/Word)
            - Social media monitoring
            - Structured data analysis
            """)
            
        with col2:
            st.subheader("🤖 AI-Powered Insights")
            st.markdown("""
            - Fraud pattern recognition
            - Timeline reconstruction
            - Impact assessment
            - Educational insights
            """)
            
        with col3:
            st.subheader("📊 Comprehensive Reporting")
            st.markdown("""
            - Visual analytics
            - Key findings summary
            - Risk assessment
            - Prevention recommendations
            """)
        
        st.markdown("---")
        
        # Quick start section
        st.subheader("Get Started")
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown("""
            **Start your analysis in 3 simple steps:**
            1. **Select** fraud type from our comprehensive taxonomy
            2. **Provide** data through keywords, documents, or URLs
            3. **Analyze** with our AI-powered fraud detection system
            """)
            
        with col2:
            if st.button("Start Analysis", type="primary", use_container_width=True):
                st.session_state.current_page = "Analysis"
                st.rerun()
                
    def render_analysis_page(self):
        """Render the analysis page with fraud type selection and data input options."""
        st.title("Financial Fraud Analysis")
        st.markdown("Provide details about the fraud case you want to analyze.")
        
        # Fraud type selection
        fraud_types = [
            "Ponzi Scheme",
            "Pyramid Scheme", 
            "Investment Fraud",
            "Cryptocurrency Scam",
            "Banking Fraud",
            "Insurance Fraud",
            "Securities Fraud",
            "Other Financial Fraud"
        ]
        
        selected_fraud_type = st.selectbox(
            "Select Fraud Type*",
            options=[""] + fraud_types,
            help="Choose the most relevant category for the fraud case"
        )
        
        if selected_fraud_type:
            st.session_state.selected_fraud_type = selected_fraud_type
            
        st.markdown("---")
        
        # Data input methods
        st.subheader("Data Input Methods")
        st.markdown("Choose one or more methods to provide case information:")
        
        # Input method selection
        input_methods = st.multiselect(
            "Select Input Methods*",
            options=["Keywords", "Documents", "Structured Data", "URLs"],
            default=["Keywords"],
            help="Select at least one method to provide case data"
        )
        
        # Keyword input
        if "Keywords" in input_methods:
            self.render_keyword_input()
            
        # Document upload
        if "Documents" in input_methods:
            self.render_document_upload()
            
        # Structured data upload
        if "Structured Data" in input_methods:
            self.render_structured_data_upload()
            
        # URL input (placeholder for URL collector)
        if "URLs" in input_methods:
            self.render_url_input()
            
        st.markdown("---")
        
        # Analysis controls
        self.render_analysis_controls()
        
    def render_keyword_input(self):
        """Render keyword input section with validation and suggestions."""
        st.subheader("🔤 Keyword Analysis")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            keywords = st.text_area(
                "Enter relevant keywords, phrases, or case descriptions:",
                placeholder="e.g., high-yield investment, guaranteed returns, crypto mining scheme...",
                help="Provide specific terms related to the fraud case for comprehensive analysis"
            )
            
        with col2:
            st.markdown("**Keyword Tips:**")
            st.markdown("""
            - Company/Project names
            - Promised returns
            - Investment methods
            - Key individuals
            - Platform names
            """)
            
        if keywords:
            st.session_state.keywords = [k.strip() for k in keywords.split(',') if k.strip()]
            
    def render_document_upload(self):
        """Render document upload section with file type validation."""
        st.subheader("📄 Document Analysis")
        
        uploaded_files = st.file_uploader(
            "Upload PDF or Word documents:",
            type=['pdf', 'docx', 'doc'],
            accept_multiple_files=True,
            help="Upload relevant documents, reports, or evidence files"
        )
        
        if uploaded_files:
            for file in uploaded_files:
                if file.name not in [f.name for f in st.session_state.uploaded_files]:
                    st.session_state.uploaded_files.append(file)
                    
            st.info(f"📎 {len(uploaded_files)} document(s) ready for analysis")
            
            # Show uploaded files
            for file in uploaded_files:
                st.write(f"• {file.name} ({file.size / 1024:.1f} KB)")
                
    def render_structured_data_upload(self):
        """Render structured data upload with format validation."""
        st.subheader("📊 Structured Data Analysis")
        
        uploaded_file = st.file_uploader(
            "Upload Excel, CSV, or JSON file:",
            type=['xlsx', 'csv', 'json'],
            help="File must contain 'title' and 'url' columns/fields"
        )
        
        if uploaded_file:
            try:
                if uploaded_file.name.endswith('.csv'):
                    df = pd.read_csv(uploaded_file)
                elif uploaded_file.name.endswith('.xlsx'):
                    df = pd.read_excel(uploaded_file)
                elif uploaded_file.name.endswith('.json'):
                    df = pd.read_json(uploaded_file)
                    
                # Validate required columns
                if 'title' in df.columns and 'url' in df.columns:
                    st.success("✅ File structure validated")
                    st.dataframe(df.head(), use_container_width=True)
                    st.session_state.structured_data = df
                else:
                    st.error("❌ File must contain 'title' and 'url' columns")
                    
            except Exception as e:
                st.error(f"Error processing file: {e}")
                
    def render_url_input(self):
        """Render URL input section (placeholder for URL collector module)."""
        st.subheader("🌐 URL Analysis")
        st.info("🔧 URL collection module is under development")
        
        urls = st.text_area(
            "Enter relevant URLs (one per line):",
            placeholder="https://example.com/fraud-case\nhttps://news.site.com/scam-report",
            help="Provide URLs to relevant web pages, news articles, or social media posts"
        )
        
        if urls:
            st.session_state.urls = [url.strip() for url in urls.split('\n') if url.strip()]
            
    def render_analysis_controls(self):
        """Render analysis control buttons and status indicators."""
        col1, col2, col3 = st.columns([1, 1, 1])
        
        with col2:
            if st.button("🚀 Start Analysis", type="primary", use_container_width=True):
                if self.validate_analysis_inputs():
                    self.run_analysis()
                else:
                    st.error("Please provide required inputs before starting analysis")
                    
        # Status indicator
        if st.session_state.processing_status != 'idle':
            status_placeholder = st.empty()
            with status_placeholder.container():
                if st.session_state.processing_status == 'processing':
                    st.info("🔄 Analysis in progress... This may take a few minutes.")
                elif st.session_state.processing_status == 'completed':
                    st.success("✅ Analysis completed!")
                elif st.session_state.processing_status == 'error':
                    st.error("❌ Analysis failed. Please try again.")
                    
    def validate_analysis_inputs(self) -> bool:
        """Validate that required inputs are provided for analysis."""
        if not st.session_state.selected_fraud_type:
            st.error("Please select a fraud type")
            return False
            
        has_keywords = hasattr(st.session_state, 'keywords') and st.session_state.keywords
        has_documents = hasattr(st.session_state, 'uploaded_files') and st.session_state.uploaded_files
        has_structured_data = hasattr(st.session_state, 'structured_data') and st.session_state.structured_data is not None
        has_urls = hasattr(st.session_state, 'urls') and st.session_state.urls
        
        if not any([has_keywords, has_documents, has_structured_data, has_urls]):
            st.error("Please provide at least one data source for analysis")
            return False
            
        return True
        
    def run_analysis(self):
        """Execute the fraud analysis pipeline with provided inputs."""
        st.session_state.processing_status = 'processing'
        
        try:
            # Collect analysis inputs
            analysis_inputs = {
                'fraud_type': st.session_state.selected_fraud_type,
                'keywords': getattr(st.session_state, 'keywords', []),
                'documents': getattr(st.session_state, 'uploaded_files', []),
                'structured_data': getattr(st.session_state, 'structured_data', None),
                'urls': getattr(st.session_state, 'urls', [])
            }
            
            # Process with AI analysis
            results = self.perform_ai_analysis(analysis_inputs)
            
            # Store results
            st.session_state.analysis_results = results
            st.session_state.processing_status = 'completed'
            
            # Navigate to results page
            st.session_state.current_page = "Results"
            st.rerun()
            
        except Exception as e:
            st.error(f"Analysis failed: {e}")
            st.session_state.processing_status = 'error'
            
    def perform_ai_analysis(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform AI-powered fraud analysis using the provided inputs.
        
        Args:
            inputs: Dictionary containing fraud type and data sources
            
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
                        "content": "Always respond in Chinese. You are a financial fraud analysis expert. Provide comprehensive, educational analysis of financial fraud schemes."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
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
            return self.parse_analysis_results(analysis_text, inputs)
            
        except Exception as e:
            st.error(f"AI analysis error: {e}")
            return self.get_mock_analysis_results(inputs)
            
    def construct_analysis_prompt(self, inputs: Dict[str, Any]) -> str:
        """Construct detailed prompt for fraud analysis."""
        fraud_type = inputs['fraud_type']
        keywords = inputs['keywords']
        
        prompt = f"""
        As a financial fraud analysis expert, analyze the following {fraud_type} case:
        
        KEYWORDS/CASE DESCRIPTION: {', '.join(keywords) if keywords else 'Not provided'}
        
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
        
    def parse_analysis_results(self, analysis_text: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Parse AI response into structured results format."""
        return {
            'fraud_type': inputs['fraud_type'],
            'summary': analysis_text,
            'key_findings': self.extract_key_findings(analysis_text),
            'risk_factors': self.extract_risk_factors(analysis_text),
            'prevention_tips': self.extract_prevention_tips(analysis_text),
            'analysis_timestamp': pd.Timestamp.now().isoformat()
        }
        
    def extract_key_findings(self, analysis: str) -> List[str]:
        """Extract key findings from analysis text."""
        # Simplified extraction - in practice, use more sophisticated NLP
        sentences = [s.strip() for s in analysis.split('.') if s.strip()]
        return sentences[:5]  # Return first 5 sentences as key findings
        
    def extract_risk_factors(self, analysis: str) -> List[str]:
        """Extract risk factors from analysis text."""
        risk_indicators = ['high return', 'guaranteed', 'risk', 'warning', 'red flag', 'suspicious']
        sentences = [s.strip() for s in analysis.split('.') if any(indicator in s.lower() for indicator in risk_indicators)]
        return sentences[:3]
        
    def extract_prevention_tips(self, analysis: str) -> List[str]:
        """Extract prevention tips from analysis text."""
        prevention_indicators = ['prevent', 'avoid', 'protect', 'check', 'verify', 'due diligence']
        sentences = [s.strip() for s in analysis.split('.') if any(indicator in s.lower() for indicator in prevention_indicators)]
        return sentences[:3] if sentences else [
            "Always verify investment opportunities with regulatory authorities",
            "Be skeptical of guaranteed high returns",
            "Consult with financial advisors before making significant investments"
        ]
        
    def get_mock_analysis_results(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Provide mock analysis results when AI service is unavailable."""
        return {
            'fraud_type': inputs['fraud_type'],
            'summary': f"This is a mock analysis for {inputs['fraud_type']}. In a real scenario, this would contain comprehensive AI-generated insights about the fraud pattern, mechanisms, and prevention strategies.",
            'key_findings': [
                "Mock finding 1: Typical characteristics of this fraud type",
                "Mock finding 2: Common recruitment methods used",
                "Mock finding 3: Financial impact on victims"
            ],
            'risk_factors': [
                "High promised returns with low risk",
                "Lack of regulatory compliance",
                "Pressure to recruit others"
            ],
            'prevention_tips': [
                "Verify all investment opportunities with financial regulators",
                "Be cautious of guaranteed high returns",
                "Consult independent financial advisors"
            ],
            'analysis_timestamp': pd.Timestamp.now().isoformat(),
            'is_mock_data': True
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
            st.subheader(f"Fraud Type: {results['fraud_type']}")
            
        with col2:
            st.metric("Analysis Status", "Completed")
            if results.get('is_mock_data'):
                st.warning("Using demonstration data")
                
        st.markdown("---")
        
        # Key findings
        st.subheader("🔍 Key Findings")
        for i, finding in enumerate(results['key_findings'], 1):
            st.markdown(f"{i}. {finding}")
            
        st.markdown("---")
        
        # Detailed analysis
        st.subheader("📊 Detailed Analysis")
        with st.expander("View Complete Analysis", expanded=True):
            st.write(results['summary'])
            
        # Risk factors and prevention
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("⚠️ Risk Factors")
            for risk in results['risk_factors']:
                st.markdown(f"• {risk}")
                
        with col2:
            st.subheader("🛡️ Prevention Tips")
            for tip in results['prevention_tips']:
                st.markdown(f"• {tip}")
                
        st.markdown("---")
        
        # Educational insights
        st.subheader("🎓 Educational Insights")
        self.render_educational_insights(results)
        
        # Action buttons
        col1, col2, col3 = st.columns(3)
        with col2:
            if st.button("🔄 New Analysis", use_container_width=True):
                st.session_state.analysis_results = None
                st.session_state.current_page = "Analysis"
                st.rerun()
                
    def render_educational_insights(self, results: Dict[str, Any]):
        """Render educational insights section with fraud-specific information."""
        fraud_type = results['fraud_type']
        
        insights_data = {
            "Ponzi Scheme": {
                "definition": "Pays returns to earlier investors with funds from more recent investors",
                "warning_signs": ["Consistent high returns regardless of market conditions", "Complex or secretive strategies", "Difficulty receiving payments"],
                "historical_examples": ["Bernie Madoff (2008)", "Charles Ponzi (1920)"]
            },
            "Pyramid Scheme": {
                "definition": "Relies on recruiting more participants for returns rather than legitimate business activities",
                "warning_signs": ["Emphasis on recruitment over product sales", "Promises of high returns for minimal work", "Complex compensation structures"],
                "historical_examples": ["Herbalife (settled 2016)", "Fortune Hi-Tech Marketing (2013)"]
            },
            "Investment Fraud": {
                "definition": "Deceptive practices that induce investors to make purchase decisions based on false information",
                "warning_signs": ["Unsolicited investment offers", "Pressure to act quickly", "Unregistered investments"],
                "historical_examples": ["Enron scandal (2001)", "WorldCom (2002)"]
            }
        }
        
        if fraud_type in insights_data:
            insights = insights_data[fraud_type]
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown(f"**Definition:** {insights['definition']}")
                st.markdown("**Warning Signs:**")
                for sign in insights['warning_signs']:
                    st.markdown(f"• {sign}")
                    
            with col2:
                st.markdown("**Historical Examples:**")
                for example in insights['historical_examples']:
                    st.markdown(f"• {example}")
                    
            st.markdown("""
            **Protect Yourself:**
            - Always research investment opportunities thoroughly
            - Verify company registration with regulatory authorities
            - Be skeptical of guaranteed high returns
            - Consult with licensed financial advisors
            """)
        else:
            st.info("""
            **General Fraud Prevention Tips:**
            - Verify all investment opportunities with relevant authorities
            - Be cautious of unsolicited investment offers
            - Understand that high returns typically involve high risks
            - Don't invest in anything you don't fully understand
            - Seek independent financial advice before investing
            """)
            
    def render_about_page(self):
        """Render the about page with system information and usage guidelines."""
        st.title("About FinMycelium")
        
        st.markdown("""
        ### Financial Fraud Analysis and Education Platform
        
        FinMycelium is an advanced AI-powered system designed to analyze financial fraud schemes 
        and provide comprehensive educational insights to help protect consumers and investors.
        """)
        
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("System Capabilities")
            st.markdown("""
            - **Multi-source Data Analysis**: Process keywords, documents, and structured data
            - **AI-Powered Pattern Recognition**: Identify fraud mechanisms and characteristics
            - **Comprehensive Reporting**: Generate detailed analysis with risk assessments
            - **Educational Content**: Provide prevention tips and warning signs
            - **User-Friendly Interface**: Intuitive workflow for all user levels
            """)
            
        with col2:
            st.subheader("Methodology")
            st.markdown("""
            - **Data Collection**: Aggregate information from multiple sources
            - **Pattern Analysis**: Identify common fraud characteristics
            - **Risk Assessment**: Evaluate potential impacts and warning signs
            - **Educational Synthesis**: Create understandable prevention guidance
            - **Continuous Learning**: Adapt to new fraud patterns and techniques
            """)
            
        st.markdown("---")
        
        st.subheader("Usage Guidelines")
        st.markdown("""
        - **For Educational Purposes**: This tool is designed for educational and research purposes
        - **Consult Professionals**: Always consult licensed financial advisors for investment decisions
        - **Verify Information**: Cross-check findings with official regulatory sources
        - **Report Suspected Fraud**: Report potential fraud to relevant authorities
        - **Continuous Learning**: Financial fraud patterns evolve constantly - stay informed
        """)
        
        st.markdown("---")
        
        st.caption("""
        FinMycelium v1.0 | Financial Fraud Analysis System | 
        For educational and research purposes only.
        """)
        
    def run(self):
        """Main method to run the web interface application."""
        self.render_sidebar()
        
        current_page = st.session_state.get('current_page', 'Home')
        
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