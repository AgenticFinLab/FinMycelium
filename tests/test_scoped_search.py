import unittest

from finmy.runner.scoped_search import plan_search, publication_allowed, publication_bounds


class ScopedSearchTests(unittest.TestCase):
    def test_full_name_year_topics_and_query_bounds(self):
        plans = plan_search("Buffett activities from January 2022 through December 2023: shareholder letters, annual meeting discussions, interviews, investment decisions, philanthropy, succession and Japan visits", [], {"name": "Warren Buffett"})
        self.assertEqual(len(plans), 14)
        self.assertEqual({p["year"] for p in plans}, {2022, 2023})
        self.assertEqual(len({p["topic"] for p in plans}), 7)
        self.assertTrue(all('"Warren Buffett"' in p["query"] for p in plans))
        self.assertIn("before:2023-01-01", plans[0]["query"])
        self.assertIn("after:2021-12-31", plans[0]["query"])

    def test_partial_month_ranges_chinese_and_english(self):
        for query in ("巴菲特2022年3月至2023年6月的股东大会", "Buffett from March 2022 through June 2023 annual meeting"):
            plans = plan_search(query, [], {"name": "Warren Buffett"})
            self.assertEqual(plans[0]["start"], "2022-03-01")
            self.assertEqual(plans[-1]["end"], "2023-06-30")

    def test_numeric_exact_date_range_and_explicit_config_precedence(self):
        plans = plan_search("2022-03-14 to 2023-06-08", [], {"name": "Buffett"})
        self.assertEqual(plans[0]["start"], "2022-03-14")
        self.assertEqual(plans[-1]["end"], "2023-06-08")
        plans = plan_search("2022 to 2023", [], {"name": "Buffett", "coverage_start": "2021", "coverage_end": "2021"}, {"publication_start": "2020-03", "publication_end": "2020-04"})
        self.assertEqual((plans[0]["start"], plans[0]["end"]), ("2020-03-01", "2020-04-30"))

    def test_no_year_or_oversized_scope_never_runs_unbounded(self):
        for query, options in (("Buffett biography", {}), ("1900 through 2023", {}), ("2022 to 2023 interviews and philanthropy", {"max_queries": 3})):
            with self.subTest(query=query), self.assertRaises(ValueError):
                plan_search(query, [], {"name": "Buffett"}, options)

    def test_publication_scope_rejects_future_unknown_and_ambiguous_dates(self):
        for value in ("2026-11-01", "", None, "today", "2023", "2023-05", "2023-02-30"):
            with self.subTest(value=value):
                self.assertFalse(publication_allowed(value, "2023-05-10", "2023-05-20")[0])
        self.assertTrue(publication_allowed("2023-05-10T00:05:00+08:00", "2023-05-10", "2023-05-20")[0])
        self.assertTrue(publication_allowed("2023-05", "2023-01-01", "2023-12-31")[0])
        self.assertTrue(publication_allowed("2023年5月20日", "2023-05-10", "2023-05-20")[0])
        self.assertTrue(publication_allowed("May 20, 2023", "2023-05-10", "2023-05-20")[0])

    def test_narrow_subject_scope_kept_in_every_query(self):
        plans = plan_search("2022 through 2023 investment", [], {"name": "Warren Buffett", "scope": "Occidental Petroleum OXY"})
        self.assertTrue(all("Occidental Petroleum OXY" in p["query"] for p in plans))

    def test_explicit_query_topic_is_preserved_without_scope_field(self):
        for query in ("investment decisions related to Occidental Petroleum (OXY) 2022–2023", "2022至2023年关于西方石油公司(OXY)的投资决策"):
            plans = plan_search(query, [], {"name": "Warren Buffett"})
            self.assertTrue(all("OXY" in p["query"] for p in plans))
        plans = plan_search("2022–2023 investments", [], {"name": "Warren Buffett"}, {"scope": "Occidental Petroleum"})
        self.assertTrue(all("Occidental Petroleum" in p["query"] for p in plans))

    def test_visit_destination_is_not_invented(self):
        plans = plan_search("2022–2023 visits to India", [], {"name": "Warren Buffett"})
        self.assertTrue(all("India" in p["query"] and "Japan" not in p["query"] for p in plans))
        plans = plan_search("2022–2023 visits", [], {"name": "Warren Buffett"})
        self.assertTrue(all("Japan" not in p["query"] for p in plans))
        plans = plan_search("2022–2023 Japan visits", [], {"name": "Warren Buffett"})
        self.assertTrue(all("Japan" in p["query"] for p in plans))

    def test_reference_year_does_not_expand_requested_range(self):
        plans = plan_search("2022–2023 interviews; compare with his 2019 letter", [], {"name": "Warren Buffett"})
        self.assertEqual({p["year"] for p in plans}, {2022, 2023})
        plans = plan_search("Background from 2019; reconstruct between January 2022 and December 2023 interviews", [], {"name": "Warren Buffett"})
        self.assertEqual({p["year"] for p in plans}, {2022, 2023})
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            plan_search("2022 shareholder letter published in 2023", [], {"name": "Warren Buffett"})


if __name__ == "__main__":
    unittest.main()
