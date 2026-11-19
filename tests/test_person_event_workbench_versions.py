"""Read both event protocols while keeping historical checkpoints immutable."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from finmy.person_epg.event.evidence_support import upgrade_package_evidence
from finmy.person_epg.event.schema import GRAPH_VERSION, LEGACY_GRAPH_VERSION
from finmy.person_epg.validation import validate_person_epg
from finmy.workbench.build_tasks import BuildController, execute_person_build
from finmy.workbench.graph_collection import _identity
from finmy.workbench.store import Store


FIXTURES = Path(__file__).parent / 'fixtures' / 'person_event'


def test_collection_and_public_validation_read_both_event_protocols():
    legacy = json.loads((FIXTURES / 'graph.json').read_text())
    current = upgrade_package_evidence(legacy)
    assert current['schema_version'] == GRAPH_VERSION != LEGACY_GRAPH_VERSION
    catalog = dict(event_id=legacy['event']['event_id'], person_id=legacy['person']['person_id'],
                   storyline_id=legacy['storyline']['storyline_id'])
    for graph in (legacy, current):
        before = deepcopy(graph)
        _identity(catalog, graph)
        report = validate_person_epg(graph)
        assert report['valid'], report
        assert graph == before
    current['schema_version'] = 'person-event-unknown'
    with pytest.raises(ValueError, match='身份'):
        _identity(catalog, current)


@pytest.mark.parametrize('method,status,kwargs', [
    ('prepare_person_resume', 'partial', {}),
    ('prepare_person_read_recovery', 'failed', {}),
    ('prepare_person_relation_recovery', 'limit',
     dict(max_context_chars=40000, max_read_calls=10, max_read_chars=40000)),
    ('prepare_person_output_recovery', 'failed', dict(max_new_tokens=10000)),
])
def test_historical_task_cannot_enter_a_new_writer(tmp_path, method, status, kwargs):
    store = Store(tmp_path / 'workspace')
    builds = BuildController(store)
    body = dict(kind='person_event', graph_schema_version=LEGACY_GRAPH_VERSION,
                artifact_directory=str(tmp_path / 'historical-run'))
    task_id = 'PBUILD-historical'
    with store.connection() as db:
        db.execute('INSERT INTO build_tasks VALUES(?,?,?,?,?)',
                   (task_id, 'event', json.dumps(body), status, '2020-01-01'))
    before = builds.inspect(task_id)
    with pytest.raises(ValueError, match='旧协议|Historical checkpoints'):
        getattr(builds, method)(task_id, **kwargs)
    assert builds.inspect(task_id) == before
    assert not Path(body['artifact_directory']).exists()
    with pytest.raises(ValueError, match='Historical checkpoints'):
        execute_person_build(body, tmp_path / 'historical-run')
