"""
Validation utilities for web interface.
"""

import re
import streamlit as st
from typing import List, Dict, Any, Optional
import yaml


def validate_config(config_data: Dict[str, Any]) -> tuple[bool, List[str]]:
    """
    Validate configuration data.
    
    Args:
        config_data: Configuration dictionary
        
    Returns:
        Tuple of (is_valid, error_messages)
    """
    validation_passed = True
    validation_errors = []
    
    # Check for required sections
    required_sections = [
        "lm_type",
        "lm_name",
        "inference_config",
        "generation_config",
        "db_config",
        "output_dir",
        "url_collector_config",
        "pdf_collector_config",
        "summarizer_config",
        "matcher_config",
        "builder_config",
    ]
    
    for section in required_sections:
        if section not in config_data:
            validation_passed = False
            validation_errors.append(f"Missing required section: {section}")
    
    # Validate specific fields
    if "lm_name" in config_data:
        if not isinstance(config_data["lm_name"], str):
            validation_passed = False
            validation_errors.append("lm_name must be a string")
    
    return validation_passed, validation_errors


def validate_analysis_inputs() -> bool:
    """
    Validate that required inputs are provided for analysis.
    
    Returns:
        True if validation passes, False otherwise
    """
    has_natural_language = (
        hasattr(st.session_state, "main_input") and st.session_state.main_input
    )
    has_keywords = (
        hasattr(st.session_state, "keywords") and st.session_state.keywords
    )
    has_structured_data = (
        hasattr(st.session_state, "structured_data")
        and st.session_state.structured_data is not None
    )
    
    if not has_natural_language and not has_keywords and not has_structured_data:
        st.error(
            "Please provide at least one data source for analysis "
            "(natural language description, keywords, or structured data file)"
        )
        return False
    
    return True


def parse_keywords(keywords_str: str) -> List[str]:
    """
    Parse keywords from input string with flexible delimiter handling.
    
    Args:
        keywords_str: Input string containing keywords
        
    Returns:
        List of cleaned keywords
    """
    if not keywords_str:
        return []
    
    # Normalize full-width Chinese commas to standard commas
    unified_keywords = (
        keywords_str.replace("，", ",").replace(";", ",").replace("；", "")
    )
    
    # Split on commas/spaces (supports multiple consecutive delimiters)
    keyword_list = re.split(r"[,|\s]+", unified_keywords)
    
    # Clean up keywords (strip whitespace + remove empty strings)
    return [k.strip() for k in keyword_list if k.strip()]

