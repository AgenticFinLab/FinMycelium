"""Offline coverage of the production person-build result receipt."""
from copy import deepcopy
import hashlib
import json
import socket

import pytest

from finmy.person_epg.build import code_identity
from finmy.workbench.build_tasks import BuildController, code_version, execute_person_build
from finmy.workbench.domain import digest, encoded
from finmy.workbench.store import Store, now
from test_person_event_contract import graph, payload


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("No network is allowed for result receipt tests")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)


@pytest.fixture
def saved_run(tmp_path, graph, payload, monkeypatch):
    directory = tmp_path / "output" / "PBUILD-test"
    path = directory / "attempts" / "0001" / "epg.json"
    path.parent.mkdir(parents=True)
    # The file hash covers the exact bytes, including serialization whitespace.
    content = (json.dumps(graph, ensure_ascii=False, indent=4) + "\n").encode("utf-8")
    path.write_bytes(content)
    state = {
        "execution_status": "finished", "result_status": "draft",
        "render_status": "not_started", "output": str(path.relative_to(directory)),
        "graph_sha256": hashlib.sha256(content).hexdigest(),
        "calls": [{"call_id": "CALL-000001", "status": "accepted",
                   "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}}],
    }
    event = payload["user_query"]["extras"]["person_event"]
    body = {
        "kind": "person_event", "graph_schema_version": "person-event-1.0",
        "input": payload, "input_hash": digest(payload), "scope_hash": digest(event["scope"]),
        "artifact_directory": str(directory), "person_config": {}, "provenance": {},
        "code": code_version(), "person_code": code_identity(),
    }
    invocations = []
    def saved_completion(*args, **kwargs):
        invocations.append((args, kwargs))
        return deepcopy(state)
    monkeypatch.setattr("finmy.person_epg.build.run_event", saved_completion)
    return directory, path, body, state, invocations


@pytest.mark.parametrize("execution,result,expected", [
    ("finished", "draft", "completed"),
    ("finished", "partial", "partial"),
    ("limit", "partial", "limit"),
])
def test_production_person_receipt_saves_status_and_usage(saved_run, tmp_path, execution, result, expected):
    directory, path, body, state, invocations = saved_run
    state.update(execution_status=execution, result_status=result)
    original_bytes = path.read_bytes()
    store = Store(tmp_path / "workspace")
    builds = BuildController(store)
    event_id = body["input"]["user_query"]["extras"]["person_event"]["event_id"]
    with store.connection() as db:
        db.execute("INSERT INTO build_tasks VALUES(?,?,?,?,?)",
                   (directory.name, event_id, encoded(body), "queued", now()))
    # Exercise the production adapter, rather than bypassing it with an executor.
    builds.run(directory.name)
    row = builds.inspect(directory.name)
    assert row["status"] == expected, row["body"].get("error_type")
    assert row["body"]["run_state"] == state
    assert row["body"]["usage"] == state["calls"]
    assert path.read_bytes() == original_bytes
    assert len(invocations) == 1


def test_production_person_receipt_rejects_changed_file_bytes(saved_run):
    directory, path, body, state, invocations = saved_run
    original_graph = json.loads(path.read_bytes())
    path.write_bytes(path.read_bytes() + b"\n")
    assert json.loads(path.read_bytes()) == original_graph
    with pytest.raises(ValueError, match="Saved person draft integrity mismatch"):
        execute_person_build(body, directory)
    assert len(invocations) == 1


def test_production_person_receipt_preserves_no_graph_result(saved_run):
    directory, path, body, state, invocations = saved_run
    state.update(execution_status="limit", result_status="none", output=None)
    path.unlink()
    received = execute_person_build(body, directory)
    assert received == {"state": state, "graph": None}
    assert len(invocations) == 1
