"""Display columns and lanes for one Phase, using verified windows and order only."""
from bisect import bisect_left
from collections import Counter, defaultdict
from graphlib import TopologicalSorter
from math import ceil

from .temporal import ActionWindow, time_pairs


def _calendar_ticks(windows):
    """Choose comparable landmarks; keep original endpoints where windows intersect."""
    windows = list(dict.fromkeys(windows))
    by_frame = defaultdict(list)
    for w in windows:
        by_frame[w.offset].append(w)
    probes = []
    for offset, frame in by_frame.items():
        bounds = sorted({d for w in frame for d in (w.start, w.end)})
        for start, end in zip(bounds, bounds[1:]):
            active = [w for w in frame if w.start <= start and w.end >= end]
            if active:
                probes.extend([w for w in active if w.intraday] or [ActionWindow(start, end, offset=offset)])
    # A wide or differently framed window can meet several landmarks. A longest
    # chain offers the most distinct, mutually comparable ticks available.
    probes = list(dict.fromkeys([*probes, *windows]))
    before = {w: [] for w in probes}
    for a, b in time_pairs({w: w for w in probes}):
        before[b].append(a)
    lengths, parent = {}, {}
    for w in TopologicalSorter(before).static_order():
        parent[w] = max(before[w], key=lengths.get, default=None)
        lengths[w] = lengths.get(parent[w], 0) + 1
    tail = max(probes, key=lengths.get, default=None)
    chain = []
    while tail:
        chain.append(tail)
        tail = parent[tail]
    return chain[::-1]


