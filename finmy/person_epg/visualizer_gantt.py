"""Expanded single-event Gantt over the native Person EPG tables.

Reuses the full event visualizer's participant/relation styling and Plotly
presentation. Native activities are not converted into EventCascade episodes.
Rendering is deterministic and does not fetch sources or invoke a model.
"""
from collections import defaultdict
from datetime import timedelta
from html import escape
import json
import math
from pathlib import Path
import textwrap

import plotly.graph_objects as go
from plotly.offline import get_plotlyjs

from finmy.builder.agent_build.visualizer_gantt import EventCascadeGanttVisualizer
from finmy.search.state import digest
from .time_utils import date_interval
from .validation import validate_person_epg


def _index(rows, key):
    return {row[key]: row for row in rows}


def _group(rows, key):
    result = defaultdict(list)
    for row in rows:
        result[row[key]].append(row)
    return result


def _time(row):
    if not row:
        return {'label': 'Unknown', 'interval': None}
    window = row.get('window_start') and row.get('window_end')
    value = {'time_window': {'start': row['window_start'], 'end': row['window_end']}} if window else row['value']
    interval = date_interval(value)
    label = row.get('original_text') or row['value']
    if window:
        label += f" [{row['window_start']} – {row['window_end']}; {row.get('window_semantics') or 'time window'}]"
    if row.get('is_approximate'):
        label += ' (approximate)'
    if not interval:
        label += ' (not placed on the time axis)'
    return {'label': label, 'interval': interval}


