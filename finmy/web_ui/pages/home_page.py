"""
Home page renderer.
"""

import streamlit as st


class HomePage:
    """Home page component."""
    
    @staticmethod
    def render():
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
            - PDF Document processing
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

