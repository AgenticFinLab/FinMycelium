"""Contracts for person configuration and non-destructive identity indexing."""
import copy
import unittest

from finmy.person_index import build_person_index
from finmy.reconstruction_scope import date_bounds, read_reconstruction, render_scope, search_query


def config():
    return {"builder_config": {"reconstruction": {"mode": "person", "subject": {
        "subject_id": "person_warren_buffett", "name": "Warren Buffett",
        "aliases": ["巴菲特"], "coverage_start": "2022", "coverage_end": "2023",
        "scope": "Occidental investment activities only",
    }}}}


def person(pid="P_4", name="Warren Buffett", kind="individual"):
    return {"participant_id": pid, "name": {"value": name, "evidence_source_contents": [name]},
            "participant_type": {"value": kind}}


def graph():
    return {"event_id": "EV_1", "stages": [{"stage_id": "S_1", "episodes": [
        {"episode_id": "E_1", "participants": [person(), person("P_1", "Berkshire Hathaway", "organization")],
         "participant_relations": [{"from_participant_id": "P_4", "to_participant_id": "P_1",
                                    "start_time": {"value": "unknown"}}]},
        {"episode_id": "E_2", "participants": [person("P_1", "Berkshire Hathaway", "organization")]},
        {"episode_id": "E_3", "participants": [person("P_8", "巴菲特")]},
    ]}]}


class PersonScopeTests(unittest.TestCase):
    def test_event_defaults_and_search_are_exactly_legacy(self):
        self.assertEqual(read_reconstruction({}), {"mode": "event"})
        self.assertEqual(render_scope({}), "")
        self.assertEqual(search_query("Request", ["a", "b"], {}), "Request \n\nkeywords: a b")

    def test_full_and_builder_config_produce_same_scope_without_mutation(self):
        value = config()
        original = copy.deepcopy(value)
        self.assertEqual(read_reconstruction(value), read_reconstruction(value["builder_config"]))
        self.assertIn("Occidental investment activities only", search_query("Request", [], value))
        self.assertIn("not evidence", render_scope(value))
        self.assertEqual(value, original)

    def test_rejects_malformed_scope_dates_modes_and_wrong_location(self):
        for key, val in (("subject_id", ""), ("name", None), ("scope", " "),
                         ("aliases", "Buffett"), ("coverage_start", "2023-02-29"),
                         ("coverage_end", 2023), ("coverage_start", "2024")):
            value = config()
            value["builder_config"]["reconstruction"]["subject"][key] = val
            with self.subTest(key=key, value=val), self.assertRaises(ValueError):
                read_reconstruction(value)
        for bad in ({"reconstruction": {"mode": "company"}},
                    {"builder_config": {}, "reconstruction": {"mode": "person"}},
                    {"builder_type": "ClassEventBuilder", "reconstruction": {"mode": "person"}},
                    {"reconstruction": False}):
            with self.subTest(config=bad), self.assertRaises(ValueError):
                read_reconstruction(bad)

    def test_partial_dates_and_open_bounds_are_not_padded_in_metadata(self):
        value = config()
        subject = value["builder_config"]["reconstruction"]["subject"]
        subject["coverage_start"], subject["coverage_end"] = "2024-02", "2024-02-29"
        self.assertEqual(str(date_bounds("2024-02")[1]), "2024-02-29")
        self.assertEqual(read_reconstruction(value)["subject"]["coverage_start"], "2024-02")
        subject["coverage_end"] = None
        self.assertIsNone(read_reconstruction(value)["subject"]["coverage_end"])

    def test_identity_links_use_stable_subject_and_graph_local_paths(self):
        source = graph()
        original = copy.deepcopy(source)
        index = build_person_index(source, config())
        self.assertEqual(source, original)
        self.assertEqual([e["subject_presence"] for e in index["episodes"]],
                         ["matched", "not_identified", "matched"])
        self.assertEqual([p["participant_id"] for p in index["participant_links"]], ["P_4", "P_8"])
        self.assertEqual({p["subject_id"] for p in index["participant_links"]}, {"person_warren_buffett"})
        self.assertEqual(index["participant_links"][0]["relation_pointers"],
                         ["/stages/0/episodes/0/participant_relations/0"])
        index["participant_links"][0]["name_evidence"]["value"] = "mutated"
        self.assertEqual(source, original)

    def test_two_same_name_candidates_are_unresolved_not_merged(self):
        source = graph()
        source["stages"][0]["episodes"][0]["participants"].append(person("P_9"))
        index = build_person_index(source, config())
        self.assertEqual(index["episodes"][0]["subject_presence"], "ambiguous")
        self.assertEqual([p["participant_id"] for p in index["participant_links"]], ["P_8"])

    def test_name_without_individual_type_and_company_named_like_subject_are_not_linked(self):
        for kind in ("organization", "unknown", None):
            source = {"stages": [{"episodes": [{"participants": [person(kind=kind)]}]}]}
            index = build_person_index(source, config())
            self.assertEqual(index["participant_links"], [])
            self.assertEqual(index["episodes"][0]["subject_presence"], "unresolved")

    def test_graph_local_id_reuse_does_not_link_a_company_in_other_episode(self):
        source = graph()
        source["stages"][0]["episodes"][1]["participants"][0]["participant_id"] = "P_4"
        index = build_person_index(source, config())
        self.assertEqual(index["episodes"][1]["subject_presence"], "not_identified")
        self.assertEqual(len(index["participant_links"]), 2)


