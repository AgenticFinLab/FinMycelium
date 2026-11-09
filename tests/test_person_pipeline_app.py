"""Exercise real Streamlit widgets with network/build services replaced."""
from pathlib import Path
import unittest

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(AppTest is None, "Streamlit testing support is not installed")
class PersonPipelineAppTests(unittest.TestCase):
    def test_two_fields_date_validation_start_button_and_event_mode(self):
        script = '''
import importlib.util
from pathlib import Path
import types
from unittest.mock import Mock, patch
import streamlit as st
ROOT = Path(ROOT_VALUE)
def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
def package(name, relative):
    module = types.ModuleType(name)
    module.__path__ = [str(ROOT / relative)]
    return module
def module(name, **attributes):
    result = types.ModuleType(name)
    result.__dict__.update(attributes)
    return result
config = {"builder_config": {"reconstruction": {"mode": "person", "subject": {
    "subject_id": "buffett", "name": "Buffett", "coverage_start": "2022", "coverage_end": "2023"}}}}
for key, value in {"processing_status": "idle", "config_file_name": "test.yml", "config": config,
                   "keywords": ["stale event"], "structured_data": None}.items():
    st.session_state.setdefault(key, value)
fakes = {
    "finmy.web_ui": package("finmy.web_ui", "finmy/web_ui"),
    "finmy.web_ui.components": package("finmy.web_ui.components", "finmy/web_ui/components"),
    "finmy.web_ui.utils": package("finmy.web_ui.utils", "finmy/web_ui/utils"),
    "finmy.web_ui.components.config_uploader": module("config_uploader", ConfigUploader=Mock(render=lambda: (True, config))),
    "finmy.web_ui.services.reconstruction_service": module("reconstruction_service", ReconstructionService=Mock()),
    "finmy.web_ui.state": module("state", SessionStateManager=Mock()),
}
with patch.dict("sys.modules", fakes):
    page = load("pipeline_under_test", "finmy/web_ui/pages/pipeline_page.py")
    page.PipelinePage.render()
'''.replace("ROOT_VALUE", repr(str(ROOT)))
        app = AppTest.from_string(script).run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual([widget.label for widget in app.text_input], ["Person name", "Period"])
        self.assertEqual(len(app.text_area), 0)
        self.assertEqual(len(app.multiselect), 0)
        self.assertEqual(app.session_state["main_input"], "Buffett 2022 – 2023")
        self.assertEqual(app.session_state["keywords"], [])
        self.assertFalse(app.button[0].disabled)

        app.text_input[1].set_value("2023-02-30").run()
        self.assertEqual(list(app.exception), [])
        self.assertTrue(app.button[0].disabled)
        self.assertIsNone(app.session_state["reconstruction_run_config"])
        self.assertEqual(len(app.error), 1)

        app.text_input[1].set_value("2023-05").run()
        self.assertEqual(list(app.exception), [])
        self.assertFalse(app.button[0].disabled)
        self.assertEqual(app.session_state["main_input"], "Buffett 2023-05")
        subject = app.session_state["reconstruction_run_config"]["builder_config"]["reconstruction"]["subject"]
        self.assertEqual((subject["coverage_start"], subject["coverage_end"]), ("2023-05", "2023-05"))

        app.selectbox[0].select("event").run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(len(app.text_input), 0)
        self.assertEqual(app.text_area[0].label, "Event Description")
        self.assertEqual(len(app.multiselect), 1)
        self.assertEqual(app.session_state["reconstruction_run_config"]["builder_config"]["reconstruction"], {"mode": "event"})


if __name__ == "__main__":
    unittest.main()
