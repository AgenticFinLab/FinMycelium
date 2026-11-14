"""Search material preparation and metadata contracts, with no network or Builder calls."""
from copy import deepcopy
import json
from pathlib import Path
import socket

import pytest

from finmy.search.state import SearchState, digest
from finmy.search.sources import SourceStore, pdf_blocks, parse_document
from finmy.search.metadata import publication_metadata
from finmy.search.handoff import assemble_sources, prepare_complete_sources, derive_input
from finmy.search.control import SearchController
from finmy.search.agent import context_for
from finmy.person_epg.input import freeze_search_input
from finmy.person_epg.event.records import seed_facts


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail('Material checks must not use the network')
    monkeypatch.setattr(socket.socket, 'connect', blocked)
    monkeypatch.setattr(socket.socket, 'connect_ex', blocked)


def state_and_source(tmp_path, text, *, discoveries=(), task=None):
    task = task or dict(target_type='event', target_name='Aster acquisition',
                        query_text='Aster acquisition approval and closing')
    state = SearchState(tmp_path, 'case', task=task)
    store = SourceStore(state)
    sid = store.register('https://example.org/report')
    for d in discoveries:
        store.register('https://example.org/report', title='Official report', discovery=d)
    doc = store.save_raw(sid, text.encode(), 'txt')
    store.read(sid)
    return state, store, sid, doc


def test_page_blocks_are_contiguous_located_slices_with_unicode_and_table_rows():
    text = 'First paragraph.\n\n' + 'Long passage sentence. ' * 100 + '\n' + (
        'Company     Amount\nAster       1,000\nOrion       2,000\n') + '结论成立。\n下一段。'
    blocks = pdf_blocks(text, 7)
    assert len(blocks) > 3
    assert ''.join(b['text'] for b in blocks) == text
    assert all(b['page'] == 7 and b['text'] == text[b['start']:b['end']] for b in blocks)
    assert all(a['end'] == b['start'] for a, b in zip(blocks, blocks[1:]))
    assert any('Company     Amount\nAster       1,000\nOrion       2,000' in b['text'] for b in blocks)
    assert pdf_blocks('', 3)[0]['page'] == 3
    assert pdf_blocks('x' * 2000, 1)[0]['text'] == 'x' * 2000  # No mid-word cuts.


