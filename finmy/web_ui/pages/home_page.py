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
            ### 🌿 Multi-Agent Financial Event Reconstruction Platform
            
            **FinMycelium** is a cutting-edge **multi-agent system** designed specifically for 
            reconstructing and analyzing complex financial events. Powered by intelligent agents 
            working in coordination, it transforms diverse financial data sources into structured 
            event cascades with unparalleled accuracy and efficiency.
            """
        )
        
        # Features overview
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.subheader("🤖 Multi-Agent System")
            st.markdown(
                """
            - Coordinated agent pipeline
            - Specialized agent roles
            - Intelligent task allocation
            - Autonomous decision making
            """
            )
        
        with col2:
            st.subheader("🔍 Financial Event Reconstruction")
            st.markdown(
                """
            - Event type recognition
            - Timeline reconstruction
            - Multi-source event matching
            - Causal relationship analysis
            """
            )
        
        with col3:
            st.subheader("📊 Advanced Analytics")
            st.markdown(
                """
            - Visual event cascades
            - Key insights extraction
            - Risk assessment
            - Structured reporting
            """
            )
        
        st.markdown("---")
        
        col1, col2, col3 = st.columns([1, 1, 1])
        
        with col2:
            st.subheader("Get Started with Multi-Agent Analysis")
            st.markdown(
                """
            **Start your financial event reconstruction in 3 simple steps:**
            1. **Input** event-related information or keywords
            2. **Provide** data sources (Web URLs, PDFs, structured files)
            3. **Analyze** with our Multi-Agent Financial Event Reconstruction system
            """
            )

