"""One optional cross-document extraction over the existing, frozen handoff."""
from copy import deepcopy

from .prompts import system_prompt
from .proposals import Receiver, exact_deduplicate, reference, validate_envelope
from .records import evidence_samples, fingerprint, ground_quote, index_records, pointer, prompt_json
from .runtime import InvalidResponse
from .schema import COLLECTION_IDS


TASK_ID = 'whole-corpus.supplement'


def make_request(facts, payload):
    existing = {}
    evidence = index_records(facts)['evidence']
    for collection in ('entities', 'actions', 'contexts', 'relation_candidates'):
        summaries = []
        for record in facts[collection]:
            summary = {k: v for k, v in record.items() if k not in ('support', 'gaps', 'conflicts')}
            if 'support' in record:
                summary['support_samples'] = sorted({evidence[eid]['sample_id'] for s in record['support']
                                                     for eid in s.get('evidence_ids', []) if eid in evidence})
            if record.get('gaps'):
                summary['existing_gaps'] = [g.get('target') for g in record['gaps']]
            summaries.append(summary)
        existing[collection] = summaries
    source_by_id = index_records(facts)['sources']
    documents = [dict(sample_id=s['sample_id'], source_id=s['raw_data_id'],
                      title=source_by_id[s['raw_data_id']].get('title'),
                      published_at=source_by_id[s['raw_data_id']].get('published_at'),
                      text=s['content']) for s in payload['samples']]
    return dict(role='corpus_supplement', identity=payload['user_query']['extras']['person_event'],
                query_text=payload['user_query']['query_text'], existing=existing, documents=documents)


def validate_delta(value):
    if not isinstance(value, dict) or not isinstance(value.get('support_additions'), list):
        raise ValueError('Expected native extraction fields and support_additions array')
    validate_envelope('extraction', {k: v for k, v in value.items() if k != 'support_additions'})


def adopt_delta(build, raw, request):
    validate_delta(raw)
    payload = build.run.payload
    samples = evidence_samples(payload)
    ranges = {s: [(0, len(r['content']))] for s, r in samples.items()}
    namespace = TASK_ID + ':' + fingerprint(dict(request=request, response=raw))
    receiver = Receiver(build.facts, payload, build.ids, namespace, ranges)
    native = deepcopy({k: v for k, v in raw.items() if k != 'support_additions'})
    if raw['support_additions'] and not any(native[k] for k in ('entities', 'actions', 'contexts', 'relation_candidates')):
        native.setdefault('note', 'Only incremental support was proposed.')
    original_evidence = native['evidence']
    native['evidence'] = []
    for number, proposal in enumerate(original_evidence):
        try:
            entry = ground_quote(proposal, samples, 'preview', ranges[proposal['sample_id']])
            if entry['location_status'] != 'matched':
                raise ValueError('Supporting quote is ' + entry['location_status'])
            native['evidence'].append(proposal)
        except (TypeError, KeyError, ValueError) as exc:
            receiver.reject('new_evidence.' + str(number), exc)
    receiver.extract(native)
    before = index_records(build.facts)
    for number, item in enumerate(raw['support_additions']):
        label = 'additional_support.' + str(number)
        def attach(package):
            fields = {'collection', 'object_id', 'target', 'mode', 'reason', 'sample_id', 'quote'}
            if not isinstance(item, dict) or fields - item.keys() or item.keys() - fields - {'context_before', 'context_after'}:
                raise ValueError('Invalid support addition fields')
            collection, oid, target = item['collection'], item['object_id'], item['target']
            if collection not in ('actions', 'contexts', 'relation_candidates') or oid not in before[collection]:
                raise ValueError('Append support only to an existing indexed fact')
            if not isinstance(target, str) or not target.startswith('/') or target.split('/')[1] in ('support', 'gaps', 'conflicts', COLLECTION_IDS[collection], 'phase_id'):
                raise ValueError('Support must target an existing substantive fact field')
            record = index_records(package)[collection][oid]
            if pointer(record, target) is None or item['mode'] not in ('O', 'A', 'I') or not isinstance(item['reason'], str) or not item['reason'].strip():
                raise ValueError('An occupied field, support mode and reason are required')
            evidence = ground_quote(item, samples, build.ids.assign('evidence', label, namespace), ranges[item['sample_id']])
            if evidence['location_status'] != 'matched':
                raise ValueError('Additional support quote is ' + evidence['location_status'])
            same = next((e for e in package['evidence'] if e['location_status'] == 'matched' and all(
                e[k] == evidence[k] for k in ('sample_id', 'sample_sha256', 'start', 'end'))), None)
            if same is None:
                package['evidence'].append(evidence)
            eid = (same or evidence)['evidence_id']
            if any(s['target'] == target and s['mode'] == item['mode'] and eid in s.get('evidence_ids', []) for s in record['support']):
                return
            record['support'].append(dict(target=target, mode=item['mode'], evidence_ids=[eid], reason=item['reason']))
        refs = []
        if isinstance(item, dict) and item.get('collection') in ('actions', 'contexts', 'relation_candidates') and isinstance(item.get('object_id'), str):
            refs = [reference(item['collection'], item['object_id'])]
        receiver.apply(label, attach, refs, proposal=item)
    build.facts, report = receiver.finish()
    record = dict(task_id=TASK_ID, role='extraction', report=report)
    build.reports.append(record)
    build.run.state['id_map'] = build.ids.mapping
    build.run.save(TASK_ID + '-adoption.json', dict(**record, package_fingerprint=fingerprint(build.facts)))
    build.save_facts()
    return report


def supplement(build):
    """Read every handed document once together, within the original call and context budgets."""
    run = build.run
    build.facts = exact_deduplicate(build.facts, run.payload)
    request = make_request(build.facts, run.payload)
    system = system_prompt('corpus_supplement')
    characters = len(system) + len(prompt_json(dict(task=request, read_results=[])))
    receipt = dict(samples=len(request['documents']),
                   body_chars=sum(len(doc['text']) for doc in request['documents']),
                   complete_prompt_chars=characters,
                   before_facts=fingerprint(build.facts),
                   request_fingerprint=fingerprint(dict(system=system, task=request)))
    run.save('whole-corpus-delivery.json', receipt)
    if characters > run.config.max_context_chars:
        run.state['corpus_supplement'] = dict(status='skipped', reason='model_context_chars', **receipt)
        run.persist()
        return
    try:
        raw = run.infer(TASK_ID, system, request, build.facts, validate_delta, single_response=True)
    except InvalidResponse as exc:
        # This optional pass must use at most one model call, including across resumes.
        run.state['corpus_supplement'] = dict(status='invalid_response', reason=str(exc), **receipt)
    else:
        report = adopt_delta(build, raw, request)
        run.state['corpus_supplement'] = dict(status='processed', accepted=len(report['accepted']),
                                             rejected=len(report['rejected']), **receipt)
    run.persist()
