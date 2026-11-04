"""Render SubjectGraph with the existing Event Gantt renderer."""
from html import escape
from pathlib import Path
from tempfile import TemporaryDirectory

from finmy.subject_graph.compat import to_event_cascade


def render_subject_graph(graph, output_path=None, *, event_cascade=None):
    """Render the graph, optionally reusing its already validated EventCascade."""
    if graph.get("schema_version") != "subject-graph-1.0":
        raise ValueError("Expected a SubjectGraph")
    cascade = to_event_cascade(graph) if event_cascade is None else event_cascade
    subject = next(e for e in graph["entities"] if e["entity_id"] == graph["subject_id"])
    name = subject["name"]["value"]

    # Escape source text only in the disposable display copy, never in saved data.
    def safe(value):
        if isinstance(value, dict):
            return {key: safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [safe(item) for item in value]
        return escape(value, quote=True) if isinstance(value, str) else value

    if cascade["stages"]:
        from finmy.builder.agent_build.visualizer_gantt import EventCascadeGanttVisualizer
        with TemporaryDirectory() as directory:
            target = Path(directory) / "gantt.html"
            EventCascadeGanttVisualizer().plot_cascade(
                safe(cascade), str(target), subject_name=escape(name))
            page = target.read_text(encoding="utf-8")
    else:
        page = '<html><body><p>当前范围内没有已记录的经历。</p></body></html>'

    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page, encoding="utf-8")
    return page


class SubjectGraphVisualizer:
    def plot_graph(self, graph, output_path=None):
        return render_subject_graph(graph, output_path)
