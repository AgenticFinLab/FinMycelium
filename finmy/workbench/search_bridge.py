"""Explicitly adopt search passages into existing evidence review, without approval."""
import hashlib
import json
from finmy.search.control import task_lock
from finmy.search.state import write_json


def adopt_sources(controller, task_id, store):
    with task_lock(controller.root,task_id):
        data=controller.inspect(task_id)
        event_id=data['task'].get('event_id')
        if not event_id:raise ValueError('该检索任务未关联主表事件')
        store.event(event_id)
        scope_hash = data['task'].get('scope_hash')
        if scope_hash and scope_hash != store.target(event_id, 'scope'):
            raise ValueError('事件范围已变化；请按新范围检索，旧任务材料仍保留可下载。')
        payload=data.get('builder_input')
        if not payload or not payload['samples']:raise ValueError('没有可纳入的材料')
        existing={s['sha256']:s['id'] for s in store.sources(event_id)}
        record_path = controller.root/task_id/'runs/initial/workbench_sources.json'
        previous = json.loads(record_path.read_text()) if record_path.exists() else {}
        mapping=[];added=0
        for sample in payload['samples']:
            sha=hashlib.sha256(sample['content'].encode()).hexdigest()
            source=data['sources'][sample['raw_data_id']]
            if sha not in existing:
                url=source['url'] if source['url'].startswith(('https://','http://')) else ''
                existing[sha]=store.add_source(event_id,source['title'] or source['url'],text=sample['content'],url=url)
                added+=1
            mapping.append(dict(sample_id=sample['sample_id'],source_id=existing[sha],sha256=sha))
        # A revised handoff supersedes only this task's previously adopted passages.
        # Keep original source rows and every old approval; never delete evidence.
        new_ids = {row['source_id'] for row in mapping}
        shared_ids = set()
        for other_id in controller.tasks():
            if other_id == task_id:
                continue
            other_path = controller.root/other_id/'runs/initial/workbench_sources.json'
            if other_path.exists():
                other = json.loads(other_path.read_text())
                if other.get('event_id') == event_id:
                    shared_ids.update(row['source_id'] for row in other.get('mapping', []))
        for row in previous.get('mapping', []):
            if row['source_id'] not in new_ids | shared_ids:
                store.include_source(event_id, row['source_id'], False)
        for sid in new_ids:
            store.include_source(event_id, sid, True)
        write_json(record_path,dict(event_id=event_id,mapping=mapping))
        return added


def save_preview(controller, task_id, complete, limit):
    """Save a reviewed preview as the task's current handoff; keep revision history."""
    from finmy.search.handoff import assemble_sources
    from finmy.search.state import SearchState
    with task_lock(controller.root, task_id):
        state = SearchState(controller.root, task_id)
        if any(state.data['sources'][sid].get('version') != version
               for sid, version in complete['source_versions'].items()):
            raise ValueError('来源版本已变化，请重新生成预览')
        payload = assemble_sources(state, complete['source_ids'], complete_manifest=complete, max_chars=limit)
        state.data.update(status='finished' if payload['samples'] else 'insufficient', stop_reason='manual_handoff')
        state.save()
        return payload
