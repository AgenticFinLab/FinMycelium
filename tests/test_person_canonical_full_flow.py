"""Person facts -> organization -> JSON/HTML/replay with only transport mocked.

The tests forbid networking and the legacy extraction entry point. They verify
execution and artifact consistency, not live model semantic performance.
"""
import copy
from contextlib import ExitStack
from html.parser import HTMLParser
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import yaml

from sparse_test_dependencies import install_missing_lmbase_containers
install_missing_lmbase_containers()

from finmy.builder.base import BuildInput
from finmy.builder.sparse_build.main_build import SparseRagBuilder
from finmy.generic import DataSample, UserQueryInput
from finmy.person_epg.validation import validate_person_epg

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "On 2025-01-01 Alpha authorized a transfer of £23.5 million in bitcoin to Beta. Beta received the transfer."


def vf(value, quote=SOURCE):
    return {"value": value, "evidence_source_contents": [quote], "reasons": ["The retained source supports this field."]}


def fact_vf(value, document_id):
    return {"value": value, "citations": [{"document_id": document_id, "quote": SOURCE}]}


class EmbeddedPerson(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.active = False
        self.parts = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.active = dict(attrs).get("id") == "epg-data"

    def handle_endtag(self, tag):
        if tag == "script":
            self.active = False

    def handle_data(self, text):
        if self.active:
            self.parts.append(text)


class CanonicalFixtureInference:
    """Respond to actual phase requests; no builder/assembler is replaced."""
    def __init__(self, *, fail_overview=False, bad_neighbor=False):
        self.calls = []
        self.fail_overview = fail_overview
        self.bad_neighbor = bad_neighbor

    def run(self, infer_input=None, **kwargs):
        user = infer_input.user_msg
        request, end = json.JSONDecoder().raw_decode(user.lstrip())
        tail = user.lstrip()[end:]
        task = {}
        if "\n\nBATCH TASK:\n" in tail:
            task, _ = json.JSONDecoder().raw_decode(tail.split("\n\nBATCH TASK:\n", 1)[1])
        if "source" in request:
            phase = "Extract"
            doc = request["source"]["document_id"]
            field = lambda value: fact_vf(value, doc)
            subject_id = request["subject"]["subject_id"]
            actions = [{"action_id": "AUTHORIZATION", "actor_id": subject_id,
                        "action_type": field("authorize bitcoin transfer"), "timestamp": field("2025-01-01"),
                        "details": [field("Alpha authorized the transfer.")], "time_role": "occurrence"}]
            if self.bad_neighbor:
                actions.append({"action_id": "BAD_NEIGHBOR", "actor_id": "missing-actor",
                                "action_type": field("unusable actor reference"), "timestamp": field("2025-01-01"),
                                "details": []})
            response = {"entities": [{"entity_id": "beta", "name": field("Beta"),
                                       "entity_type": "organization", "aliases": [], "attributes": {}}],
                        "occurrences": [{"occurrence_id": "TRANSFER_SCENE", "title": field("Alpha transfers bitcoin to Beta"),
                                         "subject_relevance": field("Alpha authorized and made the transfer."),
                                         "start_time": field("2025-01-01"), "end_time": field("2025-01-01"),
                                         "descriptions": [], "actions": actions,
                                         "transactions": [{"transaction_id": "BITCOIN_TRANSFER", "name": field("Bitcoin transfer"),
                                                           "from_entity_id": subject_id, "to_entity_id": "beta",
                                                           "timestamp": field("2025-01-01"),
                                                           "details": [field("Alpha transferred £23.5 million in bitcoin to Beta.")],
                                                           "instruments": [field("bitcoin")], "time_role": "occurrence"}]}]}
        elif "assigned_occurrence_ids" in request:
            phase = "Reconcile"
            response = {"operations": [], "reviewed_occurrence_ids": request["assigned_occurrence_ids"]}
        elif task:
            phase = task["phase"]
            if phase == "EventLayout":
                response = {"domains": [{"domain_id": "D1", "label": "Financial activities"}],
                            "events": [{"event_id": "EVENT_TRANSFER", "domain_id": "D1",
                                        "label": "Transfer involvement", "process_scope": "Alpha's documented authorization and transfer to Beta."}]}
            elif phase == "Placement":
                response = {"memberships": [{"event_id": "EVENT_TRANSFER", "activity_id": aid,
                                               "stage_id": None, "detail_indices": None} for aid in task["assigned_ids"]],
                            "unassigned_reasons": [], "occurrence_issues": [],
                            "occurrence_relevance": [{"occurrence_id": oid,
                                                       "subject_relevance": vf("Alpha authorized and made the transfer.")}
                                                      for oid in task["relevance_ids"]]}
            elif phase == "EventStructure":
                response = {"summary": vf("Alpha authorized and made a bitcoin transfer to Beta."),
                            "stages": [{"event_id": "EVENT_TRANSFER", "stage_id": "EXECUTION",
                                        "label": "Authorization and execution",
                                        "boundary_reason": vf("The documented authorization and transfer define this stage.")}],
                            "stage_assignments": [{"activity_id": aid, "stage_id": "EXECUTION"} for aid in task["assigned_ids"]]}
            elif phase == "Relations":
                response = {"candidates": []}
            else:
                raise AssertionError("Unexpected organization phase: " + phase)
        elif "events" in request:
            phase = "Overview"
            if self.fail_overview:
                self.calls.append((phase, copy.deepcopy(request), copy.deepcopy(task)))
                raise RuntimeError("Fixture overview provider unavailable")
            response = {"summary": vf("Alpha authorized and made the documented bitcoin transfer to Beta.")}
        else:
            raise AssertionError("Unexpected inference request keys: " + str(sorted(request)))
        self.calls.append((phase, copy.deepcopy(request), copy.deepcopy(task)))
        encoded = json.dumps(response)
        return SimpleNamespace(response=encoded,
                               cost=SimpleNamespace(prompt_tokens=20, completion_tokens=15),
                               extras={"finish_reason": "stop", "reasoning_tokens": 0, "cached_tokens": 0},
                               to_dict=lambda: {"response": encoded})


class CanonicalPersonFullFlowTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")))
        self.config = copy.deepcopy(yaml.safe_load((ROOT / "configs/person_sparse.yml").read_text())["builder_config"])
        self.config["save_folder"] = str(self.root / "runs")
        self.config["reconstruction"]["subject"] = {
            "subject_id": "person_alpha", "name": "Alpha", "coverage_start": "2025-01-01",
            "coverage_end": "2025-01-02", "scope": "Documented transfer"}
        self.config["sparse_builder_config"].update(output_language="English", max_json_attempts=2)
        self.inputs = BuildInput(UserQueryInput(query_text="Alpha 2025", key_words=["Alpha"]),
                                 [DataSample(sample_id="s1", raw_data_id="r1", content=SOURCE,
                                             category="article", knowledge_field="finance")])

    def run_builder(self, **options):
        transport = CanonicalFixtureInference(**options)
        with patch("finmy.builder.sparse_build.inference.SparseAPIInference", return_value=transport):
            builder = SparseRagBuilder(build_config=copy.deepcopy(self.config))
        with patch.object(builder, "_run_validated", side_effect=AssertionError("Legacy skeleton extraction must not run for Person")):
            output = builder.run(self.inputs)
        return builder, transport, output

    def read(self, builder, name):
        return json.loads(Path(builder.save_dir, name + ".json").read_text(encoding="utf-8"))

    def test_person_build_organizes_canonical_facts_and_replays_the_same_html_data(self):
        builder, transport, output = self.run_builder()
        person = output.extras["person_epg"]
        self.assertEqual(validate_person_epg(person), {"valid": True, "errors": []})
        self.assertEqual(len(person["action"]), 1)
        self.assertEqual(len(person["financial_transaction"]), 1)
        self.assertEqual(len(person["event_activity"]), 2)
        self.assertEqual(person["financial_transaction"][0]["to_entity_id"], "beta")
        phases = [p for p, _, _ in transport.calls]
        self.assertEqual(phases[:2], ["Extract", "Reconcile"])
        self.assertLess(phases.index("Placement"), phases.index("EventStructure"))
        self.assertLess(phases.index("EventStructure"), phases.index("Overview"))
        self.assertNotIn("LayoutReview", phases)
        self.assertNotIn("Relevance", phases)
        ledger = self.read(builder, "CallLedger")
        self.assertFalse(any("Skeleton" in row["agent"] or row["agent"] == "PersonFactRepair" for row in ledger))
        self.assertEqual(self.read(builder, "PersonCanonicalAudit")["status"], "completed")
        self.assertEqual(self.read(builder, "RunManifest")["status"], "completed")
        self.assertEqual(self.read(builder, "FinalPersonEPG"), person)
        embedded = EmbeddedPerson(Path(builder.save_dir, "FinalPersonEPG.html").read_text(encoding="utf-8"))
        self.assertEqual(json.loads("".join(embedded.parts)), person)
        self.assertEqual(builder.integrate_person_from_files(strict=True), person)
        self.assertEqual(len(person["source_document"]), 1)
        self.assertEqual(person["source_document"][0]["content"], SOURCE)

    def test_invalid_fact_neighbor_preserves_valid_facts_and_draft(self):
        builder, _, output = self.run_builder(bad_neighbor=True)
        person = output.extras["person_epg"]
        self.assertEqual(len(person["action"]), 1)
        self.assertEqual(len(person["financial_transaction"]), 1)
        self.assertNotIn("BAD_NEIGHBOR", {r["action_id"] for r in person["action"]})
        self.assertEqual(self.read(builder, "PersonCanonicalAudit")["status"], "partial")
        self.assertEqual(self.read(builder, "RunManifest")["status"], "completed")
        self.assertTrue(Path(builder.save_dir, "FinalPersonEPG.html").is_file())
        self.assertEqual(builder.integrate_person_from_files(strict=True), person)

    def test_overview_failure_keeps_all_facts_and_uses_final_event_summaries(self):
        builder, _, output = self.run_builder(fail_overview=True)
        person = output.extras["person_epg"]
        self.assertEqual(len(person["activity"]), 2)
        self.assertEqual(person["graph"]["descriptions"], [person["event"][0]["summary"]])
        status = self.read(builder, "EventSummaryStatus")
        self.assertEqual(status["status"], "degraded")
        self.assertEqual(status["strategy"], "final_event_summaries")
        self.assertEqual(builder.integrate_person_from_files(strict=True), person)


if __name__ == "__main__":
    unittest.main()
