"""Field-level navigation for the offline viewer. All paths address the saved graph."""
from .records import evidence_samples, in_source_body, pointer, sha256
from .validation import located_evidence


def field_index(record):
    """Keep each support attached to its own field, including nested associations."""
    fields = {}

    def visit(value, path):
        if isinstance(value, list):
            for i, child in enumerate(value):
                visit(child, f'{path}/{i}')
        elif isinstance(value, dict):
            for kind in ('support', 'gaps', 'conflicts'):
                for i, entry in enumerate(value.get(kind, [])):
                    target = path + entry.get('target', '')
                    fields.setdefault(target, {}).setdefault(kind, []).append(f'{path}/{kind}/{i}')
            for key, child in value.items():
                if key not in ('support', 'gaps', 'conflicts') and isinstance(child, (list, dict)):
                    visit(child, path + '/' + key.replace('~', '~0').replace('/', '~1'))

    visit(record, '')
    return fields


def cited_evidence(record, fields):
    return {eid for field in fields for path in field.get('support', [])
            for eid in pointer(record, path).get('evidence_ids', [])}


def party_uses(graph, fields):
    """Point back to documented roles and mentions. A mention does not create a role."""
    uses = {}

    def add(party, owner, path, label):
        if not party:
            return
        targets = [field for field in fields.get(owner, {}) if field and (
            field == path or field.startswith(path + '/') or path.startswith(field + '/'))]
        uses.setdefault(party, []).append(dict(owner=owner, path=path, label=label, fields=targets))

    for action in graph.get('actions', []):
        aid = action['action_id']
        actor = action.get('actor') or {}
        add(actor.get('entity_id'), aid, '/actor', 'Actor')
        add(actor.get('on_behalf_of'), aid, '/actor/on_behalf_of', 'Represented party')
        for i, party in enumerate((action.get('object') or {}).get('entity_refs', [])):
            add(party, aid, f'/object/entity_refs/{i}', 'Action object')
    for ctx in graph.get('contexts', []):
        for i, party in enumerate(ctx.get('entity_refs', [])):
            add(party, ctx['context_id'], f'/entity_refs/{i}', 'Mentioned in context')
    for collection, key, refs in [('actions', 'action_id', 'delta_context_refs'),
                                  ('phases', 'phase_id', 'baseline_context_refs')]:
        for owner in graph.get(collection, []):
            for i, ref in enumerate(owner.get(refs, [])):
                if ref.get('relation_type') in ('participation', 'knowledge-source'):
                    label = 'Participation' if ref['relation_type'] == 'participation' else 'Knowledge recipient'
                    add(ref.get('entity_id'), owner[key], f'/{refs}/{i}', label)
    return uses


def passage_issues(graph, payload):
    """Report only exceptions; never change the archived Evidence or publish sample bodies."""
    samples = evidence_samples(payload) if payload is not None else None
    indexes = {'sources': {s['source_id']: s for s in graph.get('sources', [])}}
    issues = {}
    for ev in graph.get('evidence', []):
        eid = ev['evidence_id']
        status = ev.get('location_status')
        if status in ('unmatched', 'ambiguous'):
            issues[eid] = status
        elif samples is None:
            if status == 'matched' and not located_evidence(ev, indexes):
                issues[eid] = 'unverified'
        elif not located_evidence(ev, indexes, samples):
            sample = samples.get(ev.get('sample_id'))
            start, end = ev.get('start'), ev.get('end')
            if (sample and sample['raw_data_id'] == ev.get('source_id') and type(start) is int and type(end) is int
                    and 0 <= start < end <= len(sample['content']) and sample['content'][start:end] == ev['quote']
                    and ev.get('sample_sha256') == sha256(sample['content'].encode('utf-8'))
                    and not in_source_body(sample, start, end)):
                issues[eid] = 'handoff'
            else:
                issues[eid] = 'unverified'
    return issues
