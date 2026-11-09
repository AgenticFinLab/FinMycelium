"""Discovery is organization context, never a replacement for extracted evidence."""
import copy
import json
import sys
import types
import unittest
from unittest.mock import patch

from finmy.builder.sparse_build.organization_batches import organize_person_plan
from finmy.builder.sparse_build.person_organization import apply_organization
from finmy.builder.sparse_build.storyline_context import (
    align_storyline_ids, candidate_storylines, storyline_resolution,
)
from finmy.subject_graph.runner import build_from_contents
from test_sparse_person_organization import facts, plan
from test_sparse_organization_batches import many_facts, OrganizationResponses


def discovered():
    return {"version": "person-storylines-v1", "subject": {"name": "Example person"},
        "domains": [{"domain_id": "D", "label": "Public communication", "summary": "Candidate field"}],
        "events": [{"event_id": "E", "domain_id": "D", "label": "Documented communication",
                    "summary": "A candidate only", "person_connection": "To verify",
                    "scope": "Public communication", "event_terms": ["communication"],
                    "questions": ["What did the person say?"]},
                   {"event_id": "E_missing", "domain_id": "D", "label": "Unconfirmed project",
                    "summary": "NEVER PROMOTE THIS TO SOURCE EVIDENCE"}]}


class StorylineOrganizationHandoffTests(unittest.TestCase):
    def test_small_plan_receives_candidates_but_keeps_only_supported_organization(self):
        original_facts, discovery = facts(), discovered()
        before_facts, before_discovery = copy.deepcopy(original_facts), copy.deepcopy(discovery)
        saved, responses = {}, OrganizationResponses()
        result = organize_person_plan(original_facts, {"stages": []}, {"name": "Example person"},
            "English", responses, lambda data, name: saved.update({name: data}), storyline_plan=discovery)
        request = responses.calls[0]["request"]
        self.assertFalse(request["candidate_storylines"]["is_source_evidence"])
        self.assertIn("Reuse", request["storyline_instructions"])
        self.assertNotIn("NEVER PROMOTE", json.dumps(request["facts"]))
        self.assertEqual(result, plan())
        rendered, _ = apply_organization(original_facts, result)
        self.assertEqual([e["event_id"] for e in rendered["event"]], ["E"])
        audit = saved["PersonStorylineResolution"]
        self.assertEqual([r["status"] for r in audit["events"]], ["represented", "not_represented"])
        self.assertEqual(audit["events"][0]["activity_ids"], ["A"])
        self.assertFalse(audit["semantic_support_checked"])
        self.assertEqual(original_facts, before_facts)
        self.assertEqual(discovery, before_discovery)

    def test_phased_execution_receives_same_discovery_without_extra_model_calls(self):
        saved, responses = {}, OrganizationResponses()
        result = organize_person_plan(many_facts(), {"stages": []}, {"name": "Example person"},
            "English", responses, lambda data, name: saved.update({name: data}), storyline_plan=discovered())
        self.assertEqual(result["events"][0]["event_id"], "E")
        self.assertTrue(all(call["request"]["candidate_storylines"]["events"][0]["event_id"] == "E"
                            for call in responses.calls))
        self.assertEqual(len(saved["PersonStorylineResolution"]["events"]), 2)
        self.assertTrue(all(call["task"]["phase"] != "StorylineReview" for call in responses.calls))

    def test_exact_label_remap_updates_references_without_rewriting_facts(self):
        discovery = discovered()
        discovery["domains"][0]["domain_id"] = "discovered_domain"
        discovery["events"][0]["event_id"] = "discovered_event"
        for row in discovery["events"]:
            row["domain_id"] = "discovered_domain"
        candidates = candidate_storylines(discovery)
        before = plan()
        aligned, remaps = align_storyline_ids(before, candidates)
        self.assertEqual(before, plan())
        self.assertEqual(aligned["events"][0]["event_id"], "discovered_event")
        self.assertEqual(aligned["memberships"][0]["event_id"], "discovered_event")
        self.assertEqual(aligned["stages"][0]["event_id"], "discovered_event")
        self.assertEqual(aligned["events"][0]["domain_id"], "discovered_domain")
        self.assertEqual(remaps["event_id_remaps"], [{"from": "E", "to": "discovered_event"}])
        audit = storyline_resolution(candidates, aligned, remaps)
        self.assertEqual(audit["id_remap_counts"], {"domain_id_remaps": 1, "event_id_remaps": 1})
        self.assertEqual(audit["not_represented_event_count"], 1)
        package, _ = apply_organization(facts(), aligned)
        self.assertEqual(package["action"], facts()["action"])
        self.assertEqual(package["source_document"], facts()["source_document"])

    def test_ambiguous_or_occupied_ids_are_not_a_new_rejection_gate(self):
        discovery = discovered()
        discovery["events"][0]["event_id"] = "E2"
        layout = plan()
        layout["events"].append({**copy.deepcopy(layout["events"][0]), "event_id": "E2", "label": "Another storyline"})
        aligned, changes = align_storyline_ids(layout, candidate_storylines(discovery))
        self.assertEqual(aligned, layout)
        self.assertFalse(changes["event_id_remaps"])
        audit = storyline_resolution(candidate_storylines(discovery), aligned)
        self.assertFalse(audit["semantic_support_checked"])

    def test_same_label_in_another_domain_does_not_remap_event_identity(self):
        discovery = discovered()
        discovery["events"][0]["event_id"] = "planned_event"
        layout = plan()
        layout["domains"][0].update(domain_id="different_domain", label="Another field")
        layout["events"][0]["domain_id"] = "different_domain"
        aligned, changes = align_storyline_ids(layout, candidate_storylines(discovery))
        self.assertEqual(aligned, layout)
        self.assertFalse(changes["event_id_remaps"])

    def test_native_runner_keeps_plan_in_input_extras_and_not_source_text(self):
        captured = {}
        class Builder:
            def __init__(self, build_config):
                self.save_dir = "offline-build"
            def run(self, build_input):
                captured["input"] = build_input
                return "result"
        base = types.ModuleType("finmy.builder.base")
        base.BuildInput = lambda **kw: types.SimpleNamespace(**kw)
        sparse = types.ModuleType("finmy.builder.sparse_build.main_build")
        sparse.SparseRagBuilder = Builder
        config = {"storyline_plan": discovered(), "builder_config": {
            "builder_type": "SparseRagBuilder", "reconstruction": {"mode": "person", "subject": {
                "subject_id": "P", "name": "Example person"}}}}
        original = copy.deepcopy(config)
        with patch.dict(sys.modules, {"finmy.builder.base": base,
                                      "finmy.builder.sparse_build.main_build": sparse}):
            result = build_from_contents(["Actual source text."], "Example person 2022-2023", [], config)
        self.assertEqual(result, ("result", "offline-build"))
        self.assertEqual(captured["input"].user_query.extras["storyline_plan"], config["storyline_plan"])
        self.assertIsNot(captured["input"].user_query.extras["storyline_plan"], config["storyline_plan"])
        self.assertEqual(captured["input"].samples[0].content, "Actual source text.")
        self.assertEqual(config, original)


if __name__ == "__main__":
    unittest.main()
