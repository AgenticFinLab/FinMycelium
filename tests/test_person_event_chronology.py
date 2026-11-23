"""Regression coverage for the Builder-to-Phase chronology contract (offline)."""
from copy import deepcopy
from datetime import date, timedelta

import pytest

from finmy.person_epg.event.chronology import ActionChronology
from finmy.person_epg.event.context import navigation
from finmy.person_epg.event.graph_html import render_graph_html
from finmy.person_epg.event.proposals import Receiver, preserve_known_fields
from finmy.person_epg.event.records import IdMap, seed_facts, unknown_time
from finmy.person_epg.event.temporal import ActionWindow, quoted_daypart
from finmy.person_epg.event.validation import SupportIndex, check_graph, order_view
from test_person_event_contract import graph, payload
from test_person_event_temporal import proposal
from test_person_event_graph_html import embedded_data


DAY = date(2024, 3, 1)


def window(value, offset=None, day=DAY):
    return ActionWindow(day, day + timedelta(days=1), value, offset)


@pytest.mark.parametrize('first, second, expected', [
    ('morning', 'afternoon', True), ('noon', 'evening', True), ('evening', 'afternoon', False),
    ('afternoon', 'afternoon', False), ('10:21', 'afternoon', True), ('16:30', 'evening', False),
    ('12:34', '12:34:25', False), ('12:34:25', '12:34', False), ('12:34', '12:35', True),
])
def test_dayparts_and_clock_precision(first, second, expected):
    assert window(first).before(window(second)) is expected


def test_local_clock_offset_and_midnight():
    first = window('23:30', '-04:00', day=DAY - timedelta(days=1))
    assert not first.before(window('01:30', 'Z'))
    assert window('01:30', 'Z').before(first)
    assert not window('12:30', 'Z').before(window('14:00', '+02:00'))
    assert not window('12:30', 'Z').before(window('14:00'))
    assert window('morning', 'Z').before(window('afternoon', '+00:00'))
    assert not window('morning', 'Z').before(window('evening', '-05:00'))


def make_relative(payload):
    source, response = proposal(payload, ('yesterday afternoon', '2024-02-29', '2024-03-01', 'day', 'day',
                                          'The original report of March 1 says yesterday; the action was on leap day.'))
    sid = source['samples'][0]['raw_data_id']
    source['user_query']['extras']['source_registry'][sid].update(
        published_at='2024-03-01T00:15:00-05:00', retrieved_at='2024-03-06')
    response['actions'][0]['time'].update(intraday='afternoon', anchor_source_id=sid)
    return source, response


def test_relative_publication_and_merge(payload):
    source, response = make_relative(payload)
    facts, report = Receiver(seed_facts(source), source, IdMap(), 'dayparts').extract(response)
    assert not report['rejected']
    assert check_graph(facts, source)['valid']
    action = facts['actions'][0]
    assert SupportIndex(facts, source).action_window(action['action_id']).intraday == 'afternoon'
    for role in ('consolidation', 'organization', 'relations'):
        assert navigation(facts, role=role)['actions'][0]['time']['intraday'] == 'afternoon'
    replacement = deepcopy(action)
    replacement['time'].pop('intraday')
    with pytest.raises(ValueError, match='/time/intraday'):
        preserve_known_fields([action], replacement, {'evidence_ids': []}, facts)


@pytest.mark.parametrize('mistake', ['retrieval', 'other_source', 'attribution', 'wrong_day', 'duration', 'unanchored'])
def test_invalid_refinements_are_isolated(payload, mistake):
    source, response = make_relative(payload)
    action = response['actions'][0]
    if mistake == 'retrieval':
        source['user_query']['extras']['source_registry'][action['time']['anchor_source_id']]['published_at'] = None
    elif mistake == 'other_source':
        action['time']['anchor_source_id'] = 'not-the-quoted-source'
    elif mistake == 'attribution':
        action['support'][-1]['mode'] = 'A'
    elif mistake == 'wrong_day':
        action['time'].update(start='2024-03-01', end='2024-03-02')
    elif mistake == 'duration':
        action['time']['kind'] = 'duration'
    else:
        content = 'The original interview reports an earlier pledge without dating it.'
        source['samples'][0]['content'] = response['evidence'][0]['quote'] = content
    facts, report = Receiver(seed_facts(source), source, IdMap(), 'dayparts').extract(response)
    assert report['rejected'] and not facts['actions']
    assert facts['evidence'][0]['location_status'] == 'matched'


