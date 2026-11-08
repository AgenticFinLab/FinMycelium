"""Explicitly adopt search passages into existing evidence review, without approval."""
import hashlib
from finmy.search.control import task_lock
from finmy.search.state import write_json


def adopt_sources(controller, task_id, store):
    with task_lock(controller.root,task_id):
        data=controller.inspect(task_id)
        event_id=data['task'].get('event_id')
        if not event_id:raise ValueError('该检索任务未关联主表事件')
        store.event(event_id)
        payload=data.get('builder_input')
        if not payload or not payload['samples']:raise ValueError('没有可纳入的材料')
        existing={s['sha256']:s['id'] for s in store.sources(event_id)}
        mapping=[];added=0
        for sample in payload['samples']:
            sha=hashlib.sha256(sample['content'].encode()).hexdigest()
            source=data['sources'][sample['raw_data_id']]
            if sha not in existing:
                url=source['url'] if source['url'].startswith(('https://','http://')) else ''
                existing[sha]=store.add_source(event_id,source['title'] or source['url'],text=sample['content'],url=url)
                added+=1
            mapping.append(dict(sample_id=sample['sample_id'],source_id=existing[sha],sha256=sha))
        write_json(controller.root/task_id/'runs/initial/workbench_sources.json',dict(event_id=event_id,mapping=mapping))
        return added
