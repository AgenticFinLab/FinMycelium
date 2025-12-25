"""
Agent-based results renderer.
"""

import os
import json
import logging
import streamlit as st

from finmy.builder.agent_build.visualizer_gantt import EventCascadeGanttVisualizer


class AgentResultsRenderer:
    """Renderer for agent-based event reconstruction results."""
    
    @staticmethod
    def render(results: dict):
        """
        Render agent-based results.
        
        Note: This is a simplified version. The full implementation from the original
        file can be imported or extended as needed.
        """
        st.title("📋 Event Reconstruction Report")
        
        # Display save path
        if st.session_state.get("save_builder_dir_path"):
            unified_path = str(st.session_state.save_builder_dir_path).replace("\\", "/")
            st.success(f"Success: Builder Files are saved to {unified_path}")
        
        # Generate visualization
        AgentResultsRenderer._generate_visualization(results)
        
        # Render overview
        AgentResultsRenderer._render_overview(results)
        
        # Render timeline
        AgentResultsRenderer._render_timeline(results)
        
        # Render summary metrics
        AgentResultsRenderer._render_summary_metrics(results)
        
        # Export options
        AgentResultsRenderer._render_export_options(results)
    
    @staticmethod
    def _generate_visualization(results: dict):
        """Generate and display Gantt chart visualization."""
        st.subheader("📅 Event Timeline Visualization")
        
        try:
            viz = EventCascadeGanttVisualizer()
            viz_output_dir = st.session_state.save_builder_dir_path
            viz_output_path = os.path.join(
                viz_output_dir, "FinalEventCascade_gantt.html"
            )
            
            logging.info(f"Generating Gantt Chart to {viz_output_path}...")
            viz.plot_cascade(results, viz_output_path)
            
            if os.path.exists(viz_output_path):
                logging.info("Success: HTML file generated.")
                st.markdown(
                    f"""
                    #### View Instructions:
                    
                    1. **Download the file** using the button below
                    2. **Open it directly** from your file explorer
                    3. **Or access it at:** `{os.path.abspath(viz_output_path)}`
                    """
                )
                
                with open(viz_output_path, "rb") as file:
                    st.download_button(
                        label="📥 Download & Open Timeline HTML",
                        data=file,
                        file_name="event_timeline.html",
                        mime="text/html",
                        key="timeline_download",
                    )
            else:
                st.error("HTML file not found. Please generate the visualization first.")
        except Exception as e:
            logging.error(f"Error generating visualization: {e}")
            st.warning("Could not generate visualization.")
    
    @staticmethod
    def _render_overview(results: dict):
        """Render event overview section."""
        col1, col2 = st.columns([3, 1])
        
        with col1:
            event_title = results.get("title", {}).get("value", "Event Reconstruction")
            st.markdown(
                f'<div class="reconstruction-header"><h2>{event_title} Complete</h2></div>',
                unsafe_allow_html=True,
            )
        
        with col2:
            st.metric("Event ID", results.get("event_id", "N/A"), delta=None)
            st.metric(
                "Event Type",
                results.get("event_type", {}).get("value", "N/A"),
                delta=None,
            )
    
    @staticmethod
    def _render_timeline(results: dict):
        """Render event timeline."""
        st.subheader("⏳ Event Timeline (Stages & Episodes)")
        
        stages = results.get("stages", [])
        for stage_idx, stage in enumerate(stages):
            stage_name = stage.get("name", {}).get("value", f"Stage {stage_idx+1}")
            stage_conf = stage.get("name", {}).get("confidence", 0)
            
            with st.expander(
                f"Stage {stage_idx+1}: {stage_name} (Confidence: {stage_conf:.0%})",
                expanded=False,
            ):
                st.write(f"**Stage Name:** {stage_name}")
                st.write(f"**Confidence:** {stage_conf:.0%}")
                
                # Render episodes
                episodes = stage.get("episodes", [])
                for episode_idx, episode in enumerate(episodes):
                    episode_name = episode.get("name", {}).get(
                        "value", f"Episode {episode_idx+1}"
                    )
                    st.write(f"- **Episode {episode_idx+1}:** {episode_name}")
    
    @staticmethod
    def _render_summary_metrics(results: dict):
        """Render summary metrics."""
        st.markdown("---")
        st.subheader("Reconstruction Summary Metrics")
        
        stages = results.get("stages", [])
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Stages", len(stages))
        
        with col2:
            total_episodes = sum([len(s.get("episodes", [])) for s in stages])
            st.metric("Total Episodes", total_episodes)
        
        with col3:
            # Count unique participants
            all_participants = []
            for stage in stages:
                for episode in stage.get("episodes", []):
                    all_participants.extend(episode.get("participants", []))
            participant_ids = [
                p.get("participant_id")
                for p in all_participants
                if p.get("participant_id")
            ]
            unique_participants = len(set(participant_ids)) if participant_ids else 0
            st.metric("Unique Participants", unique_participants)
    
    @staticmethod
    def _render_export_options(results: dict):
        """Render export options."""
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
                    use_container_width=True,
                )