def event_view(package):
    """A read-only display projection; every item keeps its native identifiers."""
    if package.get('schema_version') == 'person-event-1.0':
        from .event.rendering import event_view as person_event_view
        return person_event_view(package)
    result = validate_person_epg(package)
    if not result['valid']:
        raise ValueError('Invalid native person graph: ' + str(result['errors'][:2]))
    if len(package['event']) != 1 or len(package['domain']) != 1:
        raise ValueError('Choose a native graph containing exactly one event and one storyline')
    event = package['event'][0]
    entities = _index(package['entity'], 'entity_id')
    occurrences = _index(package['occurrence'], 'occurrence_id')
    actions = _index(package['action'], 'action_id')
    transactions = _index(package['financial_transaction'], 'transaction_id')
    times = _index(package['time_value'], 'time_id')
    memberships = _index(package['event_activity'], 'activity_id')
    details = _group(package['activity_detail'], 'activity_id')
    instruments = _group(package['transaction_instrument'], 'transaction_id')
    participants = _group(package['occurrence_participant'], 'occurrence_id')
    participations = _group(package['participation'], 'occurrence_id')
    selected_details = _group(package['event_activity_detail'], 'activity_id')
    relations = _index(package['entity_relation'], 'relation_id')
    scoped_relations = _group(package['relation_occurrence'], 'occurrence_id')
    documents = _index(package['source_document'], 'document_id')
    spans = _index(package['evidence_span'], 'span_id')
    evidence_links = _group(package['evidence_link'], 'evidence_set_id')

    def evidence(records):
        found, seen = {}, set()
        for record in records:
            for link in evidence_links.get(record.get('evidence_set_id'), []):
                key = (link['evidence_set_id'], link['field_path'], link['span_id'])
                if key in seen:
                    continue
                seen.add(key)
                span = spans[link['span_id']]
                doc = documents.get(span.get('document_id'), {})
                entry = found.setdefault(span['span_id'], {**span, 'title': doc.get('title'), 'url': doc.get('source_url'),
                                                          'published_at': doc.get('published_at'), 'references': []})
                entry['references'].append({k: link[k] for k in ('evidence_set_id','field_path','quote_order')})
        return list(found.values())

    def item(key, kind, title, records, fields=None):
        return dict(key=key, kind=kind, title=title, fields=fields or {}, evidence=evidence(records))

    items = [item('event:' + event['event_id'], 'Event', event['label'], [event],
                  {'Event ID': event['event_id'], 'Summary': event.get('summary')})]
    stage_items = {}
    for stage in sorted(package['stage'], key=lambda r: r['sort_order']):
        entry = item('stage:' + stage['stage_id'], 'Stage', stage['label'], [stage],
                     {'Stage ID': stage['stage_id'], 'Summary': stage.get('summary'), 'Boundary': stage.get('boundary_reason')})
        stage_items[stage['stage_id']] = entry
        items.append(entry)

    activities = []
    for activity in package['activity']:
        aid = activity['activity_id']
        member = memberships.get(aid, {})
        if activity['action_id']:
            fact = actions[activity['action_id']]
            kind, title = 'Action', fact['action_type']
            roles = {fact['actor_id']: 'Actor'}
        elif activity['transaction_id']:
            fact = transactions[activity['transaction_id']]
            kind, title = 'Transaction', fact['name']
            roles = {eid: role for eid, role in [(fact.get('from_entity_id'), 'From'), (fact.get('to_entity_id'), 'To')] if eid}
        else:
            fact = occurrences[activity['context_occurrence_id']]
            kind, title, roles = 'Context', fact['title'], {}
        occurrence = occurrences[fact['occurrence_id']]
        oid = occurrence['occurrence_id']
        retained = sorted(details[aid], key=lambda r: r['detail_index'])
        detail_mode = member.get('detail_mode') or 'all'
        if detail_mode == 'selected':
            selected = {r['detail_index'] for r in selected_details[aid]}
            shown = [r for r in retained if r['detail_index'] in selected]
        else:
            shown = retained
        inst = instruments.get(activity['transaction_id'], [])
        if kind == 'Context':
            start = _time(times.get(fact.get('start_time_id')))
            end = _time(times.get(fact.get('end_time_id')))
            a, b = start['interval'], end['interval']
            interval = (a[0], b[1], 'duration') if a and b and a[0] <= b[1] else (a or b)
            time_label = start['label'] + ' → ' + end['label']
            if not (a and b):
                time_label += ' (open boundary)'
            if a and b and a[0] > b[1]:
                interval = None
                time_label += ' (inverted range; not placed on the time axis)'
        else:
            when = _time(times.get(fact.get('timestamp_time_id')))
            interval, time_label = when['interval'], when['label']
        people = {p['entity_id'] for p in participants[oid]} | set(roles)
        for p in participations[oid]:
            people.add(p['entity_id'])
            roles.setdefault(p['entity_id'], p['role'])
        edges = []
        if kind == 'Transaction' and fact.get('from_entity_id') and fact.get('to_entity_id'):
            edges.append(dict(source=fact['from_entity_id'], target=fact['to_entity_id'], label=fact['name']))
        for link in scoped_relations[oid]:
            relation = relations[link['relation_id']]
            people.update([relation['from_entity_id'], relation['to_entity_id']])
            edges.append(dict(source=relation['from_entity_id'], target=relation['to_entity_id'], label=relation['relation_type']))
        entry = item('activity:' + aid, kind, member.get('display_title') or title,
                     [fact, occurrence, *shown, *inst, *participations[oid]],
                     {'Activity ID': aid, 'Fact ID': activity['action_id'] or activity['transaction_id'] or oid,
                      'Occurrence': occurrence['title'] + ' · ' + oid, 'Time': time_label,
                      'Placement': 'In this event' if member else 'Retained fact; not assigned to this event',
                      'Person relevance': occurrence['subject_relevance'],
                      'Details': [r['value'] for r in shown] + (fact.get('details') or []),
                      'Instruments': [r['description'] for r in inst],
                      'Participants': [entities[e]['name'] + ' · ' + roles.get(e, 'Occurrence participant') for e in sorted(people)]})
        entry.update(activity_id=aid, stage_id=member.get('stage_id'), assigned=bool(member), interval=interval,
                     time_label=time_label, participants=[dict(**entities[e], role=roles.get(e, 'Occurrence participant')) for e in sorted(people)],
                     edges=edges, order=member.get('sort_order', 0))
        activities.append(entry)
        items.append(entry)
    for relation in package['activity_relation']:
        items.append(item('activity-relation:' + relation['link_id'], 'Activity relation',
                          relation.get('relation_type') or 'Relation', [relation],
                          {k: relation.get(k) for k in ('link_id','from_activity_id','to_activity_id','description','basis')}))
    for relation in package['entity_relation']:
        items.append(item('entity-relation:' + relation['relation_id'], 'Entity relation', relation['relation_type'], [relation],
                          {'Relation ID': relation['relation_id'], 'From': entities[relation['from_entity_id']]['name'],
                           'To': entities[relation['to_entity_id']]['name'],
                           'Time': _time(times.get(relation.get('valid_from_time_id')))['label'] + ' → ' + _time(times.get(relation.get('valid_to_time_id')))['label']}))
    return dict(event=event, person=entities[package['graph']['subject_entity_id']], storyline=package['domain'][0],
                stages=stage_items, activities=activities, items=items, relations=package['activity_relation'],
                graph_sha256=digest(package), source_count=len(documents))


def _wrapped(value, width=32):
    label = textwrap.shorten(str(value), width=width*2, placeholder='…')
    return '<br>'.join(escape(s) for s in textwrap.wrap(label, width=width))


