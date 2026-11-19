"""Six-step construction of one confirmed person Event, with no external retrieval."""
from collections import defaultdict
from copy import deepcopy
import json
from pathlib import Path
import re
import uuid

from finmy.search.summary import directory_lock
from .prompts import system_prompt
from .proposals import Receiver, exact_deduplicate, graph_from_facts, reference, validate_envelope
from .records import IdMap, fingerprint, index_records, seed_facts, validate_input, prompt_json
from .runtime import EventBuildConfig, Execution, InvalidResponse, LimitReached, PauseRequested, now, write_json
from .schema import COLLECTION_IDS, GRAPH_VERSION, LEGACY_GRAPH_VERSION
from .feedback import (correction_scope, correction_issues, validate_correction,
                       unresolved_report, reserved_records, clear_resolved_pending)
from .context import navigation, sized_request
from .grouping import ambiguity_groups
from .validation import check_graph
from .relation_review import discovery_scope
from .evidence_support import iter_citations, citation_is_located
from .scheduling import Task, ModelCallFailed, emit


def body_ranges(payload, config):
    for sample in payload['samples']:
        start = 0
        while start < len(sample['content']):
            end = min(start + config.extraction_chars, len(sample['content']))
            yield dict(sample_id=sample['sample_id'], source_id=sample['raw_data_id'], start=start, end=end,
                       text=sample['content'][start:end])
            if end == len(sample['content']):
                break
            start = end - config.extraction_overlap


def brief(package):
    """Global navigation index. Exact records remain available through read_records."""
    return navigation(package)


