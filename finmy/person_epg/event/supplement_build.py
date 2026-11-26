"""Checkpoint the initial graph, assess gaps once, and integrate accepted passages."""
import json

from .records import source_records
from .supplement_record import activate, retain, retained, usage
from .supplement_search import decide


def snapshot(build):
    return dict(graph=build.graph, facts=build.facts, reports=build.reports, coverage=build.coverage,
                usage=usage(build.run.state))


def restore(build, name):
    data = retained(build.run, name)
    for field in ('graph','facts','reports','coverage'):
        setattr(build, field, data[field])


def construct_graph(build, stop_after_organization=False):
    build.consolidate()
    if build.facts['actions']:
        build.organize()
        from .relation_experiment import capture
        capture(build)
        if not stop_after_organization:
            build.relate()


def with_search(build, provenance, allow_network, stop_after_organization):
    run = build.run
    if retained(run, 'base-input') is None:
        retain(run, 'base-input', run.payload)
        retain(run, 'base-provenance', json.loads((run.directory / 'provenance.json').read_text()))
    elif retained(run, 'base-provenance') is None:
        retain(run, 'base-provenance', json.loads((run.directory / 'provenance.json').read_text()))
    ledger = run.state['supplement']
    if 'baseline' not in ledger:
        ledger['baseline'] = dict(search_task_id=(provenance or {}).get('search_task_id'),
            input_sha256=ledger['files']['base-input'], samples=len(run.payload['samples']),
            material_chars=sum(len(s['content']) for s in run.payload['samples']),
            model=run.config.lm_name, reasoning_effort=run.config.reasoning_effort)
        run.persist()
    if retained(run, 'before') is None:
        if retained(run, 'extraction') is None:
            build.extract()
            if run.config.full_corpus_supplement:
                from .corpus_supplement import supplement
                supplement(build)
            retain(run, 'extraction', snapshot(build))
        else:
            restore(build, 'extraction')
        construct_graph(build, stop_after_organization)
        if stop_after_organization and build.facts['actions']:
            return build.finish('paused', 'Organization snapshot saved; relations not started')
        retain(run, 'before', snapshot(build))
    else:
        restore(build, 'before')
    decision = decide(build, provenance or {}, allow_network)
    if decision['included'] or decision['frozen_reads']:
        if decision['included'] and not run.state['supplement'].get('transition'):
            activate(run, retained(run, 'effective-input'), decision['included'])
        restore(build, 'extraction')
        build.revised = True
        build.facts['sources'] = source_records(run.payload)
        questions = {q['id']:q['question'] for q in decision['questions']}
        build.supplement_questions = list(questions.values())
        if decision['included']:
            build.extract(start_at=len(build.coverage))
        samples = {s['sample_id']:s for s in run.payload['samples']}
        for row in decision['frozen_reads']:
            sample = samples[row['sample_id']]
            block = dict(sample_id=row['sample_id'], source_id=row['source_id'], start=row['start'], end=row['end'],
                         text=sample['content'][row['start']:row['end']])
            request = build.request('extraction', build.facts, body=block, sources=build.facts['sources'],
                review_questions=[questions[q] for q in row['question_ids']])
            build.facts, _ = build.receive('supplement.reread.' + row['id'], 'extraction', build.facts, request)
            build.save_facts()
        construct_graph(build)
    retain(run, 'after-evidence-review', build.graph or build.facts)
    if build.graph:
        build.repair()
    return build.finish('finished', None if build.facts['actions'] else 'No usable focal Actions; inspect facts and gaps')
