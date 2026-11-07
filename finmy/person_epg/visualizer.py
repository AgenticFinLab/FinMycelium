"""Render stored Person EPG organization as a standalone, offline Plotly Gantt."""

import json
import re
from html import escape
from pathlib import Path

from .validation import validate_person_epg

ASSETS = Path(__file__).with_name("assets")


def render_person_epg(package, output_path=None):
    """Return HTML, optionally writing it to ``output_path``.

    The input is a person-epg-3.0 dict. Memberships, stages and selected details
    are read as stored; rendering neither classifies nor changes facts. Plotly
    is embedded so the result works without a server or internet connection.
    """
    report = validate_person_epg(package)
    if not report["valid"]:
        error = report["errors"][0]
        raise ValueError(f"Invalid Person EPG: {error['path']}: {error['message']}")
    if package["activity"] and not package["event_activity"]:
        raise ValueError(
            "Person EPG has facts but no event_activity memberships. "
            "Store domain/event organization before rendering; convert only migrates facts."
        )

    from plotly.offline import get_plotlyjs

    subject = next(
        row for row in package["entity"]
        if row["entity_id"] == package["graph"]["subject_entity_id"]
    )
    # JSON stays lossless, while literal closing-script sequences cannot escape
    # its inert script element. Data strings are escaped again for Plotly text.
    payload = json.dumps(package, ensure_ascii=False).replace("<", "\\u003c")
    template = (ASSETS / "timeline.html").read_text(encoding="utf-8")
    replacements = {
        "TITLE": escape(subject["name"]),
        "PLOTLY": get_plotlyjs(),
        "DATA": payload,
        "SCRIPT": (ASSETS / "timeline.js").read_text(encoding="utf-8"),
    }
    # Single-pass substitution: source text cannot act as another placeholder.
    page = re.sub(r"@@(TITLE|PLOTLY|DATA|SCRIPT)@@", lambda m: replacements[m[1]], template)
    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page, encoding="utf-8")
    return page
