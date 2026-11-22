"""Role-scoped views of immutable facts; full records stay in the local corpus."""
from collections import deque
from copy import deepcopy
from itertools import zip_longest

from .context_links import shared_passage_leads
from .proposals import ID_FIELDS, LIST_REFS
from .records import index_records, prompt_json
from .schema import COLLECTION_IDS


def navigation(package, preview=160, role=None, supplied=None, relation_actions=()):
    result = {}
    for collection in ('entities', 'actions', 'contexts', 'stages', 'phases', 'relation_candidates'):
        key = COLLECTION_IDS[collection]
        result[collection] = []
        for record in package.get(collection, []):
            if (collection, record[key]) in (supplied or set()):
                result[collection].append({k: record[k] for k in (key, 'name', 'phase_id', 'stage_id') if k in record})
                continue
            compact_context = collection == 'contexts' and role in ('extraction', 'consolidation')
            fields = (key, 'name', 'aliases', 'actor', 'type', 'category', 'perspective', 'entity_refs',
                      'phase_id', 'stage_id', 'from_action_id', 'to_action_id')
            item = {k: deepcopy(record[k]) for k in fields if k in record}
            if 'object' in record:
                obj = record['object']
                item['object'] = dict(entity_refs=deepcopy(obj.get('entity_refs', [])))
                if preview and obj.get('description'):
                    item['object'].update(description_preview=obj['description'][:preview],
                        description_truncated=len(obj['description']) > preview)
            if 'time' in record:
                item['time'] = {k: v for k, v in record['time'].items()
                                if k in ('start', 'end', 'kind') or (not compact_context and k != 'text')}
                if preview and record['time'].get('text') and collection in ('actions', 'stages', 'phases'):
                    item['time']['text_preview'] = record['time']['text'][:preview]
                    item['time']['text_truncated'] = len(record['time']['text']) > preview
            if collection in ('actions', 'relation_candidates'):
                item['evidence_ids'] = sorted({eid for s in record.get('support', []) for eid in s['evidence_ids']})
            if preview and 'description' in record:
                width = min(preview, 80) if compact_context else preview
                item['description_preview'] = record['description'][:width]
                item['description_truncated'] = len(record['description']) > width
            result[collection].append(item)
    # Provenance hashes, parser metadata and copied locator bodies are not navigation.
    result['evidence_index'] = [{k: e[k] for k in ('evidence_id', 'sample_id', 'source_id', 'start', 'end')}
                               for e in package.get('evidence', [])]
    if role in ('consolidation', 'organization', 'relations'):
        result['sources'] = [{k: s.get(k) for k in ('source_id', 'title', 'published_at')}
                             for s in package.get('sources', [])]
    if role == 'relations' and relation_actions:
        fields = ('relation_id', 'from_action_id', 'to_action_id', 'type', 'basis')
        result['relations'] = [{k: r[k] for k in fields} for r in package.get('relations', [])
                               if r['from_action_id'] in relation_actions or r['to_action_id'] in relation_actions]
    return result


