"""Expanded Event → Stage → Phase → Action view, projected from saved facts only."""
from datetime import timedelta
from html import escape
import json
from pathlib import Path

import plotly.graph_objects as go
from plotly.offline import get_plotlyjs

from ..visualizer_gantt import _script_json, _wrapped
from .records import compose_context, index_records, json_bytes, sha256
from .schema import COLLECTION_IDS
from .validation import check_graph, interval, order_view


def event_view(graph, graph_sha256=None):
    report = check_graph(graph, complete=False)
    if any(i['code'] == 'SCHEMA_INVALID' for i in report['issues']):
        raise ValueError('Cannot render an invalid person Event shape')
    indexes = index_records(graph)
    items, rows, used = [], [], set()

    def item(collection, record, level=0, plotted=False):
        key = record[COLLECTION_IDS[collection]] if collection in COLLECTION_IDS else record[collection + '_id']
        reference = collection + ':' + key
        seen, supports = set(), {}

        def collect(value):
            if isinstance(value, list):
                for child in value:
                    collect(child)
            elif isinstance(value, dict):
                for support in value.get('support', []):
                    for eid in support['evidence_ids']:
                        supports.setdefault(eid, []).append(dict(field_path=support['target'], evidence_set_id=support['mode']))
                    for premise in support.get('premise_refs', []):
                        identity = (premise['collection'], premise['object_id'])
                        if identity not in seen:
                            seen.add(identity)
                            collect(indexes.get(identity[0], {}).get(identity[1], {}))
                for field, child in value.items():
                    if field not in ('support', 'evidence'):
                        collect(child)
        collect(record)
        fields = {'ID': key, 'Native record': json.dumps(record, ensure_ascii=False, indent=2)}
        if collection == 'actions':
            derived = compose_context(graph, key)
            fields['Effective Context'] = json.dumps(derived, ensure_ascii=False, indent=2)
            for entry in derived['associations']:
                collect(entry['reference'])
                collect(indexes['contexts'].get(entry['reference']['context_id'], {}))
        evidence = []
        for eid, references in supports.items():
            ev = indexes['evidence'].get(eid)
            if not ev:
                continue
            source = indexes['sources'].get(ev['source_id'], {})
            evidence.append(dict(span_id=eid, quote=ev['quote'], references=references,
                title=source.get('title') or source.get('origin'), url=source.get('url'), published_at=source.get('published_at'),
                document_id=ev['sample_id'] if ev['location_status'] == 'matched' else None,
                char_start=ev['start'], char_end=ev['end']))
        label = {'event': 'Event', 'stages': 'Stage', 'phases': 'Phase', 'actions': 'Action',
                 'contexts': 'Context', 'relations': 'Relation'}[collection]
        title = record.get('name') or record.get('description') or record.get('type') or key
        entry = dict(key=reference, kind=label, title=title, fields=fields, evidence=evidence, level=level)
        items.append(entry)
        if plotted:
            when = interval(record)
            if when and when[0] >= when[1]:
                when = None
            entry.update(interval=when, time=record.get('time', {}), record=record)
            rows.append(entry)
        return entry

    item('event', graph['event'], plotted=True)
    for stage in graph['stages']:
        item('stages', stage, 1, True)
        for phase in graph['phases']:
            if phase['stage_id'] != stage['stage_id']:
                continue
            item('phases', phase, 2, True)
            used.add(('phases', phase['phase_id']))
            for action in graph['actions']:
                if action['phase_id'] == phase['phase_id']:
                    item('actions', action, 3, True)
                    used.add(('actions', action['action_id']))
    for collection, level in [('phases', 2), ('actions', 3)]:
        for record in graph[collection]:
            if (collection, record[COLLECTION_IDS[collection]]) not in used:
                item(collection, record, level, True)
    for collection in ('contexts', 'relations'):
        for record in graph[collection]:
            item(collection, record)
    # Unknown records retain hierarchy labels but do not acquire invented axis dates.
    dated = [r for r in rows if r['interval']]
    undated = [r for r in rows if not r['interval']]
    return dict(items=items, rows=dated + undated, undated_count=len(undated),
                graph_sha256=graph_sha256 or sha256(json_bytes(graph)), checks=report)


