"""Traceable quote alignment and conservative, non-mutating review diagnostics."""

import hashlib
import re

from .contracts import date_interval
from .validation import scalar


EVIDENCE_CONTRACT_VERSION = 2


def normalize_whitespace(text):
    """Return collapsed text and a character-level map into the unchanged source."""
    chars, spans = [], []
    for match in re.finditer(r"\s+|\S", text):
        token = match.group()
        chars.append(" " if token.isspace() else token)
        spans.append((match.start(), match.end()))
    return "".join(chars), spans


def _occurrences(text, needle):
    start = 0
    while needle:
        position = text.find(needle, start)
        if position < 0:
            break
        yield position
        start = position + 1


def verified_fields(value, path="event"):
    if isinstance(value, dict):
        if isinstance(value.get("value"), str):
            yield path, value
        for key, child in value.items():
            yield from verified_fields(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from verified_fields(child, f"{path}[{index}]")


class SourceIndex:
    def __init__(self, samples):
        self.sources = []
        for sample in samples:
            normalized, spans = normalize_whitespace(sample.content)
            self.sources.append({"sample_id": sample.sample_id, "text": sample.content,
                                 "sha256": hashlib.sha256(sample.content.encode("utf-8")).hexdigest(),
                                 "normalized": normalized, "spans": spans})

    def locate(self, quote):
        if not quote.strip():
            return []
        normalized_quote = normalize_whitespace(quote)[0].strip()
        anchors = []
        for source in self.sources:
            exact = list(_occurrences(source["text"], quote))
            if exact:
                positions = [(start, start + len(quote), "exact") for start in exact]
            else:
                positions = [(source["spans"][start][0],
                              source["spans"][start + len(normalized_quote) - 1][1], "whitespace")
                             for start in _occurrences(source["normalized"], normalized_quote)]
            for start, end, method in positions:
                anchors.append({"sample_id": source["sample_id"], "source_sha256": source["sha256"],
                                "start": start, "end": end, "method": method,
                                "source_text": source["text"][start:end]})
        return anchors


def grounded_evidence_report(payload, samples, user_query=None):
    index = SourceIndex(samples)
    metadata = {}
    if user_query is not None:
        metadata["query_text"] = user_query.query_text or ""
        metadata["key_words"] = list(user_query.key_words or [])
    metadata_values = [metadata.get("query_text", ""), *metadata.get("key_words", [])]
    if metadata.get("key_words"):
        metadata_values.append(", ".join(metadata["key_words"]))
    metadata_values = {normalize_whitespace(text)[0].strip() for text in metadata_values if text}
    links, missing = [], []
    for path, value in verified_fields(payload):
        quotes = value.get("evidence_source_contents", [])
        if not quotes:
            missing.append(path)
        for quote in quotes:
            anchors = index.locate(quote)
            exact = any(anchor["method"] == "exact" for anchor in anchors)
            status = "exact" if exact else "whitespace" if anchors else (
                "query_metadata_not_source" if normalize_whitespace(quote)[0].strip() in metadata_values
                else "unresolved")
            links.append({"field": path, "quote": quote, "status": status, "anchors": anchors,
                          "sample_ids": sorted({anchor["sample_id"] for anchor in anchors})})
    counts = {status: sum(link["status"] == status for link in links)
              for status in ("exact", "whitespace", "query_metadata_not_source", "unresolved")}
    return {"contract_version": EVIDENCE_CONTRACT_VERSION, "method": "exact_or_whitespace_with_offsets",
            "offset_unit": "unicode_codepoint", "offset_end": "exclusive",
            "semantic_support_checked": False, "quote_count": len(links),
            "unmatched_quote_count": counts["unresolved"] + counts["query_metadata_not_source"],
            "match_counts": counts, "fields_without_quotes": missing, "links": links,
            "query_metadata": metadata,
            "sources": [{"sample_id": s["sample_id"], "source_sha256": s["sha256"],
                         "characters": len(s["text"])} for s in index.sources]}


_CONDITIONAL = re.compile(
    r"\b(propos\w*|approv\w*|agree\w*|commit\w*|pledge\w*|intend\w*|expect\w*|"
    r"estimat\w*|enable\w*|would|will|may|could|obligation|not yet|unpaid)\b", re.I)
_EXECUTED = re.compile(r"\b(paid|disbursed|transferred|received|completed payment)\b", re.I)
_DATE = re.compile(
    r"\b\d{4}-\d{2}(?:-\d{2})?\b|"
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}\b|"
    r"\b\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}\b", re.I)


