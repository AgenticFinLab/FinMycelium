"""Contract, provenance, isolation and cost-preserving fact checkpoints."""
import copy
import json
from types import SimpleNamespace
import unittest

from sparse_test_dependencies import install_missing_lmbase_containers
install_missing_lmbase_containers()

from finmy.builder.sparse_build.completion_errors import IncompleteCompletionError
from finmy.builder.sparse_build.person_fact_pipeline import (
    apply_canonical_proposal, build_canonical_facts,
)
from finmy.person_epg.validation import validate_person_epg


TEXT = "Alice announced an investment on 2023-05-01. Alice is also known as A and is chairman."


def vf(value, document="UPSTREAM_DOC", quote=TEXT):
    return {"value": value, "citations": [{"document_id": document, "quote": quote}]}


def inputs(texts=(TEXT,), same_raw=False):
    samples = [SimpleNamespace(sample_id=f"S{i}", raw_data_id="RAW" if same_raw else f"RAW{i}", content=text)
               for i, text in enumerate(texts)]
    registry = {s.raw_data_id: {"document_id": "UPSTREAM_DOC" if len(texts) == 1 or same_raw else f"DOC{i}",
                               "event_ids": ["investment"]} for i, s in enumerate(samples)}
    return SimpleNamespace(samples=samples, user_query=SimpleNamespace(extras={"source_registry": registry}))


SUBJECT = {"subject_id": "alice", "name": "Alice", "aliases": [], "coverage_start": "2022", "coverage_end": "2023"}


def extraction(document="UPSTREAM_DOC", suffix="", text=TEXT, background=False):
    field = lambda value: vf(value, document, text)
    occurrence = {"occurrence_id": "O" + suffix, "title": field("Investment announcement"),
        "subject_relevance": field("Alice announced the investment."), "start_time": field("2023-05-01"),
        "end_time": field("2023-05-01"), "descriptions": [field("Documented investment announcement.")],
        "actions": [] if background else [{"action_id": "ACT" + suffix, "actor_id": "alice",
            "action_type": field("announces investment"), "timestamp": field("2023-05-01"),
            "details": [field("Alice publicly announced an investment.")]}], "transactions": []}
    return {"entities": [{"entity_id": "alice", "name": field("Alice"), "entity_type": "individual",
                           "aliases": ["A"], "attributes": {"role": field("chairman")}}], "occurrences": [occurrence]}


def completed_review(task):
    return {"operations": [], "reviewed_occurrence_ids": task["assigned_occurrence_ids"]}


