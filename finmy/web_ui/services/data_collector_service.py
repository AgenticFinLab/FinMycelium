"""
Data collection service for gathering information from multiple sources.
"""

import os
import logging
import datetime
import json
import traceback
import time
from typing import List, Dict, Any
import streamlit as st

from finmy.url_collector.SearchCollector.bocha_search import bochasearch_api
from finmy.url_collector.SearchCollector.baidu_search import baidusearch_api
from finmy.url_collector.base import URLCollectorInput
from finmy.url_collector.url_parser import URLParser
from finmy.url_collector.url_parser_clean import extract_content_from_parsed_content
from finmy.pdf_collector.pdf_collector import PDFCollector
from finmy.pdf_collector.base import PDFCollectorInput
from finmy.web_ui.utils.formatters import format_timestamp
from finmy.runner.source_documents import make_document
from finmy.runner.event_followup_config import followup_enabled


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
        self.documents = {name: [] for name in ("url", "file", "bocha", "baidu")}
        self.save_dir = save_dir
        self.timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        self.parser = URLParser(
            delay=2.0, use_selenium_fallback=True, selenium_wait_time=5
        )

    def collect_subject_search_results(self, query, keywords, subject):
        """Collect publication-range searches; keep the existing document contract."""
        from finmy.runner.subject_search import collect_subject_sources
        from finmy.runner.scoped_search_api import search
        from finmy.runner.scoped_page import parse
        from finmy.runner.event_followup_config import followup_enabled, initial_search_options
        options = initial_search_options(self.config)
        def progress(message):
            st.write(f"**{format_timestamp()}** - {message}")

        extra = {"usage": self.evidence_usage} if followup_enabled(self.config) else {}
        docs = collect_subject_sources(query, keywords, subject, options,
                                       search, parse, self.save_dir, progress=progress, **extra)
        for doc in docs:
            self.documents[doc["source"]].append(doc)
        return ([d["raw_text"] for d in self.documents["bocha"]],
                [d["raw_text"] for d in self.documents["baidu"]])

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
        from finmy.runner.search_status import has_search_material, incomplete_search_result, IncompleteSearchError, record_search_coverage
        if not has_search_material(result):
            raise IncompleteSearchError(incomplete_search_result(result, self.save_dir))
        self.search_coverage = record_search_coverage(result, self.save_dir)
        if not self.search_coverage["search_complete"]:
            st.warning(
                f"Search coverage is partial. Building from {len(documents)} retained sources; "
                f"{len(self.search_coverage['unresolved_events'])} storylines remain unresolved. "
                f"Coverage report: {self.search_coverage['search_coverage_report_path']}"
            )
        # The provider set includes Exa and may mix providers. Preserve the
        # handoff sequence separately from the display/provider buckets.
        self.enhanced_documents = documents
        for doc in documents:
            source = doc.get("source") or "enhanced"
            self.documents.setdefault(source, []).append(doc)
        return [doc["raw_text"] for doc in documents]

    def collect_bocha_search_results(
        self, search_query: str, keywords: List[str]
    ) -> List[str]:
        """
        Collect and parse Bocha search results.

        Args:
            search_query: Search query string
            keywords: List of keywords

        Returns:
            List of formatted content strings
        """
        logging.info("=====================================")
        logging.info("Bocha Search")
        st.write(f"**{format_timestamp()}** - Start: Bocha Search")
        logging.info("=====================================")

        formatted_content = []
        try:
            bocha_search_results = bochasearch_api(search_query, summary=True, count=10)
            logging.info("Bocha Search: %s", bocha_search_results)
            results_count = len(bocha_search_results["data"]["webPages"]["value"])
            logging.info("Bocha Search: Get %d search results.", results_count)
            st.write(
                f"**{format_timestamp()}** - Bocha Search: Get {results_count} search results."
            )
            st.write(f"**{format_timestamp()}** - Bocha Search: Parsing...")

            formatted_results = []
            for item in bocha_search_results["data"]["webPages"]["value"]:
                st.write(
                    f"**{format_timestamp()}** - Bocha Search: Parsing {item['url']}"
                )
                formatted_item = {
                    "title": item["name"],
                    "url": item["url"],
                    "search_query_content": search_query,
                    "keywords": ",".join(keywords),
                    "snippet": item["snippet"],
                    "content": item["summary"],
                    "sitename": item["siteName"],
                    "datepublished": item["datePublished"],
                }

                collector_input = URLCollectorInput(urls=[item["url"]])
                output = self.parser.run(collector_input)
                formatted_item["parsed_content"] = (
                    output.results[0]["content"]
                    if output.results and len(output.results) > 0
                    else []
                )
                formatted_results.append(formatted_item)

            # Save results
            filepath = os.path.join(
                self.save_dir, f"formatted_bocha_search_results_{self.timestamp}.json"
            )
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(formatted_results, f, ensure_ascii=False, indent=4)

            # Format content
            for item in formatted_results:
                item_content = (
                    f"Title:\n{item['title']}\n\n"
                    f"Sitename:\n{item['sitename']}\n\n"
                    f"Content:\n{item['content']}\n\n\n"
                    f"Parsed Content:\n"
                    f"{extract_content_from_parsed_content(item['parsed_content'])}\n\n\n"
                )
                formatted_content.append(item_content)
                self.documents["bocha"].append(make_document(item_content, item, "bocha"))

            st.write(f"**{format_timestamp()}** - Success: Bocha Search")
        except (
            KeyError,
            ValueError,
            AttributeError,
            ConnectionError,
            TimeoutError,
        ) as e:
            error_type = type(e).__name__
            error_msg = str(e)
            error_traceback = traceback.format_exc()

            logging.error("ERROR - Bocha Search failed: %s: %s", error_type, error_msg)
            logging.error("Traceback:\n%s", error_traceback)
            traceback.print_exc()

            st.write(
                f"**{format_timestamp()}** - Error: Bocha Search - "
                f"{error_type}: {error_msg}"
            )

        return formatted_content

    def collect_baidu_search_results(
        self, search_query: str, keywords: List[str]
    ) -> List[str]:
        """
        Collect and parse Baidu search results.

        Args:
            search_query: Search query string
            keywords: List of keywords

        Returns:
            List of formatted content strings
        """
        logging.info("=====================================")
        logging.info("Baidu Search")
        st.write(f"**{format_timestamp()}** - Start: Baidu Search")
        logging.info("=====================================")

        formatted_content = []
        try:
            baidu_search_results = baidusearch_api(search_query)
            results_count = len(baidu_search_results.get("references", []))
            logging.info("Baidu Search: Get %d search results.", results_count)
            st.write(
                f"**{format_timestamp()}** - Baidu Search: Get {results_count} search results."
            )
            st.write(f"**{format_timestamp()}** - Baidu Search: Parsing...")

            formatted_results = []
            if "references" in baidu_search_results:
                for item in baidu_search_results["references"]:
                    st.write(
                        f"**{format_timestamp()}** - Baidu Search: Parsing {item['url']}"
                    )
                    formatted_item = {
                        "title": item["title"],
                        "url": item["url"],
                        "search_query_content": search_query,
                        "keywords": ",".join(keywords),
                        "snippet": item["snippet"],
                        "content": item["content"],
                        "sitename": item["website"],
                        "datepublished": item["date"],
                    }

                    collector_input = URLCollectorInput(urls=[item["url"]])
                    output = self.parser.run(collector_input)
                    formatted_item["parsed_content"] = (
                        output.results[0]["content"]
                        if output.results and len(output.results) > 0
                        else []
                    )
                    formatted_results.append(formatted_item)

            # Save results
            filepath = os.path.join(
                self.save_dir, f"formatted_baidu_search_results_{self.timestamp}.json"
            )
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(formatted_results, f, ensure_ascii=False, indent=4)

            # Format content
            for item in formatted_results:
                item_content = (
                    f"Title:\n{item['title']}\n\n"
                    f"Sitename:\n{item['sitename']}\n\n"
                    f"Content:\n{item['content']}\n\n\n"
                    f"Parsed Content:\n"
                    f"{extract_content_from_parsed_content(item['parsed_content'])}\n\n\n"
                )
                formatted_content.append(item_content)
                self.documents["baidu"].append(make_document(item_content, item, "baidu"))

            st.write(f"**{format_timestamp()}** - Success: Baidu Search")
        except (
            KeyError,
            ValueError,
            AttributeError,
            ConnectionError,
            TimeoutError,
        ) as e:
            error_type = type(e).__name__
            error_msg = str(e)
            error_traceback = traceback.format_exc()

            logging.error("ERROR - Baidu Search failed: %s: %s", error_type, error_msg)
            logging.error("Traceback:\n%s", error_traceback)
            traceback.print_exc()

            st.write(
                f"**{format_timestamp()}** - Error: Baidu Search - "
                f"{error_type}: {error_msg}"
            )

        return formatted_content

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
                        if followup_enabled(self.config):
                            from finmy.runner.subject_search import _url
                            normalized_url = _url("https://" + url if url.startswith("www.") else url)
                            usage = self.evidence_usage
                            usage.setdefault("started_at", time.monotonic())
                            attempted = usage.setdefault("attempted_urls", [])
                            options = self.config["subject_search"]
                            reason = None
                            if not normalized_url:
                                reason = "invalid_public_url"
                            elif normalized_url in attempted:
                                reason = "already_attempted"
                            elif usage.get("parse_calls", 0) >= options["max_parse_calls"]:
                                reason = "parse_budget_exhausted"
                            elif time.monotonic() - usage["started_at"] >= options["max_elapsed_seconds"]:
                                reason = "elapsed_budget_exhausted"
                            record = {"url": url, "status": reason or "attempted"}
                            usage.setdefault("structured_urls", []).append(record)
                            if reason:
                                st.write(f"Structure Data: Skipped URL ({reason}).")
                                continue
                            attempted.append(normalized_url)
                            usage["parse_calls"] = usage.get("parse_calls", 0) + 1
                            url = normalized_url
                        # Process web URL
                        collector_input = URLCollectorInput(urls=[url])
                        output = self.parser.run(collector_input)
                        row_dict = row.to_dict()
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
                    item_content = (
                        f"title:\n{item.get('title', 'No Title')}\n\n"
                        f"content:\n"
                        f"{extract_content_from_parsed_content(item.get('parsed_content', []))}"
                    )
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
