"""Render or export a portable visualization of a saved native person event."""
import argparse
import json
import re
from hashlib import sha256
from pathlib import Path

from .graph_evidence import passage_issues
from .graph_view import build_views
from .graph_layout import arrange_graph
from .records import fingerprint
from .schema import GRAPH_VERSION

_ASSETS = Path(__file__).parent


def _load_automatic_view():
    # Keep the template and inspector with the layout code imported by this worker.
    # A deployment can replace these files while a workbench session is still open.
    names = ('rendering.py', 'event/graph_html.py', 'event/graph.html', 'event/graph_layout.py',
             'event/graph_view.py', 'event/graph_labels.py', 'event/graph_evidence.py',
             'event/graph_inspector.js', 'event/records.py', 'event/validation.py',
             'event/temporal.py', 'event/chronology.py', 'event/action_layout.py', 'event/schema.py')
    files = {name: (_ASSETS.parent / name).read_bytes() for name in names}
    template = files['event/graph.html'].decode('utf-8').replace(
        '/*__FIELD_INSPECTOR__*/', files['event/graph_inspector.js'].decode('utf-8'), 1)
    return template, {name: sha256(data).hexdigest() for name, data in files.items()}


_AUTOMATIC_TEMPLATE, AUTOMATIC_VIEW_DEPENDENCIES = _load_automatic_view()


def _script_data(value):
    # Prevent record text from closing a script data element.
    return json.dumps(value, ensure_ascii=False, allow_nan=False).replace('<', r'\u003c')


def _read_json(path):
    with path.open(encoding='utf-8-sig') as stream:
        return json.load(stream)


def _layout_pages(graph, layout):
    if layout is None:
        return None
    authored = layout
    if not isinstance(authored, dict) or not isinstance(authored.get('digest'), str):
        raise ValueError('An authored layout needs a graph digest')
    if fingerprint(graph) != authored['digest']:
        raise ValueError('The authored layout digest does not match the input graph')

    pages = authored.get('pages')
    if not isinstance(pages, list) or not pages:
        raise ValueError('An authored layout must contain at least one page')
    required = {'title', 'phase', 'cards', 'paths', 'labels', 'evidence', 'jumps'}
    if any(not isinstance(page, dict) or not required <= page.keys() for page in pages):
        raise ValueError('Each layout page needs title, phase, cards, paths, labels, evidence and jumps')
    return pages


def render_graph_html(graph, *, layout=None, graph_sha256=None, result_status=None, payload=None):
    """Generate an offline graph view, or use an explicitly supplied authored layout."""
    if not isinstance(graph, dict) or graph.get('schema_version') != GRAPH_VERSION:
        raise ValueError(f'The EPG viewer requires a {GRAPH_VERSION} graph')
    pages = _layout_pages(graph, layout)
    view = build_views(graph)
    if pages is None:
        if payload is not None:
            identity = payload.get('user_query', {}).get('extras', {}).get('person_event', {})
            if any(identity.get(key) != graph['event'].get(key) for key in ('person_id', 'storyline_id', 'event_id')):
                raise ValueError('The frozen input belongs to a different person event')
        view = arrange_graph(graph, view, passage_issues(graph, payload), payload)
        view['checked_input'] = payload is not None
    template = (_AUTOMATIC_TEMPLATE if pages is None else
                (_ASSETS / 'graph_authored.html').read_text(encoding='utf-8'))
    # Split the template before embedding untrusted record text.
    head, remainder = template.split('__EPG_GRAPH_JSON__', 1)
    if graph_sha256 is not None:
        if not re.fullmatch(r'[0-9a-f]{64}', graph_sha256):
            raise ValueError('Expected the SHA-256 of the saved graph file')
        head = head.replace('<meta charset="utf-8">', '<meta charset="utf-8">\n'
                            f'<meta name="finmy-graph-sha256" content="{graph_sha256}">', 1)
    status_label = {'draft': 'Draft · content review pending',
                    'partial': 'Partial · content review pending'}.get(result_status, '')
    head = head.replace('<!--__BUILD_STATUS__-->', f'<span>{status_label}</span>' if status_label else '', 1)
    between, remainder = remainder.split('__EPG_LAYOUT_JSON__', 1)
    middle, tail = remainder.split('__EPG_VIEW_JSON__', 1)
    return ''.join((head, _script_data(graph), between, _script_data(pages),
                    middle, _script_data(view), tail))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('graph', type=Path, help='Saved person event JSON')
    parser.add_argument('-o', '--output', required=True, type=Path, help='Destination HTML file')
    parser.add_argument('--layout', type=Path, help='Optional authored layout JSON for this exact graph')
    parser.add_argument('--input', type=Path, help='Frozen person build input for checking quoted passages')
    args = parser.parse_args(argv)
    inputs = (path for path in (args.graph, args.layout, args.input) if path is not None)
    if any(args.output.resolve() == path.resolve() for path in inputs):
        parser.error('The output path must differ from the input paths')
    try:
        source = args.graph.read_bytes()
        html = render_graph_html(json.loads(source.decode('utf-8-sig')),
                                 layout=_read_json(args.layout) if args.layout else None,
                                 graph_sha256=sha256(source).hexdigest(),
                                 payload=_read_json(args.input) if args.input else None)
        args.output.write_text(html, encoding='utf-8')
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f'Wrote {args.output}')


if __name__ == '__main__':
    main()