def temporal_graph(graph):
    template = deepcopy(graph['actions'][0])
    graph['relations'] = []
    graph['actions'] = []
    eid = graph['evidence'][0]['evidence_id']
    for aid, part in [('L', 'evening'), ('U', None), ('M', 'morning'), ('X', None)]:
        time = (dict(kind='occurrence_window', text=part, intraday=part, start=str(DAY),
                     end='2024-03-02', start_precision='day', end_precision='day')
                if part else unknown_time())
        graph['actions'].append(dict(template, action_id=aid, time=time, gaps=[], conflicts=[],
                                     support=[dict(target='/time', mode='A', evidence_ids=[eid])]))
    return graph


def link(graph, a, kind, b):
    rid = f'{a}:{kind}:{b}'
    relation = dict(relation_id=rid, from_action_id=a, to_action_id=b, type=kind, basis='asserted',
                    support=[dict(target='', mode='A', evidence_ids=[graph['evidence'][0]['evidence_id']])])
    graph['relations'].append(relation)
    return relation


def test_topology_projection_ignores_semantic_arrows(graph):
    temporal_graph(graph)
    link(graph, 'L', 'responds_to', 'M')
    link(graph, 'X', 'enables', 'M')
    link(graph, 'M', 'precedes', 'U')
    link(graph, 'U', 'precedes', 'L')  # U may belong to another Phase
    before = deepcopy(graph)
    ordered, info, groups = ActionChronology(graph).page(['L', 'X', 'M'])
    assert ordered == ['M', 'L', 'X'] and info['L']['earlier'] == ['M']
    assert groups[-1] == dict(kind='unplaced', actions=['X'])
    assert graph == before
    relation = link(graph, 'M', 'precedes', 'L')
    relation.update(basis='derived', support=[dict(target='', mode='I', evidence_ids=[], reason='Same local day.',
        premise_refs=[dict(collection='actions', object_id=aid, field='/time') for aid in ('M','L')])])
    assert SupportIndex(graph).derived(relation)
    graph['actions'][2]['gaps'].append(dict(target='/time/intraday', reason='Which part is disputed.'))
    assert not SupportIndex(graph).derived(relation)


def test_cycle_including_undated_action_preserves_claims(graph):
    temporal_graph(graph)
    one = link(graph, 'L', 'precedes', 'U')
    two = link(graph, 'U', 'precedes', 'M')
    before = deepcopy(graph)
    order = order_view(graph)
    assert not order['relation_ids']
    assert sorted(order['conflicts'][0]['relation_ids']) == sorted([one['relation_id'], two['relation_id']])
    assert all(item['conflict'] for item in ActionChronology(graph).page(['U', 'M', 'L'])[1].values())
    assert graph == before


def test_old_quote_bound_to_action_time(payload):
    source, response = make_relative(payload)
    response['actions'][0]['time'].pop('intraday')
    result, report = Receiver(seed_facts(source), source, IdMap(), 'old').extract(response)
    assert not report['rejected']
    a = result['actions'][0]
    assert not SupportIndex(result, source).action_window(a['action_id']).intraday
    assert SupportIndex(result, source).action_window(a['action_id'], legacy=True).intraday == 'afternoon'
    a['time']['text'] = 'morning'
    a['time'].pop('anchor_source_id')
    assert not SupportIndex(result, source).action_window(a['action_id'], legacy=True).intraday
    assert quoted_daypart('before that afternoon') is None
    assert quoted_daypart('上午或下午') is None
    assert quoted_daypart('Published yesterday evening') is None

