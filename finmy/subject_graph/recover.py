"""Recover saved RawSubjectGraph using its original evidence; no model or search."""
import argparse
import json
from pathlib import Path

from finmy.subject_graph.evidence import restore_source_quotes, flag_evidence_issues
from finmy.subject_graph.validation import validate_subject_graph
from finmy.subject_graph.compat import to_event_cascade
from finmy.subject_graph.visualizer import render_subject_graph


def recover_run(run_dir, output_dir=None):
    run_dir = Path(run_dir)
    destination = Path(output_dir) if output_dir else run_dir.with_name(run_dir.name + '_recovered')
    context = json.loads((run_dir / 'subject_build_input.json').read_text(encoding='utf-8'))
    raw = json.loads((run_dir / 'RawSubjectGraph.json').read_text(encoding='utf-8'))
    sources = [source['content'] for source in context['Sources']]
    if not sources or any(not isinstance(source, str) or not source.strip() for source in sources):
        raise ValueError('Original source texts are required for recovery')
    graph, changes = restore_source_quotes(raw, sources)
    graph, pending = flag_evidence_issues(graph, sources)
    scope = context['SubjectScope']
    subject = scope['subject']
    report = validate_subject_graph(graph, sources, allow_unverified_evidence=True)
    if not isinstance(graph, dict):
        raise ValueError('Recovery failed: saved graph must be an object')
    for key in ('subject_id', 'coverage_start', 'coverage_end'):
        if graph.get(key) != subject[key]:
            report['errors'].append({'path': '/' + key, 'message': 'Saved graph disagrees with original scope'})
    expected_type = 'individual' if scope['mode'] == 'person' else 'organization'
    if graph.get('subject_type') != expected_type:
        report['errors'].append({'path': '/subject_type', 'message': 'Saved subject type disagrees with original scope'})
    registry = graph.get('entities', [])
    if isinstance(registry, list):
        principal = next((e for e in registry if isinstance(e, dict)
                          and e.get('entity_id') == subject['subject_id']), {})
        name = principal.get('name', {})
        name = name.get('value') if isinstance(name, dict) else None
        normalize = lambda text: ' '.join(text.casefold().split()) if isinstance(text, str) else None
        if normalize(name) not in {normalize(n) for n in [subject['name'], *subject.get('aliases', [])]}:
            report['errors'].append({'path': '/entities', 'message': 'Subject name disagrees with original scope'})
    if not graph.get('events'):
        report['errors'].append({'path': '/events', 'message': 'No events to recover'})
    report['valid'] = not report['errors']
    if not report['valid']:
        raise ValueError('Recovery failed; original files unchanged: ' + json.dumps(report['errors'], ensure_ascii=False))
    projection = to_event_cascade(graph)
    html = render_subject_graph(graph)
    destination.mkdir(parents=True, exist_ok=False)
    artifacts = {'FinalSubjectGraph': graph, 'FinalEventCascade': projection,
                 'IntegratedEventCascade': projection, 'subject_graph_validation': report,
                 'subject_quote_restoration': changes, 'subject_evidence_review': pending,
                 'subject_build_input': context,
                 'reconstruction_scope': scope, 'RawSubjectGraph': raw}
    for name, value in artifacts.items():
        (destination / (name + '.json')).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    (destination / 'FinalSubjectGraph.html').write_text(html, encoding='utf-8')
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir')
    parser.add_argument('--output-dir')
    args = parser.parse_args()
    print(recover_run(args.run_dir, args.output_dir))


if __name__ == '__main__':
    main()
