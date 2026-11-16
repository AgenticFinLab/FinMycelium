"""Consolidation protocol compatibility and provenance-based pending cleanup."""
from copy import deepcopy
import socket

import pytest

from test_person_event_contract import graph, payload, facts_from_graph
from finmy.person_epg.event.build import Construction
from finmy.person_epg.event.feedback import clear_resolved_pending
from finmy.person_epg.event.proposals import Receiver, reference, replace_references
from finmy.person_epg.event.records import IdMap, fingerprint
from finmy.person_epg.event.runtime import EventBuildConfig, Execution


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('Network prohibited'))


def duplicate(graph, payload):
    facts = facts_from_graph(graph, payload)
    first = facts['actions'][0]
    other = deepcopy(first)
    other['action_id'] = 'ACT-second-account'
    other['support'].append(dict(target='/description', mode='A', evidence_ids=[facts['evidence'][0]['evidence_id']]))
    facts['actions'].append(other)
    refs = [reference('actions', a['action_id']) for a in (first, other)]
    merged = deepcopy(first)
    merged['support'] += [s for s in other['support'] if s not in merged['support']]
    decision = dict(operation='merge', input_refs=refs,
        outputs=[dict(collection='actions', record=merged)],
        reason='The two records describe the same supported action.', evidence_ids=[])
    return facts, decision


def test_corrected_merge_clears_only_the_resolved_pending_after_id_remap(tmp_path, graph, payload):
    facts, decision = duplicate(graph, payload)
    original = deepcopy(decision)
    calls = []
    def model(system, user, name):
        calls.append(name)
        d = deepcopy(decision)
        if len(calls) == 1:
            d['outputs'][0]['record']['support'] = deepcopy(facts['actions'][0]['support'])
        else:
            d['decision_id'] = 'decision:0'
        return dict(decisions=[d], evidence=[], pending=[])
    construction = Construction(Execution(tmp_path, payload, EventBuildConfig(), model))
    construction.facts = facts
    assigned = {('actions', r['object_id']) for r in decision['input_refs']}
    result, report = construction.receive('consolidate.0', 'consolidation', facts,
        construction.request('consolidation', facts, assigned=decision['input_refs']), assigned=assigned)
    assert len(calls) == 2
    assert not report['rejected'] and not report['pending'] and not result['pending']
    assert len(result['actions']) == len(facts['actions']) - 1
    assert decision == original
    assert construction.reports[0]['report']['rejected'][0]['refs'] == original['input_refs']
    assert construction.reports[0]['resolutions']
    assert result['lineage'][-1]['input_refs'] == original['input_refs']


@pytest.mark.parametrize('extra', [dict(decision_id=''), dict(decision_id=1), dict(decision_id={'override': True}),
                                  dict(decision_id='label', overwrite_all=True)])
def test_metadata_does_not_relax_contract_or_break_independent_neighbors(graph, payload, extra):
    facts, decision = duplicate(graph, payload)
    decision.update(extra)
    neighbor = reference('actions', facts['actions'][1]['action_id'])
    keep = dict(operation='keep', input_refs=[neighbor], outputs=[], reason='Independent supported act.', evidence_ids=[])
    assigned = {('actions', r['object_id']) for r in [*decision['input_refs'], neighbor]}
    result, report = Receiver(facts, payload, IdMap(), 'contract').consolidate(
        dict(decisions=[decision, keep], evidence=[], pending=[]), assigned)
    assert report['rejected']
    assert any(i['refs'] == [neighbor] for i in report['accepted_items'])
    assert result['actions'] == facts['actions']


def test_label_does_not_bypass_support_or_scope(graph, payload):
    facts, decision = duplicate(graph, payload)
    decision['decision_id'] = 'decision:0'
    decision['outputs'][0]['record']['support'] = deepcopy(facts['actions'][0]['support'])
    assigned = {('actions', r['object_id']) for r in decision['input_refs']}
    _, report = Receiver(facts, payload, IdMap(), 'support').consolidate(
        dict(decisions=[decision], evidence=[], pending=[]), assigned)
    assert any('preserve prior support' in i['reason'] for i in report['rejected'])
    _, report = Receiver(facts, payload, IdMap(), 'scope').consolidate(
        dict(decisions=[decision], evidence=[], pending=[]), set())
    assert any('unassigned' in i['reason'] for i in report['rejected'])


