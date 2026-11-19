"""Assemble a verified snapshot inside a curation run. Does not publish it."""
import argparse
import gzip
import hashlib
import io
import json
import shutil
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import catalog_core as core
import catalog_workflow as workflow
from snapshot_review import validate

ROW_LEDGER = 'research/row-review.csv.gz'
EVIDENCE = 'research/evidence.jsonl.gz'
BASELINE = 'research/baseline.json'
CHECKPOINT = 'research/checkpoint.json'


def materialize_pairs(run, stage, ids, source_ids):
    pairs = {}
    for path in (stage / workflow.PAIR_LEDGER, run / 'pair-review.csv'):
        if not path.is_file():
            continue
        for row in core.read(path):
            key = frozenset((row['left_event_id'], row['right_event_id']))
            if not key <= ids:
                if path.parent == run:
                    continue  # External comparisons stay in the run.
                raise ValueError(f'Current pair references an inactive event: {sorted(key)}')
            if len(key) != 2 or row['verdict'] not in {'distinct', 'bounded_overlap', 'invalid_signal'}:
                raise ValueError(f'Pair has not been settled: {sorted(key)}')
            if key in pairs and pairs[key]['verdict'] != row['verdict']:
                raise ValueError(f'Update the current pair ledger to resolve contradictory verdicts: {sorted(key)}')
            record = {field: row.get(field, '') for field in workflow.PAIR_FIELDS}
            old_ids = pairs.get(key, {}).get('source_ids', '[]')
            refs = set(json.loads(record['source_ids'] or '[]')) | set(json.loads(old_ids))
            if not refs <= source_ids:
                raise ValueError(f'Pair references an unknown source: {sorted(key)}')
            record['source_ids'] = core.encoded(sorted(refs))
            pairs[key] = record
    return [pairs[key] for key in sorted(pairs, key=lambda key: tuple(sorted(key)))]


def seal(run, finmy, target, evidence_path, *, allow_state_changes=False):
    destination = run / 'snapshot'
    if destination.exists():
        raise ValueError(f'Snapshot already exists: {destination}')
    _, _, stage = workflow.context(core, run)
    inputs = [*(stage / name for name in workflow.TABLES), run / 'row-review.csv',
              run / 'pair-review.csv', run / 'recall-method.json', evidence_path]
    if (stage / workflow.PAIR_LEDGER).is_file():
        inputs.append(stage / workflow.PAIR_LEDGER)
    input_hashes = {path: workflow.digest(path) for path in inputs}
    workflow.verify(core, run, target, finmy, final=True, allow_state_changes=allow_state_changes)
    master = core.keyed(core.read(stage / 'events.csv'), 'event_id')
    rows = core.read(run / 'row-review.csv')
    if any(list(row) != core.CATALOG_FIELDS for row in master.values()):
        raise ValueError('Snapshot publication requires the current 24-column schema')
    sources = {row['source_id'] for row in core.read(stage / 'sources.csv')}
    pairs = materialize_pairs(run, stage, master.keys(), sources)
    opener = gzip.open if evidence_path.suffix == '.gz' else open
    with opener(evidence_path, 'rt', encoding='utf-8-sig') as stream:
        evidence = core.keyed([json.loads(line) for line in stream if line.strip()], 'event_id')
    if evidence.keys() != master.keys():
        raise ValueError('Evidence JSONL must provide exactly one record per current event ID')
    for eid, item in evidence.items():
        if not all(item.get(field) for field in ('object_claims', 'date_claims', 'limitation')):
            raise ValueError(f'Evidence lacks facts, dates or reading limits: {eid}')
    decision_source = stage / 'curation-decisions.csv'
    decisions = {row['event_id']: row for row in core.read(decision_source)}
    with tempfile.TemporaryDirectory(prefix='seal-', dir=run) as tmp:
        sealed = Path(tmp) / 'snapshot'
        research = sealed / 'research'
        research.mkdir(parents=True)
        tracked = set(workflow.TABLES) | {ROW_LEDGER, workflow.PAIR_LEDGER, EVIDENCE, BASELINE}
        for name in workflow.TABLES:
            if name != 'curation-decisions.csv':
                shutil.copy2(stage / name, sealed / name)
        core.write(sealed / 'curation-decisions.csv', core.DECISION_FIELDS,
                   [decisions[eid] for eid in master])
        for row in master.values():
            for field in ('epg_path', 'gantt_path', 'review_path'):
                name = row[field]
                if name and name not in tracked:
                    (sealed / name).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(stage / name, sealed / name)
                    tracked.add(name)
        core.write(sealed / ROW_LEDGER, workflow.REVIEW_FIELDS, rows)
        core.write(sealed / workflow.PAIR_LEDGER, workflow.PAIR_FIELDS, pairs)
        with (sealed / EVIDENCE).open('wb') as raw:
            with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as compressed:
                with io.TextIOWrapper(compressed, encoding='utf-8', newline='\n') as output:
                    for eid in master:
                        output.write(core.encoded(evidence[eid]) + '\n')
        workflow.save_json(sealed / BASELINE, dict(
            identity_scope='current_catalog', active=target,
            event_ids_sha256=hashlib.sha256(core.encoded(sorted(master)).encode('utf-8')).hexdigest(),
        ))
        workflow.save_json(sealed / CHECKPOINT, dict(
            active=target, target=target, remaining=0, complete=True,
            execution_date=datetime.now(timezone.utc).date().isoformat(),
            retention_policy='current_snapshot_only',
            current_semantic_review_queue=workflow.PAIR_LEDGER,
            current_semantic_review_pending_pairs=0,
            final_all_row_review=ROW_LEDGER,
            final_review_scope='Strict recorded checks for this run; research conclusions and limits come from its evidence.',
            fact_review_statuses=dict(Counter(row['verdict'] for row in rows)),
            output_sha256={name: workflow.digest(sealed / name) for name in sorted(tracked)},
        ))
        validate(sealed.resolve(), finmy, target, allow_h2epr=False)
        if any(workflow.digest(path) != digest for path, digest in input_hashes.items()):
            raise ValueError('Seal inputs changed during verification or assembly')
        sealed.rename(destination)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-root', type=Path, required=True)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--finmy-root', type=Path, required=True)
    parser.add_argument('--target', type=int, required=True)
    parser.add_argument('--evidence-jsonl', type=Path, required=True)
    parser.add_argument('--allow-workflow-state-changes', action='store_true')
    args = parser.parse_args()
    try:
        run = workflow.run_path(args.dataset_root.resolve(), args.run_dir)
        destination = seal(run, args.finmy_root.resolve(), args.target, args.evidence_jsonl,
                           allow_state_changes=args.allow_workflow_state_changes)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        parser.exit(1, str(exc) + '\n')
    print(f'SEALED {destination}')


if __name__ == '__main__':
    main()