def test_only_verified_precedence_can_project_through_another_phase(graph):
    temporal_graph(graph)
    for a in graph['actions']:
        a['time'] = unknown_time()
    link(graph, 'M', 'precedes', 'U')
    link(graph, 'U', 'precedes', 'L')
    ordered, info, _ = ActionChronology(graph).page(['L', 'M'])
    assert ordered == ['M', 'L'] and info['M']['later'] == ['L']
    graph['relations'][1]['basis'] = 'inferred'
    ordered, info, _ = ActionChronology(graph).page(['L', 'M'])
    assert not info['M']['later'] and info['M']['unordered'] == ['L']


def test_explicit_unknown_order_and_known_part_disagree(graph):
    temporal_graph(graph)
    link(graph, 'M', 'order_unknown', 'L')
    _, info, rail = ActionChronology(graph).page(['M', 'L'])
    assert all(item['conflict'] for item in info.values())
    assert rail == [dict(kind='disputed', actions=['M', 'L'])]


def test_earlier_interview_uses_its_own_date(payload):
    source, response = make_relative(payload)
    a = response['actions'][0]
    a['time'].pop('anchor_source_id')
    a['time'].update(start='2022-09-08', end='2022-09-09')
    a['support'][-1]['reason'] = 'The quoted interview is dated 9 September 2022; yesterday is September 8.'
    content = 'In the interview of 9 September 2022, Mina said: “I announced my pledge yesterday afternoon.”'
    source['samples'][0]['content'] = response['evidence'][0]['quote'] = content
    facts, report = Receiver(seed_facts(source), source, IdMap(), 'interview').extract(response)
    assert not report['rejected'] and facts['actions'][0]['time']['start'] == '2022-09-08'
    a['time']['anchor_source_id'] = source['samples'][0]['raw_data_id']
    _, report = Receiver(seed_facts(source), source, IdMap(), 'wrong-anchor').extract(response)
    assert report['rejected']


def test_native_view_keeps_source_graph_and_groups_open_order(graph):
    temporal_graph(graph)
    link(graph, 'L', 'responds_to', 'M')
    graph['actions'][3]['time'] = deepcopy(graph['actions'][2]['time'])
    page_id = graph['actions'][0]['phase_id']
    html = render_graph_html(graph)
    assert embedded_data(html, 'epg-data') == graph
    page = next(p for p in embedded_data(html, 'epg-view')['pages'] if p['phase'] == page_id)
    group = next(s for s in page['sections'] if s['title'] == 'Action chronology')
    assert [t['label'] for t in group['ticks']] == ['2024-03-01 · morning', '2024-03-01 · evening']
    cards = {c['id']: c for c in page['cards'] if c['kind'] == 'action'}
    assert cards['M']['box'][0] < cards['L']['box'][0]
    assert cards['M']['box'][1] == cards['L']['box'][1] < group['box'][1]
    assert cards['X']['box'][0] == cards['M']['box'][0] and cards['X']['box'][1] > cards['M']['box'][1]
    cell = cards['U']['chronology']['placement']
    assert cell['band'] == 'phase' and cell['note'] == 'Phase only' and cell['mark'] == 'scope'
    assert cards['U']['box'][1] < cards['M']['box'][1] < cards['X']['box'][1] < group['box'][1]
    assert all(s['title'] != 'Timing unresolved' for s in page['sections'])
    assert cards['M']['chronology']['unordered'] == ['U', 'X']
    assert any(e['from'] == 'L' and e['to'] == 'M' and e['type'] == 'responds_to' for e in page['edges'])


def lane_view(graph):
    pages = embedded_data(render_graph_html(graph), 'epg-view')['pages']
    page = next(p for p in pages if p['phase'] == graph['actions'][0]['phase_id'])
    return {c['id']: c['chronology']['placement'] for c in page['cards'] if c['kind'] == 'action'}


