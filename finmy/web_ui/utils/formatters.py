"""
Formatting utilities for web interface.
"""

import datetime
from typing import Any, Optional


def format_timestamp(dt: Optional[datetime.datetime] = None) -> str:
    """
    Format timestamp for display.

    Args:
        dt: Datetime object (defaults to now)

    Returns:
        Formatted timestamp string
    """
    if dt is None:
        dt = datetime.datetime.now()
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def format_confidence(confidence: float) -> str:
    """
    Format confidence value as percentage.

    Args:
        confidence: Confidence value (0-1)

    Returns:
        Formatted percentage string
    """
    return f"{confidence:.0%}"


def format_field_label(key: str) -> str:
    """
    Format field key as a display label.

    Args:
        key: Field key (e.g., "participant_id")

    Returns:
        Formatted label (e.g., "Participant ID")
    """
    return " ".join(word.capitalize() for word in key.split("_"))


def format_value(value: Any, default: str = "N/A") -> str:
    """
    Format a value for display.

    Args:
        value: Value to format
        default: Default value if value is None/empty

    Returns:
        Formatted string
    """
    if value is None:
        return default
    if isinstance(value, (dict, list)) and not value:
        return default
    return str(value)