@pytest.mark.parametrize('owner', ['none', 'model', 'unresolved'])
def test_pending_cleanup_follows_merge_chains_and_preserves_live_owners(owner):
    refs = [reference('actions', x) for x in ('A', 'B')]
    pending = dict(refs=refs, reason='Rejected operation', evidence_ids=[])
    issue = dict(item='decision:0', **pending)
    record = dict(task_id='consolidate.0', report=dict(rejected=[issue], pending=[deepcopy(pending)], reported_pending=[]),
                  resolutions=[dict(issue_fingerprint=fingerprint(issue), resolved_by='consolidate.0.correct.1')])
    records = [record]
    lineage = [dict(operation='merge', input_refs=[reference('actions', x) for x in inputs],
                    output_refs=[reference('actions', target)]) for inputs, target in [(('A', 'B'), 'A'), (('A', 'C'), 'C')]]
    mapped = replace_references(pending, {'actions': {'A': 'C', 'B': 'C'}})
    unrelated = dict(refs=[reference('actions', 'D')], reason='Rejected operation', evidence_ids=[])
    if owner != 'none':
        report = dict(pending=[deepcopy(mapped)], rejected=[], reported_pending=[])
        if owner == 'model': report['reported_pending'] = [deepcopy(mapped)]
        else: report['rejected'] = [dict(item='other', **mapped)]
        records.append(dict(task_id='another', report=report))
    original = deepcopy(records)
    package = dict(lineage=lineage, pending=[deepcopy(mapped), unrelated])
    removed = clear_resolved_pending(package, records, Construction.outstanding)
    assert records == original
    assert (removed == [mapped]) == (owner == 'none')
    assert package['pending'] == ([unrelated] if owner == 'none' else [mapped, unrelated])
    assert clear_resolved_pending(package, records, Construction.outstanding) == []


def test_scalar_conflict_pointer_is_normalized_with_provenance(graph, payload):
    facts, decision = duplicate(graph, payload)
    original = deepcopy(decision)
    eid = facts['evidence'][0]['evidence_id']
    conflict = dict(target='/description', reason='The source accounts disagree on the participants.', alternatives=[
        dict(value=text, support=[dict(target='/description', mode='A', evidence_ids=[eid])])
        for text in ('Account one.', 'Account two.')])
    decision['outputs'][0]['record']['conflicts'] = [conflict]
    response = dict(decisions=[decision], evidence=[], pending=[])
    before = deepcopy(response)
    assigned = {('actions', r['object_id']) for r in decision['input_refs']}
    result, report = Receiver(facts, payload, IdMap(), 'conflict').consolidate(response, assigned)
    assert not report['rejected'] and response == before
    retained = next(a for a in result['actions'] if a['action_id'] == original['outputs'][0]['record']['action_id'])
    alternatives = retained['conflicts'][0]['alternatives']
    assert [a['value'] for a in alternatives] == ['Account one.', 'Account two.']
    assert all(a['support'] == [dict(target='/value', mode='A', evidence_ids=[eid])] for a in alternatives)
    assert len(report['normalizations'][0]['changes']) == 2
    assert retained['conflicts'][0]['target'] == '/description'


@pytest.mark.parametrize('target,value,evidence', [('/unrelated', 'Claim', None),
    ('/description', {'nested': 'Claim'}, None), ('/description', 'Claim', 'MISSING')])
def test_normalization_does_not_guess_other_targets_or_accept_missing_evidence(graph, payload, target, value, evidence):
    facts, decision = duplicate(graph, payload)
    decision['outputs'][0]['record']['conflicts'] = [dict(target='/description', reason='Disagreement.', alternatives=[
        dict(value=value, support=[dict(target=target, mode='A', evidence_ids=[evidence or facts['evidence'][0]['evidence_id']])])])]
    assigned = {('actions', r['object_id']) for r in decision['input_refs']}
    _, report = Receiver(facts, payload, IdMap(), 'invalid-conflict').consolidate(
        dict(decisions=[decision], evidence=[], pending=[]), assigned)
    assert report['rejected'] and not report.get('normalizations')
