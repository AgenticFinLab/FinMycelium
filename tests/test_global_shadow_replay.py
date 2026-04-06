import importlib.util
import json
import os
import sys
import tempfile
import types
from pathlib import Path
import unittest
from unittest.mock import patch

from finmy.context import (
    LocalContextBuilder,
    LocalContextRequest,
)
from finmy.context.assets import (
    EvidenceAssetBundle,
    EvidenceCard,
    EvidenceIndex,
    EvidenceRetrievalPolicy,
)


HELPER_PATH = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "uTEST"
    / "replay_skeleton_shadow_checkpoint.py"
)

_helper_spec = importlib.util.spec_from_file_location(
    "replay_skeleton_shadow_checkpoint",
    HELPER_PATH,
)
if _helper_spec is None or _helper_spec.loader is None:
    raise RuntimeError(f"Unable to load helper module at {HELPER_PATH}")
_helper_module = importlib.util.module_from_spec(_helper_spec)
_helper_spec.loader.exec_module(_helper_module)
summarize_latest_builder_output = _helper_module.summarize_latest_builder_output
replay_latest_readme_checkpoint = _helper_module.replay_latest_readme_checkpoint


QUERY_TEXT = "What is the case involving fraud and money laundering by Qian Zhimin?"
KEY_WORDS = ["fraud", "money laundering", "investigators property purchases"]

MIXED_BUNDLE = EvidenceAssetBundle(
    retrieval_policy=EvidenceRetrievalPolicy(),
    index=EvidenceIndex(),
    evidence_cards=[
        EvidenceCard(
            sample_id="signal-1",
            title="signal-1",
            excerpt="Qian Zhimin ran the Blue Sky scheme and fled to Britain with bitcoin proceeds.",
            tokens=[
                "qian",
                "zhimin",
                "blue",
                "sky",
                "scheme",
                "fled",
                "britain",
                "bitcoin",
                "proceeds",
            ],
        ),
        EvidenceCard(
            sample_id="signal-2",
            title="signal-2",
            excerpt=(
                "Investigators traced luxury property purchases and offshore transfers "
                "involving the same network."
            ),
            tokens=[
                "investigators",
                "traced",
                "luxury",
                "property",
                "purchases",
                "offshore",
                "transfers",
                "involving",
                "network",
            ],
        ),
        EvidenceCard(
            sample_id="chrome-1",
            title="chrome-1",
            excerpt="Skip to main content Search for Careers Contact About us International edition",
            tokens=[
                "skip",
                "to",
                "main",
                "content",
                "search",
                "for",
                "careers",
                "contact",
                "about",
                "us",
                "international",
                "edition",
            ],
        ),
    ],
)

NOISE_BUNDLE = EvidenceAssetBundle(
    retrieval_policy=EvidenceRetrievalPolicy(),
    index=EvidenceIndex(),
    evidence_cards=[
        EvidenceCard(
            sample_id="noise-1",
            title="noise-1",
            excerpt="Skip to main content Search for Careers Contact About us International edition",
            tokens=[
                "skip",
                "to",
                "main",
                "content",
                "search",
                "for",
                "careers",
                "contact",
                "about",
                "us",
                "international",
                "edition",
            ],
        ),
        EvidenceCard(
            sample_id="noise-2",
            title="noise-2",
            excerpt=(
                "Ad Feedback CNN values your feedback Video player was slow to load"
            ),
            tokens=[
                "ad",
                "feedback",
                "cnn",
                "values",
                "your",
                "feedback",
                "video",
                "player",
                "was",
                "slow",
                "to",
                "load",
            ],
        ),
        EvidenceCard(
            sample_id="noise-3",
            title="noise-3",
            excerpt="Latest headlines Related stories Sign up for newsletters",
            tokens=[
                "latest",
                "headlines",
                "related",
                "stories",
                "sign",
                "up",
                "for",
                "newsletters",
            ],
        ),
    ],
)


class GlobalShadowReplayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = LocalContextBuilder()
        cls.request = LocalContextRequest(
            agent_name="EventDescriptionReconstructor",
            query_text=QUERY_TEXT,
            key_words=KEY_WORDS,
        )

    def test_mixed_bundle_selects_small_signal_set_and_excludes_chrome(self):
        package = self.builder.build(self.request, MIXED_BUNDLE)

        self.assertEqual(package.scope, "global")
        self.assertEqual(package.retrieval_status, "sufficient")
        self.assertGreater(package.summary["selected_count"], 0)
        self.assertLessEqual(package.summary["selected_count"], 3)
        self.assertIn("signal-1", package.selected_sample_ids)
        self.assertIn("signal-2", package.selected_sample_ids)
        self.assertNotIn("chrome-1", package.selected_sample_ids)
        self.assertEqual(
            self.builder._extract_global_case_signal_tokens(
                MIXED_BUNDLE.evidence_cards[1].tokens
            ),
            [],
        )
        self.assertIn("Qian Zhimin ran the Blue Sky scheme", package.rendered_context)
        self.assertIn(
            "Investigators traced luxury property purchases",
            package.rendered_context,
        )
        self.assertNotIn("Skip to main content", package.rendered_context)

    def test_all_noise_bundle_falls_back_to_fulltext(self):
        package = self.builder.build(self.request, NOISE_BUNDLE)

        self.assertEqual(package.scope, "global")
        self.assertEqual(package.retrieval_status, "fallback_fulltext")
        self.assertEqual(package.summary["selected_count"], 0)
        self.assertEqual(package.selected_sample_ids, [])
        self.assertEqual(package.rendered_context, "")

    def test_summarize_latest_builder_output_prefers_latest_valid_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            older_valid_dir = root / "build_output_20240101010101000000"
            partial_dir = root / "build_output_20240202020202000000"
            empty_dir = root / "build_output_20240303030303000000"
            older_valid_dir.mkdir()
            partial_dir.mkdir()
            empty_dir.mkdir()

            older_skeleton_raw = older_valid_dir / "SkeletonReconstructor-1.json"
            older_skeleton = older_valid_dir / "SkeletonReconstructor-1-Result.json"
            older_skeleton_raw.write_text(
                json.dumps({"stages": [{"episodes": [{}]}]}),
                encoding="utf-8",
            )
            older_skeleton.write_text(
                json.dumps({"stages": [{"episodes": [{}]}]}),
                encoding="utf-8",
            )
            older_final = older_valid_dir / "FinalEventCascade.json"
            older_final.write_text(
                json.dumps({"stages": [{"episodes": [{}, {}]}]}),
                encoding="utf-8",
            )

            partial_skeleton = partial_dir / "SkeletonReconstructor-2-Result.json"
            partial_skeleton.write_text(
                json.dumps({"stages": [{"episodes": [{}, {}]}]}),
                encoding="utf-8",
            )

            older_mtime = 1_700_000_000
            partial_mtime = 1_800_000_000
            empty_mtime = 1_900_000_000
            for path in (older_valid_dir, older_skeleton, older_final):
                os.utime(path, (older_mtime, older_mtime))
            os.utime(older_skeleton_raw, (older_mtime + 100, older_mtime + 100))
            for path in (partial_dir, partial_skeleton):
                os.utime(path, (partial_mtime, partial_mtime))
            os.utime(empty_dir, (empty_mtime, empty_mtime))

            summary = summarize_latest_builder_output(root)

            self.assertEqual(summary["builder_output_count"], 3)
            self.assertEqual(summary["latest_builder_dir"], str(older_valid_dir))
            self.assertEqual(summary["skeleton"]["path"], str(older_skeleton))
            self.assertEqual(summary["skeleton"]["stage_count"], 1)
            self.assertEqual(summary["skeleton"]["episode_count"], 1)
            self.assertEqual(summary["final"]["path"], str(older_final))
            self.assertEqual(summary["final"]["stage_count"], 1)
            self.assertEqual(summary["final"]["episode_count"], 2)

    def test_summarize_latest_builder_output_keeps_count_when_all_invalid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            malformed_dir = root / "build_output_20240101010101000000"
            empty_dir = root / "build_output_20240202020202000000"
            malformed_dir.mkdir()
            empty_dir.mkdir()

            malformed_skeleton = malformed_dir / "SkeletonReconstructor-1-Result.json"
            malformed_final = malformed_dir / "FinalEventCascade.json"
            malformed_skeleton.write_text("not json", encoding="utf-8")
            malformed_final.write_text("not json", encoding="utf-8")

            empty_skeleton = empty_dir / "SkeletonReconstructor-1-Result.json"
            empty_final = empty_dir / "FinalEventCascade.json"
            empty_skeleton.write_bytes(b"")
            empty_final.write_bytes(b"")

            malformed_mtime = 1_700_000_000
            empty_mtime = 1_800_000_000
            for path in (malformed_dir, malformed_skeleton, malformed_final):
                os.utime(path, (malformed_mtime, malformed_mtime))
            for path in (empty_dir, empty_skeleton, empty_final):
                os.utime(path, (empty_mtime, empty_mtime))

            summary = summarize_latest_builder_output(root)

            self.assertEqual(summary["builder_output_count"], 2)
            self.assertIsNone(summary["latest_builder_dir"])
            self.assertIsNone(summary["skeleton"]["path"])
            self.assertIsNone(summary["skeleton"]["stage_count"])
            self.assertIsNone(summary["skeleton"]["episode_count"])
            self.assertIsNone(summary["final"]["path"])
            self.assertIsNone(summary["final"]["stage_count"])
            self.assertIsNone(summary["final"]["episode_count"])

    def test_summarize_latest_builder_output_skips_newer_malformed_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            older_valid_dir = root / "build_output_20240101010101000000"
            newer_bad_dir = root / "build_output_20240202020202000000"
            older_valid_dir.mkdir()
            newer_bad_dir.mkdir()

            older_skeleton = older_valid_dir / "SkeletonReconstructor-1-Result.json"
            older_final = older_valid_dir / "FinalEventCascade.json"
            older_skeleton.write_text(
                json.dumps({"stages": [{"episodes": [{}]}]}),
                encoding="utf-8",
            )
            older_final.write_text(
                json.dumps({"stages": [{"episodes": [{}, {}]}]}),
                encoding="utf-8",
            )

            newer_skeleton = newer_bad_dir / "SkeletonReconstructor-1-Result.json"
            newer_final = newer_bad_dir / "FinalEventCascade.json"
            newer_skeleton.write_bytes(b"")
            newer_final.write_text("not json", encoding="utf-8")

            older_mtime = 1_700_000_000
            newer_mtime = 1_800_000_000
            for path in (older_valid_dir, older_skeleton, older_final):
                os.utime(path, (older_mtime, older_mtime))
            for path in (newer_bad_dir, newer_skeleton, newer_final):
                os.utime(path, (newer_mtime, newer_mtime))

            summary = summarize_latest_builder_output(root)

            self.assertEqual(summary["builder_output_count"], 2)
            self.assertEqual(summary["latest_builder_dir"], str(older_valid_dir))
            self.assertEqual(summary["skeleton"]["path"], str(older_skeleton))
            self.assertEqual(summary["skeleton"]["stage_count"], 1)
            self.assertEqual(summary["skeleton"]["episode_count"], 1)
            self.assertEqual(summary["final"]["path"], str(older_final))
            self.assertEqual(summary["final"]["stage_count"], 1)
            self.assertEqual(summary["final"]["episode_count"], 2)

    def test_summarize_latest_builder_output_prefers_final_over_integrated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            checkpoint_dir = root / "build_output_20240101010101000000"
            checkpoint_dir.mkdir()

            skeleton = checkpoint_dir / "SkeletonReconstructor-1-Result.json"
            final = checkpoint_dir / "FinalEventCascade.json"
            integrated = checkpoint_dir / "IntegratedEventCascade.json"
            skeleton.write_text(
                json.dumps({"stages": [{"episodes": [{}]}]}),
                encoding="utf-8",
            )
            final.write_text(
                json.dumps({"stages": [{"episodes": [{}, {}]}]}),
                encoding="utf-8",
            )
            integrated.write_text(
                json.dumps({"stages": [{"episodes": [{}, {}, {}]}]}),
                encoding="utf-8",
            )

            checkpoint_mtime = 1_700_000_000
            integrated_mtime = 1_800_000_000
            for path in (checkpoint_dir, skeleton, final):
                os.utime(path, (checkpoint_mtime, checkpoint_mtime))
            os.utime(integrated, (integrated_mtime, integrated_mtime))

            summary = summarize_latest_builder_output(root)

            self.assertEqual(summary["builder_output_count"], 1)
            self.assertEqual(summary["latest_builder_dir"], str(checkpoint_dir))
            self.assertEqual(summary["skeleton"]["path"], str(skeleton))
            self.assertEqual(summary["final"]["path"], str(final))
            self.assertEqual(summary["final"]["stage_count"], 1)
            self.assertEqual(summary["final"]["episode_count"], 2)

    def test_summarize_latest_builder_output_skips_newer_empty_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            older_valid_dir = root / "build_output_20240101010101000000"
            newer_empty_dir = root / "build_output_20240202020202000000"
            older_valid_dir.mkdir()
            newer_empty_dir.mkdir()

            older_skeleton = older_valid_dir / "SkeletonReconstructor-1-Result.json"
            older_final = older_valid_dir / "FinalEventCascade.json"
            older_skeleton.write_text(
                json.dumps({"stages": [{"episodes": [{}]}]}),
                encoding="utf-8",
            )
            older_final.write_text(
                json.dumps({"stages": [{"episodes": [{}, {}]}]}),
                encoding="utf-8",
            )

            newer_skeleton = newer_empty_dir / "SkeletonReconstructor-1-Result.json"
            newer_final = newer_empty_dir / "FinalEventCascade.json"
            newer_skeleton.write_text(json.dumps({"stages": []}), encoding="utf-8")
            newer_final.write_text(json.dumps({"stages": []}), encoding="utf-8")

            older_mtime = 1_700_000_000
            newer_mtime = 1_800_000_000
            for path in (older_valid_dir, older_skeleton, older_final):
                os.utime(path, (older_mtime, older_mtime))
            for path in (newer_empty_dir, newer_skeleton, newer_final):
                os.utime(path, (newer_mtime, newer_mtime))

            summary = summarize_latest_builder_output(root)

            self.assertEqual(summary["builder_output_count"], 2)
            self.assertEqual(summary["latest_builder_dir"], str(older_valid_dir))
            self.assertEqual(summary["skeleton"]["path"], str(older_skeleton))
            self.assertEqual(summary["skeleton"]["stage_count"], 1)
            self.assertEqual(summary["skeleton"]["episode_count"], 1)
            self.assertEqual(summary["final"]["path"], str(older_final))
            self.assertEqual(summary["final"]["stage_count"], 1)
            self.assertEqual(summary["final"]["episode_count"], 2)

    def test_replay_latest_readme_checkpoint_uses_injected_creator(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            checkpoint_dir = root / "build_output_20240404040404000000"
            checkpoint_dir.mkdir()
            skeleton = checkpoint_dir / "SkeletonReconstructor-1-Result.json"
            final = checkpoint_dir / "FinalEventCascade.json"
            skeleton.write_text(
                json.dumps({"stages": [{"episodes": [{}, {}]}]}),
                encoding="utf-8",
            )
            final.write_text(
                json.dumps({"stages": [{"episodes": [{}, {}]}]}),
                encoding="utf-8",
            )

            def fake_creator(requested_root: Path) -> Path:
                self.assertEqual(requested_root, root)
                return checkpoint_dir

            checkpoint = replay_latest_readme_checkpoint(
                root,
                checkpoint_creator=fake_creator,
            )

            self.assertEqual(checkpoint["checkpoint_dir"], str(checkpoint_dir))
            self.assertEqual(checkpoint["summary"]["checkpoint_dir"], str(checkpoint_dir))
            self.assertEqual(checkpoint["summary"]["skeleton"]["path"], str(skeleton))
            self.assertEqual(checkpoint["summary"]["final"]["path"], str(final))

    def test_main_uses_default_root_and_prints_checkpoint(self):
        checkpoint_payload = {
            "checkpoint_dir": "/tmp/build_output_20240404040404000000",
            "summary": {
                "checkpoint_dir": "/tmp/build_output_20240404040404000000",
                "skeleton": {"path": "/tmp/SkeletonReconstructor-1-Result.json"},
                "final": {"path": "/tmp/FinalEventCascade.json"},
            },
        }

        with patch.object(
            sys,
            "argv",
            ["replay_skeleton_shadow_checkpoint.py"],
        ), patch.object(
            _helper_module,
            "replay_latest_readme_checkpoint",
            return_value=checkpoint_payload,
        ) as replay, patch("builtins.print") as print_mock:
            _helper_module.main()

        replay.assert_called_once_with(_helper_module.DEFAULT_ROOT)
        print_mock.assert_called_once_with(
            json.dumps(checkpoint_payload, indent=2, ensure_ascii=False)
        )

    def test_create_fresh_readme_checkpoint_attaches_context_assets(self):
        class FakeBuilder:
            def __init__(self) -> None:
                self.save_dir = "/tmp/fresh-readme-checkpoint"
                self.received_state = None
                self.execute_calls: list[str] = []

            def _get_agent_prompts(self):
                return ("system", "user")

            def execute_agent(self, state, agent_name):
                self.received_state = state
                self.execute_calls.append(agent_name)
                return state

            def integrate_results(self, state):
                return {"stages": []}

            def save_traces(self, *args, **kwargs):
                return None

            def integrate_from_files(self):
                return {"stages": []}

        class FakePipeline:
            def __init__(self, config):
                self.config = config
                self.builder = FakeBuilder()
                self.build_input_attach_context_assets = None

            def create_and_store_user_query(self, query_text, key_words):
                return {"query_text": query_text, "key_words": key_words}

            def create_raw_data_records(self, contents):
                return [{"content": content} for content in contents]

            def _process_matching(self, raw_data_records, summarized_query):
                return [{"sample_id": "sample-1"}]

            def store_meta_samples(self, meta_samples):
                return None

            def create_build_input(self, user_query, meta_samples, attach_context_assets=False):
                self.build_input_attach_context_assets = attach_context_assets
                return types.SimpleNamespace(context_assets="attached-assets")

        class FakeSummarizedUserQuery:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        fake_pipeline_module = types.ModuleType("finmy.pipeline")

        fake_summarizer_pkg = types.ModuleType("finmy.summarizer")
        fake_summarizer_module = types.ModuleType("finmy.summarizer.summarizer")
        fake_summarizer_module.SummarizedUserQuery = FakeSummarizedUserQuery
        fake_summarizer_pkg.summarizer = fake_summarizer_module

        fake_pipeline = FakePipeline(config={"builder_config": {}})
        fake_pipeline_module.FinmyPipeline = lambda config: fake_pipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with patch.object(
                _helper_module,
                "_load_readme_checkpoint_config",
                return_value={"builder_config": {}, "matcher_config": {}},
            ), patch.object(
                _helper_module,
                "_load_readme_contents",
                return_value=["fresh benchmark content"],
            ), patch.dict(
                sys.modules,
                {
                    "finmy.pipeline": fake_pipeline_module,
                    "finmy.summarizer": fake_summarizer_pkg,
                    "finmy.summarizer.summarizer": fake_summarizer_module,
                },
            ):
                checkpoint_dir = _helper_module.create_fresh_readme_checkpoint(root)

        self.assertEqual(checkpoint_dir, Path(fake_pipeline.builder.save_dir))
        self.assertTrue(fake_pipeline.build_input_attach_context_assets)
        self.assertIsNotNone(fake_pipeline.builder.received_state)
        self.assertEqual(fake_pipeline.builder.execute_calls, ["SkeletonReconstructor"])
        self.assertEqual(
            fake_pipeline.builder.received_state["build_input"].context_assets,
            "attached-assets",
        )



if __name__ == "__main__":
    unittest.main()
