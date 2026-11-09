"""
Data collection service for gathering information from multiple sources.
"""

import os
import logging
import datetime
import json
import traceback
from typing import List, Dict, Any
import streamlit as st

from finmy.url_collector.base import URLCollectorInput
from finmy.url_collector.url_parser import URLParser
from finmy.url_collector.url_parser_clean import extract_content_from_parsed_content
from finmy.pdf_collector.pdf_collector import PDFCollector
from finmy.pdf_collector.base import PDFCollectorInput
from finmy.web_ui.utils.formatters import format_timestamp
from finmy.runner.source_documents import make_document
from finmy.search.sources import canonical_url


class DataCollectorService:
    """Service for collecting data from various sources."""

    def __init__(self, config: Dict[str, Any], save_dir: str):
        """
        Initialize the data collector service.

        Args:
            config: Configuration dictionary
            save_dir: Directory to save collected data
        """
        self.config = config
        self.evidence_usage = {}
        self.documents = {name: [] for name in ("url", "file")}
        self.enhanced_documents = []
        self.save_dir = save_dir
        self.timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        self.parser = URLParser(**{
            "delay": 1.0, "use_selenium_fallback": False, "selenium_wait_time": 5,
            **(config.get("url_collector_config") or {}),
        })

    def collect_enhanced_search_results(self, query, keywords, subject):
        """Use shared search while retaining source provenance and handoff order."""
        from finmy.runner.enhanced_subject_search import collect_enhanced_sources

        result = collect_enhanced_sources(
            query, keywords, subject, self.config, self.save_dir,
            progress=lambda message: st.write(f"**{format_timestamp()}** - {message}"),
            usage=self.evidence_usage,
        )
        self.enhanced_search_result = result
        documents = result.get("documents", [])
        from finmy.runner.search_status import has_search_material, incomplete_search_result, record_search_coverage
        if not has_search_material(result):
            self.search_coverage = incomplete_search_result(result, self.save_dir)
            self.enhanced_documents = []
            return []
        self.search_coverage = record_search_coverage(result, self.save_dir)
        if not self.search_coverage["search_complete"]:
            st.warning(
                f"Search coverage is partial. Building from {len(documents)} retained sources; "
                f"{len(self.search_coverage['unresolved_events'])} storylines remain unresolved. "
                f"Coverage report: {self.search_coverage['search_coverage_report_path']}"
            )
        # Preserve agent handoff order across providers.
        self.enhanced_documents = documents
        return [doc["raw_text"] for doc in documents]

    def collect_structured_data(
        self, structured_data: Any, keywords: List[str]
    ) -> tuple[List[str], List[str]]:
        """
        Collect and process structured data (URLs and file paths).

        Args:
            structured_data: DataFrame with structured data
            keywords: List of keywords for PDF processing

        Returns:
            Tuple of (url_content_list, filepath_content_list)
        """
        logging.info("=====================================")
        logging.info("Structure Data Processing")
        st.write(f"**{format_timestamp()}** - Start: Structure Data Processing")
        logging.info("=====================================")

        url_link_content = []
        filepath_content = []
        structure_data_urllink = []
        structure_data_filepath = []
        structured_urls = set()

        try:
            if structured_data is None:
                return url_link_content, filepath_content

            logging.info("Structure Data: Get %d rows.", len(structured_data))
            st.write(
                f"**{format_timestamp()}** - Structure Data: Get {len(structured_data)} rows."
            )
            st.write(f"**{format_timestamp()}** - Structure Data: Parsing...")

            for index, row in structured_data.iterrows():
                logging.info(
                    "Processing row %d: %s",
                    index,
                    row.get("url", "No URL") if row.get("url") else "No URL",
                )
                st.write(
                    f"**{format_timestamp()}** - Structure Data: Parsing {row['url']}"
                )

                try:
                    url = row["url"] if row["url"] else "No URL"

                    if not isinstance(url, str):
                        logging.info("Error: %s", url if url else "No URL Provided")
                        continue

                    # Check if URL is a web link or local file path
                    if url.startswith(("http://", "https://", "www.")):
                        # Explicit source inputs do not consume the agent's search
                        # budget. Deduplicate them within this collection only.
                        url = canonical_url("https://" + url if url.startswith("www.") else url)
                        if url in structured_urls:
                            continue
                        structured_urls.add(url)
                        # Process web URL
                        collector_input = URLCollectorInput(urls=[url])
                        output = self.parser.run(collector_input)
                        row_dict = row.to_dict()
                        row_dict["url"] = url
                        row_dict["parsed_content"] = (
                            output.results[0]["content"]
                            if output.results and len(output.results) > 0
                            else []
                        )
                        structure_data_urllink.append(row_dict)
                    elif os.path.exists(url) and url.lower().endswith(".pdf"):
                        # Process local PDF file
                        logging.info("Processing local PDF file: %s", url)
                        config = self.config["pdf_collector_config"]
                        pdf_collector_input = PDFCollectorInput(
                            input_pdf_path=url, keywords=keywords or []
                        )
                        parser_instance = PDFCollector(config)
                        collect_results = parser_instance.collect(pdf_collector_input)

                        logging.info(
                            "  - Total PDFs parsed results after filtering: %d",
                            len(collect_results.records),
                        )

                        row_dict = row.to_dict()
                        row_dict["parsed_content"] = (
                            collect_results.records[0].__dict__
                            if collect_results.records
                            else {}
                        )
                        structure_data_filepath.append(row_dict)
                except (
                    KeyError,
                    ValueError,
                    AttributeError,
                    FileNotFoundError,
                    PermissionError,
                ) as e:
                    error_type = type(e).__name__
                    error_msg = str(e)
                    error_traceback = traceback.format_exc()
                    row_url = row["url"] if row["url"] else "No URL Provided"

                    logging.error(
                        "Processing error for row %d (URL: %s): %s: %s",
                        index,
                        row_url,
                        error_type,
                        error_msg,
                    )
                    logging.error("Traceback:\n%s", error_traceback)
                    traceback.print_exc()

            # Save and format URL link data
            if structure_data_urllink:
                logging.info("===== Structured Data URL Link =====")
                st.write(
                    f"**{format_timestamp()}** - Processing: Structured Data URL Link"
                )
                filepath = os.path.join(
                    self.save_dir, f"structure_data_urllink_{self.timestamp}.json"
                )
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(structure_data_urllink, f, ensure_ascii=False, indent=4)

                for item in structure_data_urllink:
                    text = extract_content_from_parsed_content(item.get("parsed_content", []))
                    if not text.strip():
                        continue
                    item_content = f"title:\n{item.get('title', 'No Title')}\n\ncontent:\n{text}"
                    url_link_content.append(item_content)
                    self.documents["url"].append(make_document(item_content, item, "url"))

            # Save and format filepath data
            if structure_data_filepath:
                logging.info("===== Structured Data Filepath =====")
                st.write(
                    f"**{format_timestamp()}** - Processing: Structured Data Filepath"
                )
                filepath = os.path.join(
                    self.save_dir, f"structured_data_filepath_{self.timestamp}.json"
                )
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(structure_data_filepath, f, ensure_ascii=False, indent=4)

                for item in structure_data_filepath:
                    parsed_content = item.get("parsed_content", {})
                    location = parsed_content.get("Location")
                    if location and os.path.exists(location):
                        with open(location, "r", encoding="utf-8") as f:
                            item_content = (
                                f"title:\n{item.get('title', 'No Title')}\n\n"
                                f"content:\n{f.read()}"
                            )
                            filepath_content.append(item_content)
                            self.documents["file"].append(make_document(item_content, item, "file"))
        except (
            KeyError,
            ValueError,
            AttributeError,
            FileNotFoundError,
            PermissionError,
        ) as e:
            error_type = type(e).__name__
            error_msg = str(e)
            error_traceback = traceback.format_exc()

            logging.error(
                "Error in structured data processing: %s: %s", error_type, error_msg
            )
            logging.error("Traceback:\n%s", error_traceback)
            traceback.print_exc()

            st.write(
                f"**{format_timestamp()}** - Error: Structured data processing "
                f"failed - {error_type}: {error_msg}"
            )

        return url_link_content, filepath_content
