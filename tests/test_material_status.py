"""Confirmation follows saved inputs, not a search or builder success flag."""
from copy import deepcopy
import json

import pytest

from test_event_collection import setup, finish, offline
from finmy.workbench.build_tasks import BuildController
from finmy.workbench.material_status import saved_confirmations, confirmed_builds
from finmy.workbench.records import find_build_record
from finmy.workbench.search_bridge import adopt_sources
from finmy.workbench.workflow import search_status_label


def label(store, search, tid, data=None):
    data = data or search.inspect(tid)
    return search_status_label(data, confirmed_builds(tid, data, saved_confirmations(store.root)))


def shared(root, tid):
    return next(p.parent for p in (root/'workbench/search').glob('*/task.json')
                if json.loads(p.read_text())['task_id'] == tid)


@pytest.mark.parametrize('status', ['ready', 'running', 'failed', 'paused', 'cancelled', 'completed'])
def test_saved_confirmation_survives_build_status_changes(setup, status):
    root, store, search, _ = setup
    tid, _ = finish(setup); original = deepcopy(search.inspect(tid))
    assert label(store, search, tid) == '待检查材料'
    builds = BuildController(store); bid = builds.create_person(search, tid, confirmed=True)
    builds.save(bid, status, builds.inspect(bid)['body'])
    assert label(store, search, tid) == '已确认用于构建'
    assert search.inspect(tid) == original
    for filename in ('task.json', 'summary.json'):
        record = json.loads((shared(root, tid)/filename).read_text())
        assert record['build_disposition'] == 'confirmed' and record['confirmed_build_tasks'] == [bid]
    assert '| finished | confirmed |' in (root/'workbench/search/README.md').read_text()
    record = json.loads(find_build_record(root, bid).read_text())
    manifest = record['search_collection']['manifest']
    assert (root/manifest['build_record']).is_file()


def test_reassembly_needs_confirmation_of_new_revision(setup):
    root, store, search, _ = setup
    tid, _ = finish(setup)
    builds = BuildController(store); old = builds.create_person(search, tid, confirmed=True)
    before = search.inspect(tid)
    changed = deepcopy(before); changed['builder_input']['samples'][0]['content'] += ' changed'
    assert label(store, search, tid, changed) == '待检查材料'
    search.reassemble(tid, 10000)
    assert search.inspect(tid)['handoff_revision'] != before['handoff_revision']
    assert label(store, search, tid) == '待检查材料'
    assert json.loads((shared(root, tid)/'summary.json').read_text())['build_disposition'] == 'pending'
    new = builds.create_person(search, tid, confirmed=True)
    current = search.inspect(tid)
    assert confirmed_builds(tid, current, saved_confirmations(store.root)) == [new]
    assert builds.inspect(old)['body']['provenance']['handoff_revision'] == before['handoff_revision']


def test_exclusion_overrides_but_does_not_erase_confirmation(setup):
    _, store, search, _ = setup
    tid, _ = finish(setup)
    BuildController(store).create_person(search, tid, confirmed=True)
    search.set_build_disposition(tid, 'excluded')
    assert label(store, search, tid) == '不参与构建'
    search.set_build_disposition(tid, 'pending')
    assert label(store, search, tid) == '已确认用于构建'


def test_failed_save_cannot_confirm_material(setup, monkeypatch):
    _, store, search, _ = setup
    tid, _ = finish(setup)
    builds = BuildController(store)
    def fail(*args, **kwargs):
        raise OSError('Synthetic save failure')
    monkeypatch.setattr(builds, '_save_prepared', fail)
    with pytest.raises(OSError):
        builds.create_person(search, tid, confirmed=True)
    assert not builds.tasks() and label(store, search, tid) == '待检查材料'


def test_ordinary_event_uses_actual_reviewed_adoption(setup):
    _, store, search, _ = setup
    tid, _ = finish(setup, person=False)
    eid = search.inspect(tid)['task']['event_id']
    adopt_sources(search, tid, store)
    assert label(store, search, tid) == '待检查材料'
    store.review(eid, 'evidence', 'approved', 'Reviewer', '', store.target(eid, 'evidence'))
    BuildController(store).create(eid, store.settings())
    assert label(store, search, tid) == '已确认用于构建'
