"""Public Person EPG contract and its relational source model."""

import json
from pathlib import Path

SCHEMA_VERSION = "person-epg-3.0"
DIRECTORY = Path(__file__).resolve().parent
MODEL = json.loads((DIRECTORY / "schema_model.json").read_text(encoding="utf-8"))
JSON_SCHEMA = json.loads((DIRECTORY / "schema.json").read_text(encoding="utf-8"))
