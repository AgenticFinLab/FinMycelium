"""Durable receipts for one optional supplement to a frozen person Event build."""
import json

from .records import fingerprint, json_bytes, sha256
from .runtime import write_json
from .schema import COLLECTION_IDS


def read_artifact(directory, name, digest):
    raw = (directory / 'supplement' / (name + '.json')).read_bytes()
    if sha256(raw) != digest:
        raise ValueError('Supplement artifact integrity mismatch: ' + name)
    return json.loads(raw)


def retained(run, name):
    digest = run.state.get('supplement', {}).get('files', {}).get(name)
    return read_artifact(run.directory, name, digest) if digest else None


def retain(run, name, value):
    ledger = run.state.setdefault('supplement', {})
    files = ledger.setdefault('files', {})
    if name in files:
        if read_artifact(run.directory, name, files[name]) != value:
            raise ValueError('A pinned supplement artifact changed: ' + name)
        return
    files[name] = write_json(run.directory / 'supplement' / (name + '.json'), value)
    run.persist()


def input_transition(directory, state, supplied):
    """Complete an interrupted activation from hash-checked parent and successor files.

    Only a prepared transition may replace the parent's two run-local pointers.
    The collected handoff and the before snapshot are immutable.
    """
    ledger = state.get('supplement', {})
    if 'transition' not in ledger:
        return supplied
    files = ledger['files']
    parent, successor = files['base-input'], files['effective-input']
    if sha256(json_bytes(supplied)) not in {parent, successor}:
        raise ValueError('Provided input differs from both frozen supplement revisions')
    read_artifact(directory, 'base-input', parent)
    final = read_artifact(directory, 'effective-input', successor)
    provenance = read_artifact(directory, 'effective-provenance', files['effective-provenance'])
    for filename, current, previous, value in (
        ('input.json', successor, parent, final),
        ('provenance.json', files['effective-provenance'], files['base-provenance'], provenance)):
        digest = sha256((directory / filename).read_bytes())
        if digest == current:
            continue
        if ledger['transition'] != 'prepared' or digest != previous:
            raise ValueError('Active build artifact changed: ' + filename)
        write_json(directory / filename, value)
    if ledger['transition'] == 'prepared':
        for field in ('facts','facts_sha256','checks','checks_sha256','output','graph_sha256','visualization',
                      'organization_snapshot','organization_snapshot_sha256','relation_discovery','relation_discovery_sha256'):
            state.pop(field, None)
        state.update(result_status='none', render_status='not_started')
        state.update(original_input_sha256=parent, input_sha256=successor,
                     provenance_sha256=files['effective-provenance'])
        ledger['transition'] = 'active'
        write_json(directory / 'state.json', state)
    return final


def activate(run, final, included):
    base_provenance = retained(run, 'base-provenance')
    provenance = {**base_provenance, 'parent_input_sha256':run.state['input_sha256'],
                  'input_sha256':sha256(json_bytes(final)), 'additional_passages':included,
                  'sample_sha256':{s['sample_id']:sha256(s['content'].encode()) for s in final['samples']}}
    retain(run, 'effective-input', final)
    retain(run, 'effective-provenance', provenance)
    run.state['supplement']['transition'] = 'prepared'
    run.persist()
    run.payload = input_transition(run.directory, run.state, run.payload)


def usage(state):
    calls, reads = state['calls'], state['reads']
    exceeded = {}
    for label, cap in (('workbench_calls', 60), ('previous_experiment_calls', 90)):
        if len(calls) > cap:
            exceeded[label] = calls[cap]['task_id']
    chars = 0
    for n, read in enumerate(reads, 1):
        chars += read['chars']
        for key, condition in [('workbench_read_calls', n > 60), ('workbench_read_chars', chars > 160000)]:
            if condition:
                exceeded.setdefault(key, read['task_id'])
    return dict(builder_calls=len(calls), local_reads=len(reads), local_read_chars=chars,
                peak_context_chars=max((c.get('context_chars', 0) for c in calls), default=0),
                first_above_previous_limits=exceeded)


def comparison(build):
    run = build.run
    before = retained(run, 'before')
    decision = retained(run, 'decision')
    if before is None or decision is None:
        return
    original = before['graph'] or before['facts']
    comparable = retained(run, 'after-evidence-review')
    final = build.graph or build.facts
    passages = {x['sample_id']: x for x in decision['included']}
    frozen = decision['frozen_reads']
    evidence = {e['evidence_id']:e for e in final['evidence']}
    changes = {}
    for collection in ('actions', 'contexts', 'stages', 'phases', 'relations'):
        key = COLLECTION_IDS[collection]
        old = {r[key]: r for r in original.get(collection, [])}
        new = {r[key]: r for r in final.get(collection, [])}
        cited = []
        for oid, record in new.items():
            for support in record.get('support', []):
                for eid in support['evidence_ids']:
                    e = evidence.get(eid, {})
                    matches = [p['id'] for p in frozen if p['sample_id'] == e.get('sample_id')
                               and e.get('start') is not None and e.get('end') is not None
                               and max(e['start'],p['start']) < min(e['end'],p['end'])]
                    if e.get('sample_id') in passages or matches:
                        cited.append(dict(object_id=oid, field=support['target'], evidence_id=eid,
                            source_id=e['source_id'], sample_id=e['sample_id'], quote=e['quote'],
                            passage_ids=matches or [passages[e['sample_id']]['id']]))
        intermediate = {r[key]:r for r in comparable.get(collection, [])}
        changes[collection] = dict(before=len(old), after_evidence_review=len(intermediate), after=len(new),
            same_stage_added=sorted(intermediate.keys()-old.keys()), same_stage_removed=sorted(old.keys()-intermediate.keys()),
            same_stage_changed=sorted(k for k in old.keys() & intermediate.keys() if fingerprint(old[k]) != fingerprint(intermediate[k])),
            added=sorted(new.keys()-old.keys()),
            removed=sorted(old.keys()-new.keys()), changed=sorted(k for k in new.keys() & old.keys()
                if fingerprint(old[k]) != fingerprint(new[k])), supplementary_support=cited)
    lineage = [r for r in build.facts.get('lineage', []) if r.get('operation') in ('merge','split')]
    report = dict(lineage=lineage, parent_input_sha256=run.state['supplement']['files']['base-input'],
                  input_sha256=run.state['input_sha256'], before_graph_sha256=sha256(json_bytes(original)),
                  final_graph_sha256=run.state.get('graph_sha256'), execution_status=run.state['execution_status'],
                  result_status=run.state['result_status'], unresolved_question_ids=decision['unresolved_question_ids'], questions=decision['questions'],
                  outcome=decision['outcome'], reason=decision['reason'], checks=decision['checks'],
                  added_chars=decision['added_chars'], included=decision['included'],
                  frozen_reads=frozen, skipped=decision['skipped'], search=decision['search'],
                  before_usage=before['usage'], total_usage=usage(run.state), changes=changes)
    path, digest = run.save('supplement-comparison.json', report)
    run.state['supplement'].update(comparison=path, comparison_sha256=digest)
    run.persist()
