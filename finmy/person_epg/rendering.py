"""Save or regenerate Gantt independently of model execution and acceptance."""
import json
import os
from pathlib import Path
import tempfile

from finmy.dataset import within
from finmy.search.state import digest, now, write_json
from finmy.search.summary import directory_lock


def save_gantt(graph, directory, graph_path):
    """Return a render record; a plotting failure never invalidates saved JSON."""
    record = {'status': 'failed', 'graph_sha256': digest(graph), 'rendered_at': now()}
    temporary = None
    try:
        from .visualizer_gantt import render_event
        html = render_event(graph).encode('utf-8')
        module = Path(__file__).parent
        record['renderer_sha256'] = digest({name: digest((module/name).read_bytes())
                                           for name in ('visualizer_gantt.py','gantt.html','rendering.py')})
        target = Path(graph_path).with_name('gantt.html')
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.gantt-', delete=False) as f:
            temporary = Path(f.name)
            f.write(html)
        os.replace(temporary, target)
        record.update(status='completed', output=str(target.relative_to(directory)), html_sha256=digest(html))
    except Exception as exc:
        record['error_type'] = type(exc).__name__
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return record


def render_saved_event(directory):
    """Explicit offline rerender; preserve graph, model calls and build status."""
    directory = Path(directory).resolve()
    with directory_lock(directory):
        state = json.loads((directory/'state.json').read_text())
        if state['status'] in {'running', 'queued', 'ready'}:
            raise ValueError('Wait for construction to stop before rendering its saved draft')
        if not state.get('output'):
            raise ValueError('There is no saved draft to render')
        graph_path = within(directory, state['output'])
        graph = json.loads(graph_path.read_text())
        if digest(graph) != state['graph_sha256']:
            raise ValueError('Saved draft integrity mismatch')
        from .build import check_identity
        payload = json.loads((directory/'input.json').read_text())
        if digest(payload) != state['input_sha256']:
            raise ValueError('Saved input integrity mismatch')
        check_identity(graph, payload['user_query']['extras']['person_event'])
        state['visualization'] = save_gantt(graph, directory, graph_path)
        write_json(directory/'state.json', state)
        return state


def read_gantt(directory, state):
    """Only display HTML that belongs to this exact saved draft."""
    graph = json.loads(within(directory, state['output']).read_text())
    if digest(graph) != state['graph_sha256']:
        raise ValueError('Saved draft integrity mismatch')
    record = state.get('visualization', {})
    if record.get('status') != 'completed' or record.get('graph_sha256') != state['graph_sha256']:
        raise ValueError('No matching Gantt is available; generate it from the saved JSON')
    path = within(directory, record['output'])
    content = path.read_bytes()
    if digest(content) != record['html_sha256']:
        raise ValueError('Saved Gantt integrity mismatch; regenerate it from the saved JSON')
    return content.decode('utf-8')
