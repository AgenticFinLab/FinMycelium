"""Temporal enrichment exercises real validation, review boundaries and exports.

Model outputs are scripted; these tests do not claim to verify live LLM calendar
reasoning. Publication dates and original graph bounds remain unchanged.
"""
import copy
from html.parser import HTMLParser
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from finmy.person_epg.validation import validate_person_epg
from finmy.runner.event_additions import empty_additions
from finmy.runner.event_enrichment import enrich_events
from finmy.runner.event_refinement import _publish


FIXTURE = Path(__file__).parent / "fixtures/buffett_person_epg_preview.json"


class EmbeddedGraph(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.capture = False
        self.payload = ""
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.capture = dict(attrs).get("id") == "epg-data"

    def handle_endtag(self, tag):
        if tag == "script":
            self.capture = False

    def handle_data(self, data):
        if self.capture:
            self.payload += data


class TemporalEnrichmentFlowTests(unittest.TestCase):
    def setUp(self):
        self.package = json.loads(FIXTURE.read_text())
        # A synthetic initial graph with a narrow observed envelope, while the
        # explicit research scope still covers the whole 2022-2023 period.
        for row in self.package["time_value"]:
            row["value"] = "2022-06-01"
            for key in ("window_start", "window_end", "original_text", "is_approximate", "window_semantics"):
                row.pop(key, None)
        self.assertTrue(validate_person_epg(self.package)["valid"])
        self.event_id = self.package["event"][0]["event_id"]
        self.config = {"builder_config": {"builder_type": "SparseRagBuilder",
            "sparse_builder_config": {"output_language": "English"},
            "reconstruction": {"mode": "person", "subject": {
                "subject_id": "buffett", "name": "Warren Buffett",
                "coverage_start": "2022", "coverage_end": "2023"}}},
            "event_followup": {"max_model_calls": 2, "max_content_length": 60000}}
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.requests = []

    def run_proposal(self, time, quote, *, review=None):
        proposal = empty_additions()
        proposal["activities"] = [{"key": "documented_meeting", "kind": "action",
            "title": "Reviewed the Occidental investment memorandum ZX-17",
            "actor_id": self.package["graph"]["subject_entity_id"],
            "from_entity_id": None, "to_entity_id": None, "time": time,
            "stage_id": None, "details": [],
            "event_reason": "The source explicitly connects this memorandum review to the same Occidental investment.",
            "citations": [{"document_id": "SUPPLEMENT", "quote": quote}]}]
        sources = [{"document_id": "SUPPLEMENT", "event_ids": [self.event_id],
            "content": quote, "source_url": "https://example.test/retrospective",
            "published_at": "2023-12-31T00:00:00Z"}]
        initial, config = copy.deepcopy(self.package), copy.deepcopy(self.config)

        def complete(system, payload):
            self.requests.append((system, copy.deepcopy(payload)))
            if "proposal" in payload:
                if isinstance(review, Exception):
                    raise review
                return json.dumps(review or {"approved": True, "issues": []})
            return json.dumps(proposal)

        result, report = enrich_events(self.package, sources, self.config, self.root,
                                      completion=complete)
        self.assertEqual(self.package, initial)
        self.assertEqual(self.config, config)
        for table, rows in initial.items():
            self.assertEqual(result[table][:len(rows)] if isinstance(rows, list) else result[table], rows)
        return result, report

    def test_same_event_earlier_activity_expands_observed_range_after_review(self):
        quote = "2022年1月15日，巴菲特审阅了西方石油投资备忘录 ZX-17。"
        value = {"value": "2022-01-15", "evidence_source_contents": [quote],
                 "reasons": ["The source's Chinese calendar date denotes January 15, 2022."]}
        result, report = self.run_proposal(value, quote)
        self.assertEqual(report["events"][0]["status"], "enriched")
        self.assertEqual(report["model_calls"], 2)
        self.assertTrue(validate_person_epg(result)["valid"])
        change = report["events"][0]["time_coverage"]
        self.assertTrue(change["range_changed"])
        self.assertEqual(change["before"]["primary"]["start"]["value"], "2022-06-01")
        self.assertEqual(change["after"]["primary"]["start"]["value"], "2022-01-15")
        proposal_request = self.requests[0][1]
        allowed = {row["activity_id"] for row in self.package["event_activity"]
                   if row["event_id"] == self.event_id}
        self.assertEqual(set(proposal_request["allowed_activity_ids"]), allowed)
        self.assertIn("current_event_time_coverage", proposal_request)
        self.assertIn("proposed_event_time_coverage", self.requests[1][1])
        self.assertEqual(result["graph"]["coverage_start"], "2022-01-01")
        self.assertEqual(result["graph"]["coverage_end"], "2023-12-31")

    def test_calendar_conversion_without_literal_iso_reaches_semantic_review(self):
        quote = "On Christmas Day 2022, Buffett reviewed Occidental memorandum ZX-17."
        time = {"value": "2022-12-25", "evidence_source_contents": [quote],
                "reasons": ["Christmas Day uses December 25 in the stated Gregorian convention."]}
        result, report = self.run_proposal(time, quote)
        self.assertNotIn("2022-12-25", quote)
        self.assertEqual(report["events"][0]["status"], "enriched")
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(result["time_value"][-1]["value"], "2022-12-25")
        for system, _ in self.requests:
            self.assertIn("A date derived by such a rule need not appear literally in Content", system)

    def test_fuzzy_window_survives_real_publish_json_and_html(self):
        quote = "2022年1月下旬，巴菲特审阅了西方石油投资备忘录 ZX-17。"
        time = {"value": "2022-01", "evidence_source_contents": [quote],
                "reasons": ["下旬 denotes day 21 through the end of January; the specific action date is unknown."],
                "time_window": {"start": "2022-01-21", "end": "2022-01-31",
                                "original": "2022年1月下旬", "approximate": True},
                "window_semantics": "uncertainty"}
        final, enrichment = self.run_proposal(time, quote)
        self.assertEqual(enrichment["events"][0]["status"], "enriched")
        initial = SimpleNamespace(extras={"person_epg": self.package, "usage": {"calls": 5}},
                                  logs=[], subject_graph=None)
        report = {"initial_builder_calls": 5, "supplementary_model_calls": enrichment["model_calls"]}
        _, directory = _publish(initial, final, self.root, self.root / "initial", report)
        output = Path(directory)
        saved = json.loads((output / "FinalPersonEPG.json").read_text())
        embedded = json.loads(EmbeddedGraph((output / "FinalPersonEPG.html").read_text()).payload)
        self.assertEqual(saved, final)
        self.assertEqual(embedded, final)
        self.assertTrue(validate_person_epg(saved)["valid"])
        temporal = saved["time_value"][-1]
        self.assertEqual(temporal["window_start"], "2022-01-21")
        self.assertEqual(temporal["window_end"], "2022-01-31")
        self.assertEqual(temporal["original_text"], "2022年1月下旬")
        self.assertTrue(temporal["is_approximate"])
        self.assertEqual(temporal["window_semantics"], "uncertainty")
        self.assertEqual(json.loads((output / "PersonRenderStatus.json").read_text())["status"], "completed")

    def test_semantically_unsupported_conversion_or_membership_still_rejected(self):
        quote = "On Christmas Day 2022, Buffett reviewed a different investment."
        time = {"value": "2022-12-26", "evidence_source_contents": [quote],
                "reasons": ["Candidate conversion submitted for semantic review."]}
        result, report = self.run_proposal(time, quote, review={"approved": False,
            "issues": ["The date conversion is wrong and the source does not establish Occidental event membership."]})
        self.assertEqual(result, self.package)
        self.assertEqual(report["events"][0]["status"], "review_rejected")
        self.assertEqual(report["model_calls"], 2)
        self.assertFalse((self.root / "checkpoint_person_epg.json").exists())

    def test_invented_temporal_evidence_still_fails_before_review(self):
        quote = "Buffett reviewed the Occidental investment memorandum ZX-17."
        time = {"value": "2022-01-15", "evidence_source_contents": ["On January 15, 2022"],
                "reasons": ["Unsupported evidence must not pass merely because the output date is valid."]}
        result, report = self.run_proposal(time, quote)
        self.assertEqual(result, self.package)
        self.assertEqual(report["model_calls"], 1)
        self.assertEqual(report["events"][0]["status"], "invalid_additions")

    def test_review_failure_cannot_commit_temporal_extension_or_reset_budget(self):
        quote = "2022年1月15日，巴菲特审阅了西方石油投资备忘录 ZX-17。"
        time = {"value": "2022-01-15", "evidence_source_contents": [quote],
                "reasons": ["The dated source directly specifies the activity date."]}
        result, report = self.run_proposal(time, quote, review=TimeoutError("No review response"))
        self.assertEqual(result, self.package)
        self.assertEqual(report["events"][0]["status"], "failed")
        self.assertEqual(report["model_calls"], self.config["event_followup"]["max_model_calls"])
        self.assertFalse((self.root / "checkpoint_person_epg.json").exists())


if __name__ == "__main__":
    unittest.main()
