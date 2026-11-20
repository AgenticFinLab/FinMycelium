"""Offline decisions on rejected changes to the support of a retained fact."""
import re

from .corpus_supplement import TASK_ID as SUPPLEMENT
from .records import fingerprint, ground_quote, index_records, pointer
from .validation import SupportIndex


def _retained(graph, collection, oid, fact):
    if collection == 'relation_candidates':
        if not all(fact.get(k) for k in ('from_action_id', 'to_action_id', 'type')):
            return None
        matches = [r for r in graph['relations'].values()
                   if all(r[k] == fact[k] for k in ('from_action_id', 'to_action_id', 'type'))]
        return matches[0] if len(matches) == 1 else None
    return graph[collection].get(oid)


def _without_support(record):
    return {k: v for k, v in record.items() if k != 'support'}


def _candidate_proposal(issue, fact, collection, index):
    proposal = issue.get('proposal')
    if (not re.fullmatch(r'candidates:\d+', issue['item'])
            or issue['reason'] != 'Extraction cannot overwrite an existing candidate'
            or not isinstance(proposal, list) or len(proposal) != 1
            or not isinstance(proposal[0], dict) or proposal[0].get('collection') != collection):
        return None
    record = proposal[0].get('record')
    if not isinstance(record, dict) or _without_support(record) != _without_support(fact):
        return None
    supports = record.get('support', [])
    if not supports or not all(index.valid(s) for s in supports):
        return None
    return {'supports': supports}


def _supplement_proposal(issue, fact, retained, collection, oid, index):
    proposal = issue.get('proposal')
    if (not re.fullmatch(r'additional_support\.\d+', issue['item']) or not isinstance(proposal, dict)
            or proposal.get('collection') != collection or proposal.get('object_id') != oid
            or not issue.get('issues') or any(
                i.get('code') != 'SUPPORT_MODE_MIXED' or i.get('severity') != 'error'
                or i.get('object_type') != collection or i.get('object_id') != oid
                for i in issue['issues'])):
        return None
    opposite = {'O': 'A', 'A': 'O'}.get(proposal.get('mode'))
    target = proposal.get('target')
    if not opposite or not target or pointer(fact, target) is None or pointer(retained, target) != pointer(fact, target):
        return None
    if not any(s['target'] == target and s['mode'] == opposite and s in retained.get('support', []) and index.valid(s)
               for s in fact.get('support', [])):
        return None
    if proposal.get('sample_id') not in index.samples or not proposal.get('quote'):
        return None
    quote = ground_quote(proposal, index.samples, 'preview')
    if quote['location_status'] == 'matched':
        return {'target': proposal['target'], 'mode': proposal['mode'], 'quote': quote}


def support_groups(review, items):
    """Group retries by extraction range and exact object; each reported pending needs explicit acknowledgement."""
    if not items:
        return []
    facts = SupportIndex(review['facts'], review['payload'])
    graph = index_records(review['graph'])
    tasks = {t['task_id']: t for t in review['checks']['unresolved_tasks']}
    groups, corrections = {}, []
    for item in items:
        pending, tid = item['pending'], item['task_id']
        if item['eligible'] or tid is None or pending not in review['facts']['pending'] or len(pending['refs']) != 1:
            continue
        task = tasks[tid]
        ref = pending['refs'][0]
        collection, oid = ref['collection'], ref['object_id']
        if (task['role'] != 'extraction' or ref['field'] or
                collection not in ('actions', 'contexts', 'relation_candidates')):
            continue
        extract = re.fullmatch(r'(extract\.(\d+))(?:\.correct\.(\d+))?', tid)
        if tid != SUPPLEMENT:
            if not extract or not task.get('body_processed'):
                continue
            number = int(extract[2])
            coverage = review['state']['coverage']
            if number >= len(coverage) or coverage[number]['body_status'] != 'processed':
                continue
        fact = facts.records[collection].get(oid)
        if not fact or not any(facts.valid(s) for s in fact.get('support', [])):
            continue
        retained = _retained(graph, collection, oid, fact)
        if not retained or (collection != 'relation_candidates' and retained.get('description') != fact.get('description')):
            continue
        report = task['report']
        if report['pending'].count(pending) != 1:
            continue
        group_id = (extract[1] if extract else tid, collection, oid)
        if pending in report.get('reported_pending', []):
            if extract and extract[3] and not report['rejected'] and pending['evidence_ids']:
                corrections.append((group_id, item, int(extract[3])))
            continue
        matches = [i for i in report['rejected'] if all(i.get(k) == v for k, v in pending.items())]
        if len(matches) != 1:
            continue
        issue = matches[0]
        # Older rejection reports may contain malformed proposals. Keep those pending.
        try:
            if extract:
                change = _candidate_proposal(issue, fact, collection, facts)
            else:
                change = _supplement_proposal(issue, fact, retained, collection, oid, facts)
                group_id += (issue['item'],)
        except (ValueError, TypeError, KeyError, IndexError):
            continue
        if not change:
            continue
        group = groups.setdefault(group_id, dict(ref=ref, record=fact, retained=retained, retained_id=retained.get('relation_id', oid),
            kind='repeated_candidate' if extract else 'mixed_support', members=[], changes=[]))
        group['members'].append(dict(item=item, rejected=issue))
        if change not in group['changes']:
            group['changes'].append(change)

    for group_id, item, attempt in corrections:
        group = groups.get(group_id)
        if not group:
            continue
        # A correction can refer only to evidence in a preceding rejected proposal for the same object.
        preceding = [m['rejected']['proposal'][0]['record'] for m in group['members'] if 'rejected' in m and
                     int(m['item']['task_id'].partition('.correct.')[2] or 0) < attempt]
        refs = {eid for record in preceding for s in record['support'] for eid in s['evidence_ids']}
        if set(item['pending']['evidence_ids']) <= refs:
            group['members'].append(dict(item=item, reported=True))

    for group in groups.values():
        group['key'] = fingerprint({'outcome': 'decline_support_change',
            'members': [m['item']['key'] for m in group['members']]})
    return list(groups.values())


def decline_support(group, decision, checks, facts, step_id):
    """Apply the reviewer's explicit decisions to these receipts, preserving all facts and graph fields."""
    reported = sorted(m['item']['key'] for m in group['members'] if m.get('reported'))
    acknowledgements = decision.get('acknowledged_pending', [])
    if (not isinstance(acknowledgements, list) or not all(isinstance(key, str) for key in acknowledgements)
            or sorted(acknowledgements) != reported):
        raise ValueError('请逐条确认修正时报告的待处理说明；未核清的事项请继续保留')
    tasks = {t['task_id']: t['report'] for t in checks['unresolved_tasks']}
    records = []
    for member in group['members']:
        item = member['item']
        report = tasks[item['task_id']]
        report['pending'].remove(item['pending'])
        receipt = dict(task_id=item['task_id'], key=item['key'], pending=item['pending'],
                       model_reported=bool(member.get('reported')))
        if 'rejected' in member:
            report['rejected'].remove(member['rejected'])
            receipt['rejection_sha256'] = fingerprint(member['rejected'])
            receipt['proposal_item'] = member['rejected']['item']
        records.append(receipt)
    ref = group['ref']
    facts['lineage'].append(dict(operation='keep', input_refs=[ref], output_refs=[ref],
                                 reason=decision['reason'].strip(), step_id=step_id))
    return records
