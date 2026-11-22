"""Build fixed graph views from native event records, without event-specific assets."""
import re


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
    overview_refs = set()
    edges = []

    def references(record, key, field):
        owner, phase_id = record[key], record.get('phase_id')
        for i, ref in enumerate(record.get(field, [])):
            context = ref.get('context_id')
            if context not in context_ids:
                continue
            if phase_id in memberships:
                memberships[phase_id].add(context)
            else:
                overview_refs.add(context)
            kind = ref.get('relation_type', 'context')
            start, end = context, owner
            if kind == 'result':
                start, end = owner, context
            elif kind in ('participation', 'knowledge-source'):
                party = ref.get('entity_id')
                if party not in entity_ids:
                    continue  # A recorded gap has no known endpoint.
                if kind == 'participation':
                    start = party
                else:
                    end = party
            edges.append({
                'from': start, 'to': end, 'type': kind, 'kind': 'context', 'record': ref,
                'owner': owner, 'ref_path': f'/{field}/{i}',
            })

    for phase in phases:
        references(phase, 'phase_id', 'baseline_context_refs')
    for action in actions:
        references(action, 'action_id', 'delta_context_refs')
    assigned = set().union(*memberships.values()) if memberships else set()
    for context in contexts:
        cid = context['context_id']
        if cid in assigned or cid in overview_refs:
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
        owners = {owner, *activity}
        scoped_edges = [edge for edge in edges if edge['kind'] != 'context' or edge['owner'] in owners]
        for edge in scoped_edges:
            if edge['kind'] == 'party' and edge['to'] in visible:
                people.append(edge['from'])
            elif edge['kind'] == 'context' and edge['type'] in ('participation', 'knowledge-source'):
                people.append(edge['record']['entity_id'])
        if not phase:
            people += [item['entity_id'] for item in graph.get('entities', [])
                       if not any(item['entity_id'] in (edge['from'], edge['to']) for edge in edges)]
        people = list(dict.fromkeys(people))
        visible.update(people)
        local_edges = [edge for edge in scoped_edges if edge['from'] in visible and edge['to'] in visible]
        jumps = []
        for edge in scoped_edges:
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
                    passage = evidence.get(eid, {})
                    sid = passage.get('source_id')
                    if sid not in source_ids:
                        continue
                    sources.setdefault(sid, set()).add(eid)
                    local_edges.append({'from': sid, 'to': node, 'type': 'supports', 'kind': 'evidence'})
        # Retain passages cited by relations, even when neither endpoint has its own support.
        for edge in scoped_edges:
            if edge['from'] not in visible and edge['to'] not in visible:
                continue
            for support in edge.get('record', {}).get('support', []):
                for eid in support.get('evidence_ids', []):
                    passage = evidence.get(eid, {})
                    if passage.get('source_id') in source_ids:
                        sources.setdefault(passage['source_id'], set()).add(eid)
        if not phase:
            sources.update((sid, sources.get(sid, set())) for sid in source_ids)
            for eid, passage in evidence.items():
                if passage.get('source_id') in source_ids:
                    sources[passage['source_id']].add(eid)

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
            'edges': list({(e['from'], e['to'], e['type'], e.get('owner'), e.get('ref_path')): e
                           for e in local_edges}.values()),
            'jumps': list({item['id']: item for item in jumps}.values()),
        })
    return {'details': details, 'pages': pages}
