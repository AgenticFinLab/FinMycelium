"""Role-scoped views of immutable facts; full records stay in the local corpus."""
from collections import deque
from copy import deepcopy

from .proposals import ID_FIELDS, LIST_REFS
from .records import index_records, prompt_json
from .schema import COLLECTION_IDS


def navigation(package, preview=160, role=None):
    result = {}
    for collection in ('entities', 'actions', 'contexts', 'stages', 'phases', 'relation_candidates'):
        key = COLLECTION_IDS[collection]
        result[collection] = []
        for record in package.get(collection, []):
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
            if preview and 'description' in record:
                width = min(preview, 80) if compact_context else preview
                item['description_preview'] = record['description'][:width]
                item['description_truncated'] = len(record['description']) > width
            result[collection].append(item)
    # Provenance hashes, parser metadata and copied locator bodies are not navigation.
    result['evidence_index'] = [{k: e[k] for k in ('evidence_id', 'sample_id', 'start', 'end')}
                               for e in package.get('evidence', [])]
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


def task_records(role, package, fields):
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
    return records


def sized_request(base, package, max_chars, reserve):
    """Compress navigation first; never truncate the body or assigned operations."""
    request = deepcopy(base)
    limit = max(0, max_chars - reserve)
    for preview in (160, 80, 0):
        request['facts_index'] = navigation(package, preview, base['role'])
        if len(prompt_json(dict(task=request, read_results=[]))) <= limit:
            break
    records = task_records(base['role'], package, base)
    request['related_records'] = []
    request['context_selection'] = dict(navigation_preview_chars=preview,
        related_available=len(records), related_included=0,
        complete_records='read_records; exact source ranges through read_sample')
    # Related context is optional. Required input gets priority and the local tools
    # remain available for any records that do not fit this proactive allocation.
    allowance, used = max_chars // 4, 0
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
