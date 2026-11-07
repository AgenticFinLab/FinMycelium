"""Relational integrity of the Person EPG interchange; no API or database calls."""

import copy
import unittest

from finmy.person_epg.schema import MODEL, SCHEMA_VERSION
from finmy.person_epg.validation import validate_person_epg


def package_fixture():
    package = {
        table["name"]: []
        for table in MODEL["tables"]
        if table["name"] != "subject_graph"
    }
    package.update(
        schema_version=SCHEMA_VERSION,
        graph={
            "graph_id": "G",
            "schema_version": "subject-graph-1.0",
            "subject_entity_id": "P",
            "subject_type": "individual",
            "title": "Schema fixture",
            "descriptions": [],
        },
    )
    package["entity"] = [
        {
            "entity_id": "P",
            "name": "Example person",
            "entity_type": "individual",
            "sort_order": 0,
        }
    ]
    package["occurrence"] = [
        {
            "occurrence_id": "O",
            "title": "Example meeting",
            "subject_relevance": "The person spoke",
            "sort_order": 0,
        }
    ]
    package["occurrence_participant"] = [{"occurrence_id": "O", "entity_id": "P"}]
    package["time_value"] = [{"time_id": "T", "value": "2023-05"}]
    package["action"] = [
        {
            "action_id": "ACT",
            "occurrence_id": "O",
            "actor_id": "P",
            "action_type": "Statement",
            "timestamp_time_id": "T",
            "sort_order": 0,
        }
    ]
    package["activity"] = [{"activity_id": "A", "action_id": "ACT"}]
    package["activity_detail"] = [
        {"activity_id": "A", "detail_index": 0, "value": "Example statement"}
    ]
    package["domain"] = [{"domain_id": "D", "label": "Example domain", "sort_order": 0}]
    package["event"] = [
        {
            "event_id": "E",
            "domain_id": "D",
            "label": "Example investment",
            "sort_order": 0,
        }
    ]
    package["stage"] = [
        {"event_id": "E", "stage_id": "S", "label": "Example stage", "sort_order": 0}
    ]
    package["event_activity"] = [
        {
            "event_id": "E",
            "activity_id": "A",
            "stage_id": "S",
            "detail_mode": "all",
            "sort_order": 0,
        }
    ]
    return package


