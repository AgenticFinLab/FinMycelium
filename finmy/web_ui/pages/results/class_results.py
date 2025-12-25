"""
Class-based results renderer.
"""

import json
import streamlit as st


class ClassResultsRenderer:
    """Renderer for class-based event reconstruction results."""
    
    @staticmethod
    def render(results: dict):
        """Render class-based results with dynamic JSON visualization."""
        st.title("📋 Event Reconstruction Report")
        
        # Overview
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.markdown(
                '<div class="reconstruction-header"><h2>🎯 Event Reconstruction Complete</h2></div>',
                unsafe_allow_html=True,
            )
        
        with col2:
            st.metric("Status", "RECONSTRUCTED", delta=None)
            if results.get("is_mock_data"):
                st.warning("Using demonstration data")
        
        # Render nested data
        ClassResultsRenderer._render_nested_data(results)
        
        # Summary metrics
        ClassResultsRenderer._render_summary_metrics(results)
        
        # Export options
        ClassResultsRenderer._render_export_options(results)
    
    @staticmethod
    def _render_nested_data(data: dict, level: int = 0, parent_key: str = ""):
        """Recursively render nested JSON data."""
        if isinstance(data, dict):
            for key, value in data.items():
                expander_key = f"{parent_key}_{key}"
                display_key = " ".join(word.capitalize() for word in key.split("_"))
                
                if isinstance(value, (dict, list)) and value:
                    if level == 0:
                        with st.expander(f"### 📊 {display_key}", expanded=True):
                            ClassResultsRenderer._render_nested_data(
                                value, level + 1, expander_key
                            )
                    elif level == 1:
                        st.markdown(
                            f'<div class="section-card"><h4>{display_key}</h4></div>',
                            unsafe_allow_html=True,
                        )
                        ClassResultsRenderer._render_nested_data(
                            value, level + 1, expander_key
                        )
                    else:
                        with st.expander(f"**{display_key}**"):
                            ClassResultsRenderer._render_nested_data(
                                value, level + 1, expander_key
                            )
                else:
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
                    ClassResultsRenderer._render_nested_data(
                        item, level + 1, f"{parent_key}_item{i}"
                    )
                else:
                    st.markdown(f"• {item}")
        else:
            st.write(data)
    
    @staticmethod
    def _render_summary_metrics(results: dict):
        """Render summary metrics."""
        st.markdown("---")
        st.subheader("📈 Key Reconstruction Metrics")
        
        # Extract and display key metrics
        metrics_col1, metrics_col2, metrics_col3 = st.columns(3)
        
        with metrics_col1:
            st.markdown("**💰 Financial Metrics**")
            # Extract financial metrics from results
        
        with metrics_col2:
            st.markdown("**👥 Demographic Impact**")
            # Extract demographic metrics from results
        
        with metrics_col3:
            st.markdown("**⏳ Temporal Metrics**")
            # Extract temporal metrics from results
    
    @staticmethod
    def _render_export_options(results: dict):
        """Render export options."""
        st.markdown("---")
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📥 Export as JSON", use_container_width=True):
                json_str = json.dumps(results, indent=2, ensure_ascii=False)
                st.download_button(
                    label="Download JSON",
                    data=json_str,
                    file_name="event_reconstruction.json",
                    mime="application/json",
                )