class FactPipelineTest(unittest.TestCase):
    def run_facts(self, infer, build_input=None, **kwargs):
        saved = {}
        def save(data, name):
            saved[name] = copy.deepcopy(data)
        result = build_canonical_facts(build_input or inputs(), SUBJECT, infer=infer, save=save, **kwargs)
        return (*result, saved)

    def test_registry_ids_routes_and_existing_subject_attributes_are_preserved(self):
        def infer(system, user, name, validator):
            task = json.loads(user)
            if "Extract" in name:
                self.assertEqual(task["source"]["document_id"], "UPSTREAM_DOC")
                self.assertEqual(task["source"]["routing"]["event_ids"], ["investment"])
                result = extraction()
            else:
                result = completed_review(task)
            validator(result)
            return result
        package, audit, _ = self.run_facts(infer)
        self.assertEqual(audit["status"], "completed")
        self.assertEqual(package["entity"][0]["attributes"]["role"], "chairman")
        self.assertIn("A", [r["alias"] for r in package["entity_alias"]])
        self.assertEqual({s["document_id"] for s in package["evidence_span"]}, {"UPSTREAM_DOC"})
        self.assertEqual(validate_person_epg(package), {"valid": True, "errors": []})

    def test_bad_fact_does_not_discard_good_fact_and_recovery_only_repairs_pending_chunk(self):
        first = True
        def infer(system, user, name, validator):
            task = json.loads(user)
            if "Extract" in name:
                result = extraction()
                bad = copy.deepcopy(result["occurrences"][0]["actions"][0])
                bad["action_id"] = "ACT_NEW"
                bad["details"][0]["citations"][0]["quote"] = "Invented quotation"
                result["occurrences"][0]["actions"].append(bad)
                return result
            return completed_review(task)
        package, audit, _ = self.run_facts(infer)
        self.assertEqual(audit["status"], "partial")
        self.assertEqual([r["action_id"] for r in package["action"]], ["ACT"])
        calls = []
        def recover(system, user, name, validator):
            calls.append(name)
            task = json.loads(user)
            if "Extract" in name:
                self.assertTrue(task["retry_items"])
                result = extraction()
                result["occurrences"][0]["actions"][0]["action_id"] = "ACT_NEW"
                return result
            return completed_review(task)
        fixed, report, _ = self.run_facts(recover, checkpoint={"package": package, "audit": audit})
        self.assertEqual({r["action_id"] for r in fixed["action"]}, {"ACT", "ACT_NEW"})
        self.assertEqual(report["status"], "completed")
        self.assertEqual(sum("Extract" in n for n in calls), 1)

    def test_source_failure_keeps_other_document_and_resumes_without_repeating_it(self):
        build_input = inputs((TEXT, TEXT))
        def infer(system, user, name, validator):
            task = json.loads(user)
            if "Extract" in name:
                doc = task["source"]["document_id"]
                if doc == "DOC0":
                    raise TimeoutError("source request timed out")
                return extraction(doc, doc)
            return completed_review(task)
        package, audit, _ = self.run_facts(infer, build_input)
        self.assertEqual(audit["status"], "partial")
        calls = []
        def recover(system, user, name, validator):
            task = json.loads(user)
            calls.append((name, task))
            if "Extract" in name:
                self.assertEqual(task["source"]["document_id"], "DOC0")
                return extraction("DOC0", "DOC0")
            return completed_review(task)
        fixed, report, _ = self.run_facts(recover, build_input, checkpoint={"package": package, "audit": audit})
        self.assertEqual(len(fixed["action"]), 2)
        self.assertEqual(report["status"], "completed")
        self.assertEqual(sum("Extract" in name for name, _ in calls), 1)

    def test_interruption_checkpoint_is_never_completed(self):
        snapshots = {}
        def save(data, name):
            snapshots[name] = copy.deepcopy(data)
        def infer(system, user, name, validator):
            if "Reconcile" in name:
                raise KeyboardInterrupt()
            return extraction()
        with self.assertRaises(KeyboardInterrupt):
            build_canonical_facts(inputs(), SUBJECT, infer=infer, save=save)
        self.assertEqual(snapshots["PersonCanonicalAudit"]["status"], "partial")
        self.assertNotEqual(snapshots["PersonCanonicalAudit"]["phase"], "completed")

    def test_length_splits_sources_but_transport_errors_do_not(self):
        text = (TEXT + "\n") * 15
        calls = []
        def infer(system, user, name, validator):
            task = json.loads(user)
            calls.append(name)
            if "Extract" in name:
                if name.endswith("001"):
                    raise IncompleteCompletionError("PersonFacts", finish_reason="length")
                return extraction(suffix=name[-1], text=task["source"]["text"])
            return completed_review(task)
        package, audit, _ = self.run_facts(infer, inputs((text,)))
        self.assertEqual(len(package["action"]), 2)
        self.assertEqual(sum("Extract" in n for n in calls), 3)
        self.assertEqual(audit["subdivisions"][0]["reason"], "output_length")
        calls.clear()
        def denied(system, user, name, validator):
            calls.append(name)
            raise RuntimeError("account rejected request")
        package, audit, _ = self.run_facts(denied, inputs((text,)))
        self.assertEqual(len(calls), 1)
        self.assertEqual(audit["status"], "no_usable_facts")

    def test_failed_reconciliation_item_is_pending_and_retried(self):
        def infer(system, user, name, validator):
            task = json.loads(user)
            if "Extract" in name:
                return extraction()
            return {"operations": [{"op": "move_fact", "fact_id": "MISSING", "occurrence_id": "O", "reason": "Bad ID"}],
                    "reviewed_occurrence_ids": ["O"]}
        package, audit, _ = self.run_facts(infer)
        self.assertEqual(audit["pending_occurrence_ids"], ["O"])
        calls = []
        def recover(system, user, name, validator):
            calls.append(name)
            self.assertIn("Reconcile", name)
            return completed_review(json.loads(user))
        _, report, _ = self.run_facts(recover, checkpoint={"package": package, "audit": audit})
        self.assertEqual(len(calls), 1)
        self.assertEqual(report["status"], "completed")

    def test_empty_retry_does_not_claim_a_rejected_fact_was_resolved(self):
        def infer(system, user, name, validator):
            if "Extract" in name:
                result = extraction()
                bad = copy.deepcopy(result["occurrences"][0]["actions"][0])
                bad["action_id"] = "BAD"
                bad["details"][0]["citations"][0]["quote"] = "Not present in the source"
                result["occurrences"][0]["actions"].append(bad)
                return result
            return completed_review(json.loads(user))
        package, audit, _ = self.run_facts(infer)
        def empty(system, user, name, validator):
            if "Extract" in name:
                return {"entities": [], "occurrences": []}
            return completed_review(json.loads(user))
        fixed, report, _ = self.run_facts(empty, checkpoint={"package": package, "audit": audit})
        self.assertEqual(report["status"], "partial")
        self.assertEqual(len(report["pending_source_chunks"]), 1)
        self.assertTrue(any(r.get("fact", {}).get("action_id") == "BAD" and not r.get("resolved")
                            for r in report["items"]))
        self.assertEqual([r["action_id"] for r in fixed["action"]], ["ACT"])

    def test_background_sources_use_context_without_inventing_actions(self):
        def infer(system, user, name, validator):
            return extraction(background=True) if "Extract" in name else completed_review(json.loads(user))
        package, audit, _ = self.run_facts(infer)
        self.assertFalse(package["action"])
        self.assertEqual(package["activity"][0]["context_occurrence_id"], "O")
        self.assertEqual(audit["status"], "completed")

    def test_same_raw_document_multiple_samples_remain_separate_snapshots(self):
        seen = []
        def infer(system, user, name, validator):
            task = json.loads(user)
            if "Extract" in name:
                doc = task["source"]["document_id"]
                seen.append(doc)
                return extraction(doc, str(len(seen)))
            return completed_review(task)
        package, _, _ = self.run_facts(infer, inputs((TEXT, TEXT), same_raw=True))
        self.assertEqual(len(set(seen)), 2)
        self.assertEqual(len(package["source_document"]), 2)

    def test_same_quote_from_two_sources_survives_fact_merge(self):
        def infer(system, user, name, validator):
            task = json.loads(user)
            if "Extract" in name:
                doc = task["source"]["document_id"]
                return extraction(doc, doc)
            return completed_review(task)
        package, _, _ = self.run_facts(infer, inputs((TEXT, TEXT)))
        merged, audit = apply_canonical_proposal(package, {"operations": [{"op": "merge_facts",
            "keep_id": "ACTDOC0", "fact_ids": ["ACTDOC1"], "reason": "Same actual announcement"}]})
        row = next(r for r in merged["action"] if r["action_id"] == "ACTDOC0")
        spans = {r["span_id"]: r for r in merged["evidence_span"]}
        docs = {spans[r["span_id"]]["document_id"] for r in merged["evidence_link"]
                if r["evidence_set_id"] == row["evidence_set_id"] and r["field_path"] == "/action_type"}
        self.assertEqual(docs, {"DOC0", "DOC1"})

    def test_programming_errors_propagate_and_do_not_look_like_api_failures(self):
        def infer(*args):
            raise AssertionError("programming defect")
        with self.assertRaises(AssertionError):
            self.run_facts(infer)


if __name__ == "__main__":
    unittest.main()
