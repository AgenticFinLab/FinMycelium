"""Offline protocol examples; these do not measure a model's calendar accuracy."""
from copy import deepcopy
import json
import socket

import pytest

from test_person_event_contract import graph, payload
from test_person_event_consolidation import duplicate
from test_person_event_pipeline import SyntheticEventModel
from finmy.person_epg.event.build import Construction, run_event
from finmy.person_epg.event.proposals import Receiver
from finmy.person_epg.event.records import IdMap, seed_facts
from finmy.person_epg.event.runtime import EventBuildConfig, Execution
from finmy.person_epg.event.validation import check_graph


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('Network prohibited'))


CASES = [
    ('calendar Q3 2022', '2022-07-01', '2022-10-01', 'month', 'month',
     'The stated calendar quarter spans July through September; exclusive end is October 1.'),
    ('2024年2月下旬 (Gregorian calendar)', '2024-02-21', '2024-03-01', 'day', 'day',
     '下旬 spans day 21 through month end. February 2024 has 29 days; March 1 is the exclusive bound, not the occurrence date.'),
    ('2022年12月下旬 (Gregorian calendar)', '2022-12-21', '2023-01-01', 'day', 'day',
     'The last third of December ends on December 31; the half-open window crosses the year boundary.'),
    ('Christmas Day 2022 under the Gregorian convention', '2022-12-25', '2022-12-26', 'day', 'day',
     'The established named day is December 25; its half-open window ends on December 26.'),
    ('Old Style Christmas 1900, explicitly equated in this synthetic record with January 7, 1901 Gregorian',
     '1901-01-07', '1901-01-08', 'day', 'day',
     'Use the conversion explicitly supplied by this synthetic source, retaining its original Old Style year; do not force Gregorian bounds into 1900.'),
    ('during Gregorian year 2022, in winter; the seasonal convention is unspecified',
     '2022-01-01', '2023-01-01', 'year', 'year',
     'The occurrence year is explicit; retain it without inventing seasonal boundaries or an occurrence day.'),
    ('by March 2020', None, '2020-04-01', 'unknown', 'month',
     'The wording supplies a latest month bound, not a start or proof of occurrence within March.'),
    ('Q3 of fiscal year 2022; the fiscal calendar is unspecified', None, None, 'unknown', 'unknown',
     'The fiscal year label does not establish Gregorian bounds without its calendar convention.'),
    ('Christmas Day in the Old Style calendar; no year is supplied', None, None, 'unknown', 'unknown',
     'The source gives no year anchor; preserve its expression without guessing Gregorian bounds.'),
]


def proposal(payload, case):
    phrase, start, end, start_precision, end_precision, reason = case
    payload = deepcopy(payload)
    payload['user_query']['query_text'] = 'Reconstruct the documented public pledge.'
    identity = payload['user_query']['extras']['person_event']
    identity['scope'] = dict(period='As documented', include='The public pledge', exclude='Other acts')
    sample = deepcopy(payload['samples'][0])
    sample['content'] = f'Mina Lee, acting in her personal capacity, announced a public pledge {phrase}.'
    payload['samples'] = [sample]
    time = dict(text=phrase, kind='occurrence_window' if start or end else 'unknown',
                start=start, end=end, start_precision=start_precision, end_precision=end_precision)
    action = dict(action_id='pledge', name='Announce a public pledge',
                  description='Mina Lee announced a public pledge.',
                  actor=dict(entity_id=identity['person_id'], capacity='personal'),
                  object=dict(description='A public pledge', entity_refs=[]), time=time, phase_id=None,
                  support=[dict(target=target, mode='A', evidence_ids=['quote'])
                           for target in ('/description', '/actor', '/object')], gaps=[])
    if start is not None and end is not None:
        action['support'].append(dict(target='/time', mode='I', evidence_ids=['quote'], reason=reason))
    else:
        for side in ('start', 'end'):
            if time[side] is None:
                action['gaps'].append(dict(target='/time/' + side, reason=reason))
            else:
                action['support'].append(dict(target='/time/' + side, mode='I', evidence_ids=['quote'], reason=reason))
    response = dict(entities=[], actions=[action], contexts=[], relation_candidates=[], pending=[],
                    evidence=[dict(evidence_id='quote', sample_id=sample['sample_id'], quote=sample['content'])])
    return payload, response


