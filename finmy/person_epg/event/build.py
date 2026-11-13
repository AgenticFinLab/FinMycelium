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
from .records import IdMap, fingerprint, index_records, seed_facts, validate_input
from .runtime import EventBuildConfig, Execution, InvalidResponse, LimitReached, now, write_json
from .schema import COLLECTION_IDS
from .validation import check_graph


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
    result = {}
    for collection in ('entities', 'actions', 'contexts', 'stages', 'phases', 'relation_candidates'):
        result[collection] = []
        key = COLLECTION_IDS[collection]
        for record in package.get(collection, []):
            item = {k: deepcopy(v) for k, v in record.items() if k in
                    (key, 'name', 'actor', 'type', 'time', 'category', 'phase_id', 'stage_id', 'from_action_id', 'to_action_id')}
            if 'description' in record:
                item['description_preview'] = record['description'][:280]
                item['description_truncated'] = len(record['description']) > 280
            result[collection].append(item)
    result['evidence_index'] = [{k: deepcopy(v) for k, v in e.items() if k != 'quote'} |
                                {'quote_preview': e['quote'][:200], 'quote_truncated': len(e['quote']) > 200}
                               for e in package.get('evidence', [])]
    return result


def ambiguity_groups(facts):
    """Cheap grouping asks the model only about possible duplicates, not every pair."""
    buckets = defaultdict(set)
    for collection in ('entities', 'actions', 'contexts', 'relation_candidates'):
        for record in facts[collection]:
            oid = record[COLLECTION_IDS[collection]]
            name = re.sub(r'\W+', ' ', record.get('name', record.get('description', '')).casefold()).strip()
            if name:
                buckets[(collection, 'name', name)].add((collection, oid))
            if collection == 'actions' and record['time']['start']:
                buckets[(collection, 'actor_time', record['actor']['entity_id'], record['time']['start'])].add((collection, oid))
    groups = []
    for group in buckets.values():
        if len(group) < 2:
            continue
        overlaps = [g for g in groups if g & group]
        for old in overlaps:
            group |= old
            groups.remove(old)
        groups.append(set(group))
    return [sorted(g) for g in groups]


