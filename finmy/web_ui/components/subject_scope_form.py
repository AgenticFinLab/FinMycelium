"""Subject controls that leave the uploaded configuration unchanged."""
import copy
import hashlib
import json
import re
import unicodedata

import streamlit as st

from finmy.reconstruction_scope import read_reconstruction
from finmy.runner.person_period import parse_person_period, period_text


def apply_subject_scope(config, mode, subject=None):
    """Build the effective run config without mutating the uploaded config."""
    effective = copy.deepcopy(config)
    builder = effective.setdefault("builder_config", {})
    options = copy.deepcopy(builder.get("reconstruction", {}))
    options["mode"] = mode
    if mode == "event":
        options.pop("subject", None)
    else:
        options["subject"] = copy.deepcopy(subject or {})
    builder["reconstruction"] = options
    normalized = read_reconstruction(effective)
    if mode != "event":
        options["subject"] = normalized["subject"]
    return effective


def person_subject(config, name, period=None):
    """Create internal identity and preserve the visible period's precision."""
    name = name.strip()
    normalize = lambda value: " ".join(unicodedata.normalize("NFKC", value).casefold().split())
    identity = normalize(name)
    original = config.get("builder_config", {}).get("reconstruction", {})
    previous = original.get("subject", {}) if original.get("mode") == "person" else {}
    previous = previous if isinstance(previous, dict) else {}
    names = [previous.get("name", "")]
    aliases = previous.get("aliases", [])
    if isinstance(aliases, list):
        names.extend(alias for alias in aliases if isinstance(alias, str))
    identifier = previous.get("subject_id")
    if not (any(isinstance(value, str) and normalize(value) == identity for value in names)
            and isinstance(identifier, str)
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", identifier)):
        identifier = "person_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    start, end = parse_person_period(period) if period is not None else (None, None)
    return {"subject_id": identifier, "name": name, "aliases": [],
            "coverage_start": start, "coverage_end": end, "scope": ""}


def person_input(config):
    subject = read_reconstruction(config)["subject"]
    period = period_text(subject)
    if not period:
        raise ValueError("Enter a valid period for this person.")
    return subject["name"] + " " + period


def render_subject_scope(config):
    """Person mode has exactly two task fields: name and period."""
    original = config.get("builder_config", {}).get("reconstruction", {})
    if not isinstance(original, dict):
        st.error("builder_config.reconstruction must be a mapping")
        return None
    # Older company configurations open in Event mode; never treat a company as a person.
    mode = "person" if original.get("mode") == "person" else "event"
    prefix = "person_input_" + hashlib.sha256(
        json.dumps(original, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:12]
    labels = {"event": "Event", "person": "Person"}
    selected = st.selectbox("Mode", list(labels),
                            index=list(labels).index(mode), format_func=labels.get,
                            key=prefix + "_mode")
    st.session_state.reconstruction_input_mode = selected
    subject = None
    if selected == "person":
        defaults = original.get("subject", {}) if mode == "person" else {}
        defaults = defaults if isinstance(defaults, dict) else {}
        name = st.text_input("Person name", value=defaults.get("name", ""),
                             placeholder="Warren Buffett", key=prefix + "_name")
        period = st.text_input("Period", value=period_text(defaults),
                               placeholder="2023, 2023-05, or 2022–2023",
                               help="Enter a year, month, date, or date range. Examples: 2023-05-06; 2022-01-01 to 2023-12-31.",
                               key=prefix + "_period")
        if not name.strip() or not period.strip():
            return None
    try:
        if selected == "person":
            subject = person_subject(config, name, period)
        effective = apply_subject_scope(config, selected, subject)
        if selected == "person":
            search = effective.setdefault("search_config", {})
            search["mode"] = "agent"
            search["storyline_discovery"] = dict(search.get("storyline_discovery") or {})
            search["storyline_discovery"]["enabled"] = True
            effective["event_followup"] = dict(effective.get("event_followup") or {})
            effective["event_followup"].setdefault("enabled", False)
            effective.setdefault("all_content_config", {}).setdefault("max_content_length", 120000)
        return effective
    except ValueError as exc:
        st.error(str(exc))
        return None
