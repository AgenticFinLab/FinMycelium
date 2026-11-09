"""Explicit budget revisions preserve native evidence and cumulative usage."""
import copy
import json
from pathlib import Path
import unittest

import test_initial_storyline_search as fixtures

from finmy.runner.enhanced_subject_search import collect_enhanced_sources
from finmy.runner.storyline_search_resume import prepare_storyline_resume
from finmy.search.control import task_lock
from finmy.search.handoff import assemble_sources
from finmy.search.sources import SourceStore
from finmy.search.state import SearchState, digest, write_json


class StorylineSearchResumeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.InitialStorylineSearchTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.source = self.fixture.root / "old"
        self.target = self.fixture.root / "new"
        self.fixture.root = self.source
        self.config = copy.deepcopy(self.fixture.config)
        self.config["search_config"]["event_search"] = {
            "max_search_requests": 6, "max_read_sources": 6,
            "max_model_calls": 12, "max_concurrent_events": 2, "reuse_sources": False}
        self.config["search_config"]["enhancement"].update(
            max_search_requests=12, max_read_sources=12, max_model_calls=24)

    def prepare(self, **kwargs):
        return prepare_storyline_resume(self.source, self.target,
            "Buffett 2022-2023", [], self.fixture.subject,
            kwargs.pop("config", self.config), **kwargs)

    def snapshot(self):
        return {str(path.relative_to(self.source)): digest(path.read_bytes())
                for path in self.source.rglob("*") if path.is_file()}

    def collect_target(self):
        def no_external(*args, **kwargs):
            raise AssertionError("Saved discovery, searches and originals must be reused")
        return collect_enhanced_sources("Buffett 2022-2023", [], self.fixture.subject,
            self.config, self.target, dependencies={
                "discovery_completion": no_external, "model": self.fixture.model,
                "transport": no_external, "fetcher": no_external})

    def legacy_ledger(self):
        phase_path = self.source / "initial_event_search/phase_report.json"
        phase = json.loads(phase_path.read_text())
        checkpoint = json.loads((self.source / "storyline_discovery/checkpoint.json").read_text())
        discovery = checkpoint["usage"]["model_calls"]
        phase["version"] = "enhanced-subject-search-v1"
        phase["base_usage"]["search_model_calls"] += discovery
        phase["usage"]["search_model_calls"] += discovery
        write_json(phase_path, phase)
        parent_path = self.source / "storyline_search_state.json"
        parent = json.loads(parent_path.read_text())
        parent.pop("version")
        parent.pop("base_discovery_model_calls")
        write_json(parent_path, parent)

    def test_legacy_paused_search_reuses_plan_raw_cache_and_counts(self):
        first = self.fixture.collect(dependencies={"max_steps": 2})
        self.assertEqual(first["status"], "partial")
        self.legacy_ledger()
        before = self.snapshot()
        metadata = self.prepare()
        self.assertEqual(before, self.snapshot())
        self.assertEqual(metadata["usage"]["search_model_calls"], 4)
        self.assertEqual(metadata["discovery_model_calls"], 1)
        self.assertEqual(metadata["required_reservations"], {
            "search_calls": 12, "parse_calls": 12, "search_model_calls": 24})
        old_plan = json.loads((self.source / "storyline_discovery/plan.json").read_text())
        self.assertEqual(old_plan, json.loads((self.target / "storyline_discovery/plan.json").read_text()))
        for old_path in self.source.glob("initial_event_search/event_*/runs/initial/run.json"):
            new_path = self.target / old_path.relative_to(self.source)
            old, new = json.loads(old_path.read_text()), json.loads(new_path.read_text())
            for key in ("task", "usage", "sources", "cache", "read_sources", "actions", "feedback"):
                self.assertEqual(old.get(key), new.get(key), key)
            self.assertEqual(new["config"]["max_model_calls"], 12)
            self.assertEqual(new["config_history"][-1]["config"], old["config"])
            self.assertEqual(new["status"], "ready")
        result = self.collect_target()
        self.assertEqual(result["status"], "finished")
        self.assertEqual(result["usage"], {"search_calls": 4, "parse_calls": 2,
            "search_model_calls": 6, "discovery_model_calls": 1, "total_model_calls": 7})
        self.assertEqual(result["storyline_plan"]["events"], old_plan["events"])
        self.assertEqual(before, self.snapshot())
        repeated = self.collect_target()
        self.assertEqual(repeated["usage"], result["usage"])

    def test_finished_tasks_are_reused_without_config_or_model_revision(self):
        first = self.fixture.collect()
        self.prepare()
        contexts = len(self.fixture.contexts)
        result = self.collect_target()
        self.assertEqual(result["status"], "finished")
        self.assertEqual(result["usage"], first["usage"])
        self.assertEqual(len(self.fixture.contexts), contexts)
        for old_path in self.source.glob("initial_event_search/event_*/runs/initial/run.json"):
            new = json.loads((self.target / old_path.relative_to(self.source)).read_text())
            old = json.loads(old_path.read_text())
            self.assertEqual(new["config"], old["config"])
            self.assertNotIn("config_history", new)

    def test_v2_scheduler_checkpoint_migrates_without_restarting_discovery_or_search(self):
        first = self.fixture.collect(dependencies={"max_steps": 2})
        path = self.source / "initial_event_search/phase_report.json"
        saved = json.loads(path.read_text())
        saved["version"] = "initial-event-search-v2"
        saved["event_search"].pop("reuse_sources")
        write_json(path, saved)
        before = self.snapshot()
        metadata = self.prepare()
        self.assertEqual(metadata["usage"], {
            key: first["usage"][key]
            for key in ("search_calls", "parse_calls", "search_model_calls")})
        migrated = json.loads((self.target / "initial_event_search/phase_report.json").read_text())
        self.assertEqual(migrated["version"], "initial-event-search-v3")
        self.assertFalse(migrated["event_search"]["reuse_sources"])
        result = self.collect_target()
        self.assertEqual(result["status"], "finished")
        self.assertEqual(result["usage"]["search_calls"], first["usage"]["search_calls"])
        self.assertEqual(result["usage"]["parse_calls"], first["usage"]["parse_calls"])
        self.assertEqual(result["usage"]["discovery_model_calls"], first["usage"]["discovery_model_calls"])
        self.assertEqual(before, self.snapshot())

    def test_finished_mojibake_reopens_only_corrected_source_review_and_preserves_history(self):
        original_text = "巴菲特增持日本商社。投资决策及持仓变动来自公司披露。"
        raw = ('<html><head><meta charset="utf-8"></head><p>' + original_text + '</p></html>').encode()
        first = self.fixture.collect(dependencies={
            "fetcher": lambda url: (raw, "html", "ISO-8859-1")})
        self.assertEqual(first["status"], "finished")
        task_id = first["reports"][0]["task_id"]
        state = SearchState(self.source / "initial_event_search", task_id)
        store = SourceStore(state)
        sid = next(iter(state.data["sources"]))
        document = store.document(sid)
        version = document["version"]
        folder = state.root / "sources" / sid / version
        # Reconstruct the pre-fix interpretation while keeping the real UTF-8
        # original and a valid historical handoff (not an integrity violation).
        legacy = {**document, "encoding": "ISO-8859-1", "parser_version": "search-v1",
                  "blocks": [{"paragraph": 1, "text": original_text.encode().decode("latin1")}]}
        for key in ("supplied_encoding", "encoding_decision"):
            legacy.pop(key, None)
        write_json(folder / "parsed.json", legacy)
        previous_hash = digest((folder / "parsed.json").read_bytes())
        state.data["sources"][sid]["parsed_hashes"][version] = previous_hash
        state.data["sources"][sid]["read_ranges"] = []
        state.save()
        store.read(sid)
        assemble_sources(state, [sid], gaps=["Later disposal remains unverified."], reason="supported")
        state.data["status"] = "finished"
        state.save()
        before_state = copy.deepcopy(state.data)
        old_manifest = json.loads((state.run_dir / "complete_material.json").read_text())
        before = self.snapshot()

        metadata = self.prepare()
        self.assertEqual(before, self.snapshot())
        self.assertEqual(metadata["reparsed_sources"], {task_id: [sid]})
        self.assertEqual(metadata["reopened_task_ids"], [task_id])
        self.assertEqual(metadata["usage"], {key: first["usage"][key]
                         for key in ("search_calls", "parse_calls", "search_model_calls")})
        self.assertEqual(metadata["required_reservations"], {
            "search_calls": 8, "parse_calls": 7, "search_model_calls": 15})
        repaired = SearchState(self.target / "initial_event_search", task_id)
        self.assertEqual(repaired.data["status"], "ready")
        self.assertEqual(repaired.data["usage"], before_state["usage"])
        self.assertEqual(repaired.data["read_sources"], before_state["read_sources"])
        self.assertEqual(repaired.data["sources"][sid]["read_ranges"], [])
        repaired_folder = repaired.root / "sources" / sid / version
        self.assertEqual((repaired_folder / "raw").read_bytes(), raw)
        self.assertEqual(SourceStore(repaired).document(sid)["encoding"], "utf-8")
        self.assertEqual(json.loads((repaired_folder / "parsed_revisions" /
                         (previous_hash + ".json")).read_text()), legacy)
        self.assertFalse((repaired.run_dir / "complete_material.json").exists())
        archive = next((repaired.run_dir / "parse_repairs").iterdir())
        self.assertEqual(json.loads((archive / "complete_material.json").read_text()), old_manifest)

        result = self.collect_target()  # External searches and fetches are forbidden here.
        self.assertEqual(result["status"], "finished")
        self.assertEqual(result["usage"]["search_calls"], first["usage"]["search_calls"])
        self.assertEqual(result["usage"]["parse_calls"], first["usage"]["parse_calls"])
        self.assertEqual(result["usage"]["search_model_calls"], first["usage"]["search_model_calls"] + 2)
        self.assertTrue(all(original_text in row["raw_text"] for row in result["documents"]))
        self.assertEqual(before, self.snapshot())
        # A second explicit revision of the repaired run must not reinterpret
        # healthy sources again or spend another model review.
        third = self.fixture.root.parent / "third"
        next_metadata = prepare_storyline_resume(self.target, third,
            "Buffett 2022-2023", [], self.fixture.subject, self.config)
        self.assertFalse(next_metadata.get("reparsed_sources"))
        self.assertEqual(next_metadata["reopened_task_ids"], [])
        self.assertEqual(next_metadata["usage"], {key: result["usage"][key]
                         for key in ("search_calls", "parse_calls", "search_model_calls")})
        again = SearchState(third / "initial_event_search", task_id)
        self.assertEqual(again.data["status"], "finished")
        self.assertEqual(len(again.data["parse_repairs"]), 1)
        self.assertEqual(before, self.snapshot())

    def test_explicit_revision_reopens_insufficient_without_resetting_usage(self):
        def insufficient(context):
            if context["sources"] and any(s["reviewed"] for s in context["sources"]):
                self.fixture.contexts.append(copy.deepcopy(context))
                return {"action": "finish", "source_ids": [],
                        "gaps": ["Important process gap remains"], "reason": "insufficient"}
            return self.fixture.model(context)
        first = self.fixture.collect(dependencies={"model": insufficient})
        self.assertEqual(first["status"], "insufficient")
        self.prepare()
        result = self.collect_target()
        self.assertEqual(result["status"], "finished")
        self.assertEqual(result["usage"]["search_model_calls"], first["usage"]["search_model_calls"] + 2)
        self.assertEqual(result["usage"]["search_calls"], first["usage"]["search_calls"])

    def test_rejects_unaffordable_reservations_before_output_creation(self):
        self.fixture.collect(dependencies={"max_steps": 2})
        config = copy.deepcopy(self.config)
        config["search_config"]["enhancement"]["max_model_calls"] = 23
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "required.*24"):
            self.prepare(config=config)
        self.assertFalse(self.target.exists())
        self.assertEqual(before, self.snapshot())

    def test_rejects_changed_scope_or_tampered_original(self):
        self.fixture.collect(dependencies={"max_steps": 2})
        subject = {**self.fixture.subject, "coverage_end": "2024"}
        with self.assertRaisesRegex(ValueError, "scope must match"):
            prepare_storyline_resume(self.source, self.target,
                "Buffett 2022-2023", [], subject, self.config)
        raw = next(self.source.glob("initial_event_search/event_*/sources/*/*/raw"))
        raw.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "integrity mismatch"):
            self.prepare()
        self.assertFalse(self.target.exists())

    def test_rejects_nonempty_target_and_symlinked_artifacts(self):
        self.fixture.collect()
        self.target.mkdir()
        (self.target / "keep.txt").write_text("existing output")
        with self.assertRaisesRegex(ValueError, "new or empty"):
            self.prepare()
        (self.target / "keep.txt").unlink()
        link = self.source / "storyline_discovery" / "untrusted"
        link.symlink_to(self.source / "storyline_search_state.json")
        with self.assertRaisesRegex(ValueError, "symbolic links"):
            self.prepare()

    def test_preexisting_discovery_baseline_is_preserved_once(self):
        usage = {"discovery_model_calls": 1}
        first = self.fixture.collect(usage=usage)
        self.assertEqual(first["usage"]["discovery_model_calls"], 2)
        self.prepare()
        result = self.collect_target()
        self.assertEqual(result["usage"], first["usage"])

    def test_active_source_is_rejected_without_copying_or_interrupting(self):
        self.fixture.collect(dependencies={"max_steps": 2})
        before = self.snapshot()
        with task_lock(self.source, "storyline_search"):
            with self.assertRaisesRegex(ValueError, "already running"):
                self.prepare()
        self.assertFalse(self.target.exists())
        self.assertEqual(before, self.snapshot())


if __name__ == "__main__":
    unittest.main()