def test_relative_diamond_and_independent_chain_have_separate_lanes(graph):
    temporal_graph(graph)
    for a in graph['actions']:
        a['time'] = unknown_time()
    graph['actions'].extend(dict(graph['actions'][0], action_id=a) for a in ['Y', 'Z'])
    for a, b in [('M', 'L'), ('M', 'U'), ('L', 'X'), ('U', 'X'), ('Y', 'Z')]:
        link(graph, a, 'precedes', b)
    cells = lane_view(graph)
    assert [cells[a]['column'] for a in ['M', 'U', 'L', 'X']] == [0, 1, 1, 2]
    assert cells['M']['row'] == cells['L']['row'] == cells['X']['row'] != cells['U']['row']
    assert cells['Y']['row'] == cells['Z']['row'] and cells['Y']['row'] > cells['U']['row']
    assert {c['band'] for c in cells.values()} == {'relative'}


def test_intersecting_ranges_keep_their_endpoints_and_kind(graph):
    temporal_graph(graph)
    for a, (lo, hi, kind) in zip(graph['actions'], [(0, 5, 'occurrence_window'), (3, 9, 'duration'),
                                                      (6, 12, 'duration'), (0, 5, 'occurrence_window')]):
        a['time'] = dict(kind=kind, text='March', start=str(DAY + timedelta(days=lo)),
                         end=str(DAY + timedelta(days=hi)), start_precision='day', end_precision='day')
    cells = lane_view(graph)
    a, b, c, other = [cells[key] for key in ['L', 'U', 'M', 'X']]
    assert a['first'] < b['first'] <= a['last'] < c['first'] <= b['last'] < c['last']
    assert b['row'] != c['row'] and a['row'] != b['row'] and a['row'] != other['row']
    assert (a['mark'], b['mark'], c['mark']) == ('window', 'duration', 'duration')
    assert (a['first'], a['last']) == (other['first'], other['last'])


def test_lone_remote_bound_stays_out_of_local_date_order(graph):
    temporal_graph(graph)
    p2 = 'OFFPAGE'
    graph['phases'].append(dict(phase_id=p2, name='Later phase'))
    graph['actions'][0]['phase_id'] = p2
    link(graph, 'U', 'precedes', 'L')  # U precedes the remote evening, with no order against local morning.
    page = embedded_data(render_graph_html(graph), 'epg-view')['pages'][1]
    placements = {c['id']: c['chronology'] for c in page['cards'] if c['kind'] == 'action'}
    assert placements['U']['placement']['band'] == 'phase'
    assert placements['U']['placement']['note'] == 'Before A01' and not placements['U']['label']
    assert placements['U']['anchor_after'] == ['L']
    assert placements['M']['placement']['band'] == 'calendar'


@pytest.mark.parametrize('side,value,precision,label', [
    ('end', '2024-03-01', 'day', 'By 29 Feb 2024'), ('end', '2024-04-01', 'month', 'By Mar 2024'),
    ('start', '2024-01-01', 'year', 'From 2024')])
def test_equal_single_limits_are_adjacent_and_do_not_determine_order(graph, side, value, precision, label):
    temporal_graph(graph)
    graph['actions'] = graph['actions'][:2]
    for a in graph['actions']:
        a['time'] = dict(unknown_time(), kind='occurrence_window', **{side:value, side+'_precision':precision})
    graph['actions'][0]['delta_context_refs'] = [dict(context_id='C', relation_type='result')]
    graph['actions'][1]['delta_context_refs'] = [dict(context_id='C', relation_type='condition')]
    graph['contexts'].append(dict(context_id='C', description='One context, two uses.'))
    page = embedded_data(render_graph_html(graph), 'epg-view')['pages'][1]
    cards = {c['id']: c for c in page['cards']}
    first, second = cards['L'], cards['U']
    assert first['date'] == second['date'] == label
    assert first['box'][0] == second['box'][0] and second['box'][1] > first['box'][1]
    assert first['chronology']['placement']['row'] + 1 == second['chronology']['placement']['row']
    assert not first['chronology']['earlier'] and not first['chronology']['later']
    assert first['chronology']['placement']['mark'] == ('upper' if side == 'end' else 'lower')
    assert cards['C']['box'][1] < first['box'][1]
    assert {('L','C','result'), ('C','U','condition')} <= {(e['from'],e['to'],e['type']) for e in page['edges']}
    assert [t['label'] for s in page['sections'] for t in s.get('ticks', [])] == [label]

    graph['actions'][0]['support'] = []
    cells = lane_view(graph)
    assert cells['L']['note'] == 'Phase only' and cells['U']['mark'] in ('lower', 'upper')