def _calendar_cells(chronology, ordered, info, aliases):
    windows = {aid: w for aid, w in chronology.windows.items() if w and aid not in chronology.conflicts}
    limits = {a: chronology.limits[a] for a in ordered if a in chronology.limits and a not in chronology.conflicts}
    anchors = {}
    used = {a for a in ordered if a in windows}
    local_dates = used.copy()

    def nearest(prior, following):
        return ([b for b in windows if b in prior and chronology.after[b].isdisjoint(prior)],
                [b for b in windows if b in following and not any(b in chronology.after[c] for c in following)])

    for a in ordered:
        if a in windows or a in chronology.conflicts:
            continue
        earlier = {b for b in windows if a in chronology.after[b]}
        later = chronology.after[a] & windows.keys()
        prev, nxt = nearest(earlier, later)
        info[a]['anchor_before'], info[a]['anchor_after'] = prev, nxt
        local_prev, local_next = nearest(earlier & local_dates, later & local_dates)
        # One remote anchor is a relative label, not a tick in this Phase.
        if local_prev or local_next:
            anchors[a] = local_prev, local_next
        elif prev and nxt:
            anchors[a] = prev, nxt
            used.update([*prev, *nxt])
    landmarks = {a: windows[a] for a in windows if a in used}
    landmarks.update({a: landmark for a, (_, landmark, _) in limits.items()})
    ticks = _calendar_ticks(landmarks.values())
    if not ticks:
        return {}, []
    spans = {}
    for a, w in landmarks.items():
        start = next(i for i, t in enumerate(ticks) if not t.before(w))
        end = max(i for i, t in enumerate(ticks) if not w.before(t))
        spans[a] = start, end
    bounds = dict(spans)
    for a, (side, _, _) in limits.items():
        lo, hi = spans[a]
        bounds[a] = (lo, len(ticks)-1) if side == 'start' else (0, hi)
    for a, (prev, nxt) in anchors.items():
        lo, hi = bounds.get(a, (0, len(ticks)-1))
        bounds[a] = (max([lo, *(spans[b][0] for b in prev)]), min([hi, *(spans[b][1] for b in nxt)]))
    for a in ordered:
        if a not in bounds and any(a in chronology.after[b] or b in chronology.after[a] for b in limits):
            bounds[a] = (0, len(ticks)-1)

    cells, slots = {}, set()
    for a in ordered:
        if a not in bounds:
            continue
        first, last = bounds[a]
        earlier = [b for b in bounds if b != a and a in chronology.after[b]]
        later = [b for b in bounds if b in chronology.after[a]]
        low = max([first, *(bounds[b][0] for b in earlier)])
        high = min([last, *(bounds[b][1] for b in later)])
        # Half steps allow a broad window to sit between two finer ticks.
        center = low + high
        note = ''
        if a in anchors:
            prev, nxt = anchors[a]
            labels = []
            if prev:
                labels.append('After ' + ', '.join(aliases[b] for b in prev))
            if nxt:
                labels.append('Before ' + ', '.join(aliases[b] for b in nxt))
            note = ' / '.join(labels)
            if not nxt:
                center = 2 * low + 1
            elif not prev:
                center = 2 * high - 1
        if a in limits:
            # A day may contain several finer ticks. Face its entire boundary
            # period, with independent precedence narrowing the feasible slot.
            lo, hi = spans[a]
            boundary_side = hi if limits[a][0] == 'start' else lo
            center = 2 * max(low, min(boundary_side, high))
        elif a not in windows and a not in anchors:
            note = _anchor_note(a, chronology, aliases)
        # When the date is shared, create only the substeps required by actual
        # precedence. A process arrow never supplies one of these constraints.
        predecessors = [cells[b]['slot'] for b in earlier if b in cells]
        center = max([center, *(s[0] for s in predecessors)])
        substep = max((s[1] + 1 for s in predecessors if s[0] == center), default=0)
        slot = (center, substep)
        slots.add(slot)
        cells[a] = dict(slot=slot, note=note, band='calendar')
    slots.update((2*i, 0) for i in range(len(ticks)))
    # Substeps already encode established order. Only within the same substep
    # does a one-sided card flank the date, with a neutral position for its cap.
    display_slots = {(*slot, 0) for slot in slots}
    for aid, cell in cells.items():
        flank = 0
        if aid in limits:
            flank = -1 if limits[aid][0] == 'end' else 1
        cell['slot'] = (*cell['slot'], flank)
        display_slots.add(cell['slot'])
    positions = {slot: i for i, slot in enumerate(sorted(display_slots))}
    last_at = {center: column for (center, _, flank), column in positions.items() if flank == 0}
    clocks_at = defaultdict(set)
    for a, (lo, hi) in spans.items():
        if a in windows and lo == hi and windows[a].intraday:
            clocks_at[lo].add(windows[a])
    rail = []
    for i, tick in enumerate(ticks):
        label = tick.label({})
        if len(clocks_at[i]) > 1:
            # Nearby clocks/parts in different source frames can share a display
            # column without sharing a proven instant. Keep each time on its card.
            dates = {w.start for w in clocks_at[i]}
            label = (str(tick.start) + ' · ' if len(dates) == 1 else '') + 'See individual action times'
        elif not tick.intraday and tick.offset:
            label += ' · ' + tick.offset
        elif not any(lo <= i <= hi for a, (lo, hi) in spans.items() if a in windows):
            label = ' / '.join(dict.fromkeys(limit[2] for a, limit in limits.items() if spans[a][0] <= i <= spans[a][1]))
        rail.append(dict(column=positions[2*i, 0, 0], label=label))
    for a, cell in cells.items():
        col = positions[cell.pop('slot')]
        first = last = col
        mark = None
        if a in limits:
            side = limits[a][0]
            lo, hi = spans[a]
            mark = 'lower' if side == 'start' else 'upper'
            if side == 'start':
                first, last = rail[lo]['column'], max(col, last_at[2 * (len(ticks)-1)])
            else:
                first, last = min(col, rail[0]['column']), last_at[2 * hi]
            first, last = min(first, col), max(last, col)
        elif a in windows:
            w = windows[a]
            lo, hi = spans[a]
            if a in chronology.durations:
                mark = 'duration'
            elif chronology.actions[a].get('time', {}).get('kind') == 'duration':
                mark, cell['note'] = 'window', 'Duration unverified'
            elif not w.intraday:
                day = (w.end - w.start).days == 1
                if not day or any(b != a and b in windows and b in spans and spans[b][0] <= hi and lo <= spans[b][1]
                                  for b in ordered):
                    mark = 'window'
                    if day:
                        cell['note'] = 'Time within day unresolved'
            if not mark and lo < hi:
                mark = 'window'  # Exact local wording can still have an ambiguous position.
            if mark:
                first = min(col, rail[lo]['column'])
                last = max(col, last_at[2 * hi])
        cell.update(column=col, first=first, last=last, mark=mark)
    return cells, rail