class Construction:
    def __init__(self, execution):
        self.run = execution
        self.facts = seed_facts(execution.payload)
        self.graph = None
        self.coverage = []
        self.reports = []
        self.ids = IdMap(execution.state['id_map'])

    def request(self, role, package, **fields):
        return dict(role=role, identity=self.run.payload['user_query']['extras']['person_event'],
                    query_text=self.run.payload['user_query']['query_text'], facts_index=brief(package),
                    read_limits=dict(read_chars=self.run.config.read_chars, retrieval_top_k=self.run.config.retrieval_top_k),
                    **fields)

    def receive(self, task_id, role, package, request, **scope):
        raw = self.run.infer(task_id, system_prompt(role), request, package, lambda v: validate_envelope(role, v))
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
            if evidence['location_status'] == 'matched':
                ranges[evidence['sample_id']].append((evidence['start'], evidence['end']))
        receiver = Receiver(package, self.run.payload, self.ids, namespace, ranges)
        method = {'extraction': receiver.extract, 'consolidation': receiver.consolidate,
                  'organization': receiver.organize, 'relations': receiver.relate}[role]
        result, report = method(raw, **scope)
        record = dict(task_id=task_id, role=role, report=report)
        self.reports.append(record)
        self.run.state['id_map'] = self.ids.mapping
        self.run.persist()
        self.run.save(task_id + '-adoption.json', dict(**record, package_fingerprint=fingerprint(result)))
        return result, report

    def save_facts(self):
        path, digest = self.run.save('facts.json', self.facts)
        self.run.state.update(facts=path, facts_sha256=digest, coverage=self.coverage)
        self.run.persist()

    def extract(self):
        ranges = list(body_ranges(self.run.payload, self.run.config))
        self.coverage = [{k: v for k, v in block.items() if k != 'text'} | {'status': 'not_processed'} for block in ranges]
        self.save_facts()
        for number, block in enumerate(ranges):
            task_id = 'extract.' + str(number)
            request = self.request('extraction', self.facts, body=block, sources=self.facts['sources'])
            try:
                self.facts, report = self.receive(task_id, 'extraction', self.facts, request)
                self.coverage[number]['status'] = 'partial' if report['rejected'] or report['pending'] else 'processed'
            except InvalidResponse as exc:
                self.coverage[number]['status'] = 'failed'
                pending = dict(refs=[], reason=f"Unprocessed body {block['sample_id']} [{block['start']},{block['end']}): {exc}", evidence_ids=[])
                self.facts['pending'].append(pending)
                self.reports.append(dict(task_id=task_id, role='extraction', report=dict(accepted=[], rejected=[], pending=[pending])))
            self.save_facts()

    def consolidate(self):
        self.facts = exact_deduplicate(self.facts, self.run.payload)
        groups = ambiguity_groups(self.facts)
        assigned_all = {ref for group in groups for ref in group}
        for collection in ('entities', 'actions', 'contexts', 'relation_candidates'):
            for record in self.facts[collection]:
                ref = reference(collection, record[COLLECTION_IDS[collection]])
                if (collection, ref['object_id']) not in assigned_all:
                    self.facts['lineage'].append(dict(operation='keep', input_refs=[ref], output_refs=[ref],
                        reason='No deterministic duplicate or ambiguous candidate group.', step_id='consolidate.keep'))
        for number, group in enumerate(groups):
            assigned = {(c, oid) for c, oid in group if oid in index_records(self.facts)[c]}
            if len(assigned) < 2:
                continue
            request = self.request('consolidation', self.facts, assigned=[reference(c, oid) for c, oid in sorted(assigned)],
                candidates=[dict(collection=c, record=index_records(self.facts)[c][oid]) for c, oid in sorted(assigned)])
            self.facts, _ = self.receive('consolidate.' + str(number), 'consolidation', self.facts, request, assigned=assigned)
            self.save_facts()
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

    def relate(self):
        # Batches partition ownership. No Cartesian expansion of action pairs.
        action_ids = [a['action_id'] for a in self.graph['actions']]
        phase_ids = [p['phase_id'] for p in self.graph['phases']]
        for number, start in enumerate(range(0, max(1, len(action_ids)), 24)):
            owned_actions = action_ids[start:start + 24]
            owned_phases = phase_ids if number == 0 else []
            request = self.request('relations', self.graph, assigned_action_ids=owned_actions,
                assigned_phase_ids=owned_phases, relation_candidates=self.facts['relation_candidates'],
                assigned_records=dict(actions=[a for a in self.graph['actions'] if a['action_id'] in owned_actions],
                                     phases=[p for p in self.graph['phases'] if p['phase_id'] in owned_phases]))
            self.graph, _ = self.receive('relate.' + str(number), 'relations', self.graph, request,
                                         action_ids=owned_actions, phase_ids=owned_phases)

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
                if done:
                    record.setdefault('resolutions', []).append(dict(
                        issue_fingerprint=fingerprint(issue), resolved_by='repair.' + role))

    def repair(self):
        checks = check_graph(self.graph, self.run.payload)
        # One round handles concrete failed organization/association work, not legal uncertainty.
        unresolved = [dict(r, report=self.outstanding(r)) for r in self.reports
                      if r['role'] in ('organization', 'relations') and self.outstanding(r)['rejected']]
        if not unresolved and checks['valid']:
            return
        if not self.run.config.final_repair_rounds:
            return
        plan_path = self.run.directory / 'checkpoints' / 'final-repair-plan.json'
        if self.run.state['final_repair_used']:
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
            if not tasks:
                return
            plan = dict(base_fingerprint=fingerprint(self.graph), tasks=tasks)
            write_json(plan_path, plan)
            self.run.state['final_repair_used'] = True
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
            self.graph, report = self.receive('repair.' + role, role, self.graph, request, **scope)
            if role == 'organization':
                self.retain_splits(report)
            self.record_resolutions(role, report)

    def finish(self, execution_status, reason=None):
        self.save_facts()
        if self.graph is None and self.facts['actions']:
            self.graph = graph_from_facts(self.facts)
        unresolved = [dict(r, report=self.outstanding(r)) for r in self.reports
                      if self.outstanding(r)['rejected'] or self.outstanding(r)['pending']]
        coverage_done = bool(self.coverage) and all(r['status'] == 'processed' for r in self.coverage)
        report = check_graph(self.graph, self.run.payload) if self.graph else check_graph(self.facts, self.run.payload)
        facts_check = check_graph(self.facts, self.run.payload)
        if self.graph:
            fact_errors = [i for i in facts_check['issues'] if i['severity'] == 'error']
            report['issues'].extend(fact_errors)
            report['summary']['errors'] += len(fact_errors)
            report['summary']['checked'].append('fact_contract')
            report['valid'] = report['valid'] and facts_check['valid']
        result = 'none'
        graph_path, graph_hash = None, None
        if self.graph and self.graph['actions']:
            graph_path, graph_hash = self.run.save('epg.json', self.graph)
            result = 'draft' if execution_status == 'finished' and report['valid'] and coverage_done and not unresolved and not self.facts['pending'] else 'partial'
        elif self.facts['contexts'] or self.facts['evidence']:
            result = 'partial'
        checks = dict(run_id=self.run.state['run_id'], input_sha256=self.run.state['input_sha256'],
            graph_sha256=graph_hash, artifact_hashes=dict(facts=self.run.state['facts_sha256']),
            summary=report['summary'], issues=report['issues'], review_required=True,
            coverage=self.coverage, unresolved_tasks=unresolved,
            result_status=result, execution_status=execution_status)
        if not coverage_done:
            checks['issues'].append(dict(code='BODY_PROCESSING_INCOMPLETE', severity='warning', artifact='facts',
                object_type='event', object_id=self.facts['event']['event_id'], field='',
                message='Some handed body ranges or their proposals remain unprocessed or unresolved.'))
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


def run_event(payload, directory=None, config=None, *, allow_network=False, model=None, resume=False, provenance=None):
    config = EventBuildConfig(**config) if isinstance(config, dict) else config or EventBuildConfig()
    validate_input(payload)
    if model is None and not allow_network:
        raise PermissionError('Model execution requires explicit permission')
    if directory is None:
        directory = Path(__file__).resolve().parents[3] / 'output' / 'builds' / uuid.uuid4().hex
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    if model is None:
        from ..build import Model
        model = Model(config)
    with directory_lock(directory):
        execution = Execution(directory, payload, config, model, resume=resume, provenance=provenance)
        construction = Construction(execution)
        try:
            construction.extract()
            construction.consolidate()
            if not construction.facts['actions']:
                return construction.finish('finished', 'No usable focal Actions; inspect the facts and pending items')
            construction.organize()
            construction.relate()
            construction.repair()
            return construction.finish('finished')
        except LimitReached as exc:
            return construction.finish('limit', str(exc))
        except (KeyboardInterrupt, SystemExit):
            construction.finish('interrupted', 'Execution interrupted; cumulative usage is retained')
            raise
        except Exception as exc:
            # Raw transport messages can contain request credentials; retain only the class.
            return construction.finish('failed', type(exc).__name__)