class PersonIndexSafetyTests(unittest.TestCase):
    def test_duplicate_local_id_with_other_name_blocks_subject_and_relation_links(self):
        source = graph()
        source["stages"][0]["episodes"][0]["participants"][1]["participant_id"] = "P_4"
        original = copy.deepcopy(source)
        result = build_person_index(source, config())
        self.assertEqual(source, original)
        self.assertEqual(result["episodes"][0]["subject_presence"], "ambiguous")
        self.assertEqual([link["participant_id"] for link in result["participant_links"]], ["P_8"])
        self.assertIn("ambiguous_subject_id", {warning["code"] for warning in result["warnings"]})

    def test_placeholder_or_nonstring_ids_never_create_subject_links(self):
        for identifier in (None, "", " ", "unknown", "UNSPECIFIED", "null", "n/a", "未知",
                           42, {"value": "P_1"}, ["P_1"], " P_1", "P 1", "P_1\n"):
            with self.subTest(identifier=identifier):
                source = {"stages": [{"episodes": [{"participants": [person(pid=identifier)]}]}]}
                original = copy.deepcopy(source)
                result = build_person_index(source, config())
                self.assertEqual(source, original)
                self.assertEqual(result["participant_links"], [])
                self.assertEqual(result["episodes"][0]["subject_presence"], "unresolved")
                self.assertIn("invalid_participant_id", {w["code"] for w in result["warnings"]})

    def test_invalid_rows_are_skipped_without_shifting_json_pointers(self):
        source = {"stages": [None, {"episodes": ["bad episode", {
            "participants": [None, person()],
            "participant_relations": ["bad relation", {
                "from_participant_id": "P_4", "to_participant_id": "P_1",
            }],
        }]}]}
        original = copy.deepcopy(source)
        result = build_person_index(source, config())
        self.assertEqual(source, original)
        self.assertEqual(len(result["participant_links"]), 1)
        link = result["participant_links"][0]
        self.assertEqual(link["graph_pointer"], "/stages/1/episodes/1/participants/1")
        self.assertEqual(link["relation_pointers"], ["/stages/1/episodes/1/participant_relations/1"])
        self.assertEqual({w["graph_pointer"] for w in result["warnings"]}, {
            "/stages/0", "/stages/1/episodes/0", "/stages/1/episodes/1/participants/0",
            "/stages/1/episodes/1/participant_relations/0",
        })

    def test_malformed_collections_warn_without_mutating_or_crashing(self):
        for invalid in (None, "placeholder", {"not": "a list"}, 42):
            for key in ("stages", "episodes", "participants", "participant_relations"):
                with self.subTest(key=key, invalid=invalid):
                    source = graph()
                    target = source if key == "stages" else source["stages"][0]
                    if key in ("participants", "participant_relations"):
                        target = target["episodes"][0]
                    target[key] = invalid
                    original = copy.deepcopy(source)
                    result = build_person_index(source, config())
                    self.assertEqual(source, original)
                    self.assertIn("invalid_collection", {w["code"] for w in result["warnings"]})

    def test_invalid_graph_root_has_no_links_and_an_explicit_warning(self):
        result = build_person_index(["not a graph mapping"], config())
        self.assertEqual(result["episodes"], [])
        self.assertEqual(result["participant_links"], [])
        self.assertIn("invalid_graph", {w["code"] for w in result["warnings"]})


if __name__ == "__main__":
    unittest.main()
