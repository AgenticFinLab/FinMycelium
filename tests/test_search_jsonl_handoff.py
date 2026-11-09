"""Native handoff accepts Unicode separators inside valid JSONL source strings."""
import json
from pathlib import Path
import tempfile
import unittest

from finmy.search.agent import execute_action
from finmy.search.sources import SourceStore
from finmy.search.state import SearchState
from finmy.search.tools import SearchTools


class SearchJsonlHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = SearchState(self.tmp.name, "unicode", task={
            "target_type": "event", "target_name": "Repurchases",
            "query_text": "Trace the share repurchase policy"})
        self.store = SourceStore(self.state)
        self.sid = self.store.register("https://example.test/shareholder-letter")
        self.original = "The board approved repurchases.\u2028Cash policy was retained.\u2029Conditions were disclosed."
        self.store.save_raw(self.sid, self.original.encode(), "txt")
        self.tools = SearchTools(self.state)
        self.tools.read_source(self.sid)  # Creates a native trace with the original text.

    def finish(self):
        return execute_action(self.state, self.tools, {
            "action": "finish", "source_ids": [self.sid], "gaps": [], "reason": "supported"})

    def test_original_unicode_source_and_query_survive_native_handoff(self):
        query = "repurchases\u2028cash\u2029conditions"
        self.state.trace({"action": "provider_started", "query": query})
        before = (self.state.run_dir / "trace.jsonl").read_bytes()
        self.finish()
        payload = json.loads((self.state.run_dir / "builder_input.json").read_text())
        complete = json.loads((self.state.run_dir / "complete_material.json").read_text())
        self.assertEqual(self.state.data["status"], "finished")
        self.assertIn(self.original, payload["samples"][0]["content"])
        self.assertIn(query, complete["retrieval_queries"])
        self.assertEqual(before, (self.state.run_dir / "trace.jsonl").read_bytes())

    def test_blank_records_are_skipped(self):
        with (self.state.run_dir / "trace.jsonl").open("a") as stream:
            stream.write("\n  \n")
        self.finish()
        self.assertEqual(self.state.data["status"], "finished")

    def test_malformed_json_is_still_rejected(self):
        with (self.state.run_dir / "trace.jsonl").open("a") as stream:
            stream.write('{"malformed"\n')
        with self.assertRaises(json.JSONDecodeError):
            self.finish()
        self.assertFalse((self.state.run_dir / "builder_input.json").exists())


if __name__ == "__main__":
    unittest.main()
