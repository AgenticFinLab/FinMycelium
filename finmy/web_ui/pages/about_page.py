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
            ### Multi-Agent Financial Event Reconstruction System
            
            FinMycelium leverages a sophisticated **multi-agent architecture** to reconstruct 
            and analyze complex financial events from diverse data sources, providing in-depth 
            insights for educational and research purposes.
            """
        )
        
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Multi-Agent System Capabilities")
            st.markdown(
                """
            - **Distributed Agent Architecture**: Specialized agents working in coordinated pipelines
            - **Advanced Event Reconstruction**: Multi-agent collaboration for timeline and relationship mapping
            - **Intelligent Data Processing**: LLM-powered agents for context-aware analysis
            - **Adaptive Learning**: Agents continuously improve through collective knowledge
            - **Scalable Design**: Modular architecture for easy extension and customization
            """
            )
        
        with col2:
            st.subheader("Multi-Agent Methodology")
            st.markdown(
                """
            - **Specialized Agent Deployment**: Task-specific agents activated for different stages
            - **Coordinated Event Processing**: Agents collaborate through defined communication protocols
            - **Contextual Knowledge Sharing**: Shared knowledge base for consistent analysis
            - **AI-Driven Decision Making**: LLM-powered agents for complex pattern recognition
            - **Structured Event Reconstruction**: Systematic assembly of event components into cascades
            """
            )
        
        st.markdown("---")
        
        st.subheader("Usage Guidelines")
        st.markdown(
            """
        - **For Educational Purposes**: This multi-agent system is designed for educational and research purposes
        - **Consult Professionals**: Always consult licensed financial advisors for investment decisions
        - **Verify Information**: Cross-check multi-agent findings with official regulatory sources
        - **Report Suspected Event**: Report potential event to relevant authorities
        - **Leverage Multi-Agent Insights**: Use comprehensive event reconstructions for deeper understanding
        """
        )
        
        st.markdown("---")
        
        st.caption(
            """
        FinMycelium v1.0 | Multi-Agent Financial Event Reconstruction System | 
        For educational and research purposes only.
        """
        )

