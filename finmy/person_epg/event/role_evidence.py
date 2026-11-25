"""Locate the evidence behind a particular merge, boundary or directed link."""
from collections import defaultdict

from .records import prompt_json


def citations(record, evidence, fields=None):
    groups = {}
    for support in record.get('support', []):
        field = support['target']
        if fields and field and field.split('/')[1] not in fields:
            continue
        for eid in support['evidence_ids']:
            passage = evidence.get(eid)
            if passage and passage['location_status'] == 'matched':
                groups.setdefault(passage['source_id'], {}).setdefault(field, []).append(eid)
    return groups


def role_rows(role, fields, indexes, order_candidates):
    evidence = indexes['evidence']
    if role == 'consolidation':
        for ref in fields.get('assigned', []):
            record = indexes.get(ref['collection'], {}).get(ref['object_id'], {})
            yield dict(record=ref['object_id'], actor=record.get('actor'), by_source=citations(record, evidence))
    elif role == 'organization':
        for link in order_candidates:
            if link.get('from_action_id') and link.get('to_action_id'):
                yield dict(extracted_candidate=link['candidate_id'], proposed_type=link.get('type'),
                           endpoints=[link['from_action_id'],link['to_action_id']],
                           link_by_source=citations(link, evidence))
        # Normalized bounds retain precision. Sequence in this index carries no precedence claim.
        for action in indexes['actions'].values():
            yield dict(action=action['action_id'], time=action.get('time'),
                       by_source=citations(action, evidence, {'time', 'description', 'object'}))
        for context in indexes['contexts'].values():
            yield dict(context=context['context_id'], description=context['description'][:180],
                       by_source=citations(context, evidence, {'time', 'description'}))
    elif role == 'relations':
        for link in fields.get('relation_candidates', []):
            ends = []
            for key in ('from_action_id', 'to_action_id'):
                action = indexes['actions'].get(link.get(key))
                if action:
                    ends.append(dict(action=action['action_id'], name=action['name'], time=action['time'],
                                     by_source=citations(action, evidence, {'description', 'time'})))
            yield dict(candidate=link['candidate_id'], endpoints=ends, link_by_source=citations(link, evidence))


def nearby_passages(indexes, owned, payload, known_pairs):
    """Show a short exact span between grounded endpoints, including other phases."""
    by_sample = defaultdict(list)
    for aid, action in indexes['actions'].items():
        for by_field in citations(action, indexes['evidence'], {'description','name','object'}).values():
            for eid in sorted({e for ids in by_field.values() for e in ids}):
                e = indexes['evidence'][eid]
                by_sample[e['sample_id']].append((e['start'],e['end'],aid,eid))
    samples = {s['sample_id']:s for s in payload['samples']}
    seen = set(known_pairs)
    for sid, spans in by_sample.items():
        spans.sort()
        for i,(a,b,aid,eid) in enumerate(spans):
            for j in range(i+1,len(spans)):
                c,d,bid,fid = spans[j]
                if c-b > 600:
                    break
                pair = tuple(sorted((aid,bid)))
                end = max(b,d)
                if (aid == bid or pair in seen or not owned.intersection(pair) or
                        end-a > 1800 or sid not in samples):
                    continue
                seen.add(pair)
                yield dict(actions=[aid,bid], evidence_ids=[eid,fid], sample_id=sid,
                           source_id=samples[sid]['raw_data_id'], start=a,end=end,
                           text=samples[sid]['content'][a:end])


def add_role_evidence(request, indexes, limit, payload=None, order_candidates=()):
    role = request['role']
    if role not in {'consolidation', 'organization', 'relations'}:
        return request
    # Spend only spare context. Exact records already delivered need only an ID;
    # attach missing passages with their actual source and offsets once per task.
    delivered = {r['record']['evidence_id'] for r in request.get('related_records', []) if r['collection'] == 'evidence'}
    available = limit - len(prompt_json(dict(task=request, read_results=[]))) - 120
    available = min(available, limit // 8)
    rows, excerpts = [], {}
    for row in role_rows(role, request, indexes, order_candidates):
        groups = [row.get('by_source', {}), row.get('link_by_source', {})]
        groups.extend(end['by_source'] for end in row.get('endpoints', []) if isinstance(end, dict))
        ids = dict.fromkeys(eid for group in groups for fields in group.values() for eids in fields.values() for eid in eids)
        new = {eid: {k: indexes['evidence'][eid][k] for k in ('source_id','sample_id','start','end','quote')}
               for eid in ids if eid not in excerpts and eid not in delivered}
        size = len(prompt_json(row)) + len(prompt_json(new)) + 5
        if size <= available:
            rows.append(row)
            excerpts.update(new)
            available -= size
    windows = []
    if role == 'relations' and payload and not request.get('correction'):
        known = {tuple(sorted((r['from_action_id'],r['to_action_id']))) for r in request.get('relation_candidates', [])
                 if r.get('from_action_id') and r.get('to_action_id')}
        for window in nearby_passages(indexes, set(request.get('assigned_action_ids', [])), payload, known):
            size = len(prompt_json(window)) + 2
            if size <= available:
                windows.append(window)
                available -= size
    if rows or windows:
        request['role_evidence'] = dict(records=rows, passages=excerpts, nearby_passages=windows)
    return request