@pytest.mark.parametrize('side', ['start', 'end'])
def test_crowded_limit_shares_a_bracket_and_keeps_the_date_and_each_action(graph, side):
    temporal_graph(graph)
    day = dict(kind='occurrence_window', text='March 1', start=str(DAY), end='2024-03-02',
               start_precision='day', end_precision='day')
    bound = dict(unknown_time(), kind='occurrence_window', **{side:day[side], side+'_precision':'day'})
    for action in graph['actions']:
        action['time'] = day if action['action_id'] == 'X' else bound.copy()
    before = deepcopy(graph)
    page = embedded_data(render_graph_html(graph), 'epg-view')['pages'][1]
    cards = {c['id']: c for c in page['cards'] if c['kind'] == 'action'}
    cells = {a: c['chronology']['placement'] for a, c in cards.items()}
    group = [cells[a] for a in ('L', 'U', 'M')]
    assert cells['L']['mark_members'] == ['L', 'U'] and cells['U']['mark_members'] == []
    assert cells['M']['mark_members'] == ['M']
    assert cells['L']['row'] == cells['U']['row'] != cells['M']['row']
    assert len({p['column'] for p in group}) == 1
    assert len({p['row'] for p in cells.values()}) == 2
    xs = [cards[a]['box'][0] for a in ('L', 'U', 'M')]
    tick, = next(s['ticks'] for s in page['sections'] if s['title'] == 'Action chronology')
    closed = 'first' if side == 'start' else 'last'
    assert all(p[closed] == tick['column'] == cells['X']['column'] for p in group)
    if side == 'start':
        assert min(xs) > cards['X']['box'][0]
    else:
        assert max(xs) < cards['X']['box'][0]
    assert all(not c['chronology']['earlier'] and not c['chronology']['later'] for c in cards.values())
    assert len(group) == len(set(xs)) and graph == before
    link(graph, 'U', 'precedes', 'L')
    cells = lane_view(graph)
    assert cells['U']['column'] < cells['L']['column']
    assert all(not {'U', 'L'} <= set(c.get('mark_members', [])) for c in cells.values())


def test_phase_only_actions_share_rows_around_focal_actor_without_borrowing_dates(graph):
    temporal_graph(graph)
    graph['actions'].extend(dict(graph['actions'][0], action_id=aid) for aid in ('Y', 'Z', 'W'))
    for action in graph['actions']:
        action['time'] = unknown_time()
    page = embedded_data(render_graph_html(graph), 'epg-view')['pages'][1]
    actions = [c for c in page['cards'] if c['kind'] == 'action']
    cells = [c['chronology']['placement'] for c in actions]
    tops = {c['box'][1] for c in actions}
    focal = next(c for c in page['cards'] if c.get('caption') == 'Focal person')
    assert len(actions) == 7 and len(tops) == 4
    assert focal['box'][1] + 28 == (min(tops) + max(tops) + 90) / 2
    assert all(c['note'] == 'Phase only' and c['mark'] == 'scope' for c in cells)
    assert all(not c['date'] and not c['chronology']['earlier'] and not c['chronology']['later'] for c in actions)
    axis = next(s for s in page['sections'] if s['title'] == 'Action chronology')
    assert axis['ticks'] == [] and axis['box'][1] > max(tops) + 90


def test_action_with_conflicting_bound_or_without_phase_cannot_acquire_date(graph):
    temporal_graph(graph)
    a = graph['actions'][1]
    a['time'] = dict(unknown_time(), kind='occurrence_window', end='2024-02-01', end_precision='day')
    link(graph, 'M', 'precedes', 'U')  # March 1 cannot precede an act completed by the end of January.
    assert lane_view(graph)['U']['band'] == 'disputed'
    graph['actions'][3].pop('phase_id')
    pages = embedded_data(render_graph_html(graph), 'epg-view')['pages']
    unassigned = next(c for c in pages[0]['cards'] if c['id'] == 'X')
    assert unassigned['chronology']['placement']['note'] == 'Date unknown'
    assert unassigned['chronology']['placement']['mark'] is None


