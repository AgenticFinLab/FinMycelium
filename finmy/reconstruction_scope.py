"""Validated reconstruction scope shared by search, filtering, and the builder.

The configuration is task metadata, never source evidence. Keeping it inside
builder_config ensures the regular FinmyPipeline passes it to the builder.
"""
import calendar
import datetime as dt
import json
import re


def date_bounds(value):
    """Return inclusive date bounds for YYYY, YYYY-MM, or YYYY-MM-DD."""
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}(?:-\d{2}){0,2}", value):
        raise ValueError("Coverage dates must use YYYY, YYYY-MM, YYYY-MM-DD, or null")
    parts = [int(part) for part in value.split("-")]
    year = parts[0]
    month = parts[1] if len(parts) > 1 else 1
    day = parts[2] if len(parts) > 2 else 1
    start = dt.date(year, month, day)
    end_month = month if len(parts) > 1 else 12
    end_day = day if len(parts) > 2 else calendar.monthrange(year, end_month)[1]
    return start, dt.date(year, end_month, end_day)


def read_reconstruction(config=None):
    """Read either a complete pipeline config or its builder_config mapping.

Absent configuration preserves event mode. Person mode requires an explicit
identity and scope so a topic-specific request cannot silently become a bio.
"""
    if config is None:
        config = {}
    if not isinstance(config, dict):
        raise ValueError("Reconstruction configuration must be a mapping")
    if "builder_config" in config:
        if "reconstruction" in config:
            raise ValueError("Place reconstruction inside builder_config, not at pipeline top level")
        config = config["builder_config"]
        if not isinstance(config, dict):
            raise ValueError("builder_config must be a mapping")
    options = config.get("reconstruction", {})
    if not isinstance(options, dict):
        raise ValueError("reconstruction must be a mapping")
    mode = options.get("mode", "event")
    if mode not in ("event", "person"):
        raise ValueError("reconstruction.mode must be event or person")
    if mode == "event":
        if options.get("subject"):
            raise ValueError("A subject requires reconstruction.mode: person")
        return {"mode": "event"}
    if config.get("builder_type", "AgentEventBuilder") != "AgentEventBuilder":
        raise ValueError("Person reconstruction currently requires builder_type: AgentEventBuilder")
    subject = options.get("subject")
    if not isinstance(subject, dict):
        raise ValueError("Person mode requires a subject mapping")
    normalized = {}
    for key in ("subject_id", "name", "scope"):
        value = subject.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Person mode requires nonempty subject.{key}")
        normalized[key] = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", normalized["subject_id"]):
        raise ValueError("subject_id must be a stable identifier using letters, digits, _, ., :, or -")
    aliases = subject.get("aliases", [])
    if not isinstance(aliases, list) or any(not isinstance(a, str) or not a.strip() for a in aliases):
        raise ValueError("subject.aliases must be a list of nonempty strings")
    normalized["aliases"] = list(dict.fromkeys(a.strip() for a in aliases))
    for key in ("coverage_start", "coverage_end"):
        value = subject.get(key)
        if value is not None:
            date_bounds(value)
        normalized[key] = value
    start, end = normalized["coverage_start"], normalized["coverage_end"]
    if start and end and date_bounds(start)[0] > date_bounds(end)[1]:
        raise ValueError("subject.coverage_start must not be after coverage_end")
    return {"mode": "person", "subject": normalized}


def render_scope(config=None):
    """Render authoritative scope separately from evidence and original query."""
    reconstruction = read_reconstruction(config)
    if reconstruction["mode"] == "event":
        return ""
    return (
        "PERSON RECONSTRUCTION SCOPE (task metadata, not evidence):\n"
        + json.dumps(reconstruction["subject"], ensure_ascii=False, sort_keys=True)
        + "\nUse only supplied source evidence within this scope. The original request may "
        "narrow this scope further; do not expand a selected topic to the whole biography. "
        "A company action is not automatically the person's action."
    )


def search_query(query, keywords, config=None):
    """Keep the legacy event query exact; add concise person scope for search."""
    reconstruction = read_reconstruction(config)
    original = f"{query} \n\nkeywords: {' '.join(keywords or [])}"
    if reconstruction["mode"] == "event":
        return original
    subject = reconstruction["subject"]
    bounds = " – ".join(value or "unspecified" for value in
                        (subject["coverage_start"], subject["coverage_end"]))
    return (f"{original}\nSubject: {subject['name']}"
            f"\nAliases: {', '.join(subject['aliases'])}"
            f"\nPeriod: {bounds}\nScope: {subject['scope']}")
