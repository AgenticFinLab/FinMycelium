"""Render a portable, interactive graph from a saved native person event."""
from hashlib import sha256
import json
from pathlib import Path


def _script_data(value):
    # Prevent source text from closing the script data element.
    return json.dumps(value, ensure_ascii=False, allow_nan=False).replace('<', r'\u003c')


def render_graph_html(graph):
    """Embed the graph and, when available, its authored layout in one document."""
    if graph.get('schema_version') != 'person-event-1.0':
        raise ValueError('The EPG viewer requires a person-event-1.0 graph')
    template = Path(__file__).with_name('graph.html').read_text(encoding='utf-8')
    layout = None
    if graph['event']['event_id'] == 'PERSON-0001-E0034':
        authored = json.loads(Path(__file__).with_name('graph_layout_goldman.json').read_text(encoding='utf-8'))
        canonical = json.dumps(graph, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        if sha256(canonical).hexdigest() == authored['digest']:
            layout = authored['pages']
    # Replace both placeholders in the template before embedding user content.
    head, remainder = template.split('__EPG_GRAPH_JSON__', 1)
    between, tail = remainder.split('__EPG_LAYOUT_JSON__', 1)
    return head + _script_data(graph) + between + _script_data(layout) + tail
