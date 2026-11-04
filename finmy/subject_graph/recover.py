"""Recover a saved subject graph without discarding reviews; no model or search."""
import argparse
import json
from pathlib import Path

from finmy.subject_graph.evidence import restore_source_quotes, flag_evidence_issues
from finmy.subject_graph.validation import validate_subject_graph
from finmy.subject_graph.compat import to_event_cascade
from finmy.subject_graph.visualizer import render_subject_graph
from finmy.subject_graph.build import _unique_record_ids
from finmy.subject_graph.event_sources import (select_event_sources, restrict_event_evidence,
                                             exclude_outside_coverage)


def _has_accepted_reviews(value):
    if isinstance(value, dict):
        return bool(value.get('accepted')) or any(_has_accepted_reviews(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_accepted_reviews(v) for v in value)
    return False


def _extend_unique(original, additions):
    return original + [item for item in additions if item not in original]


def recover_run(run_dir, output_dir=None):
    run_dir = Path(run_dir)
    destination = Path(output_dir) if output_dir else run_dir.with_name(run_dir.name + '_recovered')
    context = json.loads((run_dir / 'subject_build_input.json').read_text(encoding='utf-8'))
    raw = json.loads((run_dir / 'RawSubjectGraph.json').read_text(encoding='utf-8'))
    saved = {}
    for name in ('SubjectPlanner-1-Result', 'subject_event_sources', 'subject_event_evidence_review',
                 'subject_scope_review', 'subject_event_detail_review', 'subject_coverage_review',
                 'subject_statement_duplicates', 'subject_record_id_normalization',
                 'subject_quote_restoration', 'subject_graph_validation'):
        path = run_dir / (name + '.json')
        if path.exists():
            saved[name] = json.loads(path.read_text(encoding='utf-8'))
    sources = [source['content'] for source in context['Sources']]
    if not sources or any(not isinstance(source, str) or not source.strip() for source in sources):
        raise ValueError('Original source texts are required for recovery')
    final_path = run_dir / 'FinalSubjectGraph.json'
    has_final = final_path.exists()
    if has_final:
        graph = json.loads(final_path.read_text(encoding='utf-8'))
    else:
        # Raw predates repairs and reviews. Do not guess how to replay later
        # accepted patches/merges on its original array indices.
        if any(_has_accepted_reviews(saved.get(name)) for name in
               ('subject_event_detail_review', 'subject_coverage_review')):
            raise ValueError('Recovery failed: accepted reviews require the saved FinalSubjectGraph.json')
        graph = raw
    if not isinstance(graph, dict):
        raise ValueError('Recovery failed: saved graph must be an object')
    if not has_final:
        graph, id_changes = _unique_record_ids(graph)
        saved['subject_record_id_normalization'] = id_changes
    graph, changes = restore_source_quotes(graph, sources)
    changes = _extend_unique(saved.get('subject_quote_restoration', []), changes)
    warnings = list(saved.get('subject_graph_validation', {}).get('warnings', []))
    if not has_final:
        allocation = saved.get('subject_event_sources')
        plan = saved.get('SubjectPlanner-1-Result')
        if allocation is not None or plan is not None or saved.get('subject_event_evidence_review'):
            if not isinstance(allocation, dict) or not isinstance(plan, dict):
                raise ValueError('Recovery failed: saved event source allocation and planner are required')
            targets = {event['event_id']: event for event in plan['events']}
            source_ids = {source['source_id'] for source in context['Sources']}
            event_sources = {}
            for event in graph.get('events', []):
                eid = event['event_id']
                ids = allocation.get(eid)
                if (eid not in targets or not isinstance(ids, list)
                        or any(not isinstance(sid, str) or sid not in source_ids for sid in ids)):
                    raise ValueError('Recovery failed: incomplete event source allocation for ' + eid)
                event_sources[eid] = select_event_sources(targets[eid], context['Sources'], ids)
            graph, excluded = restrict_event_evidence(graph, targets, event_sources, context['Sources'])
            saved['subject_event_evidence_review'] = _extend_unique(
                saved.get('subject_event_evidence_review', []), excluded)
        else:
            # Older two-file runs can still be inspected, but global quote
            # matching cannot certify event attribution.
            warnings.append({'path': '/events', 'message':
                'Recovery lacks saved event source allocation; event attribution needs review'})
        graph, excluded = exclude_outside_coverage(graph)
        saved['subject_scope_review'] = _extend_unique(saved.get('subject_scope_review', []), excluded)
    for name in ('subject_event_evidence_review', 'subject_scope_review'):
        warnings.extend({'path': item['path'], 'message': item['message'] +
                         '; original record saved in ' + name + '.json'}
                        for item in saved.get(name, []))
    graph, pending = flag_evidence_issues(graph, sources)
    scope = context['SubjectScope']
    subject = scope['subject']
    report = validate_subject_graph(graph, sources, allow_unverified_evidence=True)
    for warning in warnings:
        if warning not in report['warnings']:
            report['warnings'].append(warning)
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
    html = render_subject_graph(graph, event_cascade=projection)
    destination.mkdir(parents=True, exist_ok=False)
    artifacts = {**saved, 'FinalSubjectGraph': graph, 'FinalEventCascade': projection,
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
