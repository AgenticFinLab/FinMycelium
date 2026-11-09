"""A damaged child or deferred provider never erases healthy event evidence."""
import json
from pathlib import Path
import unittest

from finmy.search.pipeline import run_search
from finmy.search.state import SearchState
from finmy.runner.search_status import incomplete_search_result
import test_event_search_scheduling as scheduling


class SearchPhaseIsolationTests(unittest.TestCase):
    setUp = scheduling.EventSearchSchedulingTests.setUp
    discovery = scheduling.EventSearchSchedulingTests.discovery
    model = scheduling.EventSearchSchedulingTests.model
    transport = scheduling.EventSearchSchedulingTests.transport
    fetcher = scheduling.EventSearchSchedulingTests.fetcher
    collect = scheduling.EventSearchSchedulingTests.collect

    def test_corrupt_child_ledger_is_charged_at_reservation_and_healthy_child_exports(self):
        def runner(task, **kwargs):
            result = run_search(task, **kwargs)
            if task["target_name"] == "Occidental investment":
                (Path(result["run_dir"]) / "run.json").write_text("{")
            return result

        result = self.collect(dependencies={"run_search": runner})
        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["documents"]), 1)
        bad, good = result["reports"]
        self.assertEqual(bad["status"], "invalid_state")
        self.assertEqual(good["status"], "finished")
        self.assertEqual(bad["usage_accounting"], "reserved_ceiling_unreadable_child")
        self.assertEqual(result["usage"]["search_calls"], 8)
        self.assertEqual(result["usage"]["search_model_calls"], 15)
        before = len(self.contexts)
        repeated = self.collect()
        self.assertEqual(len(self.contexts), before)
        self.assertEqual(repeated["usage"], result["usage"])

    def test_bad_selection_diagnostics_does_not_erase_valid_originals(self):
        def runner(task, **kwargs):
            result = run_search(task, **kwargs)
            if task["target_name"] == "Occidental investment":
                (Path(result["run_dir"]) / "selection.json").write_text("{")
            return result
        result = self.collect(dependencies={"run_search": runner})
        self.assertEqual(len(result["documents"]), 2)
        self.assertEqual(result["reports"][0]["errors"][0]["stage"], "selection_diagnostics")

    def test_malformed_child_status_does_not_raise_during_phase_counters(self):
        def runner(task, **kwargs):
            result = run_search(task, **kwargs)
            if task["target_name"] == "Occidental investment":
                path = Path(result["run_dir"]) / "run.json"
                state = json.loads(path.read_text())
                state["status"] = []
                path.write_text(json.dumps(state))
            return result
        result = self.collect(dependencies={"run_search": runner})
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["reports"][0]["status"], "invalid_state")
        self.assertEqual(len(result["documents"]), 1)

    def test_paused_task_exports_its_verified_selection_and_coverage_keeps_resume(self):
        def runner(task, **kwargs):
            result = run_search(task, **kwargs)
            if task["target_name"] == "Occidental investment":
                state = SearchState(kwargs["root"], kwargs["task_id"])
                resume = {"retryable": True, "next_retry_at": 12345}
                state.data.update(status="paused", stop_reason="provider_cooldown", resume=resume)
                state.save()
                result.update(status="paused", stop_reason="provider_cooldown", resume=resume)
            return result
        result = self.collect(dependencies={"run_search": runner})
        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["documents"]), 2)
        self.assertEqual(result["reports"][0]["status"], "paused")
        self.assertEqual(len(result["unresolved_events"]), 1)

    def test_waiting_without_documents_is_resumable_not_insufficient(self):
        def runner(task, **kwargs):
            state = SearchState(kwargs["root"], kwargs["task_id"], task=task, config=kwargs["config"])
            state.data.update(status="paused", stop_reason="provider_cooldown",
                              resume={"retryable": True, "next_retry_at": 99999})
            state.save()
            return {"status": "paused", "run_dir": str(state.run_dir)}
        result = self.collect(dependencies={"run_search": runner})
        self.assertEqual(result["status"], "waiting")
        self.assertEqual(result["documents"], [])
        self.assertTrue(all(row["status"] == "paused" for row in result["reports"]))
        coverage = incomplete_search_result(result, self.root)
        self.assertEqual(coverage["search_status"], "waiting")
        self.assertTrue(coverage["resume"]["available"])
        self.assertTrue(coverage["resume"]["retryable"])
        self.assertEqual(coverage["resume"]["next_retry_at"], 99999)
        self.assertEqual(coverage["builder_status"], "not_started")


if __name__ == "__main__":
    unittest.main()