@pytest.mark.parametrize('case', CASES, ids=[
    'calendar-quarter', 'leap-month-xun', 'xun-year-end', 'named-day',
    'source-supplied-calendar-conversion', 'known-year-unknown-season',
    'single-bound', 'unresolved-fiscal-quarter', 'missing-holiday-year',
])
def test_nonstandard_time_survives_native_adoption_with_provenance(payload, case):
    source, response = proposal(payload, case)
    expected = deepcopy(response['actions'][0])
    result, report = Receiver(seed_facts(source), source, IdMap(), 'temporal').extract(response)
    assert not report['rejected'], report
    assert check_graph(result, source)['valid']
    actual = result['actions'][0]
    assert actual['time'] == expected['time']
    assert actual['gaps'] == expected['gaps']
    inferred = [s for s in actual['support'] if s['target'].startswith('/time')]
    assert all(s['mode'] == 'I' and s['reason'] == case[-1] for s in inferred)
    assert bool(inferred) == (case[1] is not None or case[2] is not None)
    evidence = result['evidence'][0]
    citation = evidence['citations'][0]
    assert citation['location_status'] == 'matched'
    assert source['samples'][0]['content'][citation['start']:citation['end']] == citation['quote']
    assert case[0] in citation['quote']  # Native-calendar wording is not replaced by a derived quote.
    assert all(s['evidence_ids'] == [evidence['evidence_id']] for s in inferred)


@pytest.mark.parametrize('mistake', ['missing_reason', 'missing_evidence', 'legacy_window', 'equal_day_bounds'])
def test_normalization_keeps_existing_support_and_interval_guards(payload, mistake):
    source, response = proposal(payload, CASES[3])
    action = response['actions'][0]
    time_support = action['support'][-1]
    if mistake == 'missing_reason':
        del time_support['reason']
    elif mistake == 'missing_evidence':
        time_support['evidence_ids'] = []
    elif mistake == 'legacy_window':
        action['time']['time_window'] = dict(start='2022-12-25', end='2022-12-25', approximate=False)
    else:
        action['time']['end'] = action['time']['start']
    result, report = Receiver(seed_facts(source), source, IdMap(), 'invalid-time').extract(response)
    assert report['rejected']
    assert not result['actions']
    assert result['evidence'][0]['citations'][0]['location_status'] == 'matched'  # Reject only the invalid proposal.


def assert_time_policy(system):
    assert 'Calendar normalization (all roles, within their existing write scope):' in system
    assert 'half-open [start,end)' in system
    assert 'mode I targeting /time' in system


def test_time_policy_reaches_native_flow_without_an_extra_call(tmp_path, payload):
    model = SyntheticEventModel()
    systems = {}

    def capture(system, user, name):
        systems[json.loads(user)['task']['role']] = system
        return model(system, user, name)

    state = run_event(payload, tmp_path, model=capture)
    assert state['result_status'] == 'draft'
    assert set(systems) == {'extraction', 'organization', 'relations'}
    assert len(model.calls) == 5  # Existing fixture flow; no calendar-agent phase was added.
    for system in systems.values():
        assert_time_policy(system)
    result = json.loads((tmp_path / state['output']).read_text())
    assert result['schema_version'] == 'person-event-2.0'
    assert check_graph(result, payload)['valid']


def test_time_policy_reaches_consolidation_when_needed(tmp_path, graph, payload):
    facts, decision = duplicate(graph, payload)
    systems = []

    def model(system, user, name):
        systems.append(system)
        assert json.loads(user)['task']['role'] == 'consolidation'
        return dict(decisions=[deepcopy(decision)], evidence=[], pending=[])

    construction = Construction(Execution(tmp_path, payload, EventBuildConfig(), model))
    construction.facts = facts
    assigned = {('actions', ref['object_id']) for ref in decision['input_refs']}
    result, report = construction.receive('consolidate.0', 'consolidation', facts,
        construction.request('consolidation', facts, assigned=decision['input_refs']), assigned=assigned)
    assert not report['rejected'], report
    assert len(result['actions']) == len(facts['actions']) - 1
    assert len(systems) == 1
    assert_time_policy(systems[0])
