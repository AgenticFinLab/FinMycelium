"""Read-only chronological placement for the native Phase diagram."""
from collections import defaultdict
from datetime import date, timedelta

from .temporal import ActionWindow, descendants, time_pairs
from .validation import SupportIndex, order_view


def _calendar_limit(action, support):
    """A sole supported boundary is a landmark, never an occurrence interval."""
    time = action.get('time') or {}
    sides = [side for side in ('start', 'end') if time.get(side)]
    if len(sides) != 1 or not support.relative_inference_valid(action):
        return None
    side, = sides
    if not support.supported('actions', action['action_id'], '/time/' + side):
        return None
    if 'anchor_source_id' in time and not support.publication_anchor_valid(action):
        return None
    try:
        endpoint = date.fromisoformat(time[side])
        day = endpoint if side == 'start' else endpoint - timedelta(days=1)
        landmark = ActionWindow(day, day + timedelta(days=1))
    except (OverflowError, ValueError, TypeError):
        return None
    precision = time.get(side + '_precision')
    month = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')[day.month-1]
    if precision == 'year':
        label = str(day.year)
    elif precision == 'month':
        label = f'{month} {day.year}'
    elif precision == 'day':
        label = f'{day.day} {month} {day.year}'
    else:
        return None
    return side, landmark, ('From ' if side == 'start' else 'By ') + label


class ActionChronology:
    """Project comparable dates and evidenced order paths onto each Phase."""
    def __init__(self, graph, payload=None):
        support = SupportIndex(graph, payload, partial=True)
        order = order_view(graph, support=support)
        self.actions = support.records['actions']
        self.phase_periods = {pid: (phase['time']['start'], phase['time']['end'])
                              for pid, phase in support.records['phases'].items()
                              if isinstance(phase.get('time'), dict) and support.time_ready('phases', pid)}
        self.labels = {}
        self.windows = {aid: support.action_window(aid, legacy=True) for aid in self.actions}
        self.limits = {}
        self.durations = {aid for aid in self.actions if support.supported_duration(aid)}
        for aid, window in self.windows.items():
            if window:
                self.labels[aid] = window.label(self.actions[aid]['time'])
            elif limit := _calendar_limit(self.actions[aid], support):
                self.limits[aid] = limit
                self.labels[aid] = limit[2]
        self.conflicts = {aid for aid in self.actions
                          if any(p in ('', '/time') or p.startswith('/time/') for p in
                                 support.disputed.get(('actions', aid), ()))}
        edges = defaultdict(set)
        usable = set(order['relation_ids'])
        for r in graph.get('relations', []):
            rid = r.get('relation_id')
            first, second = r['from_action_id'], r['to_action_id']
            if rid in usable:
                edges[first].add(second)
            if set(order['excluded'].get(rid, ())) & {
                'known_time_conflict', 'declared_conflict', 'precedence_cycle', 'unresolved_time_premise',
                'time_path_conflict', 'order_unknown_conflict'
            }:
                self.conflicts.update((first, second))
        for first, second in time_pairs(self.windows):
            edges[first].add(second)
        # A grounded chain A → undated B → C can still contradict the date of A.
        # Remove every member of such a cycle from placement and keep all raw links.
        reach = {a: descendants(edges, a) for a in self.actions}
        self.conflicts.update(a for a in self.actions if a in reach[a])
        # Check a recorded path against independently supported limits. A limit
        # alone never creates a path, even when its landmark is on the axis.
        earliest = {a: w for a, w in self.windows.items() if w}
        latest = earliest.copy()
        for a, (side, landmark, _) in self.limits.items():
            (earliest if side == 'start' else latest)[a] = landmark
        for a, targets in reach.items():
            for b in targets:
                if (a in self.limits or b in self.limits) and a in earliest and b in latest and latest[b].before(earliest[a]):
                    self.conflicts.update((a, b))
                    self.conflicts.update(c for c in targets if b in reach[c])
        for r in graph.get('relations', []):
            if r.get('type') == 'order_unknown':
                a, b = r['from_action_id'], r['to_action_id']
                if ((a in reach.get(b, ()) or b in reach.get(a, ())) and
                        all(support.supported('relations', r.get('relation_id'), '/' + key)
                            for key in ('from_action_id', 'to_action_id', 'type'))):
                    self.conflicts.update((a, b))
        clean = {a: targets - self.conflicts for a, targets in edges.items() if a not in self.conflicts}
        self.after = {a: descendants(clean, a) for a in self.actions}
        self.steps = defaultdict(list)
        for r in graph.get('relations', []):
            a, b = r['from_action_id'], r['to_action_id']
            if r.get('relation_id') in usable and not {a, b} & self.conflicts:
                for end in (a, b):
                    self.steps[end].append(r['relation_id'])

    def page(self, actions):
        visible = set(actions)
        info = {}
        for aid in actions:
            previous = [b for b in actions if aid in self.after[b]]
            following = [b for b in actions if b in self.after[aid]]
            unknown = visible - {aid, *previous, *following}
            w = self.windows[aid]
            by_time = [b for b in previous if w and self.windows[b] and self.windows[b].before(w)]
            by_time.extend(b for b in following if w and self.windows[b] and w.before(self.windows[b]))
            info[aid] = dict(label=self.labels.get(aid, ''), earlier=previous, later=following,
                             unordered=[b for b in actions if b in unknown],
                             conflict=aid in self.conflicts, by_time=by_time, order_steps=self.steps[aid])
        # Topological frontiers are antichains. Physical adjacency, also between
        # successive frontiers, conveys no ordering beyond the reachability above.
        pending = [a for a in actions if info[a]['earlier'] or info[a]['later']]
        groups = []
        while pending:
            remaining = set(pending)
            ready = [a for a in pending if remaining.isdisjoint(info[a]['earlier'])]
            groups.append(ready)
            pending = [a for a in pending if a not in ready]
        unplaced = [a for a in actions if not info[a]['earlier'] and not info[a]['later']
                    and not info[a]['conflict']]
        disputed = [a for a in actions if info[a]['conflict']]
        display = []
        for group in groups + [unplaced, disputed]:
            if not group:
                continue
            for aid in group:
                item = info[aid]
                if item['conflict']:
                    item['note'] = 'Order disputed'
                elif len(actions) > 1 and not item['earlier'] and not item['later']:
                    item['note'] = 'Relative order unresolved'
                elif item['unordered']:
                    item['note'] = 'Partly ordered'
                else:
                    item['note'] = ''
            display.extend(group)
        rail = [dict(kind='ordered' if len(group) == 1 else 'unordered', actions=group) for group in groups]
        if unplaced:
            rail.append(dict(kind='unplaced', actions=unplaced))
        if disputed:
            rail.append(dict(kind='disputed', actions=disputed))
        return display, info, rail
