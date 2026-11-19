"""Build fixed graph views from native event records, without event-specific assets."""
import re

from .evidence_support import iter_citations


def build_views(graph):
    groups = (
        ('actions', 'action_id'), ('contexts', 'context_id'), ('entities', 'entity_id'),
        ('phases', 'phase_id'), ('sources', 'source_id'),
    )
    records = {graph['event']['event_id']: graph['event']}
    for field, key in groups:
        records.update((record[key], record) for record in graph.get(field, []))
    phases = graph.get('phases', [])
    actions = graph.get('actions', [])
    contexts = graph.get('contexts', [])
    phase_ids = {phase['phase_id'] for phase in phases}
    context_ids = {context['context_id'] for context in contexts}
    entity_ids = {entity['entity_id'] for entity in graph.get('entities', [])}
    evidence = {item['evidence_id']: item for item in graph.get('evidence', [])}
    source_ids = {item['source_id'] for item in graph.get('sources', [])}
    memberships = {phase['phase_id']: set() for phase in phases}
    edges = []

    def references(owner, refs, phase_id):
        for ref in refs:
            context = ref.get('context_id')
            if context not in context_ids:
                continue
            if phase_id in memberships:
                memberships[phase_id].add(context)
            result = ref.get('relation_type') == 'result'
            edges.append({
                'from': owner if result else context,
                'to': context if result else owner,
                'type': ref.get('relation_type', 'context'), 'kind': 'context', 'record': ref,
            })

    for phase in phases:
        references(phase['phase_id'], phase.get('baseline_context_refs', []), phase['phase_id'])
    for action in actions:
        references(action['action_id'], action.get('delta_context_refs', []), action.get('phase_id'))
    assigned = set().union(*memberships.values()) if memberships else set()
    for context in contexts:
        cid = context['context_id']
        if cid in assigned:
            continue
        span = context.get('time') or {}
        start, end = span.get('start'), span.get('end')
        if not all(re.fullmatch(r'\d{4}-\d{2}-\d{2}', value or '') for value in (start, end)):
            continue
        matches = []
        for phase in phases:
            period = phase.get('time') or {}
            lower, upper = period.get('start'), period.get('end')
            if lower and upper and lower <= start <= end <= upper:
                matches.append(phase['phase_id'])
        if len(matches) == 1:
            memberships[matches[0]].add(cid)

    for relation in graph.get('relations', []):
        edges.append({
            'from': relation.get('from_action_id'), 'to': relation.get('to_action_id'),
            'type': relation.get('type', 'relation'), 'kind': 'relation', 'record': relation,
        })
    for owner, record in records.items():
        party_ids = [(record.get('actor') or {}).get('entity_id')]
        party_ids += (record.get('object') or {}).get('entity_refs', [])
        party_ids += record.get('entity_refs', [])
        for party in dict.fromkeys(party_ids):
            if party in entity_ids and party != owner:
                edges.append({'from': party, 'to': owner, 'type': 'participant', 'kind': 'party'})

    assigned = set().union(*memberships.values()) if memberships else set()
    destinations = {}
    for phase in phases:
        destinations[phase['phase_id']] = phase['phase_id']
        for cid in memberships[phase['phase_id']]:
            destinations.setdefault(cid, phase['phase_id'])
    for action in actions:
        destinations[action['action_id']] = action.get('phase_id') if action.get('phase_id') in phase_ids else None
    details = {}
    for node_id, record in records.items():
        title = next((record[key] for key in ('name', 'title', 'description', 'origin', 'url')
                      if isinstance(record.get(key), str) and record[key]), node_id)
        paragraphs = dict.fromkeys(record[key] for key in ('description', 'summary')
                                  if isinstance(record.get(key), str) and record[key] and record[key] != title)
        if node_id in source_ids:
            if record.get('publisher'):
                paragraphs['Publisher: ' + record['publisher']] = None
            upstream = [records.get(sid, {}).get('title') or sid
                        for sid in record.get('upstream_source_ids', [])]
            if upstream:
                paragraphs['Reports information from: ' + '; '.join(upstream)] = None
        details[node_id] = {
            'title': title, 'paragraphs': list(paragraphs),
            'date': record.get('published_at') or (record.get('time') or {}).get('text'),
        }

    pages = []
    for phase in [None, *phases]:
        pid = phase['phase_id'] if phase else None
        owner = pid or graph['event']['event_id']
        activity = [item['action_id'] for item in actions if destinations[item['action_id']] == pid]
        context = [item['context_id'] for item in contexts
                   if item['context_id'] in memberships.get(pid, context_ids - assigned)]
        if not phase:
            for aid in activity:
                action = records[aid]
                context += [ref['context_id'] for ref in action.get('delta_context_refs', [])
                            if ref.get('context_id') in context_ids]
            context = list(dict.fromkeys(context))
        visible = {owner, *activity, *context}
        people = [owner]
        for edge in edges:
            if edge['kind'] == 'party' and edge['to'] in visible:
                people.append(edge['from'])
        if not phase:
            people += [item['entity_id'] for item in graph.get('entities', [])
                       if not any(edge['from'] == item['entity_id'] for edge in edges)]
        people = list(dict.fromkeys(people))
        visible.update(people)
        local_edges = [edge for edge in edges if edge['from'] in visible and edge['to'] in visible]
        jumps = []
        for edge in edges:
            if edge['kind'] == 'party':
                continue
            missing = edge['to'] if edge['from'] in visible else edge['from']
            if (edge['from'] in visible or edge['to'] in visible) and missing not in visible and missing in records:
                jumps.append({'id': missing, 'phase': destinations.get(missing), 'type': edge['type']})

        sources = {}
        for node in records:
            if node not in visible:
                continue
            for support in records[node].get('support', []):
                for eid in support.get('evidence_ids', []):
                    for citation in iter_citations(evidence.get(eid)):
                        sid = citation.get('source_id')
                        if sid not in source_ids:
                            continue
                        sources.setdefault(sid, set()).add(eid)
                        local_edges.append({'from': sid, 'to': node, 'type': 'supports', 'kind': 'evidence'})
        # Retain passages cited by relations, even when neither endpoint has its own support.
        for edge in edges:
            if edge['from'] not in visible and edge['to'] not in visible:
                continue
            for support in edge.get('record', {}).get('support', []):
                for eid in support.get('evidence_ids', []):
                    for citation in iter_citations(evidence.get(eid)):
                        if citation.get('source_id') in source_ids:
                            sources.setdefault(citation['source_id'], set()).add(eid)
        if not phase:
            sources.update((sid, sources.get(sid, set())) for sid in source_ids)
            for eid, passage in evidence.items():
                for citation in iter_citations(passage):
                    if citation.get('source_id') in source_ids:
                        sources[citation['source_id']].add(eid)

        boxes = {}
        columns = [(people, 24, 230), (activity, 300, 350), (context, 704, 380)]
        for nodes, x, width in columns:
            for row, node in enumerate(nodes):
                boxes[node] = [x, 48 + row * 160, width, 104]
        evidence_top = 80 + 160 * max(1, *(len(nodes) for nodes, _, _ in columns))
        # Source order follows the input JSON, making repeated exports deterministic.
        ordered_sources = [item['source_id'] for item in graph.get('sources', []) if item['source_id'] in sources]
        for row, sid in enumerate(ordered_sources):
            boxes[sid] = [24 + (row % 3) * 364, evidence_top + 40 + (row // 3) * 180, 336, 120]
        pages.append({
            'phase': pid, 'title': phase['name'] if phase else 'Event overview & background',
            'columns': [people, activity, context], 'boxes': boxes,
            'evidence_top': evidence_top,
            'height': evidence_top + 80 + ((len(ordered_sources) + 2) // 3) * 180,
            'sources': {sid: sorted(sources[sid]) for sid in ordered_sources},
            'edges': list({(edge['from'], edge['to'], edge['type']): edge for edge in local_edges}.values()),
            'jumps': list({item['id']: item for item in jumps}.values()),
        })
    return {'details': details, 'pages': pages}