def references(value):
    if isinstance(value, list):
        for item in value:
            yield from references(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            collection = value.get('collection') if key == 'object_id' else ID_FIELDS.get(key)
            if collection and isinstance(item, str):
                yield collection, item
            if key in LIST_REFS and isinstance(item, list):
                yield from ((LIST_REFS[key], oid) for oid in item if isinstance(oid, str))
            yield from references(item)


def _relation_passages(indexes, fields):
    """Choose located passages for the assigned acts and the links the sources describe."""
    evidence = indexes['evidence']

    def cited(record, targets):
        return [eid for support in record.get('support', []) if support.get('target') in targets
                for eid in support['evidence_ids'] if evidence.get(eid, {}).get('location_status') == 'matched']

    candidates = fields.get('relation_candidates', [])
    link_groups = [cited(c, ('/type', '')) or cited(c, ('/description',)) for c in candidates]
    action_groups = []
    for aid in fields.get('assigned_action_ids', []):
        action = indexes['actions'].get(aid, {})
        quotes = cited(action, ('/description', ''))
        if not quotes:
            quotes = cited(action, ('/object', '/object/description', '/actor', '/actor/entity_id'))
        action_groups.append(quotes)
    # Cover each action and each candidate before taking extra citations for a link.
    selected = {}
    for groups in zip_longest(action_groups, link_groups, fillvalue=()):
        for quotes in groups:
            if quotes and selected.keys().isdisjoint(quotes):
                eid = min(quotes, key=lambda eid: len(evidence[eid]['quote']))
                selected[eid] = None
    for candidate in candidates:
        selected.update(dict.fromkeys(cited(candidate, ('/type', '/description', ''))))
    return selected


def task_records(role, package, fields, *, indexes=None):
    if indexes is None:
        indexes = index_records(package)
    roots, supplied = [], set()
    if role == 'extraction':
        body = fields.get('body', {})
        evidence_ids = {e['evidence_id'] for e in package['evidence']
            if e['sample_id'] == body.get('sample_id') and e['start'] is not None and e['end'] is not None
            and max(e['start'], body.get('start', 0)) < min(e['end'], body.get('end', 0))}
        text = body.get('text', '').casefold()
        mentioned = {e['entity_id'] for e in package['entities'] if e['entity_id'] != package['person']['person_id']
            and any(len(n.strip()) >= 3 and n.casefold() in text for n in [e['name'], *e.get('aliases', [])])}
        for collection in ('actions', 'contexts', 'relation_candidates'):
            for record in package[collection]:
                refs = set(references(record))
                if refs & ({('evidence', eid) for eid in evidence_ids} | {('entities', oid) for oid in mentioned}):
                    roots.append((collection, record[COLLECTION_IDS[collection]]))
        roots += [('evidence', eid) for eid in sorted(evidence_ids)]
    elif role == 'consolidation':
        roots = [(r['collection'], r['object_id']) for r in fields.get('assigned', [])]
        supplied = set(roots)  # Full candidate records are already in the task.
    elif role == 'organization':
        roots = [('actions', a['action_id']) for a in package['actions']]
    elif role == 'relations':
        roots = [('actions', aid) for aid in fields.get('assigned_action_ids', [])]
        roots += [('phases', pid) for pid in fields.get('assigned_phase_ids', [])]
        supplied = set(roots) if fields.get('assigned_records') else set()
        roots += list(references(fields.get('relation_candidates', [])))
    queue, visited, records = deque(roots), set(), []
    while queue:
        ref = queue.popleft()
        if ref in visited:
            continue
        visited.add(ref)
        collection, oid = ref
        record = indexes.get(collection, {}).get(oid)
        if not record:
            continue
        queue.extend(references(record))
        if collection == 'entities' or ref in supplied:
            continue
        view = deepcopy(record)
        if collection == 'evidence':
            view = {k: record[k] for k in ('evidence_id', 'sample_id', 'source_id', 'start', 'end', 'quote')}
        records.append(dict(collection=collection, record=view))
    # Deliver the evidence for the candidate links and assigned acts before bulky
    # Context dependencies can exhaust the optional allocation. Keep the entire
    # navigation index and local tools for independent cross-source discovery.
    if role in ('organization', 'relations'):
        records.sort(key=lambda item: {'actions': 0, 'evidence': 1, 'stages': 2,
                                      'phases': 2, 'contexts': 3}.get(item['collection'], 2))
    return records


def sized_request(base, package, max_chars, reserve):
    """Compress navigation first; never truncate the body or assigned operations."""
    request = deepcopy(base)
    limit = max(0, max_chars - reserve)
    supplied = {(collection, record[COLLECTION_IDS[collection]])
                for collection, records in base.get('assigned_records', {}).items() for record in records}
    indexes = index_records(package)
    records = task_records(base['role'], package, base, indexes=indexes)
    allowance = max_chars // 4
    relation_actions = set(base.get('assigned_action_ids', []))
    best = None
    for preview in (160, 80, 40, 0):
        request['facts_index'] = navigation(package, preview, base['role'], supplied, relation_actions)
        request['related_records'] = []
        request['context_selection'] = dict(navigation_preview_chars=preview, related_available=len(records),
            related_included=0, complete_records='read_records; exact source ranges through read_sample')
        if base['role'] == 'relations':
            result = balanced_relation_request(request, indexes, records, limit, allowance)
            selection = result['context_selection']
            omitted = (len(selection['uncovered_action_ids']), len(selection['omitted_relation_evidence_ids']))
            if len(prompt_json(dict(task=result, read_results=[]))) <= limit:
                if omitted == (0, 0):
                    return result
                if best is None or omitted < best[0]:
                    best = (omitted, deepcopy(result))
            if preview == 0:
                return best[1] if best is not None else result
        elif len(prompt_json(dict(task=request, read_results=[]))) <= limit:
            break
    used = 0
    for record in records:
        size = len(prompt_json(record))
        if used + size > allowance:
            continue
        request['related_records'].append(record)
        request['context_selection']['related_included'] += 1
        if len(prompt_json(dict(task=request, read_results=[]))) > limit:
            request['related_records'].pop()
            request['context_selection']['related_included'] -= 1
        else:
            used += size
    return request


def balanced_relation_request(request, indexes, records, limit, allowance):
    """Give every owned Action a quote before optional dependencies use the budget.

    Full quotes and offsets remain immutable. A minimum quote per Action may use
    more than the optional quarter-budget; the caller shrinks the owned scope if
    that minimum cannot fit. A single oversized quote stays explicitly omitted
    and available through local reads. Extra Action and Phase evidence rotates
    after the passages supporting candidate links.
    """
    views = {(item['collection'], item['record'][COLLECTION_IDS[item['collection']]]): item
             for item in records}
    owners = []
    for collection, field in (('actions', 'assigned_action_ids'), ('phases', 'assigned_phase_ids')):
        for oid in request.get(field, []):
            record = indexes[collection][oid]
            # Direct evidence includes qualifications/conflicts, but does not walk
            # through linked Contexts or the pre-existing relation candidates.
            evidence = sorted({eid for c, eid in references([
                record.get('support', []), record.get('conflicts', [])]) if c == 'evidence'})
            for eid in evidence:
                if eid in indexes['evidence'] and ('evidence', eid) not in views:
                    e = indexes['evidence'][eid]
                    views['evidence', eid] = dict(collection='evidence', record={
                        k: e[k] for k in ('evidence_id', 'sample_id', 'source_id', 'start', 'end', 'quote')})
            # Prefer evidence for the action itself, then the smallest complete record.
            preferred = {eid for support in record.get('support', [])
                         if support.get('target') in ('', '/description') for eid in support['evidence_ids']}
            sizes = {eid: len(prompt_json(views['evidence', eid])) for eid in evidence if ('evidence', eid) in views}
            evidence.sort(key=lambda eid: (eid not in preferred, sizes.get(eid, float('inf')), eid))
            owners.append((collection, oid, evidence))
    selected, used = set(), 0
    selection = request['context_selection']
    selection['policy'] = 'action-and-relation-evidence-v1'
    selection['related_available'] = len(views)
    link_quotes = {eid for c in request.get('relation_candidates', []) for s in c.get('support', [])
                   if s.get('target') in ('', '/type', '/description') for eid in s['evidence_ids']
                   if indexes['evidence'].get(eid, {}).get('location_status') == 'matched'}
    selection['relation_evidence_available'] = len(link_quotes)

    def refresh():
        delivered = {oid for c, oid in selected if c == 'evidence'}
        selection['omitted_relation_evidence_ids'] = sorted(link_quotes - delivered)
        selection['related_included'] = len(selected)
        selection['evidence_by_owner'] = [dict(collection=c, object_id=oid,
            available=len(eids), included=len(delivered.intersection(eids)),
            omitted_evidence_ids=[eid for eid in eids if eid not in delivered])
            for c, oid, eids in owners]
        selection['uncovered_action_ids'] = [oid for c, oid, eids in owners
            if c == 'actions' and eids and not delivered.intersection(eids)]
        selection['actions_without_evidence'] = [oid for c, oid, eids in owners
            if c == 'actions' and not eids]

    def add(ref, *, minimum=False):
        nonlocal used
        if ref in selected or ref not in views:
            return False
        item = views[ref]
        size = len(prompt_json(item))
        if not minimum and used + size > allowance:
            return False
        selected.add(ref)
        request['related_records'].append(item)
        refresh()
        if len(prompt_json(dict(task=request, read_results=[]))) > limit:
            selected.remove(ref)
            request['related_records'].pop()
            refresh()
            return False
        used += size
        return True

    refresh()
    # Minimum coverage is independent of candidate membership and graph order.
    for collection, oid, evidence in owners:
        if collection != 'actions' or any(('evidence', eid) in selected for eid in evidence):
            continue
        for eid in evidence:
            if add(('evidence', eid), minimum=True):
                break
    # Keep passages supporting the link itself even when both endpoints already have quotes.
    for eid in _relation_passages(indexes, request):
        add(('evidence', eid))
    # Equal turns stop an evidence-rich early Action from consuming every slot.
    for collection in ('actions', 'phases'):
        queues = [deque(eids) for c, _, eids in owners if c == collection]
        while any(queues):
            for queue in queues:
                while queue:
                    if add(('evidence', queue.popleft())):
                        break
    review_context = request.get('assigned_action_ids') and request.get('relation_discovery') and not request.get('correction')
    source_ids = []
    for item in records:
        collection = item['collection']
        oid = item['record'][COLLECTION_IDS[collection]]
        if review_context and collection == 'sources':
            source_ids.append(oid)
        else:
            add((collection, oid))
    refresh()
    if review_context:
        # Passages and substantive records come first. Source titles and dates
        # are already in the global index; additional full Source records follow.
        room = min(allowance - used, limit - len(prompt_json(dict(task=request, read_results=[]))))
        leads = []
        overhead = len(prompt_json({'context_leads': []}))
        for lead in shared_passage_leads(indexes, request['assigned_action_ids']):
            size = len(prompt_json(lead)) + (1 if leads else overhead)
            if size <= room:
                leads.append(lead)
                room -= size
                used += size
        if leads:
            selection['context_leads'] = leads
        for oid in source_ids:
            add(('sources', oid))
    return request