def test_limit_cards_flank_the_boundary_day_without_adding_precedence(graph):
    temporal_graph(graph)
    full_day = dict(kind='occurrence_window', text='March 1', start='2024-03-01', end='2024-03-02',
                    start_precision='day', end_precision='day')
    graph['actions'][1]['time'] = dict(unknown_time(), kind='occurrence_window', end='2024-03-02', end_precision='day')
    graph['actions'][3]['time'] = dict(unknown_time(), kind='occurrence_window', start='2024-03-01', start_precision='day')
    graph['actions'].append(dict(graph['actions'][0], action_id='D', time=full_day))
    before = deepcopy(graph)
    view = embedded_data(render_graph_html(graph), 'epg-view')['pages'][1]
    acts = {c['id']: c['chronology'] for c in view['cards'] if c['kind'] == 'action'}
    cols = {a: c['placement']['column'] for a, c in acts.items()}
    assert cols['U'] < cols['M'] < cols['D'] < cols['L'] < cols['X']
    ticks = next(s['ticks'] for s in view['sections'] if s['title'] == 'Action chronology')
    assert [t['column'] for t in ticks] == [cols['M'], cols['L']]
    assert acts['U']['placement']['last'] == cols['L']
    assert acts['X']['placement']['first'] == cols['M']
    assert all('D' in acts[a]['unordered'] for a in ('U', 'X'))
    assert not any(e['kind'] == 'relation' for e in view['edges'])
    assert graph == before


@pytest.mark.parametrize('side, first, second', [('end', 'M', 'U'), ('start', 'U', 'M')])
def test_known_sequence_within_boundary_day_overrides_default_flank(graph, side, first, second):
    temporal_graph(graph)
    graph['actions'] = [a for a in graph['actions'] if a['action_id'] in ('U', 'M')]
    limit = next(a for a in graph['actions'] if a['action_id'] == 'U')
    limit['time'] = dict(unknown_time(), kind='occurrence_window',
                         **{side: '2024-03-01' if side == 'start' else '2024-03-02', side+'_precision': 'day'})
    link(graph, first, 'precedes', second)
    cells = lane_view(graph)
    assert cells[first]['column'] < cells[second]['column']
    assert cells['U']['mark'] == ('lower' if side == 'start' else 'upper')


def test_mixed_context_uses_only_an_existing_gap(graph):
    temporal_graph(graph)
    graph['actions'] = [a for a in graph['actions'] if a['action_id'] != 'U']
    actions = {a['action_id']: a for a in graph['actions']}
    for a in actions.values():
        a['delta_context_refs'] = []
    # A wide window needs a different bracket row. The middle date on the
    # narrower Actions' row remains free for the dual-use Context.
    for aid, lo, hi in [('M', 0, 1), ('X', 0, 3), ('L', 2, 3)]:
        actions[aid]['time'] = dict(unknown_time(), kind='occurrence_window', start=str(DAY + timedelta(days=lo)),
                                    end=str(DAY + timedelta(days=hi)), start_precision='day', end_precision='day')
    graph['contexts'].append(dict(context_id='C', description='Consequence and subsequent condition.'))
    def snapshot():
        page = embedded_data(render_graph_html(graph), 'epg-view')['pages'][1]
        return page, {c['id']: c for c in page['cards']}
    _, initial = snapshot()
    actions['M']['delta_context_refs'] = [dict(context_id='C', relation_type='result')]
    actions['L']['delta_context_refs'] = [dict(context_id='C', relation_type='condition')]
    page, cards = snapshot()
    assert cards['M']['box'][0] < cards['C']['box'][0] < cards['L']['box'][0]
    assert cards['M']['box'][1] == cards['C']['box'][1] == cards['L']['box'][1]
    assert all(cards[a]['chronology']['placement'] == initial[a]['chronology']['placement'] for a in actions)
    assert sum(c['id'] == 'C' for c in page['cards']) == 1
    assert {('M','C','result'), ('C','L','condition')} <= {(e['from'],e['to'],e['type']) for e in page['edges']}
    actions['X']['time'] = unknown_time()  # The intervening column disappears.
    _, cards = snapshot()
    assert cards['C']['box'][1] < min(cards[a]['box'][1] for a in actions)


