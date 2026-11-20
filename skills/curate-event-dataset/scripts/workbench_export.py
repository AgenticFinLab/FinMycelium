"""Export reproducible Workbench input files; the event-epg master stays authoritative."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import catalog_core as catalog


def export(source, destination, *, baseline=None, finmy_root, chunk_size=2500, allow_withdrawals=False):
    if not 1 <= chunk_size <= 5000:
        raise ValueError('chunk_size must be between1 and5000')
    spec = importlib.util.spec_from_file_location(
        'event_workbench_domain', Path(finmy_root) / 'finmy/workbench/domain.py')
    domain = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(domain)
    fields = list(domain.FIELDS)
    rows = catalog.read(source)
    ids = [r['event_id'] for r in rows]
    id_set = set(ids)
    if not rows or len(id_set) != len(ids) or '' in ids:
        raise ValueError('nonempty master with unique event ids required')
    # Reject invalid deltas before creating or changing any export files.
    old, new, withdrawn = {}, [], []
    if baseline is not None:
        before = catalog.read(baseline)
        old = {r['event_id']: r for r in before}
        if len(old) != len(before) or '' in old:
            raise ValueError('baseline ids must be unique and nonempty')
        withdrawn = [r for r in before if r['event_id'] not in id_set]
        if withdrawn and not allow_withdrawals:
            raise ValueError('baseline ids missing from source; review withdrawals and use --allow-withdrawals')
        new = [r for r in rows if r['event_id'] not in old]
        if len(new) > 5000:
            raise ValueError('new-events exceeds5000; export it in smaller batches')
    destination.mkdir(parents=True, exist_ok=True)
    manifest = {'source': str(source.resolve()), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                'total_rows': len(rows), 'chunk_size': chunk_size, 'fields': fields,
                'note': 'Derived input files. Import full parts into an empty target, or only new-events into an existing target. Existing ids are not updated by batch import.',
                'full_parts': [], 'new_events': None, 'changed_existing_ids': [], 'existing_changes_review': None,
                'withdrawn_existing_ids': [r['event_id'] for r in withdrawn], 'withdrawn_existing_review': None,
                'withdrawal_note': 'Withdrawn rows are historical review input only: do not import them. No Workbench records are deleted. Review the curation ID mapping and reconcile existing tasks explicitly.'}

    def save(name, selected):
        path = destination / name
        catalog.write(path, fields, [{k: r[k] for k in fields} for r in selected])
        parsed = domain.read_table(path.read_bytes(), path.name, mapping={k: k for k in fields})
        expected = [domain.event_record({k: r[k] for k in fields}) for r in selected]
        if parsed != expected:
            raise ValueError('Workbench round-trip mismatch: ' + name)
        return {'file': name, 'rows': len(selected), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'first_event_id': selected[0]['event_id'], 'last_event_id': selected[-1]['event_id']}

    for start in range(0, len(rows), chunk_size):
        manifest['full_parts'].append(save(f'events-part-{start // chunk_size + 1:03d}.csv', rows[start:start + chunk_size]))
    if baseline is not None:
        manifest['baseline_sha256'] = hashlib.sha256(baseline.read_bytes()).hexdigest()
        manifest['changed_existing_ids'] = [r['event_id'] for r in rows if r['event_id'] in old and any(r[k] != old[r['event_id']][k] for k in fields)]
        if manifest['changed_existing_ids']:
            changed = set(manifest['changed_existing_ids'])
            manifest['existing_changes_review'] = save('changed-existing-review.csv', [r for r in rows if r['event_id'] in changed])
        if new:
            manifest['new_events'] = save('new-events.csv', new)
        if withdrawn:
            manifest['withdrawn_existing_review'] = save('withdrawn-existing-review.csv', withdrawn)
    (destination / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--chunk-size', type=int, default=2500)
    parser.add_argument('--finmy-root', type=Path, required=True, help='Actual FinMycelium checkout; need not be adjacent')
    parser.add_argument('--allow-withdrawals', action='store_true', help='Export removed baseline rows for review only; does not delete Workbench tasks')
    args = parser.parse_args()
    result = export(args.source, args.output, baseline=args.baseline, chunk_size=args.chunk_size, allow_withdrawals=args.allow_withdrawals, finmy_root=args.finmy_root)
    print(f"PASS: {result['total_rows']} rows in {len(result['full_parts'])} full parts; new={result['new_events']['rows'] if result['new_events'] else 0}")
