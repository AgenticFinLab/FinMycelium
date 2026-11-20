"""Arrange one scrollable canvas per Phase, plus an event-background canvas."""
import math
import re
from urllib.parse import urlparse

from .graph_labels import card_label, shorten
from .evidence_support import iter_citations


def _short(text, limit=175):
    return shorten(text, limit)


def action_order(actions, edges):
    """Keep connected actions together and respect explicit forward relations."""
    adjacency = {aid: set() for aid in actions}
    forwards = []
    for edge in edges:
        a, b = edge['from'], edge['to']
        if edge['kind'] != 'relation' or a not in adjacency or b not in adjacency:
            continue
        adjacency[a].add(b)
        adjacency[b].add(a)
        if edge['type'] in ('precedes', 'enables'):
            forwards.append((a, b))
    remaining, components = set(actions), []
    for aid in actions:
        if aid not in remaining:
            continue
        connected, todo = set(), [aid]
        while todo:
            node = todo.pop()
            if node in connected:
                continue
            connected.add(node)
            todo.extend(adjacency[node] - connected)
        remaining -= connected
        pending = [item for item in actions if item in connected]
        ordered = []
        while pending:
            ready = [item for item in pending if not any(
                b == item and a in pending for a, b in forwards)]
            # Preserve input order inside cycles; never invent an order relation.
            chosen = (ready or pending)[0]
            ordered.append(chosen)
            pending.remove(chosen)
        components.append(ordered)
    return [aid for component in components for aid in component]