class PersonEventGanttVisualizer(EventCascadeGanttVisualizer):
    """Full stage/activity timeline with the original renderer's entity styles."""

    def plot_event(self, view):
        fig = go.Figure()
        activities = [a for a in view['activities'] if a['assigned']]
        groups = list(view['stages'])
        if any(a['stage_id'] is None for a in activities):
            groups.append(None)
        rows = []
        for sid in groups:
            members = sorted([a for a in activities if a['stage_id'] == sid], key=lambda a: a['order'])
            stage = view['stages'].get(sid, dict(key='unstaged', title='Not assigned to a stage', kind='Stage', evidence=[]))
            spans = [a['interval'] for a in members if a['interval']]
            rows.append({**stage, 'interval': (min(s[0] for s in spans), max(s[1] for s in spans), 'stage') if spans else None,
                         'time_label': f'Span of dated activities; {len(members) - len(spans)} without a plottable time', 'participants':[], 'edges':[]})
            rows.extend(members)
        points = [t for row in rows if row['interval'] for t in row['interval'][:2]]
        lower, upper = (min(points), max(points)) if points else (None, None)
        pad = max((upper-lower)*0.04, timedelta(hours=12)) if points else None
        precision = {r['interval'][2] for r in activities if r['interval']}
        tickformat = '%Y' if precision == {'year'} else '%b %Y' if precision <= {'year','month'} else '%d %b %Y'
        if 'datetime' in precision:
            tickformat = '%d %b %Y<br>%H:%M'
        tick_step = 86400000 if points and 'datetime' not in precision and upper-lower < timedelta(days=4) else None
        positions = {}
        participant_legend, relation_legend = set(), set()
        labels = []
        for y, row in enumerate(rows):
            labels.append(_wrapped(('Stage · ' if row['kind']=='Stage' else row['kind']+' · ') + row['title']))
            hover = '<b>' + escape(row['title']) + '</b><br>' + escape(row['time_label']) + '<br>' + escape(row['key'])
            span = row['interval']
            if span:
                a, b, precision = span
                dated_point = row['kind'] != 'Stage' and precision in {'day', 'datetime'}
                color = '#a8d5e8' if row['kind']=='Stage' else '#356e9b' if row['kind']=='Action' else '#af7327' if row['kind']=='Transaction' else '#657781'
                fig.add_trace(go.Scatter(x=[a] if dated_point else [a,b], y=[y] if dated_point else [y,y],
                    mode='markers' if dated_point else 'lines+markers',
                    line=dict(color=color, width=14 if row['kind']=='Stage' else 5,
                              dash='solid' if precision in {'stage','duration'} else 'dot'),
                    marker=dict(color=color, symbol='diamond' if row['kind']=='Transaction' else 'circle', size=10 if dated_point else 5),
                    customdata=[row['key']]*(1 if dated_point else 2), hovertext=hover,
                    hovertemplate='%{hovertext}<extra></extra>', showlegend=False))
                positions[row.get('activity_id')] = (a, y)
            else:
                fig.add_annotation(x=0.015, xref='paper', y=y, text='Time not placed', showarrow=False,
                                   xanchor='left', font=dict(color='#6e777e', size=11))
            people = row['participants']
            # As in the full event graph, distribute entity glyphs with a sine
            # offset. Their separate, non-temporal lane cannot imply action dates.
            slots = {p['entity_id']: ((i+1)/(len(people)+1), y+0.16*math.sin(i*2.4)) for i,p in enumerate(people)}
            for edge_number, edge in enumerate(row['edges']):
                sx, sy = slots[edge['source']];tx, ty = slots[edge['target']]
                color, dash = self._get_relation_style(edge['label'])
                bend = y-0.30-(edge_number%3)*0.045
                t = [i/24 for i in range(25)]
                xs = [(1-v)**2*sx+2*(1-v)*v*(sx+tx)/2+v*v*tx for v in t]
                ys = [(1-v)**2*sy+2*(1-v)*v*bend+v*v*ty for v in t]
                fig.add_trace(go.Scatter(x=xs,y=ys,xaxis='x2',mode='lines',line=dict(color=color,dash=dash,width=1.5),
                    hovertext=escape(edge['label']),hoverinfo='text',name=escape(edge['label']),
                    showlegend=edge['label'] not in relation_legend,legendgroup='rel:'+edge['label'],
                    customdata=[row['key']]*len(xs)))
                fig.add_annotation(x=tx,y=ty,xref='x2',yref='y',ax=xs[-4],ay=ys[-4],axref='x2',ayref='y',
                                   showarrow=True,arrowhead=2,arrowsize=1,arrowwidth=1.5,arrowcolor=color,text='')
                relation_legend.add(edge['label'])
            for p in people:
                x, py = slots[p['entity_id']]
                color, symbol = self._get_participant_style(p['entity_id'], p['entity_type'])
                fig.add_trace(go.Scatter(x=[x],y=[py],xaxis='x2',mode='markers',
                    marker=dict(color=color,symbol=symbol,size=9,line=dict(color='#fff',width=1)),
                    name=escape(p['name']),legendgroup='entity:'+p['entity_id'],showlegend=p['entity_id'] not in participant_legend,
                    customdata=[row['key']],hovertext=escape(p['name']+' · '+p['role']+' · '+p['entity_id']),
                    hovertemplate='%{hovertext}<extra></extra>'))
                participant_legend.add(p['entity_id'])
        for relation in view['relations']:
            a, b = positions.get(relation['from_activity_id']), positions.get(relation['to_activity_id'])
            if not a or not b:
                continue  # Its complete native record remains selectable below.
            label = relation.get('relation_type') or 'Relation'
            color, dash = self._get_relation_style(label)
            if relation['basis'] == 'inferred':
                dash = 'dot'
            fig.add_trace(go.Scatter(x=[a[0],b[0]],y=[a[1],b[1]],mode='lines',line=dict(color=color,dash=dash,width=1),
                hovertext=escape(label+' · '+relation['basis']),hoverinfo='text',name=escape(label),showlegend=label not in relation_legend,
                customdata=['activity-relation:'+relation['link_id']]*2))
            fig.add_annotation(x=b[0],y=b[1],ax=a[0],ay=a[1],xref='x',yref='y',axref='x',ayref='y',
                               showarrow=True,arrowhead=2,arrowwidth=1,arrowcolor=color,text='')
            relation_legend.add(label)
        fig.update_layout(template='plotly_white', height=max(420, 170+len(rows)*68),
            margin=dict(l=260,r=24,t=50,b=90),dragmode='pan',hovermode='closest',
            font=dict(family='Arial, sans-serif',size=12,color='#223440'),
            xaxis=dict(type='date' if points else 'linear',domain=[0,0.68],title='Time' if points else 'No dated activities',
                       range=[lower-pad, upper+pad] if points else [0,1],showticklabels=bool(points),showgrid=bool(points),zeroline=False,
                       tickformat=tickformat if points else None,dtick=tick_step),
            xaxis2=dict(domain=[0.73,1],range=[0,1],fixedrange=True,showgrid=False,zeroline=False,showticklabels=False,
                        title='Participants & transactions'),
            yaxis=dict(tickvals=list(range(len(rows))),ticktext=labels,range=[len(rows)-0.3,-0.7],fixedrange=True,zeroline=False),
            legend=dict(orientation='h',y=-0.13,x=0,font=dict(size=11)),
            shapes=[dict(type='line',xref='paper',yref='paper',x0=0.705,x1=0.705,y0=0,y1=1,line=dict(color='#dbe3e8',width=1))])
        return fig