def _anchor_note(aid, chronology, aliases):
    previous = [b for b in chronology.actions if aid in chronology.after[b]]
    following = chronology.after[aid]
    before = [b for b in previous if not chronology.after[b].intersection(previous)]
    after = [b for b in chronology.actions if b in following and not any(b in chronology.after[c] for c in following)]
    return ' / '.join(word + ' ' + ', '.join(aliases[b] for b in group)
                      for word, group in [('After', before), ('Before', after)] if group)


def _relative_components(ids, info):
    remaining = set(ids)
    for seed in ids:
        if seed not in remaining:
            continue
        component = set()
        stack = [seed]
        while stack:
            a = stack.pop()
            if a not in remaining:
                continue
            remaining.remove(a)
            component.add(a)
            stack.extend(info[a]['earlier'] + info[a]['later'])
        yield [a for a in ids if a in component]


def _group_time_slots(chronology, cells, ticks):
    """Widen a crowded, unordered time slot by one card. All dates keep their own tick."""
    candidates = defaultdict(list)
    for aid, cell in cells.items():
        mark = cell['mark']
        if mark not in ('upper', 'lower', 'scope', 'window'):
            continue
        window = chronology.windows[aid]
        time = chronology.actions[aid].get('time') or {}
        if mark == 'window' and (not window or window.intraday or time.get('kind') == 'duration'):
            continue
        precision = (time.get('start_precision'), time.get('end_precision')) if window else None
        key = (cell['column'], cell['first'], cell['last'], mark, cell['note'],
               chronology.limits.get(aid), window, precision, chronology.labels.get(aid))
        candidates[key].append(aid)

    groups = [members for members in candidates.values()
              if len(members) >= 3 and all(chronology.after[a].isdisjoint(members) for a in members)]
    if not groups:
        return
    splits = sorted({cells[members[0]]['column'] for members in groups})

    def left(col):
        return col + bisect_left(splits, col)

    def middle(col):
        return left(col) + (0.5 if col in splits else 0)

    for tick in ticks:
        tick['column'] = middle(tick['column'])
    for cell in cells.values():
        col, lo, hi = cell['column'], cell['first'], cell['last']
        cell['column'] = middle(col)
        if lo == hi and not cell['mark']:
            cell['first'] = cell['last'] = cell['column']
            continue
        # The closed cap of a one-sided limit stays on the date. Open ends
        # and two-ended windows cover the full display width of their slot.
        cell['first'] = middle(lo) if cell['mark'] == 'lower' else left(lo)
        cell['last'] = middle(hi) if cell['mark'] == 'upper' else left(hi) + int(hi in splits)
    for members in groups:
        for i in range(0, len(members), 2):
            pair = members[i:i + 2]
            for j, a in enumerate(pair):
                cell = cells[a]
                cell['card_column'] = cell['column'] + j - (len(pair) - 1) / 2
                # The first card draws the range for both selectable endpoints.
                cell['mark_members'] = pair if j == 0 else []


