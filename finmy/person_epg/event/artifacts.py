"""Present prior artifacts independently of the latest execution outcome."""
import json
import re
from pathlib import Path

from .records import sha256


def available_artifacts(directory):
    directory = Path(directory)
    artifacts = []
    for attempt in sorted((directory / 'attempts').glob('[0-9]*')):
        graph_path = attempt / 'epg.json'
        if not graph_path.is_file():
            continue
        try:
            raw = graph_path.read_bytes()
            graph = json.loads(raw)
            checks_path = attempt / 'checks.json'
            checks = json.loads(checks_path.read_text()) if checks_path.is_file() else {}
            digest = sha256(raw)
            if checks.get('graph_sha256') not in (None, digest):
                continue
            html_path = attempt / 'gantt.html'
            html = None
            if html_path.is_file():
                header = html_path.open(encoding='utf-8')
                with header:
                    prefix = header.read(1024)
                match = re.search(r'name="finmy-graph-sha256" content="([0-9a-f]{64})"', prefix)
                if match and match[1] == digest:
                    html = str(html_path.relative_to(directory))
            artifacts.append(dict(attempt=attempt.name, output=str(graph_path.relative_to(directory)),
                html=html, graph_sha256=digest, result_status=checks.get('result_status', 'unknown'),
                execution_status=checks.get('execution_status', 'unknown'),
                has_hierarchy=bool(graph.get('stages') and graph.get('phases')),
                actions=len(graph.get('actions', [])), evidence=len(graph.get('evidence', [])),
                errors=checks.get('summary', {}).get('errors')))
        except (OSError, ValueError, TypeError, AttributeError):
            continue  # A broken old attempt cannot hide a usable later one.
    return artifacts


def artifact_summary(directory):
    artifacts = available_artifacts(directory)
    rendered = [a for a in artifacts if a['html']]
    hierarchy = [a for a in rendered if a['has_hierarchy']]
    return dict(available_artifacts=artifacts,
        latest_rendered_artifact=rendered[-1] if rendered else None,
        latest_hierarchy_artifact=hierarchy[-1] if hierarchy else None)


def update_artifact_summary(run):
    summary = artifact_summary(run.directory)
    run.state.update(summary)
    run.state['latest_attempt'] = dict(attempt=run.state['attempts'],
        execution_status=run.state.get('execution_status'), result_status=run.state.get('result_status'),
        reason=run.state.get('reason'), output=run.state.get('output'),
        error=run.state.get('last_error'))


def print_artifact_summary(state, directory):
    directory = Path(directory).resolve()
    chosen = state.get('latest_hierarchy_artifact') or state.get('latest_rendered_artifact')
    if chosen:
        print('可查看的已有产物：' + str(directory / chosen['html']) +
              ' | attempt=' + chosen['attempt'] + ' | result=' + chosen['result_status'], flush=True)
    error = state.get('last_error')
    if error:
        print('最近错误：' + error['summary'], flush=True)