def test_duration_needs_its_own_or_whole_time_support_before_overlap_is_derived(graph):
    temporal_graph(graph)
    a, b = graph['actions'][:2]
    source = graph['evidence'][0]['evidence_id']
    for item in (a, b):
        item['time'] = dict(text='March 1–5', kind='duration', start=str(DAY), end='2024-03-06',
                            start_precision='day', end_precision='day')
    a['support'] = [dict(target='/time/' + side, mode='A', evidence_ids=[source]) for side in ('start', 'end')]
    r = link(graph, 'L', 'overlaps', 'U')
    r.update(basis='derived', support=[dict(target='/type', mode='I', evidence_ids=[], reason='Intervals overlap.',
        premise_refs=[dict(collection='actions', object_id=i, field='/time') for i in ('L','U')])])
    cell = lane_view(graph)['L']
    assert (cell['mark'], cell['note']) == ('window', 'Duration unverified')
    assert not SupportIndex(graph).derived(r)
    a['support'].append(dict(target='/time/kind', mode='A', evidence_ids=[source]))
    assert lane_view(graph)['L']['mark'] == 'duration' and SupportIndex(graph).derived(r)
    changed = deepcopy(a)
    changed['time']['kind'] = 'occurrence_window'
    with pytest.raises(ValueError, match='/time/kind'):
        preserve_known_fields([a], changed, {'evidence_ids': []}, graph)


def test_unverified_arrow_and_identical_clock_minute_cannot_order_cards(graph):
    temporal_graph(graph)
    for a in graph['actions']:
        a['time'] = dict(text='09:30 UTC', kind='occurrence_window', intraday='09:30', utc_offset='Z',
                         start=str(DAY), end=str(DAY + timedelta(days=1)), start_precision='day', end_precision='day')
    rel = link(graph, 'L', 'precedes', 'U')
    rel['support'] = []
    cells = lane_view(graph)
    assert len({c['column'] for c in cells.values()}) == 1
    assert len({c['row'] for c in cells.values()}) == len(cells)
    assert {c['note'] for c in cells.values()} == {'Order within group unresolved'}


def test_relative_actions_flank_their_dated_anchor_without_borrowing_its_date(graph):
    temporal_graph(graph)
    graph['actions'][0]['time'] = unknown_time()
    link(graph, 'L', 'precedes', 'M')
    link(graph, 'M', 'precedes', 'U')
    page = embedded_data(render_graph_html(graph), 'epg-view')['pages'][1]
    cards = {c['id']: c for c in page['cards'] if c['kind'] == 'action'}
    cols = {a: c['chronology']['placement']['column'] for a, c in cards.items()}
    ticks = next(s['ticks'] for s in page['sections'] if s['title'] == 'Action chronology')
    assert cols['L'] < ticks[0]['column'] == cols['M'] < cols['U']
    assert not cards['L']['date'] and not cards['U']['date']
    assert cards['M']['chronology']['order_steps'] == ['L:precedes:M', 'M:precedes:U']
    assert not cards['M']['chronology']['by_time']


def test_dated_precedence_never_reverses_civil_clock_offsets(graph):
    temporal_graph(graph)
    for a, value, offset, day in zip(graph['actions'][:2], ['23:30', '01:30'], ['-04:00', 'Z'],
                                      [DAY - timedelta(days=1), DAY]):
        a['time'] = dict(text=value, kind='occurrence_window', intraday=value, utc_offset=offset, start=str(day),
                         end=str(day + timedelta(days=1)), start_precision='day', end_precision='day')
    graph['actions'] = graph['actions'][:2]
    cells = lane_view(graph)
    assert cells['U']['column'] < cells['L']['column'] and cells['U']['row'] == cells['L']['row']