def test_pdf_parser_uses_page_windows(tmp_path):
    from io import BytesIO
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    pdf = PdfWriter()
    for _ in range(2):
        page = pdf.add_blank_page(width=612, height=792)
        font = DictionaryObject({NameObject('/Type'):NameObject('/Font'), NameObject('/Subtype'):NameObject('/Type1'),
                                 NameObject('/BaseFont'):NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
        stream = DecodedStreamObject()
        stream.set_data(b'BT /F1 12 Tf 50 700 Td (Announcement.) Tj 0 -24 Td (Closing remained conditional.) Tj ET')
        page[NameObject('/Contents')] = pdf._add_object(stream)
    buffer = BytesIO(); pdf.write(buffer)
    blocks = parse_document(buffer.getvalue(), 'pdf')
    assert {b['page'] for b in blocks} == {1, 2}
    assert len(blocks) == 4 and all('start' in b and 'end' in b for b in blocks)


def test_saving_same_bytes_never_reparses_or_changes_status(tmp_path, monkeypatch):
    state, store, sid, doc = state_and_source(tmp_path, 'Original source.')
    folder = state.root/'sources'/sid/doc['version']
    original = (folder/'parsed.json').read_bytes()
    monkeypatch.setattr('finmy.search.sources.parse_document', lambda *a: pytest.fail('Must reuse saved parser output'))
    assert store.save_raw(sid, b'Original source.', 'txt', partial=True) == doc
    assert (folder/'parsed.json').read_bytes() == original
    assert state.data['sources'][sid]['status'] == 'success'


def test_scoped_queries_omit_exclusions_and_planning_context(tmp_path):
    task = dict(target_type='event', target_name='Aster acquisition',
                query_text='Aster acquisition. Excluded: unrelated Orion. Planning: retail sales.',
                research_scope=dict(include='Approval and closing', exclude='Orion', period='2000–2005'))
    state, _, sid, _ = state_and_source(tmp_path, 'Aster approval.', task=task)
    state.trace(dict(action='provider_started', query='Aster acquisition agreement'))
    _, complete = prepare_complete_sources(state, [sid])
    assert complete['user_query']['query_text'] == task['query_text']
    assert complete['retrieval_queries'] == ['Aster acquisition. Approval and closing', 'Aster acquisition agreement']


def test_budget_does_not_fill_distant_unrelated_sections(tmp_path):
    paragraphs = ['Opening notice.', 'Aster acquisition approval was conditional.',
                  'Conditions require divestment before closing.'] + ['Retail discounts and parking. ' * 50] * 20
    # Vary paragraphs so exact-repeat cleanup does not mask the allocation issue.
    text = '\n\n'.join(p + str(i) for i, p in enumerate(paragraphs))
    state, _, sid, _ = state_and_source(tmp_path, text)
    _, complete = prepare_complete_sources(state, [sid])
    body, selection = derive_input(state, complete, max_chars=8000)
    assert 'Conditions require divestment' in body['samples'][0]['content']
    # Progressive matching may add the immediate neighbor of a later anchor,
    # but must not fill distant unrelated blocks just to consume the budget.
    assert set(selection['selected'][0]['blocks']) <= {0, 1, 2, 3}
    assert selection['material_chars'] < 2000
    assert any(o['omission_reason'] == 'relevance_selection' for o in selection['omitted'])
    legacy = deepcopy(complete)
    legacy.pop('budget_policy'); legacy.pop('complete_id'); legacy['complete_id'] = digest(legacy)
    _, old = derive_input(state, legacy, max_chars=8000)
    assert old['budget_policy'] == 'balanced_source_windows_v1'
    assert old['material_chars'] > selection['material_chars']


def test_publication_agreement_conflict_and_unknown_dates():
    source = dict(discoveries=[dict(provider='exa', published_at='2011-03-18T00:00:00Z'),
                               dict(provider='bocha', published_at='2011-03-18')])
    assert publication_metadata(source)['published_at'] == '2011-03-18'
    source['discoveries'].append(dict(provider='baidu', published_at='2013-11-01'))
    result = publication_metadata(source)
    assert result['publication_status'] == 'conflicted' and result['published_at'] is None
    assert len(result['publication_candidates']) == 3
    assert publication_metadata(dict(url='https://example.org/2008.pdf', retrieved_at='2026-11-14'))['published_at'] is None
    assert publication_metadata(dict(published_at='last year'))['publication_status'] == 'unverified'


def test_compact_source_stays_whole_before_expanding_long_source(tmp_path):
    state, store, long_id, _ = state_and_source(tmp_path,
        '\n\n'.join('Aster acquisition approval. ' * 30 + str(i) for i in range(40)))
    short_id = store.register('https://example.org/notice')
    notice = 'Approval announced.\n\n' + 'Certain conditions remain in force. ' * 90
    store.save_raw(short_id, notice.encode(), 'txt'); store.read(short_id)
    _, complete = prepare_complete_sources(state, [long_id, short_id])
    body, selected = derive_input(state, complete, max_chars=10000)
    short_sample = next(s for s in body['samples'] if s['raw_data_id'] == short_id)
    assert notice in short_sample['content']
    assert selected['material_chars'] <= 10000


def test_published_dates_reach_person_builder_and_stay_frozen(tmp_path):
    fixture = json.loads((Path(__file__).parent/'fixtures/person_event/input.json').read_text())
    event = fixture['user_query']['extras']['person_event']
    task = dict(target_type='event', target_name=event['event_name'], query_text='Aster acquisition approval',
                research_scope=event['scope'], scope_confirmation=dict(scope_sha256=digest(event['scope'])),
                catalog=dict(kind='person_event', **{k:event[k] for k in (
                    'person_id','person_name','storyline_id','storyline_name','event_id','event_name')}))
    state, store, sid, _ = state_and_source(tmp_path, 'Aster approval was announced.', task=task,
        discoveries=[dict(provider='exa', published_at='2011-03-18T00:00:00Z')])
    assert context_for(state)['sources'][0]['published_at'] == '2011-03-18'
    payload = assemble_sources(state, [sid])
    assert 'Publication date (source/provider metadata): 2011-03-18' in payload['samples'][0]['content']
    state.data['status'] = 'finished'; state.save()
    store.register('https://example.org/report', discovery=dict(provider='baidu', published_at='2013-01-01'))
    frozen, provenance = freeze_search_input(SearchController(tmp_path), 'case', confirmed=True)
    facts = seed_facts(frozen)
    assert facts['sources'][0]['published_at'] == '2011-03-18'
    assert facts['sources'][0]['title'] == 'Official report'
    assert provenance['sources'][0]['source_metadata']['publication_candidates'][0]['provider'] == 'exa'
    assert frozen['samples'] == payload['samples']


def test_legacy_person_handoff_recovers_provider_metadata(tmp_path):
    fixture = json.loads((Path(__file__).parent/'fixtures/person_event/input.json').read_text())
    event = fixture['user_query']['extras']['person_event']
    task = dict(target_type='event', target_name=event['event_name'], query_text='Aster acquisition approval',
                research_scope=event['scope'], scope_confirmation=dict(scope_sha256=digest(event['scope'])),
                catalog=dict(kind='person_event', **{k:event[k] for k in (
                    'person_id','person_name','storyline_id','storyline_name','event_id','event_name')}))
    state, _, sid, _ = state_and_source(tmp_path, 'Aster approval.', task=task,
        discoveries=[dict(provider='bocha', published_at='2011-03-18')])
    from finmy.search.handoff import assemble
    doc = SourceStore(state).document(sid)
    assemble(state, [dict(source_id=sid, version=doc['version'], block=0, start=0, end=len(doc['blocks'][0]['text']))])
    state.data['status'] = 'finished'; state.save()
    frozen, provenance = freeze_search_input(SearchController(tmp_path), 'case', confirmed=True)
    assert seed_facts(frozen)['sources'][0]['published_at'] == '2011-03-18'
    assert provenance['sources'][0]['source_metadata']['publication_candidates']


def test_csv_uses_the_same_frozen_publication_date(tmp_path):
    import csv
    from finmy.workbench.records import export_search
    from dataset_fixture import fixture_dataset
    dataset = fixture_dataset(tmp_path/'dataset')
    task = dict(target_type='event', target_name='Aster acquisition', query_text='Aster approval',
                catalog=dict(root=str(dataset), kind='person_event'))
    root = dataset/'output/workbench/search'
    state, store, sid, _ = state_and_source(root, 'Aster approval.', task=task,
        discoveries=[dict(provider='exa', published_at='2011-03-18T10:00:00Z')])
    assemble_sources(state, [sid])
    store.register('https://example.org/report', discovery=dict(provider='baidu', published_at='2013-01-01'))
    folder = export_search(root, 'case')
    rows = list(csv.DictReader((folder/'sources.csv').open()))
    assert rows[0]['published_at'] == '2011-03-18'


def test_budget_keeps_more_than_three_relevant_positions_when_they_fit(tmp_path):
    paragraphs = []
    for i in range(5):
        paragraphs.extend([
            f'Context for milestone {i}.',
            f'Aster acquisition approval and closing milestone {i}.',
            f'Conditions for milestone {i} remain binding.',
            ('Unrelated landscape gardening. ' * 300) + str(i),
        ])
    state, _, sid, _ = state_and_source(tmp_path, '\n\n'.join(paragraphs))
    _, complete = prepare_complete_sources(state, [sid])
    assert complete['material_chars'] > 4000
    body, selection = derive_input(state, complete, max_chars=4000)
    text = body['samples'][0]['content']
    for i in range(5):
        assert f'approval and closing milestone {i}.' in text
        assert f'Conditions for milestone {i} remain binding.' in text
    assert 'Unrelated landscape gardening' not in text
    assert selection['material_chars'] <= 4000
    _, constrained = derive_input(state, complete, max_chars=500)
    assert constrained['material_chars'] <= 500
