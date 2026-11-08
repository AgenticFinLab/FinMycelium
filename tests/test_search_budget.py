"""Material allocation invariants, without API calls or source-specific expectations."""
import copy
import socket
import pytest
from finmy.search.state import SearchState, digest
from finmy.search.sources import SourceStore
from finmy.search.handoff import prepare_complete_sources, derive_input, materialize_complete

@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('Unexpected network'))

def prepared(tmp_path, texts):
    s = SearchState(tmp_path, 'case', task=dict(target_type='event', target_name='Deal',
        query_text='Trace approval and closing', key_words=['approval', 'closing']))
    store = SourceStore(s)
    ids = []
    for i, text in enumerate(texts):
        sid = store.register('https://example.org/' + str(i), title='Source ' + str(i))
        store.save_raw(sid, text.encode(), 'txt', partial=True)
        store.read(sid)
        ids.append(sid)
    return s, ids

def test_full_fit_exact_and_default_policy(tmp_path):
    s, ids = prepared(tmp_path, ['Approval was conditional.', 'Closing was later.'])
    full, c = prepare_complete_sources(s, ids)
    p, r = derive_input(s, c, max_chars=10000)
    assert p == full == materialize_complete(s, c)
    assert r['budget_policy'] == 'balanced_source_windows_v1'
    assert 'variant' not in r['allocation']
    assert not r['omitted'] and all(e['source_status'] == 'partial' for e in r['selected'])

def test_pool_recovers_context_and_preserves_references(tmp_path):
    s, ids = prepared(tmp_path, ['Opening.\n\nApproval granted.\n\n' + 'Subject to divestment. ' * 65 +
        '\n\nClosing notice.\n\n' + 'Unrelated background. ' * 250, 'Short notice.'])
    _, c = prepare_complete_sources(s, ids)
    p, r = derive_input(s, c, max_chars=2400)
    assert 'Subject to divestment. ' * 65 in p['samples'][0]['content']
    assert r['allocation']['pool_actions'] and r['material_chars'] <= 2400
    by_id = {e['source_id']: e for e in c['selected']}
    for e in r['omitted']:
        assert e['version'] == by_id[e['source_id']]['version']
        assert e['omission_reason'] == 'material_limit'
    assert r['gaps']

def test_order_budget_and_original_text_invariants(tmp_path):
    s, ids = prepared(tmp_path, ['\n\n'.join('Approval ' + str(i) + ' detail.' * 20 for i in range(25)),
        'Closing is subject to consent.'])
    _, c = prepare_complete_sources(s, ids)
    rev = copy.deepcopy(c)
    rev['selected'].reverse(); rev['source_ids'].reverse()
    rev.pop('complete_id'); rev['complete_id'] = digest(rev)
    store = SourceStore(s)
    for limit in (1, 400, 1800, 60000):
        p, r = derive_input(s, c, max_chars=limit)
        assert r['material_chars'] == sum(len(x['content']) for x in p['samples']) <= limit
        assert derive_input(s, c, max_chars=limit) == (p, r)
        _, rr = derive_input(s, rev, max_chars=limit)
        assert {e['source_id']:e['blocks'] for e in r['selected']} == {e['source_id']:e['blocks'] for e in rr['selected']}
        for e, sample in zip(r['selected'], p['samples']):
            doc = store.document(e['source_id'],e['version'])
            assert e['blocks'] == sorted(e['blocks'])
            assert all(doc['blocks'][i]['text'] in sample['content'] for i in e['blocks'])
    assert not (s.run_dir/'builder_input.json').exists()

def test_queries_and_versions_remain_frozen(tmp_path):
    s, ids = prepared(tmp_path, ['Approval announcement.\n\nClosing conditions.'])
    s.trace(dict(action='provider_started', provider='baidu', query='deal closing'))
    s.trace(dict(action='provider_started', provider='bocha', query='deal closing'))
    _, c = prepare_complete_sources(s, ids)
    assert c['retrieval_queries'].count('deal closing') == 1
    before = derive_input(s, c, max_chars=350)
    s.trace(dict(action='provider_started', provider='exa', query='unrelated later query'))
    SourceStore(s).save_raw(ids[0], b'Revised later body.', 'txt')
    assert derive_input(s, c, max_chars=350) == before

def test_legacy_manifest_uses_only_frozen_task(tmp_path):
    s, ids = prepared(tmp_path, ['Announcement.\n\nApproval.'])
    _, c = prepare_complete_sources(s, ids)
    c.pop('retrieval_queries'); c.pop('complete_id'); c['complete_id'] = digest(c)
    s.trace(dict(action='provider_started', query='later search'))
    _, r = derive_input(s, c, max_chars=10000)
    assert r['retrieval_queries'] == ['Trace approval and closing', 'approval closing']
    assert r['complete_id'] == c['complete_id']

def test_empty_and_invalid_inputs(tmp_path):
    s, ids = prepared(tmp_path, [])
    _, c = prepare_complete_sources(s, ids)
    assert derive_input(s, c)[0]['samples'] == []
    for bad in (True, 0, -1, 0.5):
        with pytest.raises(ValueError): derive_input(s, c, max_chars=bad)
    for unsupported in ('unknown', 'source_order'):
        with pytest.raises(ValueError): derive_input(s, c, budget_policy=unsupported)
    c['material_chars'] = 1
    with pytest.raises(ValueError, match='integrity'): derive_input(s, c)


def test_previous_argument_preserves_text_but_writes_current_policy(tmp_path):
    s, ids = prepared(tmp_path, ['Approval subject to conditions.\n\nClosing awaited. ' * 20])
    _, complete = prepare_complete_sources(s, ids)
    current = derive_input(s, complete, max_chars=500)
    previous = derive_input(s, complete, max_chars=500, budget_policy='c2')
    assert previous == current
    assert current[1]['budget_policy'] == 'balanced_source_windows_v1'
    assert 'variant' not in current[1]['allocation']
