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
from finmy.runner.relevance_filter import filter_documents
from finmy.runner.context_budget import allocate_context
from finmy.reconstruction_scope import read_reconstruction, search_query


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
        reconstruction = read_reconstruction(self.config)
        scoped = reconstruction["mode"] != "event" and (self.config.get("subject_search") or {}).get("enabled", True)
        from finmy.runner.enhanced_subject_search import enhanced_search_enabled
        enhanced = reconstruction["mode"] != "event" and enhanced_search_enabled(self.config)
        if scoped and not enhanced:
            from finmy.runner.scoped_search import plan_search, search_window
            # Validate the plan before any network call. Prompt dates become
            # structured event coverage; publication overrides stay search-only.
            plan_search(main_input, keywords, reconstruction["subject"], self.config.get("subject_search", {}))
            subject = self.config["builder_config"]["reconstruction"]["subject"]
            if not subject.get("coverage_start") or not subject.get("coverage_end"):
                try:
                    start, end = search_window(main_input, reconstruction["subject"])
                except ValueError:
                    # An explicit publication-only window need not assert event dates.
                    # plan_search above already validated that the search is bounded.
                    pass
                else:
                    subject["coverage_start"] = subject.get("coverage_start") or start.isoformat()
                    subject["coverage_end"] = subject.get("coverage_end") or end.isoformat()
            reconstruction = read_reconstruction(self.config)
        # Prepare search query
        search_query_content = search_query(main_input, keywords, self.config)
        st.write(f"**{format_timestamp()}** - Input has been processed.")
        
        # Create output directory
        pipeline_output_dir = f"pipeline_output_{datetime.datetime.now().strftime('%Y%m%d%H%M%S%d%f')}"
        save_dir = os.path.join(self.config["output_dir"], pipeline_output_dir)
        os.makedirs(save_dir, exist_ok=True)
        
        # Initialize data collector
        collector = DataCollectorService(self.config, save_dir)
        
        # Collect data from all sources
        if enhanced:
            search_content = collector.collect_enhanced_search_results(
                main_input, keywords, reconstruction["subject"]
            )
        elif scoped:
            bocha_content, baidu_content = collector.collect_subject_search_results(
                main_input, keywords, reconstruction["subject"]
            )
            search_content = bocha_content + baidu_content
        else:
            bocha_content = collector.collect_bocha_search_results(search_query_content, keywords)
            baidu_content = collector.collect_baidu_search_results(search_query_content, keywords)
            search_content = bocha_content + baidu_content
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
        
        # P0: classify sources BEFORE the existing context-length budget is applied.
        # Keep the original All_Text_Content and formatted search archives unchanged.
        documents = [doc for source in ("url", "file") for doc in collector.documents[source]]
        if enhanced:
            documents += collector.enhanced_documents
        else:
            documents += [doc for source in ("bocha", "baidu")
                          for doc in collector.documents[source]]
        if [d["raw_text"] for d in documents] != all_text_content:
            raise ValueError("Collected source metadata/content are out of sync")
        from finmy.runner.event_followup_config import followup_enabled, initial_search_options
        follow_events = followup_enabled(self.config)
        usage = getattr(collector, "evidence_usage", {})
        filter_kwargs = {"usage": usage} if follow_events else {}
        filtered = filter_documents(documents, main_input, keywords, self.config, save_dir,
                                    progress=st.write, **filter_kwargs)
        summary = filtered["summary"]
        st.write(f"Relevance filter: kept {summary['kept']}/{summary['retrieved']} "
                 f"documents; removed {summary['removed']}.")
        for warning in filtered["warnings"]:
            st.warning(warning)
        if not filtered["contents"]:
            raise ValueError("No relevant sources remain. Inspect relevance_decisions.json or refine the search.")

        if scoped and not enhanced and reconstruction["mode"] == "person":
            from finmy.runner.decision_followup import collect_decision_followup
            initial_config = copy.deepcopy(self.config)
            initial_config["subject_search"] = initial_search_options(self.config)
            extra = collect_decision_followup(
                filtered, main_input, keywords, reconstruction["subject"], initial_config, save_dir,
                progress=lambda message: st.write(f"**{format_timestamp()}** - {message}"),
                known_urls=[d.get("url") for d in documents],
                **filter_kwargs,
            )
            if extra:
                # Reuse the relevance cache for old documents and assign unique
                # IDs across the combined source list before the context budget.
                filtered = filter_documents(
                    documents + extra, main_input, keywords, self.config, save_dir, progress=st.write,
                    **filter_kwargs,
                )
                documents = documents + extra
                summary = filtered["summary"]
                st.write(f"Relevance filter after decision follow-up: kept {summary['kept']}/"
                         f"{summary['retrieved']} documents.")
                for warning in filtered["warnings"]:
                    st.warning(warning)

        # Budget retained evidence before building: CORE/CONTEXT first, long
        # sources as verbatim excerpts. No extra model call is needed here.
        budgeted = allocate_context(
            filtered["documents"], filtered["decisions"], self.config,
            include_metadata=summary["enabled"],
        )
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
            raise ValueError("Context budget admitted no documents. Inspect filtered_contents.json.")
        
        # Run pipeline
        self._draft_evidence = {"filtered": filtered, "documents": documents, "usage": usage}
        pipeline_config = self.config
        if enhanced:
            from finmy.subject_graph.runner import with_source_registry
            self.config = with_source_registry(self.config, filtered["documents"], budgeted)
        try:
            return self._run_pipeline(
                all_text_content_limit, main_input, keywords, save_dir
            )
        finally:
            # A reused Streamlit service must not attach this run's sources to
            # a subsequent reconstruction, including a switch to simple mode.
            if enhanced:
                self.config = pipeline_config
    
    def _limit_content_length(self, content_list: List[str]) -> List[str]:
        """Limit content to maximum allowed length."""
        max_length = self.config.get("all_content_config", {}).get(
            "max_content_length", float("inf")
        )
        
        limited_content = []
        total_length = 0
        
        for item in content_list:
            item_length = len(item)
            if total_length + item_length <= max_length:
                limited_content.append(item)
                total_length += item_length
            else:
                continue
        
        logging.info("Length of All_Text_Content String: %d", sum(len(c) for c in content_list))
        logging.info("Length of All_Text_Content_Limit String: %d", total_length)
        
        return limited_content
    
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
            error_type = type(e).__name__
            error_msg = str(e)
            error_traceback = traceback.format_exc()
            
            logging.error("Error during EventBuilder: %s: %s", error_type, error_msg)
            logging.error("Traceback:\n%s", error_traceback)
            traceback.print_exc()
            
            st.error(f"❌ Error during EventBuilder: {error_type}: {error_msg}")
            return None

