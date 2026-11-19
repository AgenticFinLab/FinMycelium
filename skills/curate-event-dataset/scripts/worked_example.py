"""Replay the packaged synthetic case through the actual curation commands."""
import argparse
import json
from pathlib import Path

import catalog_core as core
import catalog_workflow as workflow
from seal_snapshot import seal
from workbench_export import export

DAY = '2020-04-01'
REVIEWER = '合成教学示例'


def replay(dataset, finmy, run):
    fixture = json.loads((Path(__file__).resolve().parents[1] / 'assets/worked-example.json').read_bytes())
    workflow.initialize(core, dataset, run, 'fresh')
    stage = run / 'stage'
    records = {}
    sources, links, decisions, evidence, inputs = [], [], [], [], []
    for number, event in enumerate(fixture['events'], start=1):
        row = dict.fromkeys(core.CATALOG_FIELDS, '')
        row.update(event['row'])
        eid, sid = row['event_id'], event['source_id']
        records[eid] = event
        row.update(aliases=core.encoded(['示例港海堤许可']), status='planned',
                   related_events='[]', source_hints=core.encoded([event['source_url']]))
        part = run / f'input-{number}.csv'
        core.write(part, core.CATALOG_FIELDS, [row])
        inputs.append(part)
        sources.append(dict(
            source_id=sid, title=event['source_title'], url=event['source_url'],
            publisher='合成教学档案', publication_info='', accessed_on=DAY,
            locator=event['source_locator'], reading_note=fixture['notice'],
        ))
        links.append(dict(
            event_id=eid, source_id=sid, supported_fields=core.encoded([
                'description', 'scope_include', 'coverage_start', 'coverage_end']),
            support_note=event['support'], verification_result='supported',
            verified_on=DAY, reviewer=REVIEWER,
        ))
        decisions.append(dict(
            record_id='RETAIN-'+eid, event_id=eid, legacy_uid='', decision='retain',
            canonical_event_id=eid, reason=event['support'], source_ids=core.encoded([sid]),
            changed_fields='{}', reviewed_on=DAY, reviewer=REVIEWER,
        ))
        evidence.append(dict(
            event_id=eid, source_ids=[sid],
            object_claims={'fact': event['support'], 'locator': event['source_locator']},
            date_claims={'start': row['coverage_start'], 'end': row['coverage_end'], 'reason': event['date_reason']},
            limitation=fixture['notice'],
        ))
    workflow.stage_composition(core, run, inputs, sequential_ids=True)
    for name, fields, data in (
        ('sources.csv', core.SOURCE_FIELDS, sources),
        ('event-sources.csv', core.LINK_FIELDS, links),
        ('curation-decisions.csv', core.DECISION_FIELDS, decisions),
    ):
        core.write(stage / name, fields, data)
    resolved_pair = dict(fixture['pair'], scores='{}', reviewed_on=DAY, reviewer=REVIEWER)
    core.write(stage / workflow.PAIR_LEDGER, workflow.PAIR_FIELDS, [resolved_pair])
    workflow.sync_marks(core, run)
    workflow.ledger(core, run, None)
    workflow.recall(core, run, 7)
    incoming = core.read(run / 'pair-review.csv')
    if len(incoming) != 1 or (incoming[0]['left_event_id'], incoming[0]['right_event_id']) != ('event1', 'event2'):
        raise ValueError('Worked example expected one pair to exercise manual adjudication')
    core.write(run / 'pair-review.csv', workflow.PAIR_FIELDS, [dict(resolved_pair, scores=incoming[0]['scores'])])
    ledger = core.read(run / 'row-review.csv')
    for audit in ledger:
        event = records[audit['event_id']]
        audit.update(identity_note=event['support'], date_note=event['date_reason'],
                     scope_note=event['row']['scope_exclude'], fact_locators=event['source_locator'],
                     review_method=fixture['notice'], verdict='supported', reviewed_on=DAY, reviewer=REVIEWER)
    core.write(run / 'row-review.csv', workflow.REVIEW_FIELDS, ledger)
    facts = run / 'evidence.jsonl'
    facts.write_text(''.join(core.encoded(item) + '\n' for item in evidence), encoding='utf-8', newline='\n')
    snapshot = seal(run, finmy, len(records), facts)
    manifest = export(snapshot / 'events.csv', run / 'workbench', finmy_root=finmy, chunk_size=1)
    return snapshot, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-root', type=Path, required=True)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--finmy-root', type=Path, required=True)
    args = parser.parse_args()
    dataset = args.dataset_root.resolve()
    run = workflow.run_path(dataset, args.run_dir)
    snapshot, result = replay(dataset, args.finmy_root.resolve(), run)
    print(f'SYNTHETIC EXAMPLE {snapshot}; {result["total_rows"]} rows in {len(result["full_parts"])} Workbench parts')


if __name__ == '__main__':
    main()
