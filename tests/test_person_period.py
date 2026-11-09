"""Point/range precision and shared UI/CLI period behavior, without live APIs."""
import copy
import unittest

from finmy.runner.person_period import compact_person_request, parse_person_period, period_text
from finmy.runner.person_storyline_pipeline import person_config


class PersonPeriodTests(unittest.TestCase):
    def test_points_and_ranges_preserve_precision(self):
        examples = {
            "2023": ("2023", "2023"),
            "2023-05": ("2023-05", "2023-05"),
            "2023-5-6": ("2023-05-06", "2023-05-06"),
            "2022-2023": ("2022", "2023"),
            "2023-05 – 2023-07": ("2023-05", "2023-07"),
            "2022-01-01 to 2023-12-31": ("2022-01-01", "2023-12-31"),
            "2022-01-01-2023-12-31": ("2022-01-01", "2023-12-31"),
            "2022年 至 2023年": ("2022", "2023"),
            "2023年5月": ("2023-05", "2023-05"),
            "2023年5月6日": ("2023-05-06", "2023-05-06"),
            "2022年1月到2023年3月": ("2022-01", "2023-03"),
            "2023-05-06 ～ 2023-06": ("2023-05-06", "2023-06"),
        }
        for value, expected in examples.items():
            with self.subTest(value=value):
                self.assertEqual(parse_person_period(value), expected)
                start, end = expected
                rendered = period_text({"coverage_start": start, "coverage_end": end})
                self.assertEqual(parse_person_period(rendered), expected)
                self.assertEqual(compact_person_request("Warren Buffett " + value), ("Warren Buffett", start, end))

    def test_invalid_dates_and_reversed_ranges_are_rejected(self):
        for value in (None, "", "2023-13", "2023-02-29", "2024-02-30", "2023-2022",
                      "2023-06 to 2023-05", "2023-05-06 to 2023-05-05", "recent years"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_person_period(value)
        self.assertEqual(parse_person_period("2024-02-29"), ("2024-02-29", "2024-02-29"))

    def test_cli_accepts_points_and_preserves_configured_identity_and_explicit_budget(self):
        original = {"builder_config": {"reconstruction": {"mode": "person", "subject": {
            "subject_id": "known_buffett", "name": "Warren Buffett", "aliases": ["Buffett"],
            "coverage_start": "2022", "coverage_end": "2023"}}},
            "all_content_config": {"max_content_length": 45000}}
        snapshot = copy.deepcopy(original)
        for period in ("2023", "2023-05", "2023-05-06"):
            with self.subTest(period=period):
                effective = person_config("Buffett " + period, original)
                subject = effective["builder_config"]["reconstruction"]["subject"]
                self.assertEqual(subject["subject_id"], "known_buffett")
                self.assertEqual((subject["coverage_start"], subject["coverage_end"]), (period, period))
                self.assertEqual(effective["all_content_config"]["max_content_length"], 45000)
        self.assertEqual(original, snapshot)
        self.assertEqual(person_config("Buffett 2023", {})["all_content_config"]["max_content_length"], 120000)

    def test_natural_language_keeps_explicit_scope_but_invalid_compact_dates_do_not(self):
        config = person_config("Buffett 2022-2023", {})
        self.assertEqual(person_config("Research Buffett's investments in 2022 and 2023", config)
                         ["builder_config"]["reconstruction"], config["builder_config"]["reconstruction"])
        with self.assertRaises(ValueError):
            person_config("Buffett 2023-13", config)


if __name__ == "__main__":
    unittest.main()
