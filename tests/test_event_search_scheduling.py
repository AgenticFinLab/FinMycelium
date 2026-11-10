"""Offline regressions for full per-event budgets and the shared search lifecycle."""
import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import patch

from finmy.search.pipeline import run_search
from finmy.search.state import SearchState
import test_initial_storyline_search as fixtures


class EventSearchSchedulingTests(unittest.TestCase):
    # Reuse only the fixture helpers, not another class's test methods.
    discovery = fixtures.InitialStorylineSearchTests.discovery
    model = fixtures.InitialStorylineSearchTests.model
    transport = fixtures.InitialStorylineSearchTests.transport
    fetcher = fixtures.InitialStorylineSearchTests.fetcher
    collect = fixtures.InitialStorylineSearchTests.collect

    def setUp(self):
        fixtures.InitialStorylineSearchTests.setUp(self)
        self.config["search_config"]["event_search"].update(
            max_search_requests=6, max_read_sources=6, max_model_calls=12,
            max_concurrent_events=2)
        self.config["search_config"]["enhancement"].update(
            max_search_requests=36, max_read_sources=36, max_model_calls=72)

    def six_candidates(self):
        template = self.candidates["events"][0]
        self.candidates["events"] = [
            {**copy.deepcopy(template), "event_id": "event-" + str(i),
             "label": "Investment matter " + str(i)} for i in range(6)]

    def phase(self):
        return json.loads((self.root / "initial_event_search/phase_report.json").read_text())

    def test_low_global_capacity_keeps_all_candidates_and_uses_remaining_allowance(self):
        self.six_candidates()
        self.config["search_config"]["enhancement"].update(
            max_search_requests=6, max_read_sources=6, max_model_calls=12)
        result = self.collect()
        self.assertEqual(self.discovery_calls[0][1]["max_events"], 8)
        self.assertEqual(len(result["storyline_plan"]["events"]), 6)
        self.assertEqual(len(result["reports"]), 6)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["documents"]), 3)
        funded = [r for r in result["reports"] if "config" in r]
        self.assertEqual(len(funded), 3)
        self.assertEqual([r["config"]["max_search_requests"] for r in funded], [6, 4, 2])
        self.assertEqual([r["config"]["max_read_sources"] for r in funded], [6, 5, 4])
        self.assertEqual([r["config"]["max_model_calls"] for r in funded], [12, 9, 6])
        self.assertEqual(sum(r["status"] == "budget_exhausted" for r in result["reports"]), 3)
        self.assertEqual(result["usage"]["search_model_calls"], 9)
        self.assertEqual(result["usage"]["search_calls"], 6)
        self.assertEqual(result["usage"]["parse_calls"], 3)
        self.assertFalse(self.phase()["complete"])


    def test_native_agent_can_follow_a_gap_and_repair_unread_final_selection(self):
        self.candidates["events"] = self.candidates["events"][:1]
        calls = []
        remembered_unread = []

        def transport(provider, payload, settings):
            self.requests.append((provider, copy.deepcopy(payload), settings))
            query = payload["query"] if provider == "bocha" else payload["messages"][0]["content"]
            names = ["initial", "unread-lead"] if query == "Initial purchase" else ["later-filing"]
            rows = [{"url": "https://example.test/" + name, "title": name, "name": name}
                    for name in names]
            return {"data": {"webPages": {"value": rows}}} if provider == "bocha" else {"references": rows}

        def model(context):
            calls.append(copy.deepcopy(context))
            sources = context["sources"]
            step = len(calls)
            if step == 1:
                return {"action": "search", "query": "Initial purchase"}
            if step == 2:
                remembered_unread.append(next(s["source_id"] for s in sources
                                               if s["url"].endswith("unread-lead")))
                return {"action": "read_source", "source": sources[0]["source_id"]}
            if step == 3:
                return {"action": "search", "query": "Later filing",
                        "gap": "The first report does not establish the subsequent ownership change."}
            if step == 4:
                source = next(s for s in sources if s["url"].endswith("later-filing"))
                return {"action": "read_source", "source": source["source_id"]}
            if context["phase"] != "finalize":
                # Cached rereads cannot consume the full model allowance: three
                # unchanged reads trigger early bounded finalization.
                return {"action": "read_source", "source": sources[0]["source_id"]}
            selected = [s["source_id"] for s in sources if s["reviewed"]]
            # Final context excludes unread leads, but the model can remember an
            # ID from research; its invalid selection must still be repairable.
            if len([c for c in calls if c["phase"] == "finalize"]) == 1:
                selected += remembered_unread
            return {"action": "finish", "source_ids": selected,
                    "gaps": [], "reason": "supported"}

        result = self.collect(dependencies={"model": model, "transport": transport,
            "fetcher": lambda url: ((self.body + " Original source: " + url).encode(), "txt", "utf-8")})
        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(calls), 9)
        self.assertEqual(result["usage"]["search_calls"], 4)
        self.assertEqual(result["usage"]["parse_calls"], 2)
        self.assertEqual(result["usage"]["search_model_calls"], 9)
        self.assertEqual(len(result["documents"]), 2)
        self.assertEqual([c["phase"] for c in calls[-2:]], ["finalize", "finalize"])
        self.assertEqual(calls[-1]["feedback"]["error"], "SourceSelectionError")
        self.assertEqual(calls[-1]["feedback"]["invalid_source_ids"],
                         {remembered_unread[0]: "not_inspected"})
        self.assertEqual(calls[-1]["feedback"]["next_action"], "finish")
        self.assertNotIn(remembered_unread[0], calls[-1]["eligible_source_ids"])
        self.assertIn("Do not read or search", calls[-1]["feedback"]["repair"])
        self.assertTrue(all(not d["url"].endswith("unread-lead") for d in result["documents"]))
        self.assertEqual(sum(p == "bocha" for p, _, _ in self.requests), 2)
        self.assertEqual(sum(p == "baidu" for p, _, _ in self.requests), 2)


    def test_paused_resume_preserves_originals_and_does_not_repeat_search_or_reads(self):
        first = self.collect(dependencies={"max_steps": 2})
        self.assertEqual(first["status"], "paused")
        self.assertEqual(first["documents"], [])
        self.assertTrue(all(r["status"] == "paused" for r in first["reports"]))
        before = {p: p.read_bytes() for p in (self.root / "initial_event_search").rglob("raw") if p.is_file()}
        self.assertTrue(before)
        counts = len(self.requests), len(self.fetches), len(self.discovery_calls)
        second = self.collect()
        self.assertEqual(second["status"], "finished")
        self.assertEqual(counts, (len(self.requests), len(self.fetches), len(self.discovery_calls)))
        self.assertEqual(second["usage"]["search_model_calls"], 6)
        self.assertEqual(second["usage"]["search_calls"], 4)
        self.assertEqual(second["usage"]["parse_calls"], 2)
        self.assertEqual(before, {p: p.read_bytes() for p in before})


    def test_two_concurrent_tasks_cannot_multiply_phase_request_or_model_allowances(self):
        self.six_candidates()
        self.config["search_config"]["enhancement"].update(
            max_search_requests=12, max_read_sources=12, max_model_calls=24)
        barrier = threading.Barrier(2, timeout=5)
        guard = threading.Lock()
        active, peak, started = 0, 0, []

        def runner(task, *, root, task_id, config, **kwargs):
            nonlocal active, peak
            with guard:
                started.append(task_id)
                active += 1
                peak = max(peak, active)
            try:
                state = SearchState(root, task_id, task=task, config=config)
                barrier.wait()
                for _ in range(config.max_search_requests):
                    state.consume("search")
                for _ in range(config.max_model_calls):
                    state.consume("model")
                for i in range(config.max_read_sources):
                    state.reading("source-" + str(i))
                state.data["status"] = "insufficient"
                state.save()
                return {"status": "insufficient", "run_dir": str(state.run_dir)}
            finally:
                with guard:
                    active -= 1

        first = self.collect(dependencies={"run_search": runner})
        self.assertEqual(peak, 2)
        self.assertEqual(len(started), 2)
        self.assertEqual(first["usage"]["search_calls"], 12)
        self.assertEqual(first["usage"]["parse_calls"], 12)
        self.assertEqual(first["usage"]["search_model_calls"], 24)
        self.assertEqual(sum(r["status"] == "budget_exhausted" for r in first["reports"]), 4)
        repeated = self.collect(dependencies={"run_search": runner})
        self.assertEqual(len(started), 2)
        self.assertEqual(first["usage"], repeated["usage"])

    def test_default_model_instances_are_isolated_between_concurrent_events(self):
        barrier = threading.Barrier(2, timeout=5)
        instances = []
        decide = self.model

        class Model:
            def __init__(model, config):
                model.config = config
                model.calls = 0
                instances.append(model)

            def __call__(model, context):
                model.calls += 1
                if model.calls == 1:
                    barrier.wait()
                return decide(context)

        with patch("finmy.search.agent.LmbaseModel", Model):
            result = self.collect(dependencies={"model": None})
        self.assertEqual(result["status"], "finished")
        self.assertEqual(len(instances), 2)
        self.assertEqual([model.calls for model in instances], [3, 3])
        self.assertIsNot(instances[0], instances[1])


    def test_interrupted_runner_counts_attempts_and_resumes_same_source_cache(self):
        interrupted = set()

        def runner(task, **kwargs):
            if task["target_name"] == "Occidental investment" and not interrupted:
                interrupted.add(task["event_id"])
                run_search(task, **kwargs, max_steps=1)
                raise RuntimeError("Interrupted after a persisted search request")
            return run_search(task, **kwargs)

        first = self.collect(dependencies={"run_search": runner})
        self.assertEqual(first["status"], "partial")
        self.assertEqual(first["usage"]["search_calls"], 4)
        self.assertEqual(first["usage"]["search_model_calls"], 4)
        self.assertEqual([r["status"] for r in first["reports"]], ["failed", "finished"])
        repeated = self.collect(dependencies={"run_search": runner})
        self.assertEqual(repeated["status"], "finished")
        self.assertEqual(len(self.requests), 4)
        self.assertEqual(len(self.fetches), 2)
        self.assertEqual(repeated["usage"]["search_model_calls"], 6)
        self.assertEqual(repeated["usage"]["discovery_model_calls"], 1)

    def test_early_finish_releases_unused_reservations_for_queued_events(self):
        self.six_candidates()
        self.config["search_config"]["enhancement"].update(
            max_search_requests=16, max_read_sources=12, max_model_calls=27)
        result = self.collect()
        self.assertEqual(result["status"], "finished")
        self.assertEqual(len(result["documents"]), 6)
        self.assertEqual(result["usage"]["search_calls"], 12)
        self.assertEqual(result["usage"]["parse_calls"], 6)
        self.assertEqual(result["usage"]["search_model_calls"], 18)
        self.assertTrue(all(3 <= r["config"]["max_model_calls"] <= 12 for r in result["reports"]))
        self.assertTrue(any(r["allocation"]["reduced_to_remaining_budget"] for r in result["reports"]))

    def test_same_output_concurrent_invocation_cannot_duplicate_discovery_or_search(self):
        entered, release = threading.Event(), threading.Event()
        decide = self.model

        def blocked(context):
            entered.set()
            if not release.wait(timeout=5):
                raise RuntimeError("Test worker was not released")
            return decide(context)

        with ThreadPoolExecutor(max_workers=1) as executor:
            first = executor.submit(self.collect, dependencies={"model": blocked})
            try:
                self.assertTrue(entered.wait(timeout=5))
                with self.assertRaisesRegex(ValueError, "already running"):
                    self.collect()
            finally:
                release.set()
            result = first.result(timeout=5)
        self.assertEqual(result["status"], "finished")
        self.assertEqual(len(self.discovery_calls), 1)
        self.assertEqual(len(self.requests), 4)
        self.assertEqual(len(self.fetches), 2)


    def test_new_pause_request_after_worker_start_remains_effective(self):
        self.candidates["events"] = self.candidates["events"][:1]
        paused = []

        def runner(task, **kwargs):
            if not paused:
                flag = Path(kwargs["root"]) / kwargs["task_id"] / "pause_requested"
                flag.parent.mkdir(parents=True, exist_ok=True)
                flag.touch()
                paused.append(flag)
            return run_search(task, **kwargs)

        first = self.collect(dependencies={"run_search": runner})
        self.assertEqual(first["status"], "paused")
        self.assertEqual(first["reports"][0]["status"], "paused")
        self.assertEqual(first["usage"]["search_model_calls"], 0)
        self.assertTrue(paused[0].exists())
        resumed = self.collect(dependencies={"run_search": runner})
        self.assertEqual(resumed["status"], "finished")
        self.assertFalse(paused[0].exists())
        self.assertEqual(resumed["usage"]["search_model_calls"], 3)

    def test_shared_metered_model_keeps_token_usage_with_the_correct_event(self):
        decide = self.model
        guard = threading.Lock()
        active, peak = 0, 0
        calls = {}

        class MeteredModel:
            last_usage = None

            def __call__(model, context):
                nonlocal active, peak
                label = context["task"]["target_name"]
                with guard:
                    active += 1
                    peak = max(peak, active)
                    calls[label] = calls.get(label, 0) + 1
                    number = calls[label]
                try:
                    action = decide(context)
                    base = 100 if label == "Occidental investment" else 200
                    model.last_usage = {"prompt_tokens": base + number, "completion_tokens": number}
                    time.sleep(0.003)  # Expose mutable metadata races between workers.
                    return action
                finally:
                    with guard:
                        active -= 1

        result = self.collect(dependencies={"model": MeteredModel()})
        self.assertEqual(result["status"], "finished")
        self.assertEqual(peak, 1)
        for record in result["reports"]:
            directory = Path(record["run_directory"])
            state = json.loads((directory / "run.json").read_text())
            base = 100 if state["task"]["target_name"] == "Occidental investment" else 200
            rows = [json.loads(line) for line in (directory / "trace.jsonl").read_text().split("\n") if line]
            responses = [row for row in rows if row["action"] == "model_response"]
            self.assertEqual(len(responses), 3)
            for number, response in enumerate(responses, 1):
                self.assertEqual(response["usage"], {"prompt_tokens": base + number,
                                                     "completion_tokens": number})


if __name__ == "__main__":
    unittest.main()
