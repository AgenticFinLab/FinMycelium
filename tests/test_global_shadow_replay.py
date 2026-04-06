import importlib.util
import json
import os
import tempfile
from pathlib import Path
import unittest

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

    def test_summarize_latest_builder_output_counts_latest_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            older_dir = root / "build_output_20240101010101000000"
            newer_dir = root / "build_output_20240202020202000000"
            older_dir.mkdir()
            newer_dir.mkdir()

            older_skeleton = older_dir / "SkeletonReconstructor-1-Result.json"
            older_skeleton.write_text(
                json.dumps({"stages": [{"episodes": [{}]}]}),
                encoding="utf-8",
            )
            older_final = older_dir / "FinalEventCascade.json"
            older_final.write_text(
                json.dumps({"stages": [{"episodes": [{}, {}]}]}),
                encoding="utf-8",
            )

            newer_skeleton = newer_dir / "SkeletonReconstructor-2-Result.json"
            newer_skeleton.write_text(
                json.dumps(
                    {
                        "stages": [
                            {"episodes": [{}, {}]},
                            {"episodes": [{}]},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            newer_final = newer_dir / "FinalEventCascade.json"
            newer_final.write_text(
                json.dumps(
                    {
                        "stages": [
                            {"episodes": [{}, {}, {}]},
                            {"episodes": [{}]},
                            {"episodes": [{}, {}]},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            older_mtime = 1_700_000_000
            newer_mtime = 1_800_000_000
            for path in (older_dir, older_skeleton, older_final):
                os.utime(path, (older_mtime, older_mtime))
            for path in (newer_dir, newer_skeleton, newer_final):
                os.utime(path, (newer_mtime, newer_mtime))

            summary = summarize_latest_builder_output(root)

            self.assertEqual(summary["builder_output_count"], 2)
            self.assertEqual(summary["latest_builder_dir"], str(newer_dir))
            self.assertEqual(summary["skeleton"]["path"], str(newer_skeleton))
            self.assertEqual(summary["skeleton"]["stage_count"], 2)
            self.assertEqual(summary["skeleton"]["episode_count"], 3)
            self.assertEqual(summary["final"]["path"], str(newer_final))
            self.assertEqual(summary["final"]["stage_count"], 3)
            self.assertEqual(summary["final"]["episode_count"], 6)



if __name__ == "__main__":
    unittest.main()
