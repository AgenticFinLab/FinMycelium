"""Native subject graph contracts, not tests of model historical accuracy."""
import copy
import unittest

from finmy.subject_graph.compat import to_event_cascade
from finmy.subject_graph.schema import JSON_SCHEMA, SCHEMA_VERSION
from finmy.subject_graph.validation import date_interval, validate_subject_graph
from finmy.builder.agent_build.structure import (
    Action, Episode, EventCascade, EventStage, Participant,
    ParticipantRelation, Transaction,
)


SOURCE = (
    "In May 2023, Warren Buffett spoke at Berkshire Hathaway's meeting. "
    "Berkshire Hathaway bought shares in May 2023; its counterparty was not named. "
    "Buffett chaired Berkshire throughout May 2023."
)


def field(value, quote=SOURCE):
    return {"value": value, "evidence_source_contents": [quote] if quote else [],
            "reasons": ["fixture source"], "confidence": 0.9}


def entity(identifier, name, kind):
    return {"entity_id": identifier, "name": field(name), "aliases": [],
            "entity_type": kind, "attributes": {}}


def participation(identifier, entity_id, role):
    return {"participation_id": identifier, "entity_id": entity_id, "role": field(role),
            "start_time": field("2023-05"), "end_time": field("2023-05")}


def graph_fixture():
    """Two overlapping, independent activities with distinct actual actors."""
    return {
        "schema_version": SCHEMA_VERSION, "graph_id": "buffett-2023",
        "subject_id": "person_warren_buffett", "subject_type": "individual",
        "coverage_start": "2023", "coverage_end": "2023",
        "title": field("Selected activities of Warren Buffett", None), "descriptions": [],
        "entities": [entity("person_warren_buffett", "Warren Buffett", "individual"),
                     entity("org_berkshire", "Berkshire Hathaway", "organization")],
        "events": [
            {"event_id": "EV_meeting", "title": field("Annual meeting"),
             "start_time": field("2023-05"), "end_time": field("2023-05"),
             "subject_relevance": field("Buffett personally spoke at the meeting"),
             "descriptions": [field("Buffett spoke at the meeting")],
             "participations": [participation("PAR_speaker", "person_warren_buffett", "speaker"),
                                participation("PAR_host", "org_berkshire", "host")],
             "actions": [{"action_id": "ACT_speech", "actor_id": "person_warren_buffett",
                          "action_type": field("public statement"), "timestamp": field("2023-05"),
                          "details": [field("Spoke at the meeting")]}],
             "transactions": []},
            {"event_id": "EV_purchase", "title": field("Company share purchase"),
             "start_time": field("2023-05"), "end_time": field("2023-05"),
             "subject_relevance": field("Buffett chaired Berkshire when the company bought shares; individual decision attribution is unknown"),
             "descriptions": [],
             "participations": [participation("PAR_buyer", "org_berkshire", "buyer")],
             "actions": [{"action_id": "ACT_purchase", "actor_id": "org_berkshire",
                          "action_type": field("share purchase"), "timestamp": field("2023-05"),
                          "details": [field("Bought shares")]}],
             "transactions": [{"transaction_id": "TX_purchase", "name": field("share purchase"),
                               "from_entity_id": field("org_berkshire"),
                               "to_entity_id": field("unknown", None), "timestamp": field("2023-05"),
                               "instruments": [field("shares")], "details": []}]},
        ],
        "relations": [{"relation_id": "REL_chair", "from_entity_id": "person_warren_buffett",
                       "to_entity_id": "org_berkshire", "relation_type": field("chairman of"),
                       "valid_from": field("unknown", None), "valid_to": field("unknown", None),
                       "event_ids": ["EV_meeting"]}],
    }


