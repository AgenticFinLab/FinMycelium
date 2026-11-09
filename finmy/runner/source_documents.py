"""Source identity, provenance and replay archives; no relevance model or labels."""
from __future__ import annotations

import copy
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from finmy.reconstruction_scope import read_reconstruction



def make_document(text: str, metadata: dict[str, Any], source: str) -> dict[str, str]:
    """Carry provenance beside the legacy content, without changing raw archives."""
    def field(*names: str) -> str:
        for name in names:
            value = metadata.get(name)
            if value is not None and str(value).strip().lower() not in {"", "nan", "none"}:
                return str(value)
        return ""

    return {
        "title": field("title", "name"), "url": field("url"),
        "published_at": field("datepublished", "datePublished", "date"),
        "source": source, "raw_text": text,
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def render_document(document: dict[str, Any]) -> str:
    """Attach provenance to unchanged source text; publication time is metadata."""
    metadata = {key: document.get(key, "") for key in
                ("document_id", "title", "url", "published_at", "source")}
    return ("Source metadata (published_at is NOT event time):\n" +
            json.dumps(metadata, ensure_ascii=False) + "\n\n" + document["raw_text"])


def load_saved_documents(directory: str | Path) -> list[dict[str, Any]]:
    """Replay existing Web UI output, without new searches or page fetches."""
    directory = Path(directory)
    archived = directory / "retrieved_documents.json"
    if archived.exists():
        return json.loads(archived.read_text(encoding="utf-8"))
    content_files = list(directory.glob("All_Text_Content_*.json"))
    if len(content_files) != 1:
        raise ValueError("Choose one pipeline_output directory containing one All_Text_Content_*.json")
    contents = json.loads(content_files[0].read_text(encoding="utf-8"))
    if not isinstance(contents, list) or not all(isinstance(x, str) for x in contents):
        raise ValueError("All_Text_Content must be a list of strings")
    candidates = defaultdict(list)
    for pattern, source in (("formatted_bocha_search_results_*.json", "bocha"),
                            ("formatted_baidu_search_results_*.json", "baidu"),
                            ("structure_data_urllink_*.json", "url"),
                            ("structured_data_filepath_*.json", "file")):
        for file in directory.glob(pattern):
            for item in json.loads(file.read_text(encoding="utf-8")):
                candidates[str(item.get("title", ""))].append((item, source))
    docs = []
    for text in contents:
        match = re.match(r"(?i)title:\s*\n([^\n]*)", text)
        title = match.group(1) if match else ""
        matches = candidates.get(title, [])
        # Do not attach an arbitrary URL/date when several pages share a title.
        if len(matches) == 1:
            metadata, source = matches[0]
        else:
            metadata, source = {"title": title}, "unknown"
        docs.append(make_document(text, metadata, source))
    return docs


def prepare_documents(documents, query, keywords, config, save_dir, *, document_id_offset=0):
    """Archive selected source bodies and routing without reclassifying them.

    Deterministic IDs are shared by budget reports and source registries. Search
    source_id/version, event routes and raw characters survive unchanged. Old
    relevance labels are deliberately discarded when replaying an older run.
    """
    reconstruction = read_reconstruction(config)
    if type(document_id_offset) is not int or document_id_offset < 0:
        raise ValueError("document_id_offset must be a nonnegative integer")
    docs = []
    for index, item in enumerate(documents, document_id_offset + 1):
        if not isinstance(item, dict) or not isinstance(item.get("raw_text"), str):
            raise ValueError("Each document must have string raw_text")
        doc = copy.deepcopy(item)
        for key in ("relevance", "relevance_reason", "confidence", "chunks"):
            doc.pop(key, None)
        doc.update(make_document(item["raw_text"], {**item,
            "datepublished": item.get("published_at", "")}, str(item.get("source", "unknown"))))
        doc["document_id"] = f"DOC_{index:04d}"
        doc.setdefault("search_phase", "initial")
        saved_queries = item.get("retrieval_queries")
        saved_queries = saved_queries if isinstance(saved_queries, list) else []
        queries = [query, *keywords, *saved_queries]
        discoveries = item.get("discoveries")
        for discovery in discoveries if isinstance(discoveries, list) else []:
            if isinstance(discovery, dict):
                queries.append(discovery.get("query"))
        doc["retrieval_queries"] = list(dict.fromkeys(q for q in queries if isinstance(q, str) and q.strip()))
        docs.append(doc)
    destination = Path(save_dir)
    _write_json(destination / "retrieved_documents.json", docs)
    _write_json(destination / "reconstruction_profile.json", reconstruction)
    subject = reconstruction.get("subject") or {}
    profile = {"subject": subject.get("name", query), "organizations": [],
               "period": [subject.get("coverage_start"), subject.get("coverage_end")],
               "focus": [subject["scope"]] if subject.get("scope") else []}
    _write_json(destination / "event_profile.json", {
        "original_request": query, "keywords": keywords,
        "reconstruction": reconstruction, "profile": profile, "status": "declared_scope"})
    return docs