def arrange_graph(graph, view):
    records = {graph['event']['event_id']: graph['event']}
    kinds, aliases = {}, {}
    for field, key, kind, prefix in (
        ('actions', 'action_id', 'action', 'A'),
        ('contexts', 'context_id', 'context', 'C'),
        ('entities', 'entity_id', 'party', 'E'),
        ('sources', 'source_id', 'source', 'S'),
        ('evidence', 'evidence_id', 'evidence', 'EV'),
        ('phases', 'phase_id', 'phase', 'P'),
    ):
        for index, record in enumerate(graph.get(field, []), 1):
            nid = record[key]
            records[nid] = record
            kinds[nid], aliases[nid] = kind, prefix + str(index).zfill(2)
    phases = graph.get('phases', [])
    evidence = {record['evidence_id']: record for record in graph.get('evidence', [])}
    evidence_order = {eid: i for i, eid in enumerate(evidence)}

    def passages(record):
        return {eid for support in record.get('support', []) for eid in support.get('evidence_ids', [])
                if eid in evidence}

    def source_ids(record):
        return {citation['source_id'] for eid in passages(record)
                for citation in iter_citations(evidence[eid])}

    details = view['details']
    for eid, record in evidence.items():
        details[eid] = {'title': record.get('statement') or record.get('quote') or eid,
                        'paragraphs': [], 'date': ''}
    person = graph.get('person', {})
    person_id = person.get('person_id')
    if person_id and person_id not in records:
        records[person_id] = {**person, 'type': 'person'}
        kinds[person_id], aliases[person_id] = 'party', ''
        details[person_id] = {'title': person.get('name', person_id), 'paragraphs': [], 'date': ''}
    for source in graph.get('sources', []):
        sid = source['source_id']
        title = source.get('title')
        if not title:
            title = urlparse(source.get('url') or source.get('origin') or '').netloc.removeprefix('www.')
        if title:
            details[sid]['title'] = title

    # Retain explicit memberships and place remaining background using its own
    # dates or evidence shared with a Phase. This is a display assignment.
    phase_context = {page['phase']: list(page['columns'][2]) for page in view['pages'][1:]}
    unassigned = []
    profiles = {}
    for phase in phases:
        pid = phase['phase_id']
        associated = [phase] + [a for a in graph.get('actions', []) if a.get('phase_id') == pid]
        profiles[pid] = (
            set().union(*(passages(item) for item in associated)),
            set().union(*(source_ids(item) for item in associated)),
        )
    for cid in view['pages'][0]['columns'][2]:
        record = records[cid]
        span = record.get('time') or {}
        years = set(re.findall(r'\b(?:19|20)\d{2}\b', span.get('text') or ''))
        if not years:
            years = set(re.findall(r'\b(?:19|20)\d{2}\b', record.get('description') or ''))
        scores = []
        for phase in phases:
            pid = phase['phase_id']
            overlap = len(passages(record) & profiles[pid][0])
            score = overlap * 10
            period = phase.get('time') or {}
            lower, upper = period.get('start'), period.get('end')
            if years and (lower or upper):
                lo = int((lower or upper)[:4])
                hi = int((upper or lower)[:4])
                if any(lo <= int(year) <= hi for year in years):
                    score += 3
            scores.append((score, pid))
        scores.sort(reverse=True)
        if scores and scores[0][0] > 0 and (len(scores) == 1 or scores[0][0] > scores[1][0]):
            phase_context[scores[0][1]].append(cid)
        else:
            unassigned.append(cid)

    all_edges = []
    for page in view['pages']:
        all_edges.extend(edge for edge in page['edges'] if edge['kind'] not in ('evidence', 'party'))
    # Include action relations with endpoints on different Phases.
    all_edges += [
        {'from': item['from_action_id'], 'to': item['to_action_id'], 'type': item['type'],
         'kind': 'relation', 'record': item}
        for item in graph.get('relations', [])
    ]
    all_edges = list({(edge['from'], edge['to'], edge['type']): edge for edge in all_edges}.values())
    for nid, record in records.items():
        actor = (record.get('actor') or {}).get('entity_id')
        if actor in records and kinds.get(actor) == 'party':
            all_edges.append({'from': actor, 'to': nid, 'type': 'actor', 'kind': 'party'})
        for party in dict.fromkeys((record.get('object') or {}).get('entity_refs', [])):
            if kinds.get(party) == 'party':
                all_edges.append({'from': nid, 'to': party, 'type': 'object', 'kind': 'party'})
        for party in dict.fromkeys(record.get('entity_refs', [])):
            if kinds.get(party) == 'party':
                all_edges.append({'from': nid, 'to': party, 'type': 'about', 'kind': 'party'})
    output = []

    def make_card(nid, box):
        record = records[nid]
        kind = kinds.get(nid, 'context')
        parties = [(record.get('actor') or {}).get('entity_id')]
        parties += (record.get('object') or {}).get('entity_refs', []) + record.get('entity_refs', [])
        badges = sorted((c['source_id'] for c in iter_citations(record)) if kind == 'evidence'
                        else source_ids(record), key=lambda key: aliases.get(key, key))
        return {
            'key': nid, 'id': nid, 'kind': kind, 'alias': aliases.get(nid, ''),
            'title': card_label(record, kind, details[nid]['title'], records.get(parties[0])),
            'date': _short(details[nid]['date'], 36), 'parties': '',
            'entity_type': record.get('type', 'person') if kind == 'party' else '',
            'badges': list(dict.fromkeys(aliases.get(sid, '') for sid in badges)), 'box': box,
        }

    def add_parties(cards, body_top, body_end, canvas_width):
        visible = {card['id'] for card in cards}
        actors = list(dict.fromkeys(edge['from'] for edge in all_edges
                                   if edge['kind'] == 'party' and edge['type'] == 'actor'
                                   and edge['to'] in visible))
        related = set()
        for edge in all_edges:
            if edge['kind'] == 'party' and edge['from'] in visible:
                related.add(edge['to'])
        other = [nid for nid in records if nid in related and nid not in actors]
        action_tops = [card['box'][1] for card in cards if card['kind'] == 'action']
        first = min(action_tops, default=body_top + 52)
        for i, nid in enumerate(actors):
            card = make_card(nid, [42, first + i * 138, 148, 108])
            card['caption'] = 'Focal person' if nid == person_id else 'Actor'
            cards.append(card)
        if actors:
            body_end = max(body_end, first + (len(actors) - 1) * 138 + 132)
        # Reuse free slots beside the action rows before adding another row.
        xs = sorted({card['box'][0] for card in cards if card['kind'] == 'action'})
        width = 260
        slots = [[x + (width - 160) / 2, y, 160, 108]
                 for y in sorted(set(action_tops)) for x in xs]
        def clear(box):
            x, y, w, h = box
            return all(not (x < ox + ow + 10 and x + w > ox - 10 and
                            y < oy + oh + 10 and y + h > oy - 10)
                       for ox, oy, ow, oh in (card['box'] for card in cards))
        other.sort(key=lambda nid: -sum(edge['kind'] == 'party' and edge['to'] == nid
                                        and edge['from'] in visible for edge in all_edges))
        pending = []
        for nid in other:
            anchors = [card['box'] for card in cards if any(
                edge['from'] == card['id'] and edge['to'] == nid for edge in all_edges)]
            available = [box for box in slots if clear(box)]
            if available:
                box = min(available, key=lambda b: sum(abs(b[0] - a[0]) + abs(b[1] - a[1])
                                                      for a in anchors))
                card = make_card(nid, box)
                card['caption'] = 'Related party'
                cards.append(card)
            else:
                pending.append(nid)
        other = pending
        if other:
            top = body_end + 20
            columns = max(1, (canvas_width - 66) // 178)
            free = list(range(columns))
            row = 0
            for nid in other:
                anchors = [card['box'][0] + card['box'][2] / 2 for card in cards if any(
                    edge['from'] == card['id'] and edge['to'] == nid for edge in all_edges)]
                preferred = sum(anchors) / len(anchors) if anchors else 122
                if not free:
                    row += 1
                    free = list(range(columns))
                column = min(free, key=lambda i: abs(122 + i * 178 - preferred))
                free.remove(column)
                card = make_card(nid, [42 + column * 178, top + row * 132, 160, 108])
                card['caption'] = 'Related party'
                cards.append(card)
            body_end = top + (row + 1) * 132

        return body_end

    def finish(pid, title, cards, sections, body_end, canvas_width, extra_evidence=(), extra_sources=()):
        present = {card['id'] for card in cards}
        edges = [dict(edge) for edge in all_edges if edge['from'] in present and edge['to'] in present]
        quotes = {sid: set() for sid in extra_sources}
        shown_evidence = set(extra_evidence)
        for card in cards:
            for eid in sorted(passages(records[card['id']]), key=evidence_order.get):
                shown_evidence.add(eid)
                edges.append({'from': eid, 'to': card['id'], 'type': 'supports', 'kind': 'evidence'})
                for citation in iter_citations(evidence[eid]):
                    sid = citation['source_id']
                    if sid not in records:
                        continue
                    quotes.setdefault(sid, set()).add(eid)
        for edge in edges[:]:
            for eid in sorted(passages(edge.get('record', {})), key=evidence_order.get):
                shown_evidence.add(eid)
                for citation in iter_citations(evidence[eid]):
                    sid = citation['source_id']
                    if sid in records:
                        quotes.setdefault(sid, set()).add(eid)
        for eid in extra_evidence:
            for citation in iter_citations(evidence[eid]):
                sid = citation['source_id']
                if sid in records:
                    quotes.setdefault(sid, set()).add(eid)
        top = body_end + 30
        evidence_list = sorted(shown_evidence, key=evidence_order.get)
        evidence_columns = max(1, (canvas_width - 38) // 354)
        for i, eid in enumerate(evidence_list):
            card = make_card(eid, [38 + i % evidence_columns * 354,
                top + 48 + i // evidence_columns * 126, 328, 102])
            card['title'] = _short(details[eid]['title'], 175)
            card['quotes'] = [eid]
            cards.append(card)
        evidence_end = top + 72 + max(1, math.ceil(len(evidence_list) / evidence_columns)) * 126
        sections.append({'title': 'Evidence', 'box': [22, top, canvas_width - 44, evidence_end - top - 20]})
        top = evidence_end + 10
        source_list = sorted(quotes, key=lambda sid: aliases[sid])
        source_columns = max(1, (canvas_width - 38) // 274)
        for i, sid in enumerate(source_list):
            card = make_card(sid, [38 + i % source_columns * 274, top + 48 + i // source_columns * 104, 248, 82])
            ids = sorted(quotes[sid], key=evidence_order.get)
            card['evidence_ids'] = ids
            for eid in ids:
                edges.append({'from': sid, 'to': eid, 'type': 'cites', 'kind': 'citation'})
            cards.append(card)
        height = top + 72 + max(1, math.ceil(len(source_list) / source_columns)) * 104
        sections.append({'title': 'Sources', 'box': [22, top, canvas_width - 44, height - top - 20]})
        edges = list({(edge['from'], edge['to'], edge['type']): edge for edge in edges}.values())
        return {
            'phase': pid, 'title': title, 'cards': cards, 'sections': sections,
            'edges': edges, 'height': max(820, height), 'width': canvas_width, 'jumps': [],
        }

    plans = []
    for phase in [None, *phases]:
        pid = phase['phase_id'] if phase else None
        actions = list(next(page for page in view['pages'] if page['phase'] == pid)['columns'][1])
        ordered = action_order(actions, all_edges)
        title = phase['name'] if phase else 'Event background'
        baseline = list(dict.fromkeys(ref['context_id'] for ref in (phase or {}).get('baseline_context_refs', [])
                                      if ref.get('context_id') in records))
        context = phase_context[pid] if pid else unassigned
        has_actor = any(kinds.get((records[aid].get('actor') or {}).get('entity_id')) == 'party'
                        for aid in ordered)
        left = 236 if has_actor else 42
        canvas_width = max(1134, left + max(0, len(ordered) - 1) * 320 + 298,
                           54 + min(6, max(3, math.ceil(math.sqrt(len(context))))) * 360)
        columns = max(1, (canvas_width - 54) // 360)
        cards, sections, shown = [], [], set()
        y = 18
        if baseline:
            for i, cid in enumerate(baseline):
                cards.append(make_card(cid, [42 + i % columns * 360, y + 44 + i // columns * 96, 330, 72]))
                shown.add(cid)
            end = y + 48 + math.ceil(len(baseline) / columns) * 96
            sections.append({'title': 'Shared phase context', 'box': [22, y, canvas_width - 44, end - y]})
            y = end + 20
        body_top = y
        y += 54
        before, after = [], []
        # Each action owns a horizontal column. A shared context is drawn once;
        # its existing links can reach any other action on the same canvas.
        for aid in ordered:
            prior, result = [], []
            for ref in records[aid].get('delta_context_refs', []):
                cid = ref.get('context_id')
                if cid not in records or cid in shown:
                    continue
                (result if ref.get('relation_type') == 'result' else prior).append(cid)
                shown.add(cid)
            before.append(prior)
            after.append(result)
        for column, neighbors in enumerate(before):
            for i, cid in enumerate(neighbors):
                cards.append(make_card(cid, [left + column * 320, y + i * 104, 260, 72]))
        if ordered:
            action_y = y + max(map(len, before), default=0) * 104
            for column, aid in enumerate(ordered):
                cards.append(make_card(aid, [left + column * 320, action_y, 260, 88]))
            y = action_y + 132
            for column, neighbors in enumerate(after):
                for i, cid in enumerate(neighbors):
                    cards.append(make_card(cid, [left + column * 320, y + i * 104, 260, 72]))
            y += max(map(len, after), default=0) * 104
        remaining = list(dict.fromkeys(cid for cid in context if cid not in shown))
        if remaining:
            columns = max(1, (canvas_width - left - 12) // 360)
            for i, cid in enumerate(remaining):
                cards.append(make_card(cid, [left + i % columns * 360, y + i // columns * 112, 330, 80]))
            y += math.ceil(len(remaining) / columns) * 112
        if not cards and phase:
            cards.append(make_card(pid, [42, y, 1050, 116]))
            y += 146
        y = add_parties(cards, body_top, y, canvas_width)
        if cards:
            sections.append({'title': 'Actions and their context' if ordered else 'Context',
                             'box': [22, body_top, canvas_width - 44, y - body_top]})
        # Keep a source-free plan so uncited evidence can be merged into the
        # existing overview, instead of creating extra views for the same scope.
        plans.append((pid, title, cards, sections, y, canvas_width))
    for pid, title, cards, sections, end, width in plans:
        output.append(finish(pid, title, list(cards), list(sections), end, width))

    used_evidence = {eid for page in output for card in page['cards'] for eid in card.get('quotes', [])}
    unused = [eid for eid in evidence if eid not in used_evidence]
    displayed_sources = {card['id'] for page in output for card in page['cards'] if card['kind'] == 'source'}
    unused_sources = list(dict.fromkeys([citation['source_id'] for eid in unused
                                        for citation in iter_citations(evidence[eid])] +
                                      [source['source_id'] for source in graph.get('sources', [])
                                       if source['source_id'] not in displayed_sources]))
    if unused or unused_sources:
        pid, title, cards, sections, end, width = plans[0]
        output[0] = finish(pid, title, list(cards), list(sections), end, width, unused, unused_sources)

    destinations = {}
    for i,page in enumerate(output):
        for card in page['cards']:
            destinations.setdefault(card['id'],i)
    for page in output:
        present = {card['id'] for card in page['cards']}
        for edge in all_edges:
            if (edge['kind'] != 'party' and edge['from'] in present
                    and edge['to'] not in present and edge['to'] in destinations):
                page['jumps'].append({'from': aliases.get(edge['from'], ''),
                                     'to':aliases.get(edge['to'],''), 'id':edge['to'],
                                     'type':edge['type'], 'page':destinations[edge['to']]})
        # Assign unique keys to all card instances, including repeated contexts.
        for i,card in enumerate(page['cards']):
            card['key'] = 'card:' + str(i)
        for edge in page['edges']:
            pairs = [(a,b) for a in page['cards'] for b in page['cards']
                     if a['id']==edge['from'] and b['id']==edge['to']]
            if pairs:
                a,b = min(pairs,key=lambda pair:abs(pair[0]['box'][0]-pair[1]['box'][0])+abs(pair[0]['box'][1]-pair[1]['box'][1]))
                edge['from_key'],edge['to_key'] = a['key'],b['key']
        page['edges'] = [edge for edge in page['edges'] if 'from_key' in edge]
    return {'details':details,'pages':output}