class Construction:
    def __init__(self, execution):
        self.run = execution
        self.facts = seed_facts(execution.payload)
        self.graph = None
        self.coverage = []
        self.reports = []
        self.ids = IdMap(execution.state['id_map'])

    def request(self, role, package, **fields):
        base = dict(role=role, identity=self.run.payload['user_query']['extras']['person_event'],
                    query_text=self.run.payload['user_query']['query_text'],
                    read_limits=dict(read_chars=self.run.config.read_chars, retrieval_top_k=self.run.config.retrieval_top_k,
                                     max_read_rounds=self.run.config.max_read_rounds),
                    **fields)
        base['readable_samples'] = [dict(source_id=sample['raw_data_id'],
            sample_id=sample['sample_id'], length=len(sample['content']))
            for sample in self.run.payload['samples']]
        reserve = self.run.config.read_chars + 1024
        if role == 'relations':
            reserve = max(reserve, self.run.config.max_context_chars // 4)
            base['read_limits']['max_record_refs'] = 20
        return sized_request(base, package, self.run.config.max_context_chars - len(system_prompt(role)),
                             reserve=reserve)

    def receive(self, task_id, role, package, request, **kwargs):
        return self.run.drive(task_id, self.receive_steps(task_id, role, package, request, **kwargs), stage='repair' if task_id.startswith('repair.') else role)

    def receive_steps(self, task_id, role, package, request, *, reserved=None, initial_package=None, live=False, **scope):
        system = system_prompt(role)
        frozen = package if initial_package is None else initial_package
        request = self.run.task_request(task_id, system, request, frozen)
        group = self.run.attempt_group(task_id, system, request, frozen)
        records, allowed = [], None
        result = package
        for number in range(self.run.config.max_json_attempts):
            step_id = task_id if number == 0 else task_id + '.correct.' + str(number)
            if number:
                request = self.run.task_request(step_id, system, request, result)
            validator = (lambda v: validate_envelope(role, v)) if allowed is None else \
                (lambda v: validate_correction(role, v, allowed))
            try:
                infer_package = frozen if number == 0 else result
                raw = yield from self.run.infer_steps(step_id, system, request, infer_package, validator, attempt_group=group)
            except InvalidResponse:
                if not records:
                    raise
                break  # Preserve adopted facts and the outstanding rejection evidence.
            if live:
                result = self.graph if role in ('organization', 'relations') else self.facts
            result, record = self.adopt(step_id, role, result, request, raw, reserved=allowed or reserved, **scope)
            records.append(record)
            if number:
                if role == 'relations':
                    self.resolve_relation_corrections(records[:-1], record, result)
                else:
                    self.resolve_fact_corrections(records[:-1], record)
                clear_resolved_pending(result, self.reports, self.outstanding)
            if role in ('organization', 'relations'):
                self.graph = result  # Preserve adopted edges if a local correction pauses/fails.
            if result.get('schema_version') == self.facts['schema_version']:
                self.facts = result
                self.save_facts()  # A pause/error during correction must retain valid neighbors.
            combined = unresolved_report(records, self.outstanding)
            handled = {(ref['collection'], ref['object_id']) for r in records[1:]
                       for item in r['report']['accepted_items'] for ref in item['refs']}
            allowed = correction_scope(role, combined, result, handled)
            if not allowed:
                break
            self.run.task_event('RetryRequested', reason='adoption_rejected')
            self.run.reject_proposals(group, fingerprint(dict(task_id=step_id, response=raw)), combined['rejected'])
            fields = {k: deepcopy(v) for k, v in request.items() if k not in (
                'role', 'identity', 'query_text', 'facts_index', 'read_limits', 'related_records', 'context_selection')}
            fields['correction'] = dict(issues=correction_issues(combined['rejected'], allowed), allowed_records=allowed)
            if role == 'consolidation':
                scope = dict(assigned={(c, oid) for c, ids in allowed.items() for oid in ids})
                fields['assigned'] = [reference(c, oid) for c, oid in sorted(scope['assigned'])]
                fields['candidates'] = [dict(collection=c, record=index_records(result)[c][oid])
                                         for c, oid in sorted(scope['assigned'])]
            elif role == 'relations':
                scope = dict(action_ids=allowed.get('actions', []), phase_ids=allowed.get('phases', []),
                             review_scope=scope.get('review_scope') if 'relation_review' in allowed else None)
                fields['assigned_action_ids'] = scope['action_ids']
                fields['assigned_phase_ids'] = scope['phase_ids']
                fields['assigned_records'] = {
                    c: [r for r in result[c] if r[COLLECTION_IDS[c]] in allowed.get(c, [])]
                    for c in ('actions', 'phases')}
                if scope['review_scope'] is None:
                    fields.pop('relation_discovery', None)
                else:
                    fields['accepted_relations'] = [{k: r[k] for k in (
                        'relation_id', 'from_action_id', 'to_action_id', 'type')}
                        for r in result['relations'] if r['from_action_id'] in scope['review_scope']['action_ids']]
            request = self.request(role, result, **fields)
        return result, unresolved_report(records, self.outstanding)

    def resolve_relation_corrections(self, previous, correction, package):
        updated = {(r['collection'], r['object_id'])
                   for record in [*previous[1:], correction]
                   for item in record['report']['accepted_items'] if item['item'].startswith('context_updates:')
                   for r in item['refs']}
        linked = {ref['context_id'] for c, field in (
            ('actions', 'delta_context_refs'), ('phases', 'baseline_context_refs'))
            for record in package[c] for ref in record.get(field, [])}
        for record in previous:
            for issue in self.outstanding(record)['rejected']:
                refs = {(r['collection'], r['object_id']) for r in issue['refs']}
                done = issue['item'] == 'relation_review' and 'relation_review' in correction['report']['accepted']
                if issue['item'] == 'missing_context_update' or issue['item'].startswith('context_updates:'):
                    done = bool(refs) and refs <= updated
                if issue['item'].startswith('context:'):
                    ids = {oid for c, oid in refs if c == 'contexts'}
                    done = bool(ids) and ids <= linked
                if done:
                    record.setdefault('resolutions', []).append(dict(issue_fingerprint=fingerprint(issue),
                                                                     resolved_by=correction['task_id']))

    def resolve_fact_corrections(self, previous, correction):
        accepted = {(r['collection'], r['object_id']) for record in [*previous[1:], correction]
                    for item in record['report']['accepted_items'] for r in item['refs']}
        for record in previous:
            for issue in self.outstanding(record)['rejected']:
                refs = {(r['collection'], r['object_id']) for r in issue['refs']
                        if isinstance(r, dict) and 'collection' in r and 'object_id' in r}
                if refs and refs <= accepted:
                    record.setdefault('resolutions', []).append(dict(issue_fingerprint=fingerprint(issue),
                        resolved_by=correction['task_id']))

    def adopt(self, task_id, role, package, request, raw, *, reserved=None, **scope):
        namespace = task_id + ':' + fingerprint(dict(request=request, response=raw))
        ranges = defaultdict(list)
        if 'body' in request:
            block = request['body']
            ranges[block['sample_id']].append((block['start'], block['end']))
        for read in self.run.state['reads']:
            if read['task_id'] != task_id:
                continue
            values = read['result'] if isinstance(read['result'], list) else [read['result']]
            for value in values:
                if isinstance(value, dict) and {'sample_id', 'start', 'end', 'text'} <= value.keys():
                    ranges[value['sample_id']].append((value['start'], value['end']))
        for evidence in package['evidence']:
            for citation in iter_citations(evidence):
                if citation_is_located(citation):
                    ranges[citation['sample_id']].append((citation['start'], citation['end']))
        receiver = Receiver(package, self.run.payload, self.ids, namespace, ranges, reserved=reserved)
        method = {'extraction': receiver.extract, 'consolidation': receiver.consolidate,
                  'organization': receiver.organize, 'relations': receiver.relate}[role]
        result, report = method(raw, **scope)
        record = dict(task_id=task_id, role=role, report=report)
        if scope.get('review_scope') is not None:
            record['relation_discovery_scope'] = deepcopy(scope['review_scope'])
        if role == 'extraction' and 'body' in request:
            record['body_processed'] = True
        self.reports.append(record)
        self.run.state['id_map'] = self.ids.mapping
        self.run.persist()
        self.run.save(task_id + '-adoption.json', dict(**record, package_fingerprint=fingerprint(result)))
        return result, record

    def save_facts(self):
        self.sync_coverage()
        path, digest = self.run.save('facts.json', self.facts)
        self.run.state.update(facts=path, facts_sha256=digest, coverage=self.coverage)
        self.run.persist()

    def sync_coverage(self):
        """Body delivery/processing and unresolved proposals are different facts."""
        for number, block in enumerate(self.coverage):
            task_id = 'extract.' + str(number)
            records = [r for r in self.reports if r['task_id'] == task_id or r['task_id'].startswith(task_id + '.correct.')]
            if any(r.get('body_processed') for r in records):
                block['body_status'] = 'processed'
                report = unresolved_report(records, self.outstanding)
                block['proposal_status'] = 'unresolved' if report['rejected'] or report['pending'] else 'resolved'
                block['status'] = 'partial' if block['proposal_status'] == 'unresolved' else 'processed'
            else:
                block['body_status'] = 'failed' if block['status'] == 'failed' else 'not_processed'
                block['proposal_status'] = 'not_processed'

    def fail_task(self, task_id, role, reason, *, refs=None, number=None):
        item = dict(refs=refs or [], reason=task_id + ': ' + reason, evidence_ids=[])
        self.facts['pending'].append(item)
        if number is not None:
            self.coverage[number]['status'] = 'failed'
        self.reports.append(dict(task_id=task_id, role=role,
            report=dict(accepted=[], rejected=[], pending=[item])))
        self.save_facts()

    def blocked(self, stage, reason):
        emit(self.run, stage, stage, 'TaskQueued')
        emit(self.run, stage, stage, 'TaskBlocked', reason=reason)
        self.run.state.setdefault('stages', {})[stage] = dict(status='blocked', reason=reason)
        self.run.persist()

    def stage(self, name, operation):
        """Reuse a completed stage snapshot, or rebuild it from per-call checkpoints."""
        for key in list(self.run.state.get('task_states', {})):
            if key.startswith(name + ':'):
                del self.run.state['task_states'][key]
        self.run.state.setdefault('stages', {})[name] = dict(status='running')
        before = fingerprint(dict(input=self.run.state['input_sha256'], facts=self.facts,
            graph=self.graph, coverage=self.coverage, reports=self.reports))
        path = self.run.directory / 'checkpoints' / ('stage-' + name + '.json')
        if path.is_file():
            saved = json.loads(path.read_text())
            if saved['before'] == before:
                data = saved['result']
                if fingerprint(data) != saved['result_sha256']:
                    raise ValueError('Stage checkpoint changed')
                self.facts, self.graph = data['facts'], data['graph']
                self.coverage, self.reports = data['coverage'], data['reports']
                self.ids.mapping.update(data['id_map'])
                self.run.state['id_map'] = self.ids.mapping
                self.run.state.setdefault('stages', {})[name] = dict(status='completed', reused=True)
                self.save_facts()
                return True
        try:
            operation()
        except (ModelCallFailed, InvalidResponse, LimitReached) as exc:
            reason = str(exc) if isinstance(exc, LimitReached) else type(
                exc.original if isinstance(exc, ModelCallFailed) else exc).__name__
            if not any(t['stage'] == name and t['status'] in ('failed', 'limited')
                       for t in self.run.state.get('task_states', {}).values()):
                emit(self.run, name, name, 'TaskQueued')
                emit(self.run, name, name, 'TaskLimited' if isinstance(exc, LimitReached) else 'TaskFailed', reason=reason)
            self.fail_task(name, name, reason)
            self.run.state.setdefault('stages', {})[name] = dict(status='partial', reason=reason)
            self.run.persist()
            return False
        status = self.run.state.get('stages', {}).get(name, {}).get('status', 'completed')
        if status == 'running':
            status = 'completed'
            self.run.state['stages'][name]['status'] = status
        if status == 'completed':
            data = dict(facts=self.facts, graph=self.graph, coverage=self.coverage,
                        reports=self.reports, id_map=self.ids.mapping)
            write_json(path, dict(before=before, result=data, result_sha256=fingerprint(data)))
        return status == 'completed'

    def extract(self):
        ranges = list(body_ranges(self.run.payload, self.run.config))
        self.coverage = [{k: v for k, v in block.items() if k != 'text'} | {'status': 'not_processed'} for block in ranges]
        self.save_facts()
        frozen = deepcopy(self.facts)

        def process(number, block):
            task_id = 'extract.' + str(number)
            request = self.request('extraction', frozen, body=block, sources=frozen['sources'])
            self.facts, report = yield from self.receive_steps(task_id, 'extraction', self.facts, request,
                initial_package=frozen, live=True)
            self.coverage[number]['status'] = 'partial' if report['rejected'] or report['pending'] else 'processed'
            self.save_facts()

        tasks = [Task('extract.' + str(n), process(n, block),
            lambda task_id, reason, n=n: self.fail_task(task_id, 'extraction', reason, number=n))
            for n, block in enumerate(ranges)]
        self.run.execute_tasks('extraction', tasks)

    def consolidate(self):
        self.facts = exact_deduplicate(self.facts, self.run.payload)
        groups = ambiguity_groups(self.facts)
        assigned_all = {ref for group in groups for ref in group}
        for collection in ('entities', 'actions', 'contexts', 'relation_candidates'):
            for record in self.facts[collection]:
                ref = reference(collection, record[COLLECTION_IDS[collection]])
                if (collection, ref['object_id']) not in assigned_all:
                    self.facts['lineage'].append(dict(operation='keep', input_refs=[ref], output_refs=[ref],
                        reason='Retained without semantic merge: no bounded ambiguity group selected.', step_id='consolidate.keep'))
        frozen = deepcopy(self.facts)
        tasks = []

        def process(task_id, assigned, request):
            self.facts, _ = yield from self.receive_steps(task_id, 'consolidation', self.facts, request,
                assigned=assigned, initial_package=frozen, live=True)
            self.save_facts()

        for number, group in enumerate(groups):
            assigned = {(c, oid) for c, oid in group if oid in index_records(frozen)[c]}
            if len(assigned) < 2:
                continue
            refs = [reference(c, oid) for c, oid in sorted(assigned)]
            request = self.request('consolidation', frozen, assigned=refs,
                candidates=[dict(collection=c, record=index_records(frozen)[c][oid]) for c, oid in sorted(assigned)])
            task_id = 'consolidate.' + str(number)
            tasks.append(Task(task_id, process(task_id, assigned, request),
                lambda task_id, reason, refs=refs: self.fail_task(task_id, 'consolidation', reason, refs=refs)))
        self.run.execute_tasks('consolidation', tasks)
        self.save_facts()

    def organize(self):
        self.graph = graph_from_facts(self.facts)
        request = self.request('organization', self.graph)
        self.graph, report = self.receive('organize', 'organization', self.graph, request)
        self.retain_splits(report)

    def retain_splits(self, report):
        if not report.get('lineage'):
            return
        previous_ids = {a['action_id'] for a in self.facts['actions']}
        actions = deepcopy(self.graph['actions'])
        for action in actions:
            action['phase_id'] = None
            action['support'] = [s for s in action['support'] if s['target'] != '/phase_id']
            action.pop('delta_context_refs', None)
            action.pop('baseline_context_exclusions', None)
        self.facts['actions'] = actions
        self.facts['evidence'] = deepcopy(self.graph['evidence'])
        self.facts['lineage'].extend(deepcopy(report['lineage']))
        removed = previous_ids - {a['action_id'] for a in actions}
        for candidate in self.facts['relation_candidates']:
            for field in ('from_action_id', 'to_action_id'):
                if candidate[field] in removed:
                    candidate[field] = None
                    candidate.setdefault('gaps', []).append(dict(target='/' + field, reason='Endpoint needs confirmation after Action split.'))
                    self.facts['pending'].append(dict(refs=[reference('relation_candidates', candidate['candidate_id'])],
                        reason='Resolve relation endpoint after Action split.', evidence_ids=[]))
        self.save_facts()

    def relation_request(self, actions, phases):
        candidates = [c for c in self.facts['relation_candidates']
            if c.get('from_action_id') in actions
            or (c.get('from_action_id') is None and c.get('to_action_id') in actions)
            or (c.get('from_action_id') is None and c.get('to_action_id') is None
                and self.graph['actions'] and self.graph['actions'][0]['action_id'] in actions)]
        return self.request('relations', self.graph, assigned_action_ids=actions,
            assigned_phase_ids=phases, relation_candidates=candidates,
            relation_discovery=discovery_scope(actions, candidates),
            assigned_records=dict(actions=[a for a in self.graph['actions'] if a['action_id'] in actions],
                                 phases=[p for p in self.graph['phases'] if p['phase_id'] in phases]))

    def relate(self):
        # Own each Action/Phase once, while all other endpoints remain navigable.
        actions = [a['action_id'] for a in self.graph['actions'] if a.get('phase_id') in
                   {p['phase_id'] for p in self.graph['phases']}]
        phases = [p['phase_id'] for p in self.graph['phases']]
        action_phases = {a['action_id']: a.get('phase_id') for a in self.graph['actions']}
        reserve = max(self.run.config.read_chars + 1024, self.run.config.max_context_chars // 4)
        initial_limit = self.run.config.max_context_chars - reserve
        workers = self.run.config.extraction_workers
        number = 0
        while actions or phases or number == 0:
            frozen = deepcopy(self.graph)
            jobs = []
            remaining_actions, remaining_phases = list(actions), list(phases)
            for slot in range(len(actions) + len(phases) + 1 if frozen is not None else 1):
                if not (remaining_actions or remaining_phases) and (number or jobs):
                    break
                cap = None
                if frozen is not None and remaining_actions:
                    cap = max(1, (len(actions) + workers-1) // workers)
                owned_actions, owned_phases = [], []
                request = self.relation_request([], [])
                for aid in remaining_actions:
                    if cap is not None and len(owned_actions) >= cap:
                        break
                    pid = action_phases[aid]
                    candidate_phases = owned_phases + ([pid] if pid in remaining_phases and pid not in owned_phases else [])
                    candidate = self.relation_request(owned_actions + [aid], candidate_phases)
                    selection = candidate['context_selection']
                    missing_evidence = selection['uncovered_action_ids'] or selection['omitted_relation_evidence_ids']
                    if ((owned_actions and missing_evidence) or
                            len(system_prompt('relations')) + len(prompt_json(dict(task=candidate, read_results=[]))) > initial_limit):
                        break
                    owned_actions.append(aid); owned_phases = candidate_phases; request = candidate
                # Empty Phases still need a baseline. An oversized Action+Phase pair
                # may first process the Phase, then retry the Action independently.
                if not owned_actions or len(owned_actions) == len(remaining_actions):
                    for pid in remaining_phases:
                        if pid in owned_phases:
                            continue
                        candidate = self.relation_request(owned_actions, owned_phases + [pid])
                        if len(system_prompt('relations')) + len(prompt_json(dict(task=candidate, read_results=[]))) > initial_limit:
                            break
                        current = request['context_selection']
                        selection = candidate['context_selection']
                        if any(set(selection[field]) - set(current[field]) for field in
                               ('uncovered_action_ids', 'omitted_relation_evidence_ids')):
                            break
                        owned_phases.append(pid); request = candidate
                if (remaining_actions or remaining_phases) and not (owned_actions or owned_phases):
                    # Isolate an oversized item instead of discarding already planned work.
                    owned_actions = remaining_actions[:1]
                    owned_phases = [] if owned_actions else remaining_phases[:1]
                    request = None
                jobs.append((number, owned_actions, owned_phases, request))
                remaining_actions = [aid for aid in remaining_actions if aid not in owned_actions]
                remaining_phases = [pid for pid in remaining_phases if pid not in owned_phases]
                number += 1
            by_id = {'relate.' + str(n): (n, owned_actions, owned_phases, request)
                     for n, owned_actions, owned_phases, request in jobs}

            def process(task_id):
                n, owned_actions, owned_phases, request = by_id[task_id]
                if request is None:
                    raise LimitReached('model_context_chars')
                self.graph, _ = yield from self.receive_steps(task_id, 'relations', self.graph, request,
                    initial_package=frozen, live=True, action_ids=owned_actions, phase_ids=owned_phases,
                    review_scope=request['relation_discovery'])
            tasks = []
            for task_id, (_, owned_actions, owned_phases, _) in by_id.items():
                refs = [reference('actions', aid) for aid in owned_actions]
                refs += [reference('phases', pid) for pid in owned_phases]
                tasks.append(Task(task_id, process(task_id),
                    lambda task_id, reason, refs=refs: self.fail_task(task_id, 'relations', reason, refs=refs)))
            self.run.execute_tasks('relations', tasks)
            actions, phases = remaining_actions, remaining_phases

    @staticmethod
    def outstanding(record):
        """Project unresolved items without changing the original adoption evidence."""
        report = deepcopy(record['report'])
        resolved = {r['issue_fingerprint'] for r in record.get('resolutions', [])}
        dismissed = [r for r in report['rejected'] if fingerprint(r) in resolved]
        report['rejected'] = [r for r in report['rejected'] if fingerprint(r) not in resolved]
        def pending_of(issue):
            return {k: issue[k] for k in ('refs', 'reason', 'evidence_ids')}
        report['pending'] = [p for p in report['pending']
            if p in report.get('reported_pending', [])
            or p not in [pending_of(r) for r in dismissed]
            or p in [pending_of(r) for r in report['rejected']]]
        return report

    def record_resolutions(self, role, repaired):
        """Only program-verifiable repairs clear matching rejection items.

        A model-authored pending item is never discharged by silence in a later
        response. Unmatched rejected proposals remain visible for review.
        """
        accepted = repaired['accepted']
        assigned = {r['object_id'] for item in repaired.get('accepted_items', [])
                    if item['item'].startswith('assignment:') for r in item['refs']}
        updated = {(r['collection'], r['object_id']) for item in repaired.get('accepted_items', [])
                   if item['item'].startswith('context_updates:') for r in item['refs']}
        adopted = {(r['collection'], r['object_id']) for item in repaired.get('accepted_items', []) for r in item['refs']}
        for record in self.reports:
            if record['role'] != role or record['task_id'].startswith('repair.'):
                continue
            for issue in self.outstanding(record)['rejected']:
                refs = {(r['collection'], r['object_id']) for r in issue['refs']}
                done = (issue['item'] == 'event_overview' and 'event_overview' in accepted)
                if issue['item'] == 'unassigned_action' or issue['item'].startswith('assignment:'):
                    ids = {oid for collection, oid in refs if collection == 'actions'}
                    if not ids and issue['item'].startswith('assignment:'):
                        ids = {issue['item'].split(':', 1)[1]}
                    done = bool(ids) and ids <= assigned
                if issue['item'] == 'missing_context_update' or issue['item'].startswith('context_updates:'):
                    done = bool(refs) and refs <= updated
                if issue['item'].startswith(('stages:', 'phases:', 'relation:')):
                    done = bool(refs) and refs <= adopted
                if issue['item'].startswith('context:'):
                    ids = {oid for collection, oid in refs if collection == 'contexts'}
                    linked = {ref['context_id'] for collection, field in (
                        ('phases', 'baseline_context_refs'), ('actions', 'delta_context_refs'))
                        for record in self.graph[collection] for ref in record.get(field, [])}
                    done = bool(ids) and ids <= linked
                if done:
                    record.setdefault('resolutions', []).append(dict(
                        issue_fingerprint=fingerprint(issue), resolved_by='repair.' + role))

    def repair(self, *, organization_only=False):
        checks = check_graph(self.graph, self.run.payload)
        # One round handles concrete failed organization/association work, not legal uncertainty.
        unresolved = []
        for record in self.reports:
            report = self.outstanding(record)
            # Discovery receipts already use their bounded local retry allowance.
            # A legacy final Context repair cannot discharge a missing review.
            report['rejected'] = [i for i in report['rejected'] if i['item'] != 'relation_review']
            if record['role'] in ('organization', 'relations') and report['rejected']:
                unresolved.append(dict(record, report=report))
        if not unresolved and checks['valid']:
            return
        if not self.run.config.final_repair_rounds:
            return
        flag = 'hierarchy_repair_used' if organization_only else 'final_repair_used'
        plan_path = self.run.directory / 'checkpoints' / ('hierarchy-repair-plan.json' if organization_only else 'final-repair-plan.json')
        if self.run.state.get(flag):
            if not plan_path.is_file():
                return
            plan = json.loads(plan_path.read_text())
            if plan['base_fingerprint'] != fingerprint(self.graph):
                return  # An earlier changed dependency cannot buy another repair round.
        else:
            tasks = []
            for role in ('organization', 'relations'):
                records = [r for r in unresolved if r['role'] == role]
                if records:
                    tasks.append(dict(role=role, issues=[i for r in records for i in r['report']['rejected']]))
            if not {'time', 'summary', 'support'} <= self.graph['event'].keys() and not any(t['role'] == 'organization' for t in tasks):
                tasks.insert(0, dict(role='organization', overview_only=True, issues=[dict(
                    item='event_overview', refs=[], reason='Complete the missing supported Event overview.', evidence_ids=[])]))
            if any(t['role'] == 'organization' and not t.get('overview_only') for t in tasks):
                # Context ownership depends on hierarchy; recheck against repaired parents.
                relation_task = next((t for t in tasks if t['role'] == 'relations'), None)
                if relation_task is None:
                    tasks.append(dict(role='relations', issues=[], recheck_after_organization=True))
                else:
                    relation_task['recheck_after_organization'] = True
            if organization_only:
                tasks = [task for task in tasks if task['role'] == 'organization']
            elif self.run.state.get('hierarchy_repair_used'):
                tasks = [task for task in tasks if task['role'] != 'organization']
            if not tasks:
                return
            plan = dict(base_fingerprint=fingerprint(self.graph), tasks=tasks)
            write_json(plan_path, plan)
            self.run.state[flag] = True
            self.run.persist()
        for task in plan['tasks']:
            role = task['role']
            refs = [r for item in task['issues'] for r in item['refs']]
            if role == 'organization':
                assigned = [] if task.get('overview_only') else [a['action_id'] for a in self.graph['actions'] if a.get('phase_id') is None]
                scope = dict(assigned=assigned)
                request = self.request(role, self.graph, repair_issues=task['issues'], assigned_action_ids=assigned)
            else:
                action_ids = sorted({r['object_id'] for r in refs if r['collection'] == 'actions'})
                phase_ids = sorted({r['object_id'] for r in refs if r['collection'] == 'phases'})
                if task.get('recheck_after_organization'):
                    action_ids = [a['action_id'] for a in self.graph['actions']]
                    phase_ids = [p['phase_id'] for p in self.graph['phases']]
                # Rejected records without a canonical ID are replayed only within their original ownership.
                if not action_ids and not phase_ids:
                    action_ids = [a['action_id'] for a in self.graph['actions']]
                scope = dict(action_ids=action_ids, phase_ids=phase_ids)
                request = self.request(role, self.graph, repair_issues=task['issues'], assigned_action_ids=action_ids, assigned_phase_ids=phase_ids)
            self.graph, report = self.receive('repair.' + role, role, self.graph, request,
                reserved=reserved_records(task['issues']), **scope)
            if role == 'organization':
                self.retain_splits(report)
            self.record_resolutions(role, report)

    def finish(self, execution_status, reason=None):
        if execution_status == 'finished' and any(
                t['status'] == 'limited' and t.get('reason') in ('model_calls', 'read_calls', 'read_chars')
                for t in self.run.state.get('task_states', {}).values()):
            execution_status = 'limit'
            reason = reason or 'Run budget exhausted; completed results retained'
        self.save_facts()
        reviews = [dict(task_id=r['task_id'], scope=r['relation_discovery_scope'],
                        review=r['report'].get('relation_review'),
                        accepted='relation_review' in r['report']['accepted'])
                   for r in self.reports if 'relation_discovery_scope' in r]
        completed = {aid for r in reviews if r['accepted'] for aid in r['scope']['action_ids']}
        expected = {a['action_id'] for a in (self.graph or self.facts)['actions']}
        path, digest = self.run.save('relation-discovery.json', dict(reviews=reviews,
            completed_action_ids=sorted(completed), incomplete_action_ids=sorted(expected - completed),
            semantic_review_required=True))
        self.run.state.update(relation_discovery=path, relation_discovery_sha256=digest)
        if self.graph is None and self.facts['actions']:
            self.graph = graph_from_facts(self.facts)
        unresolved = [dict(r, report=self.outstanding(r)) for r in self.reports
                      if self.outstanding(r)['rejected'] or self.outstanding(r)['pending']]
        body_done = bool(self.coverage) and all(r['body_status'] == 'processed' for r in self.coverage)
        coverage_done = body_done and all(r['proposal_status'] == 'resolved' for r in self.coverage)
        report = check_graph(self.graph, self.run.payload) if self.graph else check_graph(self.facts, self.run.payload)
        facts_check = check_graph(self.facts, self.run.payload)
        if self.graph:
            fact_errors = [i for i in facts_check['issues'] if i['severity'] == 'error']
            report['issues'].extend(fact_errors)
            report['summary']['errors'] += len(fact_errors)
            report['summary']['checked'].append('fact_contract')
            report['valid'] = report['valid'] and facts_check['valid']
        task_failures = [v for v in self.run.state.get('task_states', {}).values()
                         if v['status'] in ('failed', 'limited', 'blocked')]
        result = 'partial' if task_failures else 'none'
        graph_path, graph_hash = None, None
        if self.graph and self.graph['actions']:
            graph_path, graph_hash = self.run.save('epg.json', self.graph)
            result = 'draft' if (execution_status == 'finished' and report['valid'] and coverage_done
                and not task_failures and not unresolved and not self.facts['pending'] and expected <= completed) else 'partial'
        elif self.facts['contexts'] or self.facts['evidence']:
            result = 'partial'
        checks = dict(run_id=self.run.state['run_id'], input_sha256=self.run.state['input_sha256'],
            graph_sha256=graph_hash, artifact_hashes=dict(facts=self.run.state['facts_sha256']),
            summary=report['summary'], issues=report['issues'], review_required=True,
            coverage=self.coverage, unresolved_tasks=unresolved, task_failures=task_failures,
            result_status=result, execution_status=execution_status)
        if not body_done:
            checks['issues'].append(dict(code='BODY_PROCESSING_INCOMPLETE', severity='warning', artifact='facts',
                object_type='event', object_id=self.facts['event']['event_id'], field='',
                message='Some handed body ranges have not produced a processed response.'))
            checks['summary']['warnings'] += 1
        if any(r['proposal_status'] == 'unresolved' for r in self.coverage):
            checks['issues'].append(dict(code='PROPOSALS_UNRESOLVED', severity='warning', artifact='facts',
                object_type='event', object_id=self.facts['event']['event_id'], field='',
                message='Body processing returned candidate work that remains rejected or pending.'))
            checks['summary']['warnings'] += 1
        if task_failures:
            checks['issues'].append(dict(code='TASKS_INCOMPLETE', severity='warning', artifact='facts',
                object_type='event', object_id=self.facts['event']['event_id'], field='',
                message='Some tasks failed, reached a limit, or lacked required upstream results.'))
            checks['summary']['warnings'] += 1
        checks_path, checks_hash = self.run.save('checks.json', checks)
        self.run.save('adoption.json', self.reports)
        self.run.state.update(execution_status=execution_status, result_status=result,
            output=graph_path, graph_sha256=graph_hash, checks=checks_path, checks_sha256=checks_hash,
            finished_at=now(), review_required=True)
        if graph_path:
            from ..rendering import save_gantt
            self.run.state['visualization'] = save_gantt(self.graph, self.run.directory, self.run.directory / graph_path, result_status=result)
            self.run.state['render_status'] = self.run.state['visualization']['status']
        if reason:
            self.run.state['reason'] = reason
        else:
            self.run.state.pop('reason', None)
        self.run.persist()
        return deepcopy(self.run.state)


def run_event(payload, directory=None, config=None, *, allow_network=False, model=None, resume=False, provenance=None, stop_after_organization=False):
    if not resume and not isinstance(config, EventBuildConfig):
        settings = dict(config or {})
        # A v1 config is a source of run limits, not a request to write v1 artifacts.
        if settings.get('graph_schema_version') == LEGACY_GRAPH_VERSION:
            settings['graph_schema_version'] = GRAPH_VERSION
        config = EventBuildConfig(**settings)
    validate_input(payload)
    if model is None and not allow_network:
        raise PermissionError('Model execution requires explicit permission')
    if directory is None:
        directory = Path(__file__).resolve().parents[3] / 'output' / 'builds' / uuid.uuid4().hex
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    with directory_lock(directory):
        if resume and not isinstance(config, EventBuildConfig):
            state_path = directory / 'state.json'
            if not state_path.is_file():
                raise ValueError('No run exists to resume')
            saved = json.loads(state_path.read_text())['config']
            config = EventBuildConfig.from_saved({**saved, **(config or {})})
        model_factory = None
        if model is None:
            from ..build import Model
            model = Model(config)
            model_factory = lambda: Model(config)
        execution = Execution(directory, payload, config, model, resume=resume, provenance=provenance,
                              model_factory=model_factory)
        construction = Construction(execution)
        try:
            construction.stage('extraction', construction.extract)
            if config.full_corpus_supplement:
                from .corpus_supplement import supplement
                construction.stage('corpus_supplement', lambda: supplement(construction))
            construction.stage('consolidation', construction.consolidate)
            if not construction.facts['actions']:
                construction.blocked('organization', 'No usable focal Actions')
                construction.blocked('relations', 'Organization has no usable Actions')
                return construction.finish('finished', 'No usable focal Actions; inspect task failures and facts')
            organized = construction.stage('organization', construction.organize)
            if organized and (not construction.graph.get('stages') or not construction.graph.get('phases')):
                construction.stage('hierarchy_repair', lambda: construction.repair(organization_only=True))
            if not organized or not construction.graph.get('stages') or not construction.graph.get('phases'):
                construction.blocked('relations', 'Organization did not produce a usable hierarchy')
                construction.blocked('repair', 'Organization did not produce a usable hierarchy')
                return construction.finish('finished', 'Organization incomplete; available facts retained')
            from .relation_experiment import capture
            # Only complete upstream construction can be exported as an isolated experiment.
            if (all(row['status'] == 'processed' for row in construction.coverage)
                    and not construction.facts['pending']
                    and not any(construction.outstanding(r)['rejected'] or construction.outstanding(r)['pending']
                                for r in construction.reports)):
                capture(construction)
            if stop_after_organization:
                return construction.finish('paused', 'Organization finished; relations not started')
            construction.stage('relations', construction.relate)
            construction.stage('repair', construction.repair)
            return construction.finish('finished')
        except PauseRequested as exc:
            result = construction.finish('paused', str(exc))
            (execution.directory/'pause_requested').unlink(missing_ok=True)
            return result
        except LimitReached as exc:
            return construction.finish('limit', str(exc))
        except (KeyboardInterrupt, SystemExit):
            construction.finish('interrupted', 'Execution interrupted; cumulative usage is retained')
            raise
        except Exception as exc:
            # Raw transport messages can contain request credentials; retain only the class.
            return construction.finish('failed', type(exc.original if isinstance(exc, ModelCallFailed) else exc).__name__)