class SubjectGraphSchemaTest(unittest.TestCase):
    def test_overlapping_activities_and_company_actions_are_valid(self):
        graph = graph_fixture()
        before = copy.deepcopy(graph)
        report = validate_subject_graph(graph, [SOURCE])
        self.assertTrue(report["valid"], report)
        self.assertEqual(graph, before)
        self.assertEqual(report["warnings"], [])

    def test_company_subject_uses_same_native_schema(self):
        graph = graph_fixture()
        graph["subject_id"], graph["subject_type"] = "org_berkshire", "organization"
        report = validate_subject_graph(graph, [SOURCE])
        self.assertTrue(report["valid"], report)
        self.assertEqual(to_event_cascade(graph)["stages"][1]["episodes"][0]["participants"][0]["participant_id"], "P_1")

    def test_event_relevance_is_required_without_fabricating_subject_participation(self):
        graph = graph_fixture()
        purchase = graph["events"][1]
        self.assertNotIn(graph["subject_id"], [p["entity_id"] for p in purchase["participations"]])
        self.assertTrue(validate_subject_graph(graph, [SOURCE])["valid"])
        self.assertIn(purchase["subject_relevance"], to_event_cascade(graph)["stages"][1]["episodes"][0]["descriptions"])
        for bad in (field("unknown", None), field("", None), field("Buffett's company", None)):
            purchase["subject_relevance"] = bad
            self.assertFalse(validate_subject_graph(graph, [SOURCE])["valid"])
        del purchase["subject_relevance"]
        self.assertFalse(validate_subject_graph(graph)["valid"])

    def test_missing_subject_and_wrong_subject_type_fail(self):
        for key, value in (("subject_id", "absent"), ("subject_type", "organization")):
            graph = graph_fixture()
            graph[key] = value
            with self.subTest(key=key):
                self.assertFalse(validate_subject_graph(graph)["valid"])

    def test_duplicate_global_entity_event_action_participation_and_relation_ids_fail(self):
        for target, key in (("entities", "entity_id"), ("events", "event_id"), ("relations", "relation_id")):
            graph = graph_fixture()
            graph[target].append(copy.deepcopy(graph[target][0]))
            with self.subTest(key=key):
                report = validate_subject_graph(graph)
                self.assertFalse(report["valid"])
                self.assertTrue(any("Duplicate " + key in e["message"] for e in report["errors"]))
        for collection, key in (("actions", "action_id"), ("participations", "participation_id")):
            graph = graph_fixture()
            graph["events"][1][collection][0][key] = graph["events"][0][collection][0][key]
            with self.subTest(key=key):
                self.assertFalse(validate_subject_graph(graph)["valid"])

    def test_registry_identity_alone_does_not_establish_event_participation(self):
        graph = graph_fixture()
        graph["events"][1]["actions"][0]["actor_id"] = "person_warren_buffett"
        report = validate_subject_graph(graph)
        self.assertFalse(report["valid"])
        self.assertTrue(any("actor must participate" in e["message"] for e in report["errors"]))

    def test_transaction_requires_event_party_or_explicit_unknown(self):
        for party in ("person_warren_buffett", "missing", "", "unspecified"):
            graph = graph_fixture()
            graph["events"][1]["transactions"][0]["to_entity_id"]["value"] = party
            with self.subTest(party=party):
                self.assertFalse(validate_subject_graph(graph)["valid"])

    def test_contextual_relationship_warns_without_fabricating_participation(self):
        graph = graph_fixture()
        graph["relations"][0]["event_ids"].append("EV_purchase")
        original = copy.deepcopy(graph)
        report = validate_subject_graph(graph, [SOURCE])
        self.assertTrue(report["valid"], report)
        self.assertTrue(any(w["path"] == "/relations/0/event_ids/1" for w in report["warnings"]))
        projected = to_event_cascade(graph)
        self.assertEqual(graph, original)
        self.assertEqual(len(projected["stages"][0]["episodes"][0]["participant_relations"]), 1)
        self.assertEqual(projected["stages"][1]["episodes"][0]["participant_relations"], [])
        self.assertEqual(len(projected["stages"][1]["episodes"][0]["participants"]), 1)

    def test_relation_missing_event_or_endpoint_still_fails(self):
        graph = graph_fixture()
        graph["relations"][0]["event_ids"] = ["missing_event"]
        self.assertFalse(validate_subject_graph(graph)["valid"])
        graph = graph_fixture()
        graph["relations"][0]["from_entity_id"] = "missing_entity"
        self.assertFalse(validate_subject_graph(graph)["valid"])

    def test_multiple_roles_for_one_entity_do_not_duplicate_legacy_actor_or_actions(self):
        graph = graph_fixture()
        graph["events"][0]["participations"].append(participation("PAR_chair", "person_warren_buffett", "chair"))
        self.assertTrue(validate_subject_graph(graph)["valid"])
        participants = to_event_cascade(graph)["stages"][0]["episodes"][0]["participants"]
        self.assertEqual(len(participants), 2)
        self.assertEqual(participants[0]["base_role"]["value"], "speaker; chair")
        self.assertEqual(len(participants[0]["actions"]), 1)

    def test_unknown_and_partial_dates_preserve_original_precision(self):
        graph = graph_fixture()
        graph["events"][0]["start_time"]["value"] = "2023"
        before = copy.deepcopy(graph)
        self.assertTrue(validate_subject_graph(graph)["valid"])
        self.assertEqual(date_interval("2024-02")[1].day, 29)
        self.assertEqual(date_interval("2023")[2], "year")
        self.assertIsNone(date_interval("2023-02-29"))
        legacy = to_event_cascade(graph)
        self.assertEqual(legacy["start_time"]["value"], "2023")
        self.assertEqual(graph, before)

    def test_backwards_dates_and_out_of_event_actions_fail(self):
        for first, last in (("2023-06", "2023-05"), ("2024", "2023")):
            graph = graph_fixture()
            graph["events"][0]["start_time"]["value"] = first
            graph["events"][0]["end_time"]["value"] = last
            self.assertFalse(validate_subject_graph(graph)["valid"])
        graph = graph_fixture()
        graph["events"][0]["actions"][0]["timestamp"]["value"] = "2022"
        self.assertFalse(validate_subject_graph(graph)["valid"])

    def test_coverage_is_not_invented_relationship_duration(self):
        graph = graph_fixture()
        graph["relations"][0]["valid_from"] = field("2010")
        graph["relations"][0]["valid_to"] = field("2024")
        self.assertTrue(validate_subject_graph(graph)["valid"])
        graph["coverage_start"], graph["coverage_end"] = "2024", "2024"
        report = validate_subject_graph(graph)
        self.assertTrue(report["valid"])
        self.assertEqual(len(report["warnings"]), 2)

    def test_global_relation_is_preserved_natively_without_fabricated_event_membership(self):
        graph = graph_fixture()
        graph["relations"][0]["event_ids"] = []
        self.assertTrue(validate_subject_graph(graph)["valid"])
        projected = to_event_cascade(graph)
        self.assertTrue(all(not s["episodes"][0]["participant_relations"] for s in projected["stages"]))
        self.assertEqual(len(graph["relations"]), 1)

    def test_evidence_quotes_must_occur_in_supplied_sources(self):
        graph = graph_fixture()
        graph["events"][0]["actions"][0]["details"][0] = field("Unsupported claim", "invented source text")
        report = validate_subject_graph(graph, [SOURCE])
        self.assertFalse(report["valid"])
        self.assertTrue(any("absent from supplied" in e["message"] for e in report["errors"]))

    def test_whitespace_does_not_count_as_a_source_quote(self):
        graph = graph_fixture()
        graph["events"][0]["title"]["evidence_source_contents"] = [" "]
        self.assertFalse(validate_subject_graph(graph, [SOURCE])["valid"])

    def test_only_configured_subject_identity_and_graph_title_may_lack_known_value_evidence(self):
        graph = graph_fixture()
        graph["entities"][0]["name"] = field("Warren Buffett", None)
        graph["entities"][0]["name"]["reasons"] = ["configured_identity"]
        self.assertTrue(validate_subject_graph(graph, [SOURCE])["valid"])
        graph["events"][0]["title"] = field("meeting", None)
        self.assertFalse(validate_subject_graph(graph, [SOURCE])["valid"])

    def test_no_behavior_is_forced_by_schema(self):
        graph = graph_fixture()
        for event in graph["events"]:
            event["actions"], event["transactions"] = [], []
        self.assertTrue(validate_subject_graph(graph, [SOURCE])["valid"])

    def test_projection_preserves_actual_actors_times_and_input(self):
        graph = graph_fixture()
        original = copy.deepcopy(graph)
        projected = to_event_cascade(graph)
        self.assertEqual(len(projected["stages"]), 2)
        meeting, purchase = [s["episodes"][0] for s in projected["stages"]]
        self.assertEqual(meeting["participants"][0]["participant_id"], "P_1")
        self.assertEqual(purchase["participants"][0]["participant_id"], "P_2")
        self.assertEqual(purchase["transactions"][0]["from_participant_id"]["value"], "P_2")
        self.assertEqual(purchase["transactions"][0]["to_participant_id"]["value"], "unknown")
        self.assertEqual(meeting["start_time"]["value"], "2023-05")
        projected["stages"][0]["episodes"][0]["participants"][0]["name"]["value"] = "changed"
        self.assertEqual(graph, original)

    def test_invalid_projection_refuses_silent_repair(self):
        graph = graph_fixture()
        graph["events"][0]["actions"][0]["actor_id"] = "absent"
        with self.assertRaisesRegex(ValueError, "Invalid SubjectGraph"):
            to_event_cascade(graph)

    def test_projection_matches_legacy_dataclass_constructor_contracts(self):
        projected = to_event_cascade(graph_fixture())
        EventCascade(**projected)
        for stage in projected["stages"]:
            EventStage(**stage)
            for episode in stage["episodes"]:
                Episode(**episode)
                for participant in episode["participants"]:
                    Participant(**participant)
                    for action in participant["actions"]:
                        Action(**action)
                for relation in episode["participant_relations"]:
                    ParticipantRelation(**relation)
                for transaction in episode["transactions"]:
                    Transaction(**transaction)

    def test_schema_rejects_malformed_types_unknown_keys_and_nonfinite_confidence(self):
        for mutate in (lambda g: g.update(extra="unknown"),
                       lambda g: g.update(events=None),
                       lambda g: g["entities"][0].update(entity_id="bad ID"),
                       lambda g: g["events"][0]["title"].update(confidence=float("nan")),
                       lambda g: g["events"][0]["title"].update(confidence=True)):
            graph = graph_fixture()
            mutate(graph)
            self.assertFalse(validate_subject_graph(graph)["valid"])
        self.assertEqual(JSON_SCHEMA["properties"]["schema_version"]["const"], SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main()
