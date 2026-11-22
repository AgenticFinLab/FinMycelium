"""Find existing Context worth checking against an Action's cited passages."""
from collections import defaultdict


def _content_citations(record, fields):
    citations = set()
    for support in record.get('support', []):
        target = support.get('target', '/')
        if target == '' or target.removeprefix('/').split('/', 1)[0] in fields:
            citations.update(support['evidence_ids'])
    return citations


def shared_passage_leads(indexes, action_ids):
    """Yield evidence for inspection. Co-citation alone cannot establish an association."""
    by_passage = defaultdict(list)
    for cid, context in indexes['contexts'].items():
        for eid in _content_citations(context, ('description',)):
            if indexes['evidence'].get(eid, {}).get('location_status') == 'matched':
                by_passage[eid].append(cid)

    for aid in action_ids:
        action = indexes['actions'][aid]
        phase = indexes['phases'].get(action.get('phase_id'), {})
        # A Phase reference was already considered, including an explicit exception.
        attached = {r['context_id'] for r in phase.get('baseline_context_refs', [])}
        attached.update(r['context_id'] for r in action.get('delta_context_refs', []))
        matches = defaultdict(list)
        for eid in sorted(_content_citations(action, ('name', 'description', 'actor', 'object'))):
            for cid in by_passage.get(eid, ()):
                if cid not in attached:
                    matches[cid].append(eid)
        for cid in sorted(matches):
            yield dict(action_id=aid, context_id=cid, evidence_ids=matches[cid])
