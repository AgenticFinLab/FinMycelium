"""Contracts for person configuration and search scope."""
import copy
import unittest

from finmy.reconstruction_scope import date_bounds, read_reconstruction, render_scope, search_query


def config():
    return {"builder_config": {"reconstruction": {"mode": "person", "subject": {
        "subject_id": "person_warren_buffett", "name": "Warren Buffett",
        "aliases": ["巴菲特"], "coverage_start": "2022", "coverage_end": "2023",
        "scope": "Occidental investment activities only",
    }}}}


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
        for key, val in (("subject_id", ""), ("name", None), ("scope", None),
                         ("aliases", "Buffett"), ("coverage_start", "2023-02-29"),
                         ("coverage_end", 2023), ("coverage_start", "2024")):
            value = config()
            value["builder_config"]["reconstruction"]["subject"][key] = val
            with self.subTest(key=key, value=val), self.assertRaises(ValueError):
                read_reconstruction(value)
        for bad in ({"reconstruction": {"mode": "unsupported"}},
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


if __name__ == "__main__":
    unittest.main()
