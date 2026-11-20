"""Explicit offline pending dispositions; retain drafts, gaps and execution history."""
from copy import deepcopy
import json
import re
from pathlib import Path
import uuid

from finmy.dataset import within
from finmy.search.summary import directory_lock
from .closure_support import decline_support, support_groups
from .records import fingerprint, sha256
from .runtime import now, write_json
from .validation import check_graph


def load_review(directory):
    directory = Path(directory)
    raw = (directory / 'state.json').read_bytes()
    state = json.loads(raw)
    if state['execution_status'] != 'finished' or not state.get('output'):
        raise ValueError('请先完成构建；此入口只处理已有图的离线收尾')
    objects = {}
    for name, field in [('graph', 'output'), ('facts', 'facts'), ('checks', 'checks')]:
        path = within(directory, state[field])
        digest = state['graph_sha256' if name == 'graph' else name + '_sha256']
        content = path.read_bytes()
        if sha256(content) != digest:
            raise ValueError('产物校验失败，请保留原文件并检查：' + field)
        objects[name] = json.loads(content)
    raw_input = (directory / 'input.json').read_bytes()
    payload = json.loads(raw_input)
    if sha256(raw_input) != state['input_sha256']:
        raise ValueError('固定输入校验失败')
    checks = objects['checks']
    if (checks['run_id'] != state['run_id'] or checks['input_sha256'] != state['input_sha256']
            or checks['graph_sha256'] != state['graph_sha256']
            or checks['artifact_hashes']['facts'] != state['facts_sha256']):
        raise ValueError('检查记录与当前图、事实或输入不一致')
    if 'relation_discovery' in state:
        path = within(directory, state['relation_discovery'])
        raw_receipt = path.read_bytes()
        if sha256(raw_receipt) != state['relation_discovery_sha256']:
            raise ValueError('关系审查记录校验失败')
        objects['discovery'] = json.loads(raw_receipt)
    if 'review' in state or 'relation_review' in checks['artifact_hashes']:
        raw_review = within(directory, state['review']).read_bytes()
        if sha256(raw_review) != state['review_sha256'] or state['review_sha256'] != checks['artifact_hashes'].get('relation_review'):
            raise ValueError('独立关系复核记录与检查记录不一致')
        objects['semantic_review'] = json.loads(raw_review)
    return dict(state=state, state_sha256=sha256(raw), payload=payload, **objects)


def pending_items(review):
    """List outstanding receipts and identify evidenced Contexts that can retain an explicit gap."""
    graph = review['graph']; facts = review['facts']; checks = review['checks']
    contexts = {c['context_id']: c for c in graph['contexts']}
    fact_contexts = {c['context_id']: c for c in facts['contexts']}
    result = []; owned = set()
    for task in checks['unresolved_tasks']:
        report = task['report']
        for pending in report['pending']:
            fp = fingerprint(pending); owned.add(fp)
            options = []
            refs = pending['refs']
            scoped = bool(refs) and all(
                (r['collection'] == 'event' and r['object_id'] == graph['event']['event_id']
                 and r['field'] == '/actions') or r['collection'] == 'contexts' for r in refs)
            if (task['role'] == 'extraction' and task.get('body_processed') and scoped
                    and not report['rejected'] and pending in report.get('reported_pending', [])
                    and pending in facts['pending'] and pending['evidence_ids']):
                accepted = {r['object_id'] for item in report.get('accepted_items', []) for r in item['refs']
                            if r['collection'] == 'contexts'}
                for cid in sorted(accepted & contexts.keys() & fact_contexts.keys()):
                    # The chosen retained record must support the very evidence under review.
                    for context in (contexts[cid], fact_contexts[cid]):
                        evidence = {e for s in context['support'] for e in s.get('evidence_ids', [])}
                        if not set(pending['evidence_ids']) <= evidence:
                            break
                    else:
                        options.append(cid)
            result.append(dict(key=fingerprint(dict(task_id=task['task_id'], pending=pending)),
                task_id=task['task_id'], pending=pending, context_ids=options,
                eligible=bool(options)))
    for pending in facts['pending']:
        if fingerprint(pending) not in owned:
            result.append(dict(key=fingerprint(pending), task_id=None, pending=pending,
                               context_ids=[], eligible=False))
    return result


