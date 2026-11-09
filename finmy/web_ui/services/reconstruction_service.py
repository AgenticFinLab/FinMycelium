"""
Event reconstruction service.
"""

import os
import logging
import traceback
import datetime
import json
import copy
from typing import Dict, Any, List
import streamlit as st

from finmy.pipeline import FinmyPipeline
from finmy.builder.utils import estimate_complete_time
from finmy.web_ui.utils.formatters import format_timestamp
from finmy.web_ui.services.data_collector_service import DataCollectorService
from finmy.runner.source_documents import prepare_documents
from finmy.runner.context_budget import allocate_context
from finmy.reconstruction_scope import read_reconstruction


class ReconstructionService:
    """Service for event reconstruction pipeline."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize reconstruction service.
        
        Args:
            config: Configuration dictionary
        """
        from finmy.runner.event_followup_config import normalize_followup_config
        self.config = normalize_followup_config(config)
        # Reject malformed person scope before starting any search or model call.
        read_reconstruction(config)
    
    def run_reconstruction(
        self, main_input: str, keywords: List[str], structured_data: Any
    ) -> Dict[str, Any]:
        """
        Run the complete event reconstruction pipeline.
        
        Args:
            main_input: Main event description
            keywords: List of keywords
            structured_data: Structured data DataFrame (optional)
            
        Returns:
            Reconstruction results dictionary
        """
        keywords = keywords or []
        # Coverage belongs to this run, never to a previous person or Event result.
        st.session_state.search_coverage = None
        self.search_coverage = None
        reconstruction = read_reconstruction(self.config)
        st.write(f"**{format_timestamp()}** - Input has been processed.")
        
        # Create output directory
        pipeline_output_dir = f"pipeline_output_{datetime.datetime.now().strftime('%Y%m%d%H%M%S%d%f')}"
        save_dir = os.path.join(self.config["output_dir"], pipeline_output_dir)
        os.makedirs(save_dir, exist_ok=True)
        
        # Initialize data collector
        collector = DataCollectorService(self.config, save_dir)
        
        # Person and single-event requests share the agent acquisition path.
        search_content = collector.collect_enhanced_search_results(
            main_input, keywords, reconstruction.get("subject", {})
        )
        self._search_acquisition = collector.enhanced_search_result
        self.search_coverage = collector.search_coverage
        st.session_state.search_coverage = self.search_coverage
        url_content, filepath_content = collector.collect_structured_data(
            structured_data, keywords
        )
        
        # Combine all content
        all_text_content = (
            url_content + filepath_content + search_content
        )
        
        # Save combined content
        all_content_filepath = os.path.join(
            save_dir, f"All_Text_Content_{collector.timestamp}.json"
        )
        with open(all_content_filepath, "w", encoding="utf-8") as f:
            json.dump(all_text_content, f, ensure_ascii=False, indent=4)
        
        st.write(f"**{format_timestamp()}** - Processing: All_Text_Content")
        logging.info("All_Text_Content: %s", all_text_content)
        logging.info("Length of All_Text_Content List: %d", len(all_text_content))
        
        # Assign stable document IDs before allocating the source-text budget.
        # Keep the original All_Text_Content and formatted search archives unchanged.
        documents = [doc for source in ("url", "file") for doc in collector.documents[source]]
        documents += collector.enhanced_documents
        if [d["raw_text"] for d in documents] != all_text_content:
            raise ValueError("Collected source metadata/content are out of sync")
        if not documents:
            return None
        usage = getattr(collector, "evidence_usage", {})
        documents = prepare_documents(documents, main_input, keywords, self.config, save_dir)
        budget_config = copy.deepcopy(self.config)
        storyline_plan = collector.enhanced_search_result.get("storyline_plan")
        if storyline_plan:
            budget_config.setdefault("all_content_config", {})["allocation_strategy"] = "event"
        budgeted = allocate_context(documents, [], budget_config, include_metadata=True)
        all_text_content_limit = budgeted["contents"]
        budget_report = budgeted["report"]
        with open(os.path.join(save_dir, "context_budget_report.json"), "w", encoding="utf-8") as f:
            json.dump(budget_report, f, ensure_ascii=False, indent=2)
        budget_summary = budget_report["summary"]
        st.write(f"Context budget: {budget_summary['included_documents']}/"
                 f"{budget_summary['candidate_documents']} sources; "
                 f"{budget_summary['used_chars']}/{budget_summary['max_content_length']} chars; "
                 f"{budget_summary['truncated_documents']} excerpted.")
        for warning in budget_report["warnings"]:
            st.warning(warning)
        # Archive exactly what the builder receives, rather than only pre-budget data.
        with open(os.path.join(save_dir, "builder_input_contents.json"), "w", encoding="utf-8") as f:
            json.dump(all_text_content_limit, f, ensure_ascii=False, indent=2)
        if not all_text_content_limit:
            raise ValueError("Context budget admitted no documents. Inspect context_budget_report.json.")
        
        # Run pipeline
        self._draft_evidence = {"documents": documents, "usage": usage}
        pipeline_config = self.config
        from finmy.subject_graph.runner import with_source_registry
        self.config = with_source_registry(self.config, documents, budgeted)
        if storyline_plan:
            self.config["storyline_plan"] = copy.deepcopy(storyline_plan)
        try:
            return self._run_pipeline(
                all_text_content_limit, main_input, keywords, save_dir
            )
        finally:
            # Run-specific source metadata never leaks into the next request.
            self.config = pipeline_config

    def _run_pipeline(
        self, contents: List[str], query_text: str, keywords: List[str], save_dir: str
    ) -> Dict[str, Any]:
        """Run the building pipeline."""
        logging.info("Builder_Pipeline")
        st.write(f"**{format_timestamp()}** - Processing: Builder_Pipeline")
        
        builder_type = self.config["builder_config"]["builder_type"]
        st.write(
            f"**{format_timestamp()}** - Builder Type: **{builder_type}**"
        )
        
        # Estimate completion time
        estimate_time = estimate_complete_time(
            str_list=contents, build_type=builder_type
        )
        st.session_state.estimate_time = estimate_time
        st.write(
            f"**{format_timestamp()}** - Estimated time to complete building: "
            f"**{estimate_time} minutes**"
        )
        
        try:
            logging.info("Pipeline initialization ...")
            st.write(
                f"**{format_timestamp()}** - Building pipeline initialization ..."
            )
            logging.info("config: %s", self.config)
            
            if getattr(self, "search_coverage", None) is not None:
                from finmy.runner.search_status import record_search_coverage
                self.search_coverage = record_search_coverage(
                    self._search_acquisition, save_dir, builder_status="running")
                st.session_state.search_coverage = self.search_coverage
            if read_reconstruction(self.config)["mode"] != "event":
                # Filtered evidence goes directly to the native subject builder.
                # Legacy financial matching/summarization can drop person/company history.
                from finmy.subject_graph.runner import build_from_contents
                from finmy.runner.event_followup_config import followup_enabled
                if followup_enabled(self.config) and hasattr(self, "_draft_evidence"):
                    from finmy.runner.event_refinement import build_with_draft_event_followup
                    pipeline_result, builder_save_path = build_with_draft_event_followup(
                        contents, query_text, keywords, self.config, save_dir,
                        **self._draft_evidence, build=build_from_contents,
                        progress=lambda message: st.write(f"**{format_timestamp()}** - {message}"))
                else:
                    pipeline_result, builder_save_path = build_from_contents(
                        contents, query_text, keywords, self.config)
            else:
                pipeline = FinmyPipeline(self.config)
                pipeline_result = pipeline.lm_build_pipeline_with_contents(
                    contents=contents, query_text=query_text, key_words=keywords
                )
                builder_save_path = pipeline.save_builder_dir_path
            st.session_state.save_builder_dir_path = builder_save_path
            if getattr(self, "search_coverage", None) is not None:
                from finmy.runner.search_status import record_search_coverage
                self.search_coverage = record_search_coverage(
                    self._search_acquisition, save_dir, builder_directory=builder_save_path,
                    builder_status="completed" if pipeline_result is not None else "failed")
                st.session_state.search_coverage = self.search_coverage
            logging.info("builder save directory: %s", builder_save_path)

            logging.info("type of pipeline_result: %s", type(pipeline_result))
            logging.info("pipeline_result:\n %s", pipeline_result)
            
            if pipeline_result:
                logging.info("Building completed.")
                st.write(f"**{format_timestamp()}** - Building completed.")
                
                # Return appropriate result format
                extras = getattr(pipeline_result, "extras", None)
                if isinstance(extras, dict) and extras.get("person_epg") is not None:
                    # Keep the stored hierarchy for the Person EPG renderer.
                    # A legacy projection cannot restore domains or memberships.
                    return extras["person_epg"]
                if getattr(pipeline_result, "subject_graph", None) is not None:
                    return pipeline_result.subject_graph
                if isinstance(pipeline_result, dict):
                    return pipeline_result
                elif hasattr(pipeline_result, "event_cascades"):
                    logging.info("pipeline_result json: %s", pipeline_result.event_cascades)
                    return pipeline_result.event_cascades
                else:
                    logging.warning(
                        "Unexpected pipeline_result type: %s", type(pipeline_result)
                    )
                    return pipeline_result
            
            return None
        except Exception as e:
            # Only a still-running Builder has failed. Errors in later result
            # presentation must not rewrite a completed reconstruction as failed.
            if (getattr(self, "search_coverage", None) or {}).get("builder_status") == "running":
                from finmy.runner.search_status import record_search_coverage
                builder_directory = getattr(e, "builder_directory", None)
                try:
                    self.search_coverage = record_search_coverage(
                        self._search_acquisition, save_dir, builder_directory=builder_directory,
                        builder_status="failed", builder_error=e)
                    st.session_state.search_coverage = self.search_coverage
                    if builder_directory is not None:
                        st.session_state.save_builder_dir_path = builder_directory
                except OSError:
                    logging.exception("Could not update Builder failure status")
            error_type = type(e).__name__
            error_msg = str(e)
            error_traceback = traceback.format_exc()
            
            logging.error("Error during EventBuilder: %s: %s", error_type, error_msg)
            logging.error("Traceback:\n%s", error_traceback)
            traceback.print_exc()
            
            st.error(f"❌ Error during EventBuilder: {error_type}: {error_msg}")
            return None

