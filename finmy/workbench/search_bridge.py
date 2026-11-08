"""Explicitly adopt search passages into existing evidence review, without approval."""
import copy
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
        registry=payload['user_query'].get('extras',{}).get('source_registry',{})
        mapping=[];added=0
        for sample in payload['samples']:
            sha=hashlib.sha256(sample['content'].encode()).hexdigest()
            raw_id=sample['raw_data_id']
            source=copy.deepcopy(registry.get(raw_id))
            if source is None:
                # Older exports have no metadata snapshot. Their selected version
                # is still known; a newer current source version is not this input.
                entry=data['sources'][raw_id]
                source={key:entry[key] for key in ('source_id','title','url')}
                selection=data.get('selection') or {}
                versions=list(dict.fromkeys(row['version'] for row in selection.get('selected',[])
                    if row.get('source_id')==raw_id and isinstance(row.get('version'),str)))
                if not versions and raw_id in selection.get('source_versions',{}):
                    versions=[selection['source_versions'][raw_id]]
                if len(versions)==1:
                    source.update(version=versions[0],source_version=versions[0])
                elif versions:
                    source['versions']=versions
            if sha not in existing:
                url=source['url'] if source['url'].startswith(('https://','http://')) else ''
                published=source.get('published_at_raw',source.get('published_at'))
                existing[sha]=store.add_source(event_id,source['title'] or source['url'],text=sample['content'],url=url,
                    published=published if isinstance(published,str) else '',metadata=source)
                added+=1
            mapping.append(dict(sample_id=sample['sample_id'],source_id=existing[sha],sha256=sha,
                                raw_data_id=sample['raw_data_id'],metadata=source))
        write_json(controller.root/task_id/'runs/initial/workbench_sources.json',dict(event_id=event_id,mapping=mapping))
        return added