def close_pending(directory, decisions, *, expected_state_sha256, reviewer):
    """Save an explicit successor; no model, search, or builder checkpoint mutation."""
    directory = Path(directory)
    with directory_lock(directory):
        review = load_review(directory)
        if review['state_sha256'] != expected_state_sha256:
            raise ValueError('记录已更新，请刷新后重新检查')
        if not isinstance(reviewer, str) or not reviewer.strip():
            raise ValueError('请填写处置人')
        if not decisions:
            raise ValueError('请至少选择一条明确处置；其他事项可以继续保留')
        pending = pending_items(review)
        groups = {g['key']: g for g in support_groups(review, pending)}
        items = {x['key']: x for x in pending}
        graph, facts, checks = (deepcopy(review[k]) for k in ('graph','facts','checks'))
        state = deepcopy(review['state']); stamp = now()
        rid = 'manual-' + uuid.uuid4().hex[:12]
        relative = Path('revisions') / rid
        resolutions = []; handled = []; seen = set()
        for decision in decisions:
            key = decision['key']
            reason = decision.get('reason', '').strip()
            if not reason or key in seen:
                raise ValueError('请填写每项处置理由，并避免重复选择')
            seen.add(key)
            if decision.get('outcome') == 'decline_support_change':
                group = groups.get(key)
                if not group:
                    raise ValueError('这项提案不能按补充引证退回，请核对当前记录')
                receipts = decline_support(group, decision, checks, facts, 'offline.' + rid)
                handled.extend(receipts)
                resolutions.append(dict(key=key, outcome='decline_support_change', kind=group['kind'],
                    ref=group['ref'], retained_id=group['retained_id'], receipts=receipts,
                    reason=reason, reviewer=reviewer.strip(), at=stamp))
                continue
            item = items.get(key)
            if decision.get('outcome') not in (None, 'retained_context_with_gap') or not item or not item['eligible']:
                raise ValueError('该事项不能通过缺口确认解除')
            cid = decision['context_id']
            if cid not in item['context_ids']:
                raise ValueError('请选择有对应证据的 Context，并填写缺口与处置说明')
            gap = dict(target='/description', reason=reason)
            for package in (graph, facts):
                context = next(c for c in package['contexts'] if c['context_id'] == cid)
                if gap not in context.setdefault('gaps', []):
                    context['gaps'].append(gap)
            task = next(t for t in checks['unresolved_tasks'] if t['task_id'] == item['task_id'])
            task['report']['pending'].remove(item['pending'])
            handled.append(item)
            resolutions.append(dict(**item, outcome='retained_context_with_gap', context_id=cid,
                reason=reason, reviewer=reviewer.strip(), at=stamp))
            ref = dict(collection='contexts', object_id=cid, field='')
            facts['lineage'].append(dict(operation='keep', input_refs=[ref], output_refs=[ref],
                                        reason=reason, step_id='offline.' + rid))
        checks['unresolved_tasks'] = [t for t in checks['unresolved_tasks']
                                     if t['report']['pending'] or t['report']['rejected']]
        still_pending = [p for t in checks['unresolved_tasks'] for p in t['report']['pending']]
        resolved = [item['pending'] for item in handled]
        facts['pending'] = [p for p in facts['pending'] if p not in resolved or p in still_pending]
        coverage = deepcopy(review['state']['coverage'])
        remaining = {t['task_id'].split('.correct.')[0] for t in checks['unresolved_tasks']}
        completed_tasks = {item['task_id'].split('.correct.')[0] for item in handled} - remaining
        for tid in completed_tasks:
            block = re.fullmatch(r'extract\.(\d+)', tid)
            if block:
                number = int(block[1])
                if number < len(coverage) and coverage[number]['body_status'] == 'processed':
                    coverage[number].update(proposal_status='resolved', status='processed')
        graph_check = check_graph(graph, review['payload'])
        fact_check = check_graph(facts, review['payload'])
        errors = [i for i in fact_check['issues'] if i['severity'] == 'error']
        graph_check['issues'].extend(errors)
        graph_check['summary']['errors'] += len(errors)
        graph_check['summary']['checked'].append('fact_contract')
        body_done = bool(coverage) and all(c['body_status'] == 'processed' for c in coverage)
        discovery = review.get('discovery')
        discovery_done = discovery is None or (
            not discovery['incomplete_action_ids'] and
            set(discovery['completed_action_ids']) == {a['action_id'] for a in graph['actions']})
        done = (body_done and all(c['proposal_status'] == 'resolved' for c in coverage)
                and graph_check['valid'] and fact_check['valid'] and not checks['unresolved_tasks']
                and not facts['pending'] and bool(graph['actions']) and discovery_done
                and review.get('semantic_review', {}).get('complete', True))
        result = 'draft' if done else 'partial'
        for code, active in [('BODY_PROCESSING_INCOMPLETE', not body_done),
                             ('PROPOSALS_UNRESOLVED', bool(checks['unresolved_tasks'] or facts['pending'])
                              or any(c['proposal_status'] == 'unresolved' for c in coverage))]:
            if active:
                graph_check['issues'].append(dict(code=code, severity='warning', artifact='facts',
                    object_type='event', object_id=graph['event']['event_id'], field='', message=code))
                graph_check['summary']['warnings'] += 1
        target = directory / relative
        target.mkdir(parents=True, exist_ok=False)
        # Parent outputs are immutable. Preserve the exact state bytes before publishing.
        (target / 'parent-state.json').write_bytes((directory / 'state.json').read_bytes())
        if graph == review['graph']:
            # A declined support change must retain even the serialization of the parent graph.
            parent_graph = within(directory, state['output']).read_bytes()
            if sha256(parent_graph) != state['graph_sha256']:
                raise ValueError('图已更新，请重新检查')
            (target / 'epg.json').write_bytes(parent_graph)
            graph_hash = state['graph_sha256']
        else:
            graph_hash = write_json(target / 'epg.json', graph)
        facts_hash = write_json(target / 'facts.json', facts)
        checks.update(graph_sha256=graph_hash, artifact_hashes=dict(checks['artifact_hashes'], facts=facts_hash),
            summary=graph_check['summary'], issues=graph_check['issues'], coverage=coverage,
            result_status=result, review_required=True, offline_disposition=str(relative/'revision.json'))
        checks_hash = write_json(target / 'checks.json', checks)
        record = dict(revision_id=rid, kind='manual_pending_disposition', at=stamp,
            parent_state_sha256=review['state_sha256'], parent_graph=state['output'],
            parent_graph_sha256=state['graph_sha256'], parent_facts=state['facts'],
            parent_checks=state['checks'], input_sha256=state['input_sha256'],
            dispositions=resolutions, result_status=result, additional_model_calls=0,
            content_review='not_implied_by_disposition',
            artifacts={'epg.json':graph_hash,'facts.json':facts_hash,'checks.json':checks_hash})
        revision_hash = write_json(target/'revision.json', record)
        from ..rendering import save_gantt
        visualization = save_gantt(graph, directory, target/'epg.json', result_status=result)
        state.update(output=str(relative/'epg.json'), graph_sha256=graph_hash,
            facts=str(relative/'facts.json'), facts_sha256=facts_hash,
            checks=str(relative/'checks.json'), checks_sha256=checks_hash,
            coverage=coverage, result_status=result, review_required=True,
            visualization=visualization, render_status=visualization['status'], updated_at=stamp)
        state.setdefault('offline_revisions', []).append(dict(path=str(relative/'revision.json'),
            sha256=revision_hash, revision_id=rid, created_at=stamp,
            parent_state=str(relative/'parent-state.json')))
        write_json(target/'state.json', state)
        write_json(directory/'state.json', state)
        return state