def render_event(graph, graph_sha256=None, *, result_status=None):
    view = event_view(graph, graph_sha256)
    fig = go.Figure()
    points = [p for row in view['rows'] if row['interval'] for p in row['interval']]
    low, high = (min(points), max(points)) if points else (None, None)
    pad = max((high-low)*0.04, timedelta(days=1)) if points else None
    colors = {'Event': '#22465e', 'Stage': '#6e9eb9', 'Phase': '#aacad9', 'Action': '#356e9b'}
    labels, positions = [], {}
    for y, row in enumerate(view['rows']):
        labels.append(_wrapped('  ' * row['level'] + row['kind'] + ' · ' + row['title']))
        span = row['interval']
        if span:
            a, b = span
            duration = row['time'].get('kind') == 'duration'
            point = row['kind'] == 'Action' and not duration and b-a == timedelta(days=1) and row['time'].get('start_precision') == 'day'
            xs = [a] if point else [a, b]
            fig.add_trace(go.Scatter(x=xs, y=[y]*len(xs), mode='markers' if point else 'lines+markers',
                line=dict(color=colors[row['kind']], width=12 if row['kind'] in ('Event', 'Stage') else 7 if row['kind'] == 'Phase' else 4,
                          dash='solid' if duration else 'dot'),
                marker=dict(color=colors[row['kind']], size=10 if point else 5), customdata=[row['key']]*len(xs),
                hovertext=escape(row['title'] + ' · ' + str(row['time'].get('text') or 'Recorded interval') +
                                 ' · ' + row['time'].get('kind', 'unknown')),
                hovertemplate='%{hovertext}<extra></extra>', showlegend=False))
            if row['kind'] == 'Action':
                positions[row['record']['action_id']] = (a, y)
        else:
            fig.add_annotation(x=0.01, xref='paper', y=y, text='Time unknown / not placed', showarrow=False,
                               xanchor='left', font=dict(color='#6e777e', size=11))
    usable = set(order_view(graph)['relation_ids'])
    for relation in graph['relations']:
        if relation['type'] == 'precedes' and relation['relation_id'] not in usable:
            continue
        a, b = positions.get(relation['from_action_id']), positions.get(relation['to_action_id'])
        if not a or not b:
            continue
        fig.add_trace(go.Scatter(x=[a[0], b[0]], y=[a[1], b[1]], mode='lines',
            line=dict(color='#8799a7', width=1, dash='dot' if relation['basis'] == 'inferred' else 'dash'),
            customdata=['relations:' + relation['relation_id']]*2,
            hovertext=escape(relation['type'] + ' · ' + relation['basis']), hoverinfo='text', showlegend=False))
        fig.add_annotation(x=b[0], y=b[1], ax=a[0], ay=a[1], xref='x', yref='y', axref='x', ayref='y',
                           showarrow=True, arrowhead=2, arrowwidth=1, arrowcolor='#8799a7', text='')
    fig.update_layout(template='plotly_white', height=max(420, 160 + len(view['rows'])*54),
        margin=dict(l=280, r=30, t=35, b=60), dragmode='pan', hovermode='closest',
        font=dict(family='Arial, sans-serif', size=12, color='#223440'),
        xaxis=dict(type='date' if points else 'linear', range=[low-pad, high+pad] if points else [0, 1],
                   title='Recorded time' if points else 'No supported complete intervals', showticklabels=bool(points), zeroline=False),
        yaxis=dict(tickvals=list(range(len(labels))), ticktext=labels, range=[len(labels)-0.3, -0.7], fixedrange=True, zeroline=False))
    data = dict(items=[{k: v for k, v in item.items() if k in ('key', 'kind', 'title', 'fields', 'evidence')} for item in view['items']],
        title=graph['event']['name'], person=graph['person']['name'], storyline=graph['storyline']['name'], event_id=graph['event']['event_id'],
        graph_sha256=view['graph_sha256'], counts=dict(stages=len(graph['stages']), phases=len(graph['phases']), activities=len(graph['actions']),
            undated=view['undated_count'], unassigned=sum(a['phase_id'] is None for a in graph['actions']), sources=len(graph['sources'])),
        stat_labels=[['stages', 'stages'], ['phases', 'phases'], ['activities', 'actions'], ['undated', 'without plotted dates'], ['unassigned', 'unassigned actions'], ['sources', 'sources']],
        result_label='Partial result · unfinished work remains' if result_status == 'partial' or not check_graph(graph)['valid'] else 'Draft · content review pending',
        timeline_help='Event, Stage, Phase and Action rows are expanded. Select a plotted record or use the list to inspect Context, support, conflicts and sources.',
        time_help='Bars use each record’s own supported interval. Dotted occurrence windows are not continuous activity. Unknown times are listed separately. Conflicting precedence claims remain in the record list and do not define plotted order.')
    template = Path(__file__).parents[1].joinpath('gantt.html').read_text()
    before, after = template.split('/*__PERSON_GANTT_DATA__*/')
    html = before + 'const model = ' + _script_json(data) + ';\nconst figure = ' + _script_json(json.loads(fig.to_json())) + ';' + after
    return html.replace('/*__PLOTLY_BUNDLE__*/', get_plotlyjs(), 1)