def _compact_lanes(members, cells, info):
    """Cards and the time brackets below them occupy two different tracks per row."""
    lanes = []
    for a in members:
        cell = cells[a]
        unit = cell.get('mark_members', [a])
        if not unit:
            continue
        columns = [cells[b].get('card_column', cells[b]['column']) for b in unit]
        # Time caps are centred on a tick. Every open end extends under the card.
        span = None
        if cell['mark']:
            span = (cell['first'] - (0 if cell['mark'] == 'lower' else 0.4),
                    cell['last'] + (0 if cell['mark'] == 'upper' else 0.4))
        free = [lane for lane in lanes
                if all(abs(x - y) >= 1 for x in columns for y in lane['columns'])
                and (not span or all(span[0] > hi or span[1] < lo for lo, hi in lane['spans']))]
        if free:
            predecessors = {b for member in unit for b in info[member]['earlier']}
            lane = next((lane for lane in free if not predecessors.isdisjoint(lane['actions'])), free[0])
        else:
            lane = dict(actions=[], columns=[], spans=[])
            lanes.append(lane)
        lane['actions'].extend(unit)
        lane['columns'].extend(columns)
        if span:
            lane['spans'].append(span)
    return [lane['actions'] for lane in lanes]


def phase_layout(chronology, ordered, info, aliases, *, in_phase=True):
    """Assign every Action exactly once. Row numbers have no temporal meaning."""
    cells, ticks = _calendar_cells(chronology, ordered, info, aliases)
    order_index = {a: i for i, a in enumerate(chronology.actions)}
    # Give the clearest sequence first choice of a row.
    dated = sorted((a for a in cells if a not in chronology.limits),
                   key=lambda a: (cells[a]['last'] - cells[a]['first'], cells[a]['column'], order_index[a]))
    limited = sorted((a for a in cells if a in chronology.limits),
                     key=lambda a: (cells[a]['column'], chronology.limits[a][0],
                                    chronology.limits[a][1].start, order_index[a]))
    remaining = [a for a in ordered if a not in cells and not info[a]['conflict']]
    unplaced = []
    chains = []
    for component in _relative_components(remaining, info):
        if len(component) == 1:
            unplaced.extend(component)
            continue
        for a in component:
            col = max((cells[b]['column'] + 1 for b in info[a]['earlier'] if b in component), default=0)
            cells[a] = dict(column=col, first=col, last=col, band='relative', mark=None, note='Relative order')
        chains.append(('relative', component))
    last_col = max([0, *(t['column'] for t in ticks), *(c['last'] for c in cells.values())])
    scope_band = 'phase' if in_phase else 'undated'
    for a in unplaced:
        note = _anchor_note(a, chronology, aliases) or ('Phase only' if in_phase else 'Date unknown')
        cells[a] = dict(column=last_col / 2, first=0, last=last_col, band=scope_band,
                        mark='scope' if in_phase else None, note=note)
    disputed = [a for a in ordered if info[a]['conflict']]
    for a in disputed:
        cells[a] = dict(column=last_col / 2, first=0, last=last_col, band='disputed', mark=None, note='Order disputed')
    bands = [('timeline', dated + limited + unplaced), *chains, ('disputed', disputed)]

    _group_time_slots(chronology, cells, ticks)
    rows = []
    for band, members in bands:
        column_counts = Counter((cells[a]['band'], cells[a]['column']) for a in members)
        for a in members:
            cell = cells[a]
            if column_counts[cell['band'], cell['column']] > 1:
                if cell['band'] == 'relative':
                    cell['note'] = 'Order within branch group unresolved'
                elif cell['band'] == 'calendar' and not cell['note'] and not cell['mark']:
                    cell['note'] = 'Order within group unresolved'
        lanes = _compact_lanes(members, cells, info)
        if band == 'timeline':
            # Keep the main lane in the middle. Additional lanes alternate
            # below and above it; vertical position makes no assertion.
            above = list(reversed(lanes[2::2]))
            lanes = above + lanes[:1] + lanes[1::2]
        for i, lane in enumerate(lanes):
            for a in lane:
                cells[a]['row'] = len(rows)
            rows.append(dict(band=band, header=i == 0, actions=lane))
    columns = ceil(max([0, *(t['column'] for t in ticks), *(c['last'] for c in cells.values())])) + 1
    return cells, rows, ticks, columns
