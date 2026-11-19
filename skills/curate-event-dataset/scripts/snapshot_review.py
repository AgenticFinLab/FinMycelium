"""Verify a published catalog or summarize its classification, without editing it."""
import argparse
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import catalog_core as core


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def row_sha(row):
    return hashlib.sha256(core.encoded(row).encode('utf-8')).hexdigest()


def validate(catalog, finmy, target, allow_h2epr):
    checkpoint = json.loads((catalog / 'research/checkpoint.json').read_bytes())
    manifest = checkpoint['output_sha256']
    if 'events.csv' not in manifest:
        raise ValueError('Checkpoint does not bind the master table')
    for name, expected in manifest.items():
        path = (catalog / name).resolve()
        if not path.is_relative_to(catalog) or sha(path) != expected:
            raise ValueError(f'Invalid or stale checkpoint output: {name}')
    core.check(catalog, target, finmy_root=finmy, allow_h2epr_audit_exceptions=allow_h2epr, quiet=True)
    master = core.keyed(core.read(catalog / 'events.csv'), 'event_id')
    if checkpoint.get('active') != len(master):
        raise ValueError('Checkpoint count differs from the master')
    review = core.keyed(core.read(catalog / 'research/row-review.csv.gz'), 'event_id')
    if review.keys() != master.keys():
        raise ValueError('Row review does not cover the current ID set')
    sources = core.keyed(core.read(catalog / 'sources.csv'), 'source_id')
    links = defaultdict(set)
    for link in core.read(catalog / 'event-sources.csv'):
        links[link['event_id']].add(link['source_id'])
    statuses = Counter()
    for eid, row in master.items():
        audit = review[eid]
        if row_sha(row) != audit['current_row_sha256']:
            raise ValueError(f'Stale row review: {eid}')
        verdict = audit['verdict']
        if verdict not in {'supported', 'partially_supported', 'pending'}:
            raise ValueError(f'Unknown fact-review verdict: {eid}')
        claimed = set(json.loads(audit['source_ids']))
        if claimed != links[eid] or (verdict != 'pending' and not claimed):
            raise ValueError(f'Row review source links differ: {eid}')
        statuses[verdict] += 1
    with gzip.open(catalog / 'research/evidence.jsonl.gz', 'rt', encoding='utf-8') as stream:
        evidence = core.keyed([json.loads(line) for line in stream if line.strip()], 'event_id')
    if evidence.keys() != master.keys():
        raise ValueError('Evidence ledger does not cover the current ID set')
    for eid, item in evidence.items():
        if set(item['source_ids']) != links[eid]:
            raise ValueError(f'Evidence source links differ: {eid}')
    if checkpoint.get('fact_review_statuses', statuses) != statuses:
        raise ValueError('Checkpoint fact-review counts differ')
    if checkpoint.get('complete') and (statuses['pending'] or statuses['partially_supported']):
        raise ValueError('Checkpoint claims completion while fact reviews remain open')
    examined = set()
    pairs = core.read(catalog / 'research/duplicate-review.csv.gz')
    for row in pairs:
        key = frozenset((row['left_event_id'], row['right_event_id']))
        if len(key) != 2 or key in examined or not key <= master.keys():
            raise ValueError('Invalid or repeated duplicate-review pair')
        if row['verdict'] not in {'duplicate', 'bounded_overlap', 'distinct', 'invalid_signal', 'pending', 'possible_duplicate'}:
            raise ValueError('Unknown pair verdict')
        if not set(json.loads(row['source_ids'] or '[]')) <= sources.keys():
            raise ValueError('Duplicate-review pair references a missing source')
        examined.add(key)
    pair_verdicts = Counter(row['verdict'] for row in pairs)
    if checkpoint.get('complete') and any(pair_verdicts[v] for v in ('duplicate', 'pending', 'possible_duplicate')):
        raise ValueError('Checkpoint claims completion while duplicate pairs remain open')
    return {
        'rows': len(master), 'fields': len(next(iter(master.values()), {})),
        'checkpoint_entries_checked': len(manifest), 'master_sha256': sha(catalog / 'events.csv'),
        'fact_review_statuses': dict(statuses), 'pair_verdicts': dict(pair_verdicts),
        'duplicate_status_counts': dict(Counter(r.get('duplicate_status') or 'unmarked' for r in master.values())),
        'scope': 'Published audit consistency only; retained fact verdicts were not independently re-researched.',
    }


def classification(master_path, baseline):
    rows = core.read(master_path)
    ids = core.keyed(rows, 'event_id')
    missing = baseline - ids.keys()
    if missing:
        raise ValueError(f'Baseline includes IDs absent from the master: {sorted(missing)[:5]}')
    counts = defaultdict(lambda: [0, 0, []])
    for eid, row in ids.items():
        item = counts[row['domain'], row['category']]
        item[0 if eid in baseline else 1] += 1
        if len(item[2]) < 3:
            item[2].append(eid)
    by_domain = defaultdict(lambda: [0, 0])
    by_category = defaultdict(lambda: [0, 0])
    details = []
    for (domain, category), (first, later, examples) in sorted(counts.items()):
        for key, summary in ((domain, by_domain), (category, by_category)):
            summary[key][0] += first
            summary[key][1] += later
        details.append(dict(domain=domain, category=category, baseline=first, other=later,
                            total=first + later, example_event_ids=examples))
    summarize = lambda counts: {k: dict(baseline=a, other=b, total=a+b) for k, (a, b) in counts.items()}
    return {
        'rows': len(rows), 'master_sha256': sha(master_path), 'baseline_rows': len(baseline),
        'domains': summarize(by_domain), 'categories': summarize(by_category), 'combinations': details,
        'new_domains': sorted(k for k, (a, b) in by_domain.items() if not a and b),
        'new_categories': sorted(k for k, (a, b) in by_category.items() if not a and b),
        'new_combination_count': sum(not item['baseline'] and item['other'] > 0 for item in details),
        'scope': 'Raw labels and rows, including duplicate flags. Sample IDs are review leads, not taxonomy verdicts.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='mode', required=True)
    verify = commands.add_parser('check', help='Check a published catalog and its current audit')
    verify.add_argument('--catalog', type=Path, required=True)
    verify.add_argument('--finmy-root', type=Path, required=True)
    verify.add_argument('--target', type=int)
    verify.add_argument('--allow-h2epr-audit-exceptions', action='store_true')
    classify = commands.add_parser('classification', help='Count exact labels; optional baseline by ID')
    classify.add_argument('--master', type=Path, required=True)
    classify.add_argument('--baseline', type=Path, help='CSV with the baseline event IDs')
    args = parser.parse_args()
    if args.mode == 'check':
        result = validate(args.catalog.resolve(), args.finmy_root.resolve(), args.target, args.allow_h2epr_audit_exceptions)
    else:
        baseline = set(core.keyed(core.read(args.baseline), 'event_id')) if args.baseline else set()
        result = classification(args.master, baseline)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
