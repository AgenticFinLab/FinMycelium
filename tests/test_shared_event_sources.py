"""Cross-event originals remain unreviewed until the receiving search reads them."""
import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest

from finmy.runner.enhanced_subject_search import _documents
from finmy.runner.initial_event_search import collect_initial_events, event_search_options
from finmy.search.agent import context_for, execute_action
from finmy.search.handoff import SourceSelectionError
from finmy.search.pipeline import run_search
from finmy.search.shared_sources import SharedSourcePool
from finmy.search.sources import SourceStore
from finmy.search.state import SearchConfig, SearchState, digest
from finmy.search.tools import SearchTools


class SharedEventSourcesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.scope = {"subject_id": "buffett", "name": "Warren Buffett",
                      "coverage_start": "2022", "coverage_end": "2023"}
        self.pool = SharedSourcePool(self.root, self.scope)
        self.raw = ("Berkshire cut its TSMC holding in the fourth quarter of 2022. "
                    "The filing reports the number of shares sold and the remaining stake.").encode()

    def task(self, name):
        return {"target_type": "event", "target_name": name, "event_id": name,
                "query_text": name, "subject_scope": copy.deepcopy(self.scope)}

    def state(self, name, **settings):
        return SearchState(self.root, name, task=self.task(name), config=SearchConfig(**settings))

    def donor(self, name="chevron", url="https://example.test/tsmc", raw=None):
        state = self.state(name)
        tools = SearchTools(state, source_pool=self.pool,
                            fetcher=lambda _: (raw or self.raw, "txt", "utf-8"))
        sid = tools.sources.register(url, title="Berkshire sells TSMC",
            discovery={"provider": "bocha", "query": "Chevron Buffett", "published_at": "2023-02-15"})
        tools.read_source(sid)
        state.data.update(status="insufficient", stop_reason="insufficient")
        state.save()
        return state, sid

    def test_wrong_event_original_becomes_unreviewed_candidate_without_refetch(self):
        donor, sid = self.donor()
        recipient = self.state("tsmc", max_search_requests=0)
        tools = SearchTools(recipient, source_pool=self.pool,
            fetcher=lambda _: self.fail("Shared originals must not be fetched again"))
        self.assertEqual(tools.refresh_shared_sources(), [sid])
        entry = recipient.data["sources"][sid]
        self.assertEqual(entry["title"], "Berkshire sells TSMC")
        self.assertEqual(entry["discoveries"][0]["query"], "Chevron Buffett")
        self.assertEqual(entry["reused_from"][0]["origin_event_id"], "chevron")
        self.assertNotIn("read_ranges", entry)
        self.assertNotIn("read_progress", entry)
        self.assertFalse(context_for(recipient)["sources"][0]["reviewed"])
        self.assertEqual(context_for(recipient)["eligible_source_ids"], [])
        finish = {"action": "finish", "source_ids": [sid], "reason": "supported", "gaps": []}
        with self.assertRaises(SourceSelectionError):
            execute_action(recipient, tools, finish)
        tools.read_source(sid)
        execute_action(recipient, tools, finish)
        self.assertEqual(recipient.data["read_sources"], [sid])
        self.assertEqual(recipient.data["usage"]["search"], 0)
        original = donor.root / "sources" / sid / entry["version"]
        copied = recipient.root / "sources" / sid / entry["version"]
        self.assertEqual((original / "raw").read_bytes(), (copied / "raw").read_bytes())
        self.assertEqual((original / "parsed.json").read_bytes(), (copied / "parsed.json").read_bytes())
        handoff = json.loads((recipient.run_dir / "builder_input.json").read_text())
        provenance = handoff["user_query"]["extras"]["source_registry"][sid]["reused_from"]
        self.assertEqual(provenance, entry["reused_from"])
        self.assertEqual(donor.data["status"], "insufficient")

    def test_native_cache_only_search_counts_its_own_model_and_read_calls(self):
        _, sid = self.donor()
        contexts = []

        def model(context):
            contexts.append(copy.deepcopy(context))
            if len(contexts) == 1:
                self.assertEqual(context["remaining"]["search"], 0)
                self.assertFalse(context["tool_constraints"]["search_enabled"])
                self.assertFalse(context["sources"][0]["reviewed"])
                return {"action": "read_source", "source": sid}
            return {"action": "finish", "source_ids": [sid], "reason": "supported", "gaps": []}

        result = run_search(self.task("tsmc"), root=self.root, task_id="tsmc",
            config=SearchConfig(max_search_requests=0, max_read_sources=1, max_model_calls=2),
            model=model, source_pool=self.pool,
            transport=lambda *_: self.fail("No search capacity"),
            fetcher=lambda _: self.fail("Reuse must not download again"))
        self.assertEqual(result["status"], "finished")
        self.assertEqual(result["usage"], {"search": 0, "model": 2})
        self.assertEqual(result["read_sources"], 1)
        self.assertEqual(contexts[-1]["phase"], "finalize")

    def test_refresh_imports_later_originals_into_already_started_event(self):
        recipient = self.state("tsmc")
        self.assertEqual(self.pool.refresh(recipient), [])
        _, sid = self.donor()
        self.assertEqual(self.pool.refresh(recipient), [sid])
        self.assertEqual(self.pool.refresh(recipient), [])
        self.assertEqual(recipient.data["read_sources"], [])

    def test_hydrate_reuses_insufficient_run_and_rejects_a_different_person(self):
        donor, sid = self.donor()
        # Remove only this derived cache; original task data is the durable source.
        import shutil
        shutil.rmtree(self.pool.root)
        restored = SharedSourcePool(self.root, self.scope)
        restored.hydrate([donor.root.name])
        self.assertEqual(restored.refresh(self.state("tsmc")), [sid])
        foreign = {**self.task("different"), "subject_scope": {"subject_id": "other-person"}}
        stranger = SearchState(self.root, "different", task=foreign, config=SearchConfig())
        with self.assertRaisesRegex(ValueError, "boundaries"):
            restored.refresh(stranger)
        with self.assertRaisesRegex(ValueError, "different subject"):
            SharedSourcePool(self.root, foreign["subject_scope"])

    def test_pool_rejects_changed_originals_before_import(self):
        self.donor()
        raw = next(self.pool.root.glob("*/raw"))
        raw.write_bytes(b"tampered")
        recipient = self.state("tsmc")
        self.assertEqual(self.pool.refresh(recipient), [])
        self.assertEqual(recipient.data["sources"], {})
        self.assertEqual(self.pool.errors[0]["stage"], "shared_snapshot")
        self.assertTrue((self.pool.root / "errors.json").is_file())

    def test_reparsed_original_does_not_reintroduce_a_stale_snapshot(self):
        donor, sid = self.donor()
        entry = donor.data["sources"][sid]
        path = donor.root / "sources" / sid / entry["version"] / "parsed.json"
        corrected = json.loads(path.read_text())
        corrected["blocks"][0]["text"] += " A corrected interpretation is now available."
        path.write_text(json.dumps(corrected))
        entry["parsed_hashes"][entry["version"]] = digest(path.read_bytes())
        entry["read_ranges"] = []
        donor.save()
        recipient = self.state("tsmc")
        self.assertEqual(self.pool.refresh(recipient), [])
        SourceStore(donor).read(sid)
        self.pool.publish(donor)
        self.assertEqual(self.pool.refresh(recipient), [sid])
        copied = SourceStore(recipient).document(sid)
        self.assertEqual(copied, corrected)
        self.assertNotIn("read_ranges", recipient.data["sources"][sid])

    def test_one_malformed_snapshot_does_not_hide_another_valid_original(self):
        self.donor(name="broken", url="https://example.test/broken")
        bad = next(self.pool.root.glob("*/record.json"))
        bad.write_text("[]")
        _, good_sid = self.donor(name="valid", url="https://example.test/valid")
        recipient = self.state("recipient")
        self.assertEqual(self.pool.refresh(recipient), [good_sid])
        self.assertTrue(self.pool.has_sources())
        self.assertEqual(len(self.pool.errors), 1)

    def test_bad_hydration_child_does_not_block_valid_child(self):
        good, sid = self.donor()
        broken = self.state("broken")
        (broken.run_dir / "run.json").write_text("{")
        self.pool.hydrate(["broken", good.root.name])
        self.assertEqual(self.pool.refresh(self.state("recipient")), [sid])
        self.assertEqual(self.pool.errors[0]["stage"], "hydrate_task")

    def test_existing_version_is_pinned_and_read_history_is_not_replaced(self):
        recipient = self.state("tsmc")
        store = SourceStore(recipient, lambda _: (b"The original first edition describes a TSMC investment.", "txt", "utf-8"))
        sid = store.register("https://example.test/tsmc")
        store.read(sid)
        before = copy.deepcopy(recipient.data["sources"][sid])
        self.donor()
        self.pool.refresh(recipient)
        self.assertEqual(recipient.data["sources"][sid], before)

    def test_concurrent_publish_uses_independent_version_records(self):
        def publish(index):
            return self.donor("donor_" + str(index), "https://example.test/" + str(index))[1]
        with ThreadPoolExecutor(max_workers=4) as executor:
            ids = list(executor.map(publish, range(8)))
        recipient = self.state("tsmc")
        self.assertEqual(set(self.pool.refresh(recipient)), set(ids))
        self.assertEqual(len(list(self.pool.root.glob("*/record.json"))), 8)
        self.assertEqual(recipient.data["read_sources"], [])

    def test_separate_pool_instances_publish_same_original_idempotently(self):
        donor = self.state("donor")
        store = SourceStore(donor)
        sid = store.register("https://example.test/tsmc")
        store.save_raw(sid, self.raw, "txt")
        store.read(sid)

        def publish(_):
            SharedSourcePool(self.root, self.scope).publish(donor)

        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(publish, range(8)))
        self.assertEqual(len(list(self.pool.root.glob("*/record.json"))), 1)
        self.assertEqual(self.pool.refresh(self.state("tsmc")), [sid])

    def test_unread_and_challenge_sources_are_not_published(self):
        state = self.state("donor")
        store = SourceStore(state)
        sid = store.register("https://example.test/not-read")
        store.save_raw(sid, self.raw, "txt")
        self.pool.publish(state)
        self.assertFalse(self.pool.has_sources())
        challenge = store.register("https://example.test/challenge")
        store.save_raw(challenge, b"<html><title>Just a moment...</title><p>Verify you are human</p></html>", "html")
        store.read(challenge)
        self.pool.publish(state)
        self.assertFalse(self.pool.has_sources())

    def test_scheduler_spends_remaining_read_budget_on_shared_event_material(self):
        settings = SearchConfig(providers=["bocha", "baidu"], max_search_requests=2,
                                max_read_sources=2, max_model_calls=5)
        tasks = [self.task("chevron"), self.task("tsmc")]
        events = [{"event_id": name, "label": name} for name in ("chevron", "tsmc")]
        requests, fetches = [], []

        def transport(provider, payload, _):
            requests.append(provider)
            row = {"url": "https://example.test/tsmc", "title": "TSMC holdings", "name": "TSMC holdings"}
            return {"data": {"webPages": {"value": [row]}}} if provider == "bocha" else {"references": [row]}

        def fetcher(url):
            fetches.append(url)
            return self.raw, "txt", "utf-8"

        def model(context):
            if not context["sources"]:
                return {"action": "search", "query": "Chevron Buffett"}
            source = context["sources"][0]
            if not source["reviewed"]:
                return {"action": "read_source", "source": source["source_id"]}
            return {"action": "finish", "source_ids": [source["source_id"]],
                    "reason": "insufficient" if context["task"]["event_id"] == "chevron" else "supported",
                    "gaps": ["Chevron details still unresolved"] if context["task"]["event_id"] == "chevron" else []}

        result = collect_initial_events(tasks=tasks, events=events, shared=settings,
            config={"search_config": {"event_search": {"max_concurrent_events": 1}}},
            save_dir=self.root, usage={}, content_limit=120000, runner=run_search,
            dependencies={"model": model, "transport": transport, "fetcher": fetcher}, documents_for=_documents)
        self.assertEqual(result["status"], "partial")
        self.assertFalse(result["complete"])
        self.assertTrue(result["build_ready"])
        self.assertEqual([row["status"] for row in result["reports"]], ["insufficient", "finished"])
        self.assertEqual(result["reports"][0]["gaps"], ["Chevron details still unresolved"])
        self.assertEqual(result["reports"][0]["stop_reason"], "insufficient")
        self.assertEqual(result["reports"][1]["config"]["max_search_requests"], 0)
        self.assertEqual(result["reports"][1]["config"]["max_model_calls"], 2)
        self.assertEqual(result["usage"], {"search_calls": 2, "parse_calls": 2, "search_model_calls": 5})
        self.assertEqual(requests, ["bocha", "baidu"])
        self.assertEqual(len(fetches), 1)
        self.assertEqual(len(result["documents"]), 1)
        self.assertEqual(set(result["documents"][0]["event_ids"]), {"chevron", "tsmc"})

    def test_configurable_concurrency_and_expanded_material_defaults(self):
        self.assertEqual(event_search_options({})["max_search_requests"], 12)
        self.assertEqual(event_search_options({})["max_model_calls"], 24)
        self.assertEqual(event_search_options({"search_config": {"event_search": {"max_concurrent_events": 4}}})["max_concurrent_events"], 4)
        self.assertEqual(SearchConfig().max_builder_material_chars, 120000)
        self.assertEqual(SearchConfig(max_search_requests=0).max_search_requests, 0)
        with self.assertRaises(ValueError):
            SearchConfig(max_search_requests=-1)

    def test_large_shared_catalog_can_page_to_late_candidate_without_forced_finish(self):
        donor = self.state("portfolio", max_read_sources=100)
        store = SourceStore(donor)
        target = None
        for index in range(84):
            sid = store.register("https://example.test/original/" + str(index),
                title=("An original financial report with its full headline. " * 10) + str(index),
                discovery={"provider": "bocha", "snippet": "Discovery lead. " * 40,
                           "summary": "Additional discovery lead. " * 40})
            store.save_raw(sid, self.raw + (" Original " + str(index)).encode(), "txt")
            store.read(sid)
            target = sid
        donor.data["status"] = "insufficient"
        donor.save()
        self.pool.publish(donor)
        target = json.loads(sorted(self.pool.root.glob("*/record.json"))[-1].read_text())["source_id"]
        contexts = []

        def model(context):
            contexts.append(copy.deepcopy(context))
            self.assertLessEqual(len(json.dumps(context, ensure_ascii=False)), 100000)
            if target in context["eligible_source_ids"]:
                return {"action": "finish", "source_ids": [target], "reason": "supported", "gaps": []}
            source = next((source for source in context["sources"] if source["source_id"] == target), None)
            if source:
                return {"action": "read_source", "source": target}
            self.assertEqual(context["phase"], "research")
            self.assertIsNotNone(context["source_listing"]["next_offset"])
            return {"action": "list_sources", "offset": context["source_listing"]["next_offset"]}

        result = run_search(self.task("tsmc"), root=self.root, task_id="tsmc",
            config=SearchConfig(max_search_requests=0, max_read_sources=1, max_model_calls=12),
            model=model, source_pool=self.pool,
            fetcher=lambda _: self.fail("Catalog pagination cannot refetch originals"))
        self.assertEqual(result["status"], "finished")
        self.assertEqual(contexts[0]["phase"], "research")
        self.assertIsNotNone(contexts[0]["source_listing"]["next_offset"])
        self.assertEqual(len(SearchState(self.root, "tsmc").data["sources"]), 84)
        self.assertEqual(result["read_sources"], 1)
        self.assertEqual(result["usage"]["search"], 0)


if __name__ == "__main__":
    unittest.main()