def _script_json(value):
    return json.dumps(value, ensure_ascii=False, default=str).replace('&','\\u0026').replace('<','\\u003c').replace('>','\\u003e').replace('\u2028','\\u2028').replace('\u2029','\\u2029')


def render_event(package):
    """Return an offline standalone HTML without modifying the native graph."""
    if package.get('schema_version') == 'person-event-1.0':
        from .event.rendering import render_event as render_person_event
        return render_person_event(package)
    view = event_view(package)
    figure = PersonEventGanttVisualizer().plot_event(view)
    items = [{k:v for k,v in row.items() if k in {'key','kind','title','fields','evidence'}} for row in view['items']]
    assigned = [a for a in view['activities'] if a['assigned']]
    data = dict(items=items, title=view['event']['label'], person=view['person']['name'], storyline=view['storyline']['label'],
                graph_sha256=view['graph_sha256'], event_id=view['event']['event_id'],
                counts=dict(stages=len(view['stages']),activities=len(assigned),undated=sum(a['interval'] is None for a in assigned),
                            unassigned=len(view['activities'])-len(assigned),sources=view['source_count']))
    template = Path(__file__).with_name('gantt.html').read_text(encoding='utf-8')
    # Replace each template slot once; source strings can never become template instructions.
    chunks = template.split('/*__PERSON_GANTT_DATA__*/')
    script = 'const model = '+_script_json(data)+';\nconst figure = '+_script_json(json.loads(figure.to_json()))+';'
    html = chunks[0] + script + chunks[1]
    return html.replace('/*__PLOTLY_BUNDLE__*/', get_plotlyjs(), 1)
