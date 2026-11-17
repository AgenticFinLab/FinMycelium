"""Render or export a portable visualization of a saved native person event."""
import argparse
import json
from pathlib import Path

from .graph_view import build_views
from .graph_layout import arrange_graph
from .records import fingerprint
from .schema import GRAPH_VERSION

_ASSETS = Path(__file__).parent


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


def render_graph_html(graph, *, layout=None):
    """Generate an offline graph view, or use an explicitly supplied authored layout."""
    if not isinstance(graph, dict) or graph.get('schema_version') != GRAPH_VERSION:
        raise ValueError(f'The EPG viewer requires a {GRAPH_VERSION} graph')
    pages = _layout_pages(graph, layout)
    view = build_views(graph)
    if pages is None:
        view = arrange_graph(graph, view)
    template_name = 'graph_authored.html' if pages is not None else 'graph.html'
    template = (_ASSETS / template_name).read_text(encoding='utf-8')
    # Split the template before embedding untrusted record text.
    head, remainder = template.split('__EPG_GRAPH_JSON__', 1)
    between, remainder = remainder.split('__EPG_LAYOUT_JSON__', 1)
    middle, tail = remainder.split('__EPG_VIEW_JSON__', 1)
    return ''.join((head, _script_data(graph), between, _script_data(pages),
                    middle, _script_data(view), tail))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('graph', type=Path, help='Saved person event JSON')
    parser.add_argument('-o', '--output', required=True, type=Path, help='Destination HTML file')
    parser.add_argument('--layout', type=Path, help='Optional authored layout JSON for this exact graph')
    args = parser.parse_args(argv)
    inputs = (path for path in (args.graph, args.layout) if path is not None)
    if any(args.output.resolve() == path.resolve() for path in inputs):
        parser.error('The output path must differ from the input paths')
    try:
        html = render_graph_html(_read_json(args.graph), layout=_read_json(args.layout) if args.layout else None)
        args.output.write_text(html, encoding='utf-8')
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f'Wrote {args.output}')


if __name__ == '__main__':
    main()
