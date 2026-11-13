"""Freeze one reviewed search handoff for native person-event reconstruction."""
from copy import deepcopy
import json

from finmy.search.control import task_lock
from finmy.search.sources import SourceStore
from finmy.search.state import SearchState, digest


def validate_scope(value):
    if not isinstance(value, dict):
        raise ValueError('Expected a confirmed person event object')
    for key in ('person_id', 'person_name', 'storyline_id', 'storyline_name', 'event_id', 'event_name'):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise ValueError('Missing or invalid person event identity: ' + key)
        if key.endswith('_id') and len(value[key]) > 128:
            raise ValueError('Person event IDs cannot exceed 128 characters: ' + key)
    scope = value.get('scope', {})
    if not isinstance(scope, dict) or any(not isinstance(scope.get(k), str) for k in ('period', 'include', 'exclude')) or not scope['include'].strip():
        raise ValueError('The confirmed event needs an explicit research scope')
    aliases = value.get('aliases', [])
    if not isinstance(aliases, list) or any(not isinstance(alias, str) for alias in aliases):
        raise ValueError('Person aliases must be a list of strings')
    return value


def validate_input(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('user_query'), dict):
        raise ValueError('Expected user_query and original samples')
    query = payload['user_query']
    extras = query.get('extras')
    if not isinstance(extras, dict):
        raise ValueError('Expected confirmed person event and source registry in extras')
    event = validate_scope(extras.get('person_event'))
    registry = extras.get('source_registry')
    if not isinstance(registry, dict):
        raise ValueError('Expected a source registry object')
    samples = payload.get('samples')
    if not isinstance(samples, list) or not samples:
        raise ValueError('No original material was confirmed')
    seen = set()
    for sample in samples:
        if not isinstance(sample, dict) or not isinstance(sample.get('sample_id'), str) or not sample['sample_id'].strip() or sample['sample_id'] in seen:
            raise ValueError('Samples need unique IDs')
        seen.add(sample['sample_id'])
        if not isinstance(sample.get('content'), str) or not sample['content'].strip():
            raise ValueError('Samples need original text')
        source_id = sample.get('raw_data_id')
        if not isinstance(source_id, str) or not source_id.strip() or not isinstance(registry.get(source_id), dict):
            raise ValueError('A sample has no source registry entry')
    return event


def freeze_search_input(controller, task_id, *, confirmed=False):
    if not confirmed:
        raise ValueError('请先确认实际构建材料与已知缺口')
    with task_lock(controller.root, task_id):
        data = controller.inspect(task_id)
        task = data['task']; catalog = task.get('catalog', {})
        if catalog.get('kind') != 'person_event':
            raise ValueError('请选择已关联人物 event 的检索任务')
        if data['status'] not in {'finished', 'insufficient', 'limit', 'failed'}:
            raise ValueError('请先等待检索结束并检查材料')
        if task.get('scope_confirmation', {}).get('scope_sha256') != digest(task.get('research_scope')):
            raise ValueError('任务范围尚未确认或已变化')
        original = data.get('builder_input')
        revision = data.get('handoff_revision', '')
        if not original or not original.get('samples') or not revision.isalnum():
            raise ValueError('没有可确认的实际交接材料')
        state = SearchState(controller.root, task_id)
        folder = state.run_dir / 'handoffs' / revision
        for name in ('builder_input', 'selection'):
            if json.loads((folder / (name + '.json')).read_text()) != data[name]:
                raise ValueError('交接记录与保存版本不一致，请重新检查')
        event = {k: catalog[k] for k in ('person_id', 'person_name', 'storyline_id', 'storyline_name', 'event_id', 'event_name')}
        event.update(scope=deepcopy(task['research_scope']), aliases=deepcopy(catalog.get('aliases', [])))
        validate_scope(event)
        payload = deepcopy(original)
        registry, origins = {}, []
        previous_extras = deepcopy(payload['user_query'].get('extras') or {})
        previous_registry = previous_extras.get('source_registry', {})
        if not isinstance(previous_registry, dict):
            raise ValueError('Invalid pre-existing source registry')
        selected = data['selection'].get('selected', [])
        for sid in dict.fromkeys(s['raw_data_id'] for s in payload['samples']):
            source = data['sources'][sid]
            versions = {r['version'] for r in selected if r['source_id'] == sid}
            if not versions:
                raise ValueError('交接材料缺少来源版本')
            documents = {version: SourceStore(state).document(sid, version) for version in sorted(versions)}
            # Metadata comes from the selected immutable version, not the latest fetch.
            def agreed(field):
                values = [document.get(field) for document in documents.values()]
                return values[0] if all(value == values[0] for value in values) else None
            old = previous_registry.get(sid, {})
            if not isinstance(old, dict):
                raise ValueError('Invalid pre-existing source metadata')
            frozen = {'document_id': old.get('document_id') or 'DOC_' + sid,
                      'source_url': source['url'], 'title': source.get('title') or None,
                      'published_at': source.get('published_at'), 'retrieved_at': agreed('retrieved_at')}
            for key in ('origin', 'source_type'):
                if source.get(key) is not None:
                    frozen[key] = source[key]
            if agreed('status') is not None:
                frozen['content_status'] = agreed('status')
            for key, value in frozen.items():
                if old.get(key) is not None and value is not None and old[key] != value:
                    raise ValueError('Frozen source metadata conflicts with existing input: ' + key)
            registry[sid] = {**old, **{key: value for key, value in frozen.items() if value is not None or key not in old}}
            origins.append({'source_id': sid, 'versions': sorted(versions),
                            'parsed_hashes': {v: source['parsed_hashes'][v] for v in versions},
                            'version_metadata': {v: {k: doc.get(k) for k in ('retrieved_at', 'status', 'kind', 'parser_version')}
                                                 for v, doc in documents.items()}})
        previous_event = previous_extras.get('person_event')
        if previous_event is not None and (not isinstance(previous_event, dict)
                or any(value != event.get(key) for key, value in previous_event.items())):
            raise ValueError('Confirmed person event conflicts with existing input')
        payload['user_query']['extras'] = {**previous_extras, 'person_event': event, 'source_registry': registry}
        validate_input(payload)
        provenance = {'search_task_id': task_id, 'handoff_revision': revision,
                      'search_input_sha256': digest(original), 'selection': deepcopy(data['selection']),
                      'complete_material': deepcopy(data.get('complete_material')),
                      'catalog': deepcopy(catalog), 'sources': origins,
                      'source_root': str(state.root.resolve()),
                      'offset_origin': 'Each source_document.content is the exact confirmed sample.content; selection maps it to retained source blocks.'}
        return payload, provenance
