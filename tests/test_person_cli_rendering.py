"""Exercise CLI render dispatch with canonical Person EPG and legacy outputs.

Model construction is replaced; argument parsing, input loading and HTML export
are real. The optional Node check exercises the shipped renderer script.
"""

import copy
from contextlib import ExitStack, redirect_stdout
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from sparse_test_dependencies import install_missing_lmbase_containers

install_missing_lmbase_containers()

from finmy.builder.base import BuildOutput
from finmy.person_epg.compat_projection import project_person_epg
from finmy.person_epg.visualizer import render_person_epg
from finmy.runner import build_only_runner, sparse_build_runner


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/buffett_person_epg_preview.json"
RUNNERS = (sparse_build_runner, build_only_runner)


class PersonPayload(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.capture = False
        self.parts = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.capture = dict(attrs).get("id") == "epg-data"

    def handle_endtag(self, tag):
        if tag == "script":
            self.capture = False

    def handle_data(self, data):
        if self.capture:
            self.parts.append(data)

    @property
    def package(self):
        return json.loads("".join(self.parts))


class PersonCLIRenderingTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")))
        self.package = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.projection = project_person_epg(self.package)
        self.input_path = self.root / "input.json"
        self.input_path.write_text(json.dumps({
            "user_query": {"query_text": "Test person history", "key_words": []},
            "samples": [{"sample_id": "s1", "raw_data_id": "r1", "content": "Supplied source text"}],
        }), encoding="utf-8")

    def execute(self, runner, output):
        directory = self.root / runner.__name__.rsplit(".", 1)[-1]
        directory.mkdir()
        builder = Mock(save_dir=str(directory))
        builder.run.return_value = output
        builder.save_traces.side_effect = lambda data, name, fmt: (
            directory / (name + "." + fmt)
        ).write_text(json.dumps(data), encoding="utf-8")
        with patch.object(runner, "SparseRagBuilder", return_value=builder) as constructor, \
             patch.object(runner, "preflight", return_value={"credential_present": True}), \
             redirect_stdout(io.StringIO()):
            code = runner.main([
                "--config", str(ROOT / "configs/person_sparse.yml"),
                "--input", str(self.input_path), "--execute", "--gantt",
            ])
        self.assertEqual(code, 0)
        constructor.assert_called_once()
        builder.run.assert_called_once()
        self.assertEqual(builder.run.call_args.args[0].samples[0].content, "Supplied source text")
        return directory

    def test_both_cli_render_complete_person_package_before_legacy_projection(self):
        before = copy.deepcopy(self.package)
        for runner in RUNNERS:
            with self.subTest(runner=runner.__name__), \
                 patch("finmy.subject_graph.visualizer.render_subject_graph") as legacy:
                directory = self.execute(runner, BuildOutput(
                    event_cascades={"legacy_event": True}, subject_graph=self.projection,
                    extras={"person_epg": self.package},
                ))
                page = (directory / "gantt.html").read_text(encoding="utf-8")
                payload = PersonPayload(page).package
                self.assertEqual(payload, before)
                self.assertEqual(len(payload["domain"]), 3)
                self.assertEqual(len(payload["stage"]), 6)
                self.assertEqual(len(payload["event_activity"]), 45)
                self.assertIn("Collapse events", page)
                self.assertEqual(json.loads((directory / "GanttStatus.json").read_text()), {"status": "completed"})
                legacy.assert_not_called()
        self.assertEqual(self.package, before)


    def test_both_cli_keep_event_fallback_when_both_person_views_are_absent(self):
        event = {"event_id": "legacy-event"}
        for runner in RUNNERS:
            with self.subTest(runner=runner.__name__), \
                 patch("finmy.person_epg.visualizer.render_person_epg") as person, \
                 patch("finmy.subject_graph.visualizer.render_subject_graph") as legacy, \
                 patch("finmy.builder.agent_build.visualizer_gantt.EventCascadeGanttVisualizer") as event_renderer:
                directory = self.execute(runner, BuildOutput(event_cascades=event, extras={"person_epg": None}))
                event_renderer.return_value.plot_cascade.assert_called_once_with(
                    event, output_path=str(directory / "gantt.html"))
                legacy.assert_not_called()
                person.assert_not_called()

    def test_invalid_person_package_fails_render_instead_of_silently_using_legacy(self):
        for runner in RUNNERS:
            with self.subTest(runner=runner.__name__), \
                 patch("finmy.subject_graph.visualizer.render_subject_graph") as legacy:
                directory = self.execute(runner, BuildOutput(subject_graph=self.projection,
                                                             extras={"person_epg": {}}))
                self.assertFalse((directory / "gantt.html").exists())
                self.assertEqual(json.loads((directory / "GanttStatus.json").read_text()),
                                 {"status": "failed", "error_type": "ValueError"})
                legacy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
