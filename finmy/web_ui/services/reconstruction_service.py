"""
Event reconstruction service.
"""

import os
import logging
import traceback
import datetime
import json
from typing import Dict, Any, List
import streamlit as st

from finmy.pipeline import FinmyPipeline
from finmy.builder.utils import estimate_complete_time
from finmy.web_ui.utils.formatters import format_timestamp
from finmy.web_ui.services.data_collector_service import DataCollectorService


class ReconstructionService:
    """Service for event reconstruction pipeline."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize reconstruction service.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
    
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
        # Prepare search query
        search_query_content = f"{main_input} \n\nkeywords: {' '.join(keywords)}"
        st.write(f"**{format_timestamp()}** - Input has been processed.")
        
        # Create output directory
        pipeline_output_dir = f"pipeline_output_{datetime.datetime.now().strftime('%Y%m%d%H%M%S%d%f')}"
        save_dir = os.path.join(self.config["output_dir"], pipeline_output_dir)
        os.makedirs(save_dir, exist_ok=True)
        
        # Initialize data collector
        collector = DataCollectorService(self.config, save_dir)
        
        # Collect data from all sources
        bocha_content = collector.collect_bocha_search_results(
            search_query_content, keywords
        )
        baidu_content = collector.collect_baidu_search_results(
            search_query_content, keywords
        )
        url_content, filepath_content = collector.collect_structured_data(
            structured_data, keywords
        )
        
        # Combine all content
        all_text_content = (
            url_content + filepath_content + bocha_content + baidu_content
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
        
        # Limit content length
        all_text_content_limit = self._limit_content_length(all_text_content)
        
        # Run pipeline
        return self._run_pipeline(
            all_text_content_limit, main_input, keywords, save_dir
        )
    
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
                break
        
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
            
            pipeline = FinmyPipeline(self.config)
            logging.info("Pipeline is initialized")
            st.write(f"**{format_timestamp()}** - Building pipeline is initialized")
            
            logging.info("Building......")
            st.write(f"**{format_timestamp()}** - Building......")
            
            pipeline_result = pipeline.lm_build_pipeline_with_contents(
                contents=contents, query_text=query_text, key_words=keywords
            )
            
            st.session_state.save_builder_dir_path = pipeline.save_builder_dir_path
            logging.info("pipeline save_builder_dir_path: %s", pipeline.save_builder_dir_path)
            logging.info("st.session_state.save_builder_dir_path: %s", st.session_state.save_builder_dir_path)
            
            logging.info("type of pipeline_result: %s", type(pipeline_result))
            logging.info("pipeline_result:\n %s", pipeline_result)
            
            if pipeline_result:
                logging.info("Building completed.")
                st.write(f"**{format_timestamp()}** - Building completed.")
                
                # Return appropriate result format
                if isinstance(pipeline_result, dict):
                    return pipeline_result
                elif hasattr(pipeline_result, "result"):
                    logging.info("pipeline_result json: %s", pipeline_result.result)
                    return pipeline_result.result
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

