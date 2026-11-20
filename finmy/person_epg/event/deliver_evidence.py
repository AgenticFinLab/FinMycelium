"""Offline first delivery: apply saved same-fact reviews without validation gates."""
import argparse
import json
from pathlib import Path

from .evidence_consolidation import batches, merge_plan, apply_mapping, saved_review, source_ids
from .graph_html import render_graph_html
from .records import fingerprint
from .runtime import EventBuildConfig


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('attempt', type=Path, help='Saved evidence postprocess attempt, e.g. RUN/attempts/0004')
    parser.add_argument('--output', required=True, type=Path, help='Separate delivery directory')
    args = parser.parse_args(argv)
    attempt = args.attempt.resolve()
    directory = attempt.parent.parent
    output = args.output.resolve()
    if output == directory or output.is_relative_to(directory / 'attempts') or output.is_relative_to(directory / 'checkpoints'):
        parser.error('Choose a delivery directory outside attempts and checkpoints')
    read = lambda path: json.loads(path.read_text(encoding='utf-8'))
    state = read(directory / 'state.json')
    snapshot = read(attempt / 'evidence-postprocess-input.json')
    payload = read(directory / 'input.json')
    graph, facts = snapshot['graph'], snapshot['facts']
    config = EventBuildConfig.from_saved(state['config'])
    # Reuse the paid decisions for this exact graph, not a later failed attempt.
    decisions = saved_review(directory, state, graph, config)
    pairs = [pair for request in batches(graph, config) for pair in request['pairs']]
    mapping, conflicts = merge_plan(graph, pairs, decisions)
    merged, merged_facts = apply_mapping(graph, facts, mapping, payload)
    report = dict(mode='delivery', source_attempt=str(attempt), validation='skipped',
        candidate_pairs=len(pairs), reviewed_pairs=len(decisions), merged_records=len(mapping),
        multi_source_after=sum(len(source_ids(e)) > 1 for e in merged['evidence']),
        ignored_conflicts=conflicts, mapping=mapping, decisions=decisions,
        input_graph_fingerprint=fingerprint(graph), output_graph_fingerprint=fingerprint(merged))
    html = render_graph_html(merged, result_status='partial')
    output.mkdir(parents=True, exist_ok=True)
    for name, value in [('epg.json', merged), ('facts.json', merged_facts), ('evidence-consolidation.json', report)]:
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (output / 'graph.html').write_text(html, encoding='utf-8')
    print(json.dumps(dict(output=str(output / 'epg.json'), html=str(output / 'graph.html'),
        merged_records=len(mapping), ignored_conflicts=len(conflicts),
        multi_source_after=report['multi_source_after'], model_calls=0), ensure_ascii=False))


if __name__ == '__main__':
    main()
