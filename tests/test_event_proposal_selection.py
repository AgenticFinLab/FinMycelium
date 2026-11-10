"""Rejected claims cannot leave dangling references or bypass fresh review."""
import copy
import unittest

from finmy.runner.event_additions import empty_additions, merge_event_additions
from finmy.runner.event_proposal_selection import proposal_items, prune_proposal
from test_event_additions import activity, citation, package


QUOTE = "Investor told Trader to buy shares."


def proposal_fixture():
    proposal = empty_additions()
    proposal["entities"] = [
        {"key": key, "name": key, "entity_type": "individual", "citations": citation(QUOTE)}
        for key in ("local_actor", "unused_actor")]
    proposal["stages"] = [
        {"key": key, "label": key, "summary": None, "boundary_reason": None,
         "citations": citation(QUOTE)} for key in ("local_stage", "unused_stage")]
    first = activity(key="dependent")
    first.update(actor_id="local_actor", stage_id="local_stage",
                 details=[{"value": "Dependent detail", "citations": citation(QUOTE)}])
    second = activity(key="independent", title="Independently documented order")
    second["details"] = [
        {"value": value, "citations": citation(QUOTE)} for value in ("Good detail", "Bad detail")]
    proposal["activities"] = [first, second]
    proposal["details"] = [
        {"activity_id": key, "value": "Extra detail for " + key, "citations": citation(QUOTE)}
        for key in ("dependent", "independent", "activity")]
    proposal["relations"] = [
        {"from_activity_id": key, "to_activity_id": "activity", "relation_type": "responds_to",
         "description": None, "citations": citation(QUOTE)} for key in ("dependent", "independent")]
    return proposal


class EventProposalSelectionTests(unittest.TestCase):
    def assert_candidate_mergeable(self, selected):
        result, report = merge_event_additions(package(), "event", selected,
            [{"document_id": "EF_DOC_1", "content": QUOTE}])
        self.assertEqual(report["status"], "merged", report)
        # Mechanical validity never means semantic acceptance.
        self.assertFalse(report["semantic_improvement_verified"])
        return result


    def test_rejected_entity_cascades_but_preserves_independent_claims(self):
        proposal = proposal_fixture()
        original = copy.deepcopy(proposal)
        selected, report = prune_proposal(proposal, ["/entities/0"])
        self.assertEqual(proposal, original)
        self.assertEqual([row["key"] for row in selected["activities"]], ["independent"])
        self.assertEqual([row["activity_id"] for row in selected["details"]], ["independent", "activity"])
        self.assertEqual([row["from_activity_id"] for row in selected["relations"]], ["independent"])
        self.assertEqual(selected["entities"], [])
        self.assertEqual(selected["stages"], [])
        self.assertEqual(report["explicit_removed_paths"], ["/entities/0"])
        self.assertEqual(set(report["dependency_removed_paths"]), {
            "/activities/0", "/activities/0/details/0", "/details/0", "/relations/0"})
        self.assertEqual(set(report["orphan_removed_paths"]), {"/entities/1", "/stages/0", "/stages/1"})
        self.assertTrue(report["requires_review"])
        self.assert_candidate_mergeable(selected)
        selected["activities"][0]["details"][0]["value"] = "changed copy"
        self.assertEqual(proposal, original)


    def test_nested_detail_can_be_removed_without_discarding_activity(self):
        selected, report = prune_proposal(proposal_fixture(), ["/activities/1/details/1"])
        self.assertEqual([row["key"] for row in selected["activities"]], ["dependent", "independent"])
        self.assertEqual([row["value"] for row in selected["activities"][1]["details"]], ["Good detail"])
        self.assertEqual(report["dependency_removed_paths"], [])
        self.assertIn("/activities/1/details/0", report["remaining_paths"])
        self.assertNotIn("/activities/1/details/1", report["remaining_paths"])
        self.assert_candidate_mergeable(selected)

    def test_removed_local_key_is_not_reinterpreted_as_an_existing_id(self):
        proposal = empty_additions()
        # The existing graph also has this ID; selection must never redirect a
        # dependent claim after removing the proposed local key of that name.
        proposal["activities"] = [activity(key="activity")]
        proposal["details"] = [{"activity_id": "activity", "value": "Dependent detail",
                                "citations": citation(QUOTE)}]
        proposal["relations"] = [{"from_activity_id": "activity", "to_activity_id": "other",
            "relation_type": "responds_to", "description": None, "citations": citation(QUOTE)}]
        selected, report = prune_proposal(proposal, ["/activities/0"])
        self.assertEqual(selected, empty_additions())
        self.assertEqual(set(report["dependency_removed_paths"]), {"/details/0", "/relations/0"})


    def test_paths_must_exactly_identify_whole_existing_items(self):
        invalid = ["/activities/01", "/activities/-1", "/activities/2", "/activities/0/time",
                   "/activities/0/details", "/activities/0/details/4", "/unknown/0", "/activities/0/"]
        for path in invalid:
            with self.subTest(path=path), self.assertRaises(ValueError):
                prune_proposal(proposal_fixture(), [path])
        for paths in ("/activities/0", None, [None], {"/activities/0"}):
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                prune_proposal(proposal_fixture(), paths)


if __name__ == "__main__":
    unittest.main()
