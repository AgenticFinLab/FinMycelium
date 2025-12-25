"""
About page renderer.
"""

import streamlit as st


class AboutPage:
    """About page component."""
    
    @staticmethod
    def render():
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

