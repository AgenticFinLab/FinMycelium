"""Offline person-scope contracts; fake decisions do not measure LLM accuracy."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from finmy.runner.relevance_filter import (
    CLASSIFY_PROMPT, PERSON_CLASSIFY_PROMPT, PROFILE_PROMPT,
    filter_documents, make_document,
)


SUBJECT = {
    "subject_id": "person_warren_buffett", "name": "Warren Buffett",
    "aliases": ["巴菲特"], "coverage_start": "2022", "coverage_end": "2023",
    "scope": "Buffett's involvement in Berkshire's Occidental investments",
}
QUERY = "Reconstruct Buffett's Occidental investment statements in 2022–2023."


def person_config(**options):
    return {"builder_config": {"reconstruction": {
        "mode": "person", "subject": copy.deepcopy(SUBJECT),
    }}, "relevance_filter": options}


def document(text):
    return make_document(text, {"title": "Saved article", "url": "https://example.test/source"},
                         "file")


class RecordedCompletion:
    def __init__(self, decisions=None):
        self.calls = []
        self.decisions = decisions or {}

    def __call__(self, system, payload):
        self.calls.append((system, copy.deepcopy(payload)))
        if "chunks" not in payload:
            return json.dumps({"subject": "event", "organizations": [],
                               "period": [None, None], "focus": []})
        return json.dumps({"decisions": [
            {"chunk_id": c["chunk_id"], "relevance": self.decisions.get(c["text"], "CORE"),
             "confidence": 0.99, "event_time": None, "matched_entities": [],
             "reason": "Fixture decision only; no live relevance assessment.",
             "evidence": c["text"][:100]}
            for c in payload["chunks"]
        ]})


class PersonRelevanceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)

    def run_filter(self, docs, config=None, model=None):
        return filter_documents(docs, QUERY, ["Buffett", "OXY"],
                                config if config is not None else person_config(),
                                self.path, completion=model or RecordedCompletion())

    def test_person_profile_is_declared_scope_and_needs_no_profile_call(self):
        model = RecordedCompletion()
        config = person_config(event_profile={"subject": "unrelated injected profile"})
        self.run_filter([document("Buffett discussed Occidental in 2023.")], config, model)
        self.assertEqual(len(model.calls), 1)
        system, payload = model.calls[0]
        self.assertEqual(system, PERSON_CLASSIFY_PROMPT)
        self.assertEqual(payload["original_request"], QUERY)
        self.assertEqual(payload["person_profile"]["subject"], SUBJECT["name"])
        self.assertEqual(payload["person_profile"]["period"], ["2022", "2023"])
        self.assertEqual(payload["person_profile"]["focus"], [SUBJECT["scope"]])
        self.assertEqual(payload["reconstruction"]["subject"], SUBJECT)
        saved = json.loads((self.path / "event_profile.json").read_text())
        self.assertEqual(saved["reconstruction"]["mode"], "person")
        self.assertEqual(saved["profile"], payload["person_profile"])
        report = json.loads((self.path / "relevance_decisions.json").read_text())
        self.assertEqual(report["version"], "person-relevance-v1")

    def test_narrow_buffett_scope_keeps_episode_context_and_rejects_generic_bio(self):
        statements = "Buffett discussed the Occidental investment in 2023."
        prerequisite = "The 2019 Occidental warrants explain the later investment."
        biography = "Buffett's favorite breakfast is discussed in this biography."
        unrelated_company = "An unrelated subsidiary replaced office furniture."
        model = RecordedCompletion({statements: "CORE", prerequisite: "CONTEXT",
                                    biography: "IRRELEVANT", unrelated_company: "IRRELEVANT"})
        result = self.run_filter([document(s) for s in
                                 (statements, prerequisite, biography, unrelated_company)], model=model)
        self.assertEqual([d["raw_text"] for d in result["documents"]],
                         [statements, prerequisite])
        self.assertEqual(result["summary"]["labels"], {"CORE": 1, "CONTEXT": 1, "IRRELEVANT": 2})
        self.assertIn("Generic biography is not CONTEXT", model.calls[0][0])
        self.assertIn("Preserve the organization as actor", model.calls[0][0])
        self.assertIn("A more specific original request narrows", model.calls[0][0])
        self.assertNotIn("Fixture decision", "".join(result["contents"]))
        self.assertNotIn("person_warren_buffett", "".join(result["contents"]))

    def test_cache_separates_person_identity_window_scope_and_event_mode(self):
        docs, model = [document("Saved source")], RecordedCompletion()
        initial = person_config()
        self.run_filter(docs, initial, model)
        repeat = self.run_filter(docs, initial, model)
        self.assertEqual(repeat["summary"]["cache_hits"], 1)
        self.assertEqual(len(model.calls), 1)
        for field, value in (("subject_id", "another_person_id"),
                             ("coverage_end", "2024"), ("scope", "Appointments")):
            changed = copy.deepcopy(initial)
            changed["builder_config"]["reconstruction"]["subject"][field] = value
            self.run_filter(docs, changed, model)
        self.assertEqual(len(model.calls), 4)
        self.run_filter(docs, {}, model)
        self.assertEqual(len(model.calls), 6)
        self.assertEqual([call[0] for call in model.calls[-2:]],
                         [PROFILE_PROMPT, CLASSIFY_PROMPT])

    def test_default_and_explicit_event_modes_keep_original_payload_and_cache(self):
        docs, model = [document("Saved event source")], RecordedCompletion()
        self.run_filter(docs, {}, model)
        self.assertEqual(set(model.calls[0][1]), {"original_request", "keywords"})
        self.assertEqual(set(model.calls[1][1]),
                         {"original_request", "keywords", "event_profile", "chunks"})
        result = self.run_filter(docs, {"builder_config": {"reconstruction": {"mode": "event"}}}, model)
        self.assertEqual(result["summary"]["cache_hits"], 2)
        self.assertEqual(len(model.calls), 2)
        self.assertFalse((self.path / "reconstruction_profile.json").exists())

    def test_invalid_person_is_rejected_even_with_filter_disabled(self):
        model = RecordedCompletion()
        config = person_config(enabled=False)
        del config["builder_config"]["reconstruction"]["subject"]["subject_id"]
        with self.assertRaises(ValueError):
            self.run_filter([document("Saved source")], config, model)
        self.assertEqual(model.calls, [])
        self.assertFalse((self.path / "retrieved_documents.json").exists())

    def test_disabled_person_filter_keeps_exact_text_and_records_scope(self):
        model = RecordedCompletion()
        result = self.run_filter([document("  untouched\nsource ")],
                                 person_config(enabled=False), model)
        self.assertEqual(model.calls, [])
        self.assertEqual(result["contents"], ["  untouched\nsource "])
        saved = json.loads((self.path / "reconstruction_profile.json").read_text())
        self.assertEqual(saved["subject"], SUBJECT)

    def test_person_batch_failure_retains_all_sources_without_exception_leak(self):
        def fail(*args):
            raise TimeoutError("SECRET-MUST-NOT-BE-LOGGED")
        result = self.run_filter([document("Saved source")], model=fail)
        self.assertEqual(result["summary"]["labels"], {"REVIEW": 1})
        self.assertEqual(result["summary"]["model_calls"], 1)
        self.assertNotIn("SECRET-MUST-NOT-BE-LOGGED", json.dumps(result))

    def test_person_rejection_without_verbatim_evidence_is_retained(self):
        model = RecordedCompletion({"Source text": "IRRELEVANT"})
        def forged(system, payload):
            response = json.loads(model(system, payload))
            response["decisions"][0]["evidence"] = "Fabricated text"
            return json.dumps(response)
        result = self.run_filter([document("Source text")], model=forged)
        self.assertEqual(result["summary"]["labels"], {"REVIEW": 1})


if __name__ == "__main__":
    unittest.main()