def quality_review_report(payload, samples, evidence):
    """Report review candidates only; never certify entailment or edit model facts."""
    by_field = {}
    for link in evidence["links"]:
        by_field.setdefault(link["field"], []).extend(link["anchors"])
    issues = []

    def attached(prefix):
        return [a for path, anchors in by_field.items()
                if path == prefix or path.startswith(prefix + ".") or path.startswith(prefix + "[")
                for a in anchors]

    def issue(kind, path, **details):
        issues.append({"kind": kind, "path": path, "status": "needs_review", **details})

    for path, field in verified_fields(payload):
        if path.rsplit(".", 1)[-1] not in {"timestamp", "start_time", "end_time"}:
            continue
        interval = date_interval(field["value"])
        if interval is None:
            if field["value"].strip().casefold() not in {"unknown", "unspecified", "null", "none", "n/a", ""}:
                issue("unparsed_date", path, value=field["value"])
            continue
        if (interval[1] - interval[0]).days > 0:
            continue
        anchors = attached(path)
        dates = [date_interval(match.group()) for a in anchors
                 for match in _DATE.finditer(" ".join(a["source_text"].split()))]
        if not any(item and item[0].date() == interval[0].date() for item in dates):
            issue("precise_date_not_located_in_attached_quotes", path, value=field["value"])
        if any(re.search(r"\b(prepared|updated|estimated|expected|scheduled)\b", a["source_text"], re.I)
               for a in anchors):
            issue("document_or_projected_date_check", path, value=field["value"])

    for si, stage in enumerate(payload.get("stages", [])):
        for ei, episode in enumerate(stage.get("episodes", [])):
            base = f"event.stages[{si}].episodes[{ei}]"
            participants = {p["participant_id"]: scalar(p.get("name")) for p in episode.get("participants", [])}
            for ti, transaction in enumerate(episode.get("transactions", [])):
                path = f"{base}.transactions[{ti}]"
                quotes = [a["source_text"] for a in attached(path)]
                cues = sorted({m.group().lower() for text in quotes for m in _CONDITIONAL.finditer(text)})
                if cues:
                    issue("transfer_state_requires_review", path, conditional_cues=cues,
                          contains_execution_word=any(_EXECUTED.search(text) for text in quotes))
                if not quotes:
                    issue("transfer_without_located_evidence", path)
            for pi, participant in enumerate(episode.get("participants", [])):
                for ai, action in enumerate(participant.get("actions", [])):
                    path = f"{base}.participants[{pi}].actions[{ai}]"
                    name = scalar(action.get("name")) or ""
                    quotes = [a["source_text"] for a in attached(path)]
                    if _EXECUTED.search(name) and any(_CONDITIONAL.search(text) for text in quotes):
                        issue("action_execution_vs_conditional_evidence", path)
            for ri, relation in enumerate(episode.get("participant_relations", [])):
                path = f"{base}.participant_relations[{ri}]"
                text = " ".join(" ".join(a["source_text"].split()) for a in attached(path)).casefold()
                absent = [identifier for identifier in (relation.get("from_participant_id"), relation.get("to_participant_id"))
                          if participants.get(identifier) and
                          " ".join(participants[identifier].split()).casefold() not in text]
                if absent:
                    issue("relation_endpoint_name_not_in_attached_quotes", path, participant_ids=absent,
                          caveat="Aliases and pronouns may explain this; verify endpoint applicability and direction.")

    # These are source paragraphs, not an extracted fact inventory. A citation
    # touching a paragraph is not proof that the paragraph's facts were covered.
    units = []
    for sample in samples:
        spans = [a for link in evidence["links"] for a in link["anchors"] if a["sample_id"] == sample.sample_id]
        for number, match in enumerate(re.finditer(r"\S[\s\S]*?(?=\n\s*\n|\Z)", sample.content)):
            start, end = match.span()
            cited = any(a["start"] < end and a["end"] > start for a in spans)
            units.append({"unit_id": f"{sample.sample_id}:paragraph:{number + 1}",
                          "sample_id": sample.sample_id, "start": start, "end": end,
                          "has_quote_overlap": cited, "preview": match.group()[:240]})
    return {"method": "conservative_review_candidates_v1", "semantic_support_checked": False,
            "scope": "English cue/date diagnostics; other wording and languages may be unchecked.",
            "status": "needs_review", "issues": issues, "source_units": units,
            "uncited_source_units": sum(not u["has_quote_overlap"] for u in units),
            "limitations": ["A located quote is not proof of entailment.",
                            "Uncited paragraphs may be irrelevant; cited paragraphs may still contain omitted facts.",
                            "Zero heuristic findings is not semantic approval."]}
