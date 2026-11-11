from pathlib import Path
import socket
import threading

import pytest

from finmy.dataset import DatasetCatalog
from finmy.search.control import SearchController
from finmy.search.state import SearchState
from finmy.search import summary
from finmy.workbench.search_bridge import create_catalog_search
from finmy.workbench.store import Store
from dataset_fixture import fixture_dataset


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('No real network'))


def setup(root, workspace, *, person=False):
    store = Store(workspace)
    calls = []
    def transport(*args):
        calls.append('search')
        return {'data':{'webPages':{'value':[{'url':'https://example.org/evidence', 'name':'Synthetic notice'}]}}}
    c = SearchController(store.root / 'search', transport=transport,
        fetcher=lambda u:(b'PRIVATE_FULL_SOURCE_TEXT for an invented test.', 'txt', 'utf-8'))
    catalog = DatasetCatalog(root)
    selection = catalog.select('PERSON-EVENT-TEST', 'PERSON-TEST') if person else catalog.select('EVENT-TEST')
    tid = create_catalog_search(store,c,selection,{},'simple',period=selection['period'],
                               include=selection['scope_include'],exclude=selection['scope_exclude'],confirmed=True,seeds=[])
    return c, tid, root / selection['event_dir'] / 'search-summary.md', calls


def finish(c, tid):
    c.start(tid); c.threads[tid].join(5)
    assert not c.active(tid)
    assert c.inspect(tid)['status'] == 'finished'


