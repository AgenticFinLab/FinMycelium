"""Task receipts for relation discovery; never part of the public graph schema."""


def discovery_scope(actions, candidates):
    return dict(action_ids=list(actions), candidate_ids=[c['candidate_id'] for c in candidates])


def validate_review(value, scope, package):
    """Check declared coverage and references, not semantic/exhaustive discovery."""
    if not isinstance(value, dict) or set(value) != {'actions', 'candidates', 'pairs'}:
        raise ValueError('relation_review requires actions, candidates and pairs arrays')
    if any(not isinstance(value[k], list) for k in value):
        raise ValueError('relation_review fields must be arrays')
    actions = {a['action_id']: a for a in package['actions']}
    relations = {r['relation_id']: r for r in package['relations']}
    evidence = {e['evidence_id'] for e in package['evidence']}
    owned = set(scope['action_ids'])
    pending = []

    def reason(item, field='reason'):
        if not isinstance(item.get(field), str) or not item[field].strip():
            raise ValueError('Review needs a nonempty ' + field)

    seen = set()
    for item in value['actions']:
        if not isinstance(item, dict) or set(item) != {'action_id', 'status', 'within_phase', 'cross_phase'}:
            raise ValueError('Action review needs action_id, status, within_phase and cross_phase')
        aid = item['action_id']
        if not isinstance(aid, str) or aid not in owned or aid in seen:
            raise ValueError('Action review must cover each assigned Action exactly once')
        seen.add(aid)
        for field in ('within_phase', 'cross_phase'):
            reason(item, field)
        if item['status'] not in ('complete', 'pending'):
            raise ValueError('Action review status must be complete or pending')
        if item['status'] == 'pending':
            pending.append(aid)
    if seen != owned:
        raise ValueError('Missing assigned Action reviews: ' + ', '.join(sorted(owned - seen)))

    linked = set()

    def outcome(item, source=None, target=None):
        reason(item)
        if item['status'] not in ('linked', 'unsupported', 'pending'):
            raise ValueError('Review outcome must be linked, unsupported or pending')
        ids = item['relation_ids']
        if not isinstance(ids, list) or any(not isinstance(rid, str) for rid in ids) or len(ids) != len(set(ids)):
            raise ValueError('relation_ids must be a unique string array')
        if (item['status'] == 'linked') != bool(ids):
            raise ValueError('Only linked reviews require nonempty relation_ids')
        for rid in ids:
            rel = relations.get(rid)
            if rel is None:
                raise ValueError('Review references an unaccepted relation: ' + rid)
            if rel['from_action_id'] not in owned:
                raise ValueError('Review relation source is outside the discovery scope')
            if source is not None and (rel['from_action_id'], rel['to_action_id']) != (source, target):
                raise ValueError('Reviewed pair does not match its relation endpoints')
        if item['status'] == 'pending':
            pending.append(item.get('candidate_id', source))
        return ids

    seen = set()
    for item in value['candidates']:
        if not isinstance(item, dict) or set(item) != {'candidate_id', 'status', 'relation_ids', 'reason'}:
            raise ValueError('Candidate review needs candidate_id, status, relation_ids and reason')
        cid = item['candidate_id']
        if not isinstance(cid, str) or cid not in scope['candidate_ids'] or cid in seen:
            raise ValueError('Candidate reviews must match the assigned candidate IDs exactly once')
        seen.add(cid)
        outcome(item)
    if seen != set(scope['candidate_ids']):
        raise ValueError('Missing candidate dispositions')

    seen = set()
    for item in value['pairs']:
        if not isinstance(item, dict) or set(item) != {
                'from_action_id', 'to_action_id', 'status', 'relation_ids', 'evidence_ids', 'reason'}:
            raise ValueError('Pair review needs endpoints, status, relation_ids, evidence_ids and reason')
        source, target = item['from_action_id'], item['to_action_id']
        if (not isinstance(source, str) or not isinstance(target, str) or source not in owned
                or target not in actions or source == target or (source, target) in seen):
            raise ValueError('Pair needs a unique directed pair with an assigned source and an existing target')
        seen.add((source, target))
        ev = item['evidence_ids']
        if not isinstance(ev, list) or any(not isinstance(e, str) or e not in evidence for e in ev):
            raise ValueError('Pair evidence_ids must reference accepted evidence')
        linked.update(outcome(item, source, target))
    expected = {rid for rid, r in relations.items() if r['from_action_id'] in owned}
    if not expected <= linked:
        raise ValueError('Accepted outgoing relations lack pair reviews: ' + ', '.join(sorted(expected - linked)))
    if pending:
        raise ValueError('Relation discovery remains pending: ' + ', '.join(pending))
