"""Check the storage bridge preserves actual legacy facts and evidence."""

import copy
import unittest

from finmy.person_epg.adapter import from_subject_graph, to_subject_graph
from finmy.person_epg.schema import SCHEMA_VERSION
from test_subject_graph_schema import field, graph_fixture


class PersonEPGAdapterTest(unittest.TestCase):
    def test_lossless_roundtrip_keeps_actor_attribution_and_unknown_party(self):
        graph = graph_fixture()
        before = copy.deepcopy(graph)
        package = from_subject_graph(graph)
        self.assertEqual(package["schema_version"], SCHEMA_VERSION)
        self.assertEqual(package["graph"]["schema_version"], graph["schema_version"])
        self.assertEqual(len(package["occurrence"]), 2)
        self.assertEqual(package["action"][1]["actor_id"], "org_berkshire")
        self.assertIsNone(package["financial_transaction"][0]["to_entity_id"])
        self.assertEqual(package["source_document"], [])
        for table in (
            "domain",
            "event",
            "stage",
            "event_activity",
            "activity_relation",
        ):
            self.assertEqual(package[table], [])
        saved = copy.deepcopy(package)
        self.assertEqual(to_subject_graph(package), graph)
        self.assertEqual(graph, before)
        self.assertEqual(package, saved)

    def test_optional_evidence_metadata_and_approximate_time_survive(self):
        graph = graph_fixture()
        timestamp = graph["events"][0]["actions"][0]["timestamp"]
        timestamp["time_window"] = {
            "start": "2023-05-21",
            "end": "2023-05-31",
            "original": "2023年5月下旬",
            "approximate": True,
        }
        timestamp["confidence"] = None
        timestamp["evidence_status"] = "needs_review"
        timestamp["reasons"] = ["Month is documented; the exact date is unspecified."]
        # A value-field window can also occur outside a dedicated temporal column.
        graph["entities"][0]["attributes"]["period/~context"] = copy.deepcopy(timestamp)
        detail = graph["events"][0]["actions"][0]["details"][0]
        detail.pop("confidence")
        detail["evidence_source_contents"] *= 2
        package = from_subject_graph(graph)
        self.assertTrue(
            any(
                t.get("original_text") == "2023年5月下旬" for t in package["time_value"]
            )
        )
        self.assertEqual(to_subject_graph(package), graph)

    def test_repeated_roles_share_membership_and_keep_distinct_actions(self):
        graph = graph_fixture()
        occurrence = graph["events"][0]
        role = copy.deepcopy(occurrence["participations"][0])
        role["participation_id"] = "PAR_panelist"
        role["role"] = field("panelist")
        occurrence["participations"].append(role)
        action = copy.deepcopy(occurrence["actions"][0])
        action["action_id"] = "ACT_second_statement"
        action["details"] = [field("A second documented statement")]
        occurrence["actions"].append(action)
        package = from_subject_graph(graph)
        members = [
            r
            for r in package["occurrence_participant"]
            if r["occurrence_id"] == "EV_meeting"
        ]
        self.assertEqual(len(members), 2)
        actions = [r for r in package["action"] if r["occurrence_id"] == "EV_meeting"]
        self.assertEqual(len(actions), 2)
        self.assertEqual(to_subject_graph(package), graph)

    def test_transaction_details_and_evidence_are_preserved(self):
        graph = graph_fixture()
        tx = graph["events"][1]["transactions"][0]
        tx["details"] = [
            field("The company bought shares; no personal decision is recorded.")
        ]
        tx["to_entity_id"]["reasons"] = ["Counterparty was not disclosed."]
        package = from_subject_graph(graph)
        self.assertEqual(
            package["financial_transaction"][0]["details"], [tx["details"][0]["value"]]
        )
        self.assertEqual(to_subject_graph(package), graph)

    def test_company_subject_is_not_silently_converted_to_a_person(self):
        graph = graph_fixture()
        graph["subject_id"] = "org_berkshire"
        graph["subject_type"] = "organization"
        with self.assertRaisesRegex(ValueError, "individual subject"):
            from_subject_graph(graph)

    def test_duplicate_alias_is_rejected_instead_of_discarded(self):
        graph = graph_fixture()
        graph["entities"][0]["aliases"] = ["Buffett", "Buffett"]
        with self.assertRaises(ValueError):
            from_subject_graph(graph)


if __name__ == "__main__":
    unittest.main()