def test_incomparable_source_clocks_share_no_borrowed_time_of_day(graph):
    temporal_graph(graph)
    graph['actions'] = graph['actions'][:2]
    for action, clock in zip(graph['actions'], ['10:30', '11:30']):
        action['time'] = dict(text=clock, kind='occurrence_window', intraday=clock,
                              start=str(DAY), end='2024-03-02', start_precision='day', end_precision='day')
    graph['actions'][0]['time']['utc_offset'] = 'Z'
    page = embedded_data(render_graph_html(graph), 'epg-view')['pages'][1]
    cells = [c['chronology']['placement'] for c in page['cards'] if c['kind'] == 'action']
    ticks = next(s['ticks'] for s in page['sections'] if s['title'] == 'Action chronology')
    assert ticks == [dict(column=0, label='2024-03-01 · See individual action times')]
    assert cells[0]['column'] == cells[1]['column'] and cells[0]['row'] != cells[1]['row']


def test_remote_bounds_have_room_for_both_ticks_on_the_local_axis(graph):
    temporal_graph(graph)
    graph['phases'].append(dict(phase_id='OFFPAGE', name='Other phase'))
    for action in graph['actions']:
        if action['action_id'] in ('M', 'L'):
            action['phase_id'] = 'OFFPAGE'
    link(graph, 'M', 'precedes', 'U')
    link(graph, 'U', 'precedes', 'L')
    page = embedded_data(render_graph_html(graph), 'epg-view')['pages'][1]
    ticks = next(s['ticks'] for s in page['sections'] if s['title'] == 'Action chronology')
    body = next(s for s in page['sections'] if s['title'] == 'Actions and their context')
    u = next(c for c in page['cards'] if c['id'] == 'U')
    assert ticks[0]['column'] < u['chronology']['placement']['column'] < ticks[1]['column'] < body['columns']
    assert not u['date'] and u['chronology']['anchor_before'] == ['M'] and u['chronology']['anchor_after'] == ['L']


def test_single_action_keeps_a_visible_warning_for_cross_phase_order_conflict(graph):
    temporal_graph(graph)
    graph['phases'].append(dict(phase_id='OFFPAGE', name='Other phase'))
    graph['actions'] = [a for a in graph['actions'] if a['action_id'] in ('L', 'M')]
    graph['actions'][0]['phase_id'] = 'OFFPAGE'
    link(graph, 'L', 'precedes', 'M')  # Evening before the same morning.
    pages = embedded_data(render_graph_html(graph), 'epg-view')['pages']
    for page in [p for p in pages if any(c['kind'] == 'action' for c in p['cards'])]:
        assert any(s['title'] == 'Order disputed' for s in page['sections'])


def test_relative_day_without_publication_anchor_still_requires_inference(payload):
    source, response = make_relative(payload)
    a = response['actions'][0]
    a['time'].pop('anchor_source_id')
    a['support'][-1]['mode'] = 'A'
    facts, report = Receiver(seed_facts(source), source, IdMap(), 'unmarked').extract(response)
    assert report['rejected'] and not facts['actions']


def test_legacy_qualifier_requires_agreement_across_time_quotes(payload):
    source, response = make_relative(payload)
    a = response['actions'][0]
    a['time'].pop('intraday')
    a['time'].pop('anchor_source_id')
    sample = source['samples'][0]
    more = 'The speaker instead placed the pledge in the morning.'
    sample['content'] += ' ' + more
    response['evidence'].append(dict(evidence_id='other', sample_id=sample['sample_id'], quote=more))
    a['support'][-1]['evidence_ids'].append('other')
    result, report = Receiver(seed_facts(source), source, IdMap(), 'legacy-disagreement').extract(response)
    assert not report['rejected']
    action = result['actions'][0]
    assert not SupportIndex(result, source).action_window(action['action_id'], legacy=True).intraday
