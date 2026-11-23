"""Arrange one scrollable canvas per Phase, plus an event-background canvas."""
import math
import re
from collections import defaultdict
from urllib.parse import urlparse

from .action_layout import phase_layout
from .chronology import ActionChronology
from .graph_evidence import cited_evidence, field_index, party_uses
from .graph_labels import card_label, shorten
from .records import compose_context


def _short(text, limit=175):
    return shorten(text, limit)


def _bridge_slot(refs, placement, chronology, occupied):
    """Find an existing gap between a recorded result and a later condition."""
    ends = defaultdict(list)
    for aid, ref, settled in refs:
        if settled:
            ends[ref.get('relation_type')].append(aid)
    for a in ends['result']:
        start = placement[a]
        row = start['row']
        for b in ends['condition']:
            end = placement[b]
            if b not in chronology.after[a] or row != end['row']:
                continue
            for col in range(math.floor(start['last']) + 1, math.ceil(end['first'])):
                occupants = [c['row'] for c in placement.values() if c['first'] <= col <= c['last']]
                if (not occupants or row < min(occupants) or row > max(occupants)) and col not in occupied[row]:
                    return row, col
    return None


def _context_homes(ordered, records, context_ids, placement, chronology, inline, shown):
    """Lay out the recorded Context uses after fixing every Action row and column."""
    uses = defaultdict(list)
    for aid in ordered:
        owner = records[aid]
        issues = {issue.get('target') for key in ('gaps', 'conflicts') for issue in owner.get(key, [])}
        for i, ref in enumerate(owner.get('delta_context_refs', [])):
            cid = ref.get('context_id')
            if cid in context_ids and cid not in shown:
                path = f'/delta_context_refs/{i}'
                association = {'', '/delta_context_refs', path, path + '/context_id', path + '/relation_type', path + '/qualification'}
                settled = not (issues & association or ref.get('gaps') or ref.get('conflicts'))
                uses[cid].append((aid, ref, settled))

    above, below, between = defaultdict(list), defaultdict(list), defaultdict(dict)

    def place_outside(cid, owners, side):
        cols = sorted(placement[a]['column'] for a in set(owners))
        side[math.floor(cols[(len(cols)-1)//2])].append(cid)

    for cid in inline:
        place_outside(cid, ordered, above)
    for cid, refs in uses.items():
        if cid in inline:
            continue
        results = [aid for aid, ref, _ in refs if ref.get('relation_type') == 'result']
        others = [aid for aid, ref, _ in refs if ref.get('relation_type') != 'result']
        if results and others:
            slot = _bridge_slot(refs, placement, chronology, between)
            if slot:
                row, col = slot
                between[row][col] = cid
                continue
        if others:
            place_outside(cid, others, above)
        else:
            place_outside(cid, results, below)
    shown.update(uses)
    shown.update(inline)
    return above, below, between


def _baseline_coverage(graph, phase, actions):
    """Track each Phase use separately; a card summarizes all uses of its Context."""
    refs = phase.get('baseline_context_refs', [])
    coverage = {ref['context_id']: {'applies': [], 'excluded': [], 'unresolved': []}
                for ref in refs if ref.get('context_id')}
    members = {}
    ambiguous = set()
    scope_fields = {'/context_id', '/relation_type', '/qualification'}
    phase_issues = {issue.get('target') for kind in ('gaps', 'conflicts') for issue in phase.get(kind, [])}
    for index, ref in enumerate(refs):
        path = f'/baseline_context_refs/{index}'
        members[path] = []
        # A gap about additional baseline uses, or the date of a Context, can
        # coexist with a supported use. Only uncertainty about this use matters.
        if (path in phase_issues or any(path + field in phase_issues for field in scope_fields)
                or any(i.get('target') in scope_fields for k in ('gaps', 'conflicts') for i in ref.get(k, []))):
            ambiguous.add(path)
    for action in actions:
        aid = action['action_id']
        excluded, unresolved = set(), set()
        if action.get('baseline_context_exclusions'):
            try:
                composed = compose_context(graph, aid)
                excluded.update(composed['excluded_ref_ids'])
                unresolved.update(issue['context_ref_id'] for issue in composed['issues'])
            except (KeyError, TypeError, ValueError):
                # An incomplete saved draft can still be displayed. Its proposed
                # exceptions remain unresolved until their support can be checked.
                unresolved.update(item.get('context_ref_id') for item in action['baseline_context_exclusions'])
        states = {cid: set() for cid in coverage}
        for index, ref in enumerate(refs):
            if ref.get('context_id') not in states:
                continue
            path = f'/baseline_context_refs/{index}'
            rid = ref.get('context_ref_id')
            if rid in unresolved:
                state = 'unresolved'
            elif rid in excluded:
                state = 'excluded'
            elif path in ambiguous:
                state = 'unresolved'
            else:
                state = 'applies'
                members[path].append(aid)
            states[ref['context_id']].add(state)
        for cid, outcomes in states.items():
            state = next(s for s in ('applies', 'unresolved', 'excluded') if s in outcomes)
            coverage[cid][state].append(aid)
    return coverage, members


def _phase_context_edges(edges, pid, members):
    """Project inherited conditions and constraints; retain the original reference paths."""
    result = []
    explicit = {}

    def identity(edge):
        ref = edge['record']
        return (edge['from'], edge['to'], edge['type'], ref.get('entity_id'), ref.get('role'),
                ref.get('interaction_type'), ref.get('qualification'))

    for edge in edges:
        if edge['owner'] != pid and not (edge['record'].get('conflicts') or edge['record'].get('gaps')):
            explicit.setdefault(identity(edge), []).append(edge)
    matched = set()
    for edge in edges:
        if edge['owner'] != pid:
            continue
        recipients = members[edge['ref_path']]
        if edge['type'] not in ('condition', 'constraint') or not recipients:
            result.append(edge)
            continue
        for aid in recipients:
            branch = dict(edge, to=aid, inherited=True)
            same = explicit.get(identity(branch), [])
            if same and not (edge['record'].get('conflicts') or edge['record'].get('gaps')):
                branch['direct_paths'] = [use['ref_path'] for use in same]
                matched.update((aid, use['ref_path']) for use in same)
            result.append(branch)
    result.extend(edge for edge in edges if edge['owner'] != pid and
                  (edge['owner'], edge['ref_path']) not in matched)
    return result


def arrange_graph(graph, view, issues=None, payload=None):
    issues = issues or {}
    records = {graph['event']['event_id']: graph['event']}
    kinds, aliases = {}, {}
    for field, key, kind, prefix in (
        ('actions', 'action_id', 'action', 'A'),
        ('contexts', 'context_id', 'context', 'C'),
        ('entities', 'entity_id', 'party', 'E'),
        ('sources', 'source_id', 'source', 'S'),
        ('phases', 'phase_id', 'phase', 'P'),
        ('stages', 'stage_id', 'stage', 'ST'),
        ('evidence', 'evidence_id', 'evidence', 'EV'),
    ):
        for index, record in enumerate(graph.get(field, []), 1):
            nid = record[key]
            records[nid] = record
            kinds[nid], aliases[nid] = kind, prefix + str(index).zfill(2)
    phases = graph.get('phases', [])
    evidence = {record['evidence_id']: record for record in graph.get('evidence', [])}
    evidence_order = {eid: i for i, eid in enumerate(evidence)}
    relations = {}
    for i, relation in enumerate(graph.get('relations', []), 1):
        rid = relation.get('relation_id', f'relation:{i}')
        relations[rid] = records[rid] = relation
        kinds[rid], aliases[rid] = 'relation', f'R{i:02}'
    phase_pages = {p['phase_id']: i for i, p in enumerate(phases, 1)}
    action_phases = {a['action_id']: a.get('phase_id') for a in graph.get('actions', [])}
    phase_links = {pid: [] for pid in phase_pages}
    for rid, relation in relations.items():
        start, end = relation['from_action_id'], relation['to_action_id']
        first, second = action_phases.get(start), action_phases.get(end)
        if first == second or first not in phase_pages or second not in phase_pages:
            continue
        for local, other, here, there in ((start, end, first, second), (end, start, second, first)):
            phase_links[here].append({'action_id': local, 'id': other, 'page': phase_pages[there],
                                      'relation_id': rid, 'from': aliases[start], 'to': aliases[end],
                                      'type': relation['type']})
    fields = {nid: entries for nid, record in records.items() if (entries := field_index(record))}
    uses = party_uses(graph, fields)
    eligible = evidence.keys() - issues.keys()
    citations = {nid: cited_evidence(records[nid], entries.values()) & eligible
                 for nid, entries in fields.items()}

    def passages(record):
        return {eid for support in record.get('support', []) for eid in support.get('evidence_ids', [])
                if eid in evidence}

    def source_ids(record):
        return {evidence[eid]['source_id'] for eid in passages(record) if eid not in issues}

    details = view['details']
    for eid, ev in evidence.items():
        details[eid] = dict(title=_short(ev.get('quote'), 105), date='', paragraphs=[])
    for stage in graph.get('stages', []):
        details[stage['stage_id']] = dict(title=stage.get('name', ''), date='', paragraphs=[])
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
    overview_refs = {ref.get('context_id') for aid in view['pages'][0]['columns'][1]
                     for ref in records[aid].get('delta_context_refs', [])}
    unassigned = []
    phase_evidence = {}
    for phase in phases:
        pid = phase['phase_id']
        associated = [phase] + [a for a in graph.get('actions', []) if a.get('phase_id') == pid]
        phase_evidence[pid] = set().union(*(passages(item) for item in associated))
    for cid in view['pages'][0]['columns'][2]:
        if cid in overview_refs:
            unassigned.append(cid)
            continue
        record = records[cid]
        span = record.get('time') or {}
        years = set(re.findall(r'\b(?:19|20)\d{2}\b', span.get('text') or ''))
        if not years:
            years = set(re.findall(r'\b(?:19|20)\d{2}\b', record.get('description') or ''))
        scores = []
        for phase in phases:
            pid = phase['phase_id']
            overlap = len(passages(record) & phase_evidence[pid])
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

    # A ContextRef belongs to its owning Phase or Action. Two visible endpoints
    # alone do not establish that the reference applies on another page.
    context_edges = {page['phase']: [e for e in page['edges'] if e['kind'] == 'context']
                     for page in view['pages']}
    all_edges = [
        {'from': item['from_action_id'], 'to': item['to_action_id'], 'type': item['type'],
         'kind': 'relation', 'record': item, 'relation_id': rid}
        for rid, item in relations.items()
    ]
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
        actor = records.get((record.get('actor') or {}).get('entity_id'))
        badges = sorted(source_ids(record), key=lambda key: aliases.get(key, key))
        return {
            'key': nid, 'id': nid, 'kind': kind, 'alias': aliases.get(nid, ''),
            'title': card_label(record, kind, details[nid]['title'], actor),
            'date': _short(details[nid]['date'], 36), 'parties': '',
            'entity_type': record.get('type', 'person') if kind == 'party' else '',
            'badges': [aliases.get(sid, '') for sid in badges], 'box': box,
        }

    def add_parties(cards, body_top, body_end, canvas_width, page_owner, additional, *, reserve_timeline):
        visible = {card['id'] for card in cards} | set(additional)
        actors = list(dict.fromkeys(edge['from'] for edge in all_edges
                                   if edge['kind'] == 'party' and edge['type'] == 'actor'
                                   and edge['to'] in visible))
        related = set()
        for edge in all_edges:
            if edge['kind'] == 'party' and edge['from'] in visible:
                related.add(edge['to'])
        related.update(party for party, entries in uses.items() if
                       any(entry['owner'] in visible or entry['owner'] == page_owner for entry in entries))
        other = [nid for nid in records if kinds.get(nid) == 'party' and nid in related and nid not in actors]
        action_tops = [card['box'][1] for card in cards if card['kind'] == 'action']
        first = min(action_tops, default=body_top + 52)
        for i, nid in enumerate(actors):
            card = make_card(nid, [42, first + i * 138, 148, 108])
            card['caption'] = 'Focal person' if nid == person_id else 'Actor'
            cards.append(card)
        if actors:
            body_end = max(body_end, first + (len(actors) - 1) * 138 + 132)
        # Reuse free slots beside the action rows before adding another row.
        xs = [] if reserve_timeline else sorted({card['box'][0] for card in cards if card['kind'] == 'action'})
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
        edges = [dict(edge) for edge in (*context_edges[pid], *all_edges)
                 if edge['from'] in present and edge['to'] in present]
        owner = pid or graph['event']['event_id']
        local_evidence = set(extra_evidence) | citations.get(owner, set())
        if pid:
            local_evidence.update(citations.get(records[pid].get('stage_id'), ()))
        for card in cards:
            nid = card['id']
            attached = set(citations.get(nid, ()))
            for use in uses.get(nid, []):
                if use['owner'] not in present and use['owner'] != owner:
                    continue
                targets = use['fields']
                if use['label'] in ('Participation', 'Knowledge recipient'):
                    # Evidence attached only to context_id establishes an association,
                    # not the identity or role of any individual party in it.
                    targets = [p for p in targets if p in (use['path'] + '/entity_id', use['path'] + '/role')]
                attached.update(cited_evidence(records[use['owner']], (fields[use['owner']][p] for p in targets)))
            for eid in sorted(attached & eligible, key=evidence_order.get):
                local_evidence.add(eid)
                edges.append({'from': eid, 'to': nid, 'type': 'supports', 'kind': 'evidence'})
        for rid, relation in relations.items():
            if relation['from_action_id'] in present or relation['to_action_id'] in present:
                local_evidence.update(citations.get(rid, ()))
        top = body_end + 30
        columns = max(1, (canvas_width - 38) // 274)
        quotes = {sid: [] for sid in extra_sources}
        eids = sorted(local_evidence, key=evidence_order.get)
        for eid in eids:
            sid = evidence[eid]['source_id']
            if kinds.get(sid) == 'source':
                quotes.setdefault(sid, []).append(eid)
                edges.append({'from': sid, 'to': eid, 'kind': 'evidence', 'type': 'contains'})
        for section, items in [('Evidence', eids), ('Sources', sorted(quotes, key=aliases.get))]:
            if not items:
                continue
            for i, nid in enumerate(items):
                card = make_card(nid, [38 + i % columns * 274, top + 48 + i // columns * 104, 248, 82])
                if section == 'Sources':
                    card['quotes'] = quotes[nid]
                cards.append(card)
            height = 56 + math.ceil(len(items) / columns) * 104
            sections.append({'title': section, 'box': [22, top, canvas_width - 44, height]})
            top += height + 18
        return {
            'phase': pid, 'title': title, 'cards': cards, 'sections': sections,
            'edges': edges, 'height': max(820, top), 'width': canvas_width, 'jumps': phase_links.get(pid, []),
            'relation_slots': relation_slots[pid],
        }

    chronology = ActionChronology(graph, payload)
    plans = []
    relation_slots = {}
    for phase in [None, *phases]:
        pid = phase['phase_id'] if phase else None
        actions = list(next(page for page in view['pages'] if page['phase'] == pid)['columns'][1])
        ordered, timing, _ = chronology.page(actions)
        placement, rows, ticks, ncols = phase_layout(chronology, ordered, timing, aliases, in_phase=phase is not None)
        title = phase['name'] if phase else 'Event background'
        baseline = list(dict.fromkeys(ref['context_id'] for ref in (phase or {}).get('baseline_context_refs', [])
                                      if ref.get('context_id') in records))
        context = phase_context[pid] if pid else unassigned
        has_actor = any(kinds.get((records[aid].get('actor') or {}).get('entity_id')) == 'party'
                        for aid in ordered)
        left = 236 if has_actor else 42
        canvas_width = max(1134, left + (ncols - 1) * 320 + 298,
                           54 + min(6, max(3, math.ceil(math.sqrt(len(context))))) * 360)
        columns = max(1, (canvas_width - 54) // 360)
        cards, sections, shown = [], [], set()
        # Only wires to another Phase need a port below the outline.
        links = sorted(phase_links.get(pid, []), key=lambda link: link['page'])
        ids = [link['relation_id'] for link in links]
        columns_for_labels = max(1, canvas_width // 185)
        slots = {}
        for offset in range(0, len(ids), columns_for_labels):
            row = ids[offset:offset + columns_for_labels]
            for i, rid in enumerate(row):
                slots[rid] = [(i + 0.5) / len(row), 32 + offset // columns_for_labels * 32]
        relation_slots[pid] = slots
        y = 18 + (12 + math.ceil(len(ids) / columns_for_labels) * 32 if ids else 0)
        inline, lane_counts = set(), {}
        if baseline:
            coverage, members = _baseline_coverage(graph, phase, [records[aid] for aid in ordered])
            scoped = _phase_context_edges(context_edges[pid], pid, members)
            context_edges[pid] = scoped
            groups = {}
            for edge in scoped:
                if not edge.get('inherited'):
                    continue
                cid = edge['from']
                if len(ordered) == 1:
                    inline.add(cid)
                group = cid if cid in inline else pid
                lanes = groups.setdefault(group, {})
                edge['scope_lane'] = lanes.setdefault(edge['ref_path'], len(lanes))
            lane_counts = {group: len(lanes) for group, lanes in groups.items()}
            shared_cards = [cid for cid in baseline if cid not in inline]
            if any(pid in (edge['from'], edge['to']) for edge in scoped):
                shared_cards.insert(0, pid)
        else:
            shared_cards = []
        if shared_cards:
            for i, nid in enumerate(shared_cards):
                card = make_card(nid, [42 + i % columns * 360, y + 44 + i // columns * 96, 330, 72])
                if nid in coverage:
                    card['baseline_coverage'] = coverage[nid]
                cards.append(card)
            shown.update(shared_cards)
            end = y + 48 + math.ceil(len(shared_cards) / columns) * 96
            sections.append({'title': 'Shared phase context', 'box': [22, y, canvas_width - 44, end - y]})
            y = end + 20 + 28 * lane_counts.get(pid, 0)
        body_top, shared_count, body_section_index = y, len(cards), len(sections)
        y += 54
        before, after, between = _context_homes(ordered, records, set(context), placement, chronology,
                                               [c for c in baseline if c in inline], shown)

        def place_neighbors(neighbors, top):
            bottom = top
            columns_used = sorted(neighbors)
            centers = [left + col * 320 + 130 for col in columns_used]
            for i, col in enumerate(columns_used):
                cell_left = (centers[i-1] + centers[i]) / 2 if i else left
                cell_right = (centers[i] + centers[i+1]) / 2 if i+1 < len(centers) else canvas_width - 38
                capacity = max(1, int((cell_right - cell_left + 12) // 272))
                items = neighbors[col]
                row_top = top
                for offset in range(0, len(items), capacity):
                    chunk = items[offset:offset + capacity]
                    width = 272 * len(chunk) - 12
                    x = max(cell_left, min(centers[i] - width / 2, cell_right - width))
                    for j, cid in enumerate(chunk):
                        card = make_card(cid, [x + j * 272, row_top, 260, 72])
                        if cid in inline:
                            card.update(phase_inline=True, baseline_coverage=coverage[cid])
                        cards.append(card)
                    row_top += 96 + max(28 * lane_counts.get(cid, 0) for cid in chunk)
                bottom = max(bottom, row_top)
            return bottom

        y = place_neighbors(before, y)
        # The rail separates anchored rows from less precise ones on the same
        # grid. It never divides two Actions with the same open boundary.
        dated_rows = [i for i, row in enumerate(rows) if any(chronology.windows[a]
                      and not timing[a]['conflict'] for a in row['actions'])]
        calendar_end = max((i for i, row in enumerate(rows) if row['band'] == 'calendar'), default=-1)
        axis_row = max(dated_rows, default=calendar_end)
        phase_period = chronology.phase_periods.get(pid)

        def add_axis(top):
            sections.append(dict(title='Action chronology', ticks=ticks, phase_period=phase_period, origin=left + 130,
                                 step=320, box=[22, top, canvas_width - 44, 82]))
            return top + 98

        if phase and not ticks and len(ordered) > 1 and any(c['mark'] == 'scope' for c in placement.values()):
            y = add_axis(y)
        for i, row in enumerate(rows):
            lane = sorted(row['actions'], key=lambda a: placement[a]['column'])
            band = row['band']
            if row['header'] and band in ('relative', 'disputed'):
                label = 'Relative order' if band == 'relative' else 'Order disputed'
                sections.append(dict(kind='action-band', title=label, box=[22, y, canvas_width - 44, 30]))
                y += 40
            for col, cid in between[i].items():
                cards.append(make_card(cid, [left + col * 320, y, 260, 72]))
            for aid in lane:
                cell = placement[aid]
                card = make_card(aid, [left + cell['column'] * 320, y, 260, 90])
                card.update(chronology={**timing[aid], 'placement': cell}, date=_short(timing[aid]['label'], 48))
                cards.append(card)
            y += 132 if any(placement[a]['mark'] for a in lane) else 114
            if ticks and len(ordered) > 1 and i == axis_row:
                y = add_axis(y)
        y = place_neighbors(after, y)
        remaining = list(dict.fromkeys(cid for cid in context if cid not in shown))
        if not cards and not remaining and phase:
            cards.append(make_card(pid, [42, y, 1050, 116]))
            y += 146
        y = add_parties(cards, body_top, y, canvas_width, pid or graph['event']['event_id'], remaining,
                        reserve_timeline=len(rows) > 1)
        if len(cards) > shared_count:
            sections.insert(body_section_index,
                            dict(title='Actions and their context' if ordered else 'Context',
                                 origin=left + 130, step=320, columns=ncols,
                                 box=[22, body_top, canvas_width - 44, y - body_top]))
        else:
            y = body_top
        if remaining:
            top = y + (18 if len(cards) > shared_count else 0)
            for i, cid in enumerate(remaining):
                cards.append(make_card(cid, [42 + i % columns * 360, top + 44 + i // columns * 96, 330, 80]))
            y = top + 44 + math.ceil(len(remaining) / columns) * 96
            sections.append({'title': 'Additional context', 'box': [22, top, canvas_width - 44, y - top]})
        # Keep a source-free plan so uncited evidence can be merged into the
        # existing overview, instead of creating extra views for the same scope.
        plans.append((pid, title, cards, sections, y, canvas_width))
    for pid, title, cards, sections, end, width in plans:
        output.append(finish(pid, title, list(cards), list(sections), end, width))

    used_evidence = {card['id'] for page in output for card in page['cards'] if card['kind'] == 'evidence'}
    unused = [eid for eid in evidence if eid not in used_evidence and eid not in issues]
    displayed_sources = {card['id'] for page in output for card in page['cards'] if card['kind'] == 'source'}
    unused_sources = [s['source_id'] for s in graph.get('sources', []) if s['source_id'] not in displayed_sources]
    if unused or unused_sources:
        pid, title, cards, sections, end, width = plans[0]
        output[0] = finish(pid, title, list(cards), list(sections), end, width, unused, unused_sources)

    for page in output:
        # Assign unique keys to all card instances, including repeated contexts.
        instances = {}
        for i,card in enumerate(page['cards']):
            card['key'] = 'card:' + str(i)
            instances.setdefault(card['id'], []).append(card)
        for edge in page['edges']:
            pairs = [(a,b) for a in instances.get(edge['from'], []) for b in instances.get(edge['to'], [])]
            if pairs:
                a,b = min(pairs,key=lambda pair:abs(pair[0]['box'][0]-pair[1]['box'][0])+abs(pair[0]['box'][1]-pair[1]['box'][1]))
                edge['from_key'],edge['to_key'] = a['key'],b['key']
        page['edges'] = [edge for edge in page['edges'] if 'from_key' in edge]
    return dict(details=details, pages=output, fields=fields, party_uses=uses, aliases=aliases,
                passage_issues=issues)