@pytest.mark.parametrize('person', [False, True])
def test_background_completion_publishes_without_open_page(tmp_path, person):
    root = fixture_dataset(tmp_path / 'dataset')
    before = {str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    c, tid, target, calls = setup(root,tmp_path / 'workbench',person=person)
    assert not target.exists()
    finish(c,tid)
    assert c.inspect(tid)['summary']['status'] == 'saved'
    text = target.read_text()
    assert tid in text and 'https://example.org/evidence' in text
    assert 'PRIVATE_FULL_SOURCE_TEXT' not in text
    assert 'not automatically adopted' in text
    assert all(Path(p).read_bytes()==raw for p,raw in before.items())
    assert set(p.name for p in target.parent.iterdir()) == {'search-summary.md'}
    assert calls == ['search']


def test_retry_is_idempotent_and_preserves_notes_and_usage(tmp_path):
    root = fixture_dataset(tmp_path / 'dataset')
    c,tid,target,calls = setup(root,tmp_path / 'workbench')
    finish(c,tid)
    target.write_text(target.read_text() + '\nHuman note: retain this exact remark.\n')
    previous = target.read_text()
    usage = c.inspect(tid)['usage']
    c.save_summary(tid)
    assert target.read_text() == previous
    assert calls == ['search'] and c.inspect(tid)['usage'] == usage
    assert target.read_text().count('| '+tid+' |') == 1
    old_revision = c.inspect(tid)['handoff_revision']
    c.reassemble(tid, 1)
    assert c.inspect(tid)['handoff_revision'] != old_revision
    assert 'Human note: retain this exact remark.' in target.read_text()
    assert '0 in this input' in target.read_text()
    assert target.read_text().count('| '+tid+' |') == 1


def test_write_failure_does_not_retry_search(tmp_path, monkeypatch):
    root = fixture_dataset(tmp_path / 'dataset')
    c,tid,target,calls = setup(root,tmp_path / 'workbench')
    original = summary.atomic_text
    def denied(path, text):
        if path.is_relative_to(root): raise PermissionError('Synthetic read-only dataset')
        original(path,text)
    with monkeypatch.context() as m:
        m.setattr(summary, 'atomic_text', denied)
        finish(c,tid)
    data = c.inspect(tid)
    assert data['summary']['status'] == 'failed'
    assert (c.root / tid / 'runs/initial/search-summary.md').is_file()
    assert not target.exists()
    c.save_summary(tid)
    assert target.exists() and c.inspect(tid)['summary']['status'] == 'saved'
    assert calls == ['search']


def test_multiple_workspaces_preserve_history_and_newest_output(tmp_path):
    root = fixture_dataset(tmp_path / 'dataset')
    c1,t1,target,_ = setup(root,tmp_path / 'one')
    c2,t2,_,_ = setup(root,tmp_path / 'two')
    finish(c1,t1)
    finish(c2,t2)
    c1.save_summary(t1)  # Retrying an older report must not replace the latest result.
    text = target.read_text()
    assert f'- Search task: {t2}' in text
    assert text.count('| '+t1+' |') == text.count('| '+t2+' |') == 1
    threads = [threading.Thread(target=c.save_summary,args=(t,)) for c,t in [(c1,t1),(c2,t2)]]
    for thread in threads: thread.start()
    for thread in threads: thread.join(5)
    assert all(not thread.is_alive() for thread in threads)
    assert target.read_text().count('| '+t1+' |') == target.read_text().count('| '+t2+' |') == 1


def test_existing_unmanaged_notes_are_retained(tmp_path):
    root = fixture_dataset(tmp_path / 'dataset')
    c,tid,target,_ = setup(root,tmp_path / 'workbench')
    target.parent.mkdir(parents=True)
    target.write_text('Existing human notes.\n')
    finish(c,tid)
    assert 'Existing human notes.' in target.read_text()
    c.save_summary(tid)
    assert target.read_text().count('Existing human notes.') == 1


def test_escaped_event_directory_cannot_be_written(tmp_path):
    root = fixture_dataset(tmp_path / 'dataset')
    c,tid,_,calls = setup(root,tmp_path / 'workbench')
    state = SearchState(c.root,tid)
    state.data['task']['catalog']['event_dir'] = '../outside'
    state.save()
    finish(c,tid)
    assert c.inspect(tid)['summary']['status'] == 'failed'
    assert not (tmp_path / 'outside').exists()
    assert calls == ['search']


def test_unconfirmed_dataset_task_cannot_start(tmp_path):
    root = fixture_dataset(tmp_path / 'dataset')
    c,tid,_,calls = setup(root,tmp_path / 'workbench')
    state = SearchState(c.root,tid)
    state.data['task']['research_scope']['include'] = 'Changed after confirmation'
    state.save()
    with pytest.raises(ValueError,match='确认'): c.start(tid)
    assert not calls


def test_unlinked_search_has_no_dataset_summary(tmp_path):
    c = SearchController(tmp_path, transport=lambda *a:{'data':{'webPages':{'value':[]}}})
    tid = c.create(dict(target_type='event',target_name='Synthetic',query_text='Test'),{},'simple')
    c.start(tid);c.threads[tid].join(5)
    assert c.inspect(tid)['status'] == 'insufficient'
    assert 'summary' not in c.inspect(tid)
    assert not list(tmp_path.rglob('search-summary.md'))


def test_agent_mode_completion_uses_same_summary_path(tmp_path):
    root = fixture_dataset(tmp_path / 'dataset')
    store = Store(tmp_path / 'workbench')
    steps = []
    def model(context):
        steps.append(1)
        if len(steps) == 1: return {'action':'search','query':'synthetic appointment'}
        sid = context['sources'][0]['source_id']
        if len(steps) == 2: return {'action':'read_source','source':sid}
        return {'action':'finish','source_ids':[sid],'gaps':['Exact date unverified'],'reason':'supported'}
    c = SearchController(store.root / 'search',model=model,
        transport=lambda *a:{'data':{'webPages':{'value':[{'url':'https://example.org/a'}]}}},
        fetcher=lambda u:(b'An entirely fictional appointment notice.', 'txt','utf-8'))
    selection = DatasetCatalog(root).select('PERSON-EVENT-TEST','PERSON-TEST')
    tid = create_catalog_search(store,c,selection,{},'agent',period='1990s',include='Appointment',exclude='',confirmed=True,seeds=[])
    finish(c,tid)
    data = c.inspect(tid)
    assert data['usage']['model'] == 3
    assert data['summary']['status'] == 'saved'
    report = (root / selection['event_dir'] / 'search-summary.md').read_text()
    assert 'Exact date unverified' in report
    assert 'Complete material characters: Not recorded' not in report


def test_no_results_are_reported_as_insufficient(tmp_path):
    root = fixture_dataset(tmp_path / 'dataset')
    store = Store(tmp_path / 'workbench')
    c = SearchController(store.root/'search',transport=lambda *a:{'data':{'webPages':{'value':[]}}})
    selection = DatasetCatalog(root).select('EVENT-TEST')
    tid = create_catalog_search(store,c,selection,{},'simple',period='2024',include='Closing',exclude='',confirmed=True,seeds=[])
    c.start(tid);c.threads[tid].join(5)
    assert c.inspect(tid)['status'] == 'insufficient'
    report = (root / selection['event_dir'] / 'search-summary.md').read_text()
    assert '- Status: insufficient' in report and 'No sources recorded.' in report