class PersonEPGValidationTest(unittest.TestCase):
    def assert_invalid(self, package, path):
        report = validate_person_epg(package)
        self.assertFalse(report["valid"], report)
        self.assertTrue(
            any(error["path"].startswith(path) for error in report["errors"]), report
        )

    def test_valid_input_is_not_modified(self):
        package = package_fixture()
        before = copy.deepcopy(package)
        self.assertEqual(validate_person_epg(package), {"valid": True, "errors": []})
        self.assertEqual(package, before)

    def test_empty_organization_and_optional_stage(self):
        package = package_fixture()
        package["event_activity"][0]["stage_id"] = None
        package["stage"] = []
        self.assertTrue(validate_person_epg(package)["valid"])
        for name in ("event_activity", "event", "domain"):
            package[name] = []
        self.assertTrue(validate_person_epg(package)["valid"])

    def test_malformed_input_returns_report(self):
        for value in (None, [], {}, {"graph": []}, {"activity": "wrong"}):
            with self.subTest(value=value):
                report = validate_person_epg(value)
                self.assertFalse(report["valid"])
                self.assertTrue(report["errors"])

    def test_duplicate_primary_key(self):
        package = package_fixture()
        package["action"].append(copy.deepcopy(package["action"][0]))
        self.assert_invalid(package, "/action/1")

    def test_missing_foreign_key(self):
        package = package_fixture()
        package["action"][0]["actor_id"] = "not-a-participant"
        self.assert_invalid(package, "/action/0/actor_id")

    def test_activity_requires_exactly_one_fact(self):
        for refs in ({}, {"action_id": "ACT", "context_occurrence_id": "O"}):
            package = package_fixture()
            package["activity"] = [{"activity_id": "A", **refs}]
            self.assert_invalid(package, "/activity/0")

    def test_duplicate_registration_and_nullable_unique_keys(self):
        package = package_fixture()
        package["activity"].append({"activity_id": "B", "action_id": "ACT"})
        self.assert_invalid(package, "/activity/1")
        package["activity"][1] = {"activity_id": "B", "context_occurrence_id": "O"}
        self.assertTrue(validate_person_epg(package)["valid"])

    def test_stage_belongs_to_its_event(self):
        package = package_fixture()
        package["event"].append(
            {
                "event_id": "E2",
                "domain_id": "D",
                "label": "Other event",
                "sort_order": 1,
            }
        )
        package["stage"][0]["event_id"] = "E2"
        self.assert_invalid(package, "/event_activity/0/stage_id")
        package["event_activity"][0]["event_id"] = "E2"
        self.assertTrue(validate_person_epg(package)["valid"])

    def test_shared_activity_can_have_different_selected_details(self):
        package = package_fixture()
        package["event"].append(
            {
                "event_id": "E2",
                "domain_id": "D",
                "label": "Other event",
                "sort_order": 1,
            }
        )
        package["event_activity"].append(
            {
                "event_id": "E2",
                "activity_id": "A",
                "stage_id": None,
                "detail_mode": "selected",
                "sort_order": 0,
            }
        )
        package["event_activity_detail"] = [
            {"event_id": "E2", "activity_id": "A", "detail_index": 0}
        ]
        self.assertTrue(validate_person_epg(package)["valid"])
        package["event_activity_detail"][0]["detail_index"] = 100
        self.assert_invalid(package, "/event_activity_detail/0/detail_index")

    def test_detail_selection_requires_selected_mode(self):
        package = package_fixture()
        package["event_activity_detail"] = [
            {"event_id": "E", "activity_id": "A", "detail_index": 0}
        ]
        self.assert_invalid(package, "/event_activity/0/detail_mode")

    def test_final_subject_must_reference_person(self):
        for subject in (None, "missing"):
            package = package_fixture()
            package["graph"]["subject_entity_id"] = subject
            self.assert_invalid(package, "/graph/subject_entity_id")
        package = package_fixture()
        package["entity"][0]["entity_type"] = "organization"
        self.assert_invalid(package, "/graph/subject_entity_id")

    def test_window_shape_and_date_order(self):
        package = package_fixture()
        package["time_value"][0]["window_start"] = "2023-07-21"
        self.assert_invalid(package, "/time_value/0")
        package["time_value"][0].update(
            window_end="2023-07-31",
            original_text="late July 2023",
            is_approximate=True,
            window_semantics="uncertainty",
        )
        self.assertTrue(validate_person_epg(package)["valid"])
        package["time_value"][0]["window_end"] = "2023-07-01"
        self.assert_invalid(package, "/time_value/0/window_end")
        package["time_value"][0]["window_end"] = "2023-02-30"
        self.assert_invalid(package, "/time_value/0")

    def test_semantic_link_needs_actual_quotes(self):
        package = package_fixture()
        package["activity"].append({"activity_id": "B", "context_occurrence_id": "O"})
        package["activity_relation"] = [
            {
                "link_id": "R",
                "from_activity_id": "A",
                "to_activity_id": "B",
                "relation_type": "explains",
                "basis": "source",
                "evidence_set_id": "ES",
            }
        ]
        package["evidence_set"] = [{"evidence_set_id": "ES"}]
        self.assert_invalid(package, "/activity_relation/0/evidence_set_id")
        package["evidence_span"] = [{"span_id": "Q", "quote": "Evidence"}]
        package["evidence_link"] = [
            {
                "evidence_set_id": "ES",
                "field_path": "/description",
                "quote_order": 0,
                "span_id": "Q",
            }
        ]
        self.assertTrue(validate_person_epg(package)["valid"])
        package["activity_relation"][0]["basis"] = "temporal"
        self.assert_invalid(package, "/activity_relation/0")

    def test_quote_offsets_use_unicode_characters(self):
        package = package_fixture()
        package["source_document"] = [{"document_id": "DOC", "content": "原文证据。"}]
        package["evidence_span"] = [
            {
                "span_id": "Q",
                "document_id": "DOC",
                "char_start": 2,
                "char_end": 4,
                "quote": "证据",
            }
        ]
        self.assertTrue(validate_person_epg(package)["valid"])
        package["evidence_span"][0]["char_end"] = 40
        self.assert_invalid(package, "/evidence_span/0/quote")

    def test_publication_datetime_has_timezone_and_microsecond_precision(self):
        for timestamp in (None, "2023-05-06T09:30:00Z", "2023-05-06T09:30:00.123456+08:00",
                          "2024-02-29T23:59:59.1-05:00"):
            with self.subTest(timestamp=timestamp):
                package = package_fixture()
                package["source_document"] = [{"document_id": "DOC", "content": "Example", "published_at": timestamp}]
                self.assertTrue(validate_person_epg(package)["valid"])

    def test_publication_datetime_rejects_invalid_or_unstorable_values(self):
        for timestamp in ("not-a-date", "2023-05-06", "2023-05-06T09:30:00",
                          "2023-05-06T09:30:00.1234567Z", "2023-02-29T09:30:00Z",
                          "2023-05-06T25:30:00Z", "2023-05-06T09:30:00+01:60",
                          "0999-12-31T00:00:00Z", "9999-12-31T23:59:59-01:00"):
            with self.subTest(timestamp=timestamp):
                package = package_fixture()
                package["source_document"] = [{"document_id": "DOC", "content": "Example", "published_at": timestamp}]
                self.assert_invalid(package, "/source_document/0/published_at")


if __name__ == "__main__":
    unittest.main()
