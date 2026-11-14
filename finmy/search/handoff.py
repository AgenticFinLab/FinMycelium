"""Copy located original passages into the unchanged Builder input contract."""
from .state import write_json
from .sources import SourceStore
from .metadata import source_metadata


def assemble(state, selections, *, gaps=None, reason='', max_chars=None):
    limit = state.config.max_builder_material_chars if max_chars is None else max_chars
    if type(limit) is not int or limit <= 0:
        raise ValueError('Material character limit must be positive')
    store = SourceStore(state)
    samples, adopted, omitted, seen = [], [], [], set()
    used = 0
    for selection in selections:
        sid, version = selection['source_id'], selection['version']
        entry = state.data['sources'][sid]
        doc = store.document(sid, version)
        block, start, end = selection['block'], selection['start'], selection['end']
        if any(type(v) is not int for v in (block,start,end)) or not 0 <= block < len(doc['blocks']):
            raise ValueError('Invalid selection block')
        text = doc['blocks'][block]['text']
        if not 0 <= start < end <= len(text):
            raise ValueError('Invalid selection offsets')
        covered = start
        ranges = sorted((r['start'], r['end']) for r in entry.get('read_ranges', [])
                        if r['version'] == version and r['block'] == block)
        for lo, hi in ranges:
            if lo <= covered:
                covered = max(covered, hi)
        if covered < end:
            raise ValueError('Selected passage was not read')
        key = (sid,version,block,start,end)
        if key in seen:
            continue
        seen.add(key)
        header = f"[source={sid} version={version} block={block} chars={start}:{end}]\n{entry['url']}\n{entry['title']}\n"
        content = header + text[start:end]
        if used + len(content) > limit:
            omitted.append(dict(**selection, omission_reason='material_limit'))
            continue  # Never silently cut an evidence passage mid-sentence.
        used += len(content)
        samples.append(dict(sample_id=f'{sid}-{len(samples)}',raw_data_id=sid,content=content))
        adopted.append(selection)
    task = state.data['task']
    payload = dict(user_query=dict(query_text=task['query_text'],key_words=task.get('key_words',[])), samples=samples)
    record = dict(selected=adopted, omitted=omitted, gaps=gaps or [], reason=reason,
                  material_chars=used, max_material_chars=limit,
                  unselected_sources=sorted(set(state.data['sources']) - {s['source_id'] for s in adopted}))
    # Keep previous handoffs for review, including reassembly at a different budget.
    import uuid
    revision = state.run_dir / 'handoffs' / uuid.uuid4().hex
    write_json(revision / 'selection.json',record)
    write_json(revision / 'builder_input.json',payload)
    write_json(state.run_dir / 'selection.json',record)
    write_json(state.run_dir / 'builder_input.json',payload)
    from .state import now
    state.data.update(handoff_revision=revision.name, handoff_updated_at=now())
    state.save()
    return payload


def _clean_blocks(document):
    """Conservative cleanup only; keep original paragraph text and its block index."""
    chrome = {'首页', '登录', '注册', '返回顶部', 'home', 'sign in', 'log in', 'back to top'}
    kept, removed, seen = [], [], {}
    for index, block in enumerate(document['blocks']):
        text = block['text']
        normalized = ' '.join(text.split())
        why = None
        if not normalized:
            why = 'empty'
        elif document['kind'] == 'html' and normalized.casefold() in chrome:
            why = 'navigation_label'
        elif len(normalized) >= 80 and normalized in seen:
            why = 'exact_repeated_paragraph'
        if why:
            removed.append(dict(block=index, reason=why))
        else:
            kept.append((index, text))
            seen[normalized] = index
    return kept, removed


def prepare_complete_sources(state, source_ids, *, gaps=None, reason='', versions=None):
    """Build a document package without writes, network requests, or model calls.

    A source must have been inspected, but every packaged paragraph need not have been
    sent to the search model. Inspection is relevance screening, not fact verification.
    """
    if not isinstance(source_ids, list) or any(not isinstance(s, str) for s in source_ids):
        raise ValueError('Finish needs source_ids: a list of inspected source IDs')
    source_ids = list(dict.fromkeys(source_ids))
    store = SourceStore(state)
    documents, cleanup, duplicates, omitted, fingerprints = [], [], [], [], {}
    selected_versions = {}
    for sid in source_ids:
        if sid not in state.data['sources']:
            raise ValueError('Unknown source ID: ' + sid)
        entry = state.data['sources'][sid]
        version = (versions or {}).get(sid) or entry.get('version')
        if not version or not any(r['version'] == version and r['end'] > r['start'] for r in entry.get('read_ranges', [])):
            raise ValueError('Inspect this source before keeping it: ' + sid)
        document = store.document(sid, version)
        selected_versions[sid] = version
        blocks, removed = _clean_blocks(document)
        cleanup.extend(dict(source_id=sid, version=version, **r) for r in removed)
        if not blocks:
            omitted.append(dict(source_id=sid, version=version, omission_reason='no_usable_body'))
            continue
        body = '\n\n'.join(text for _, text in blocks)
        from .state import digest
        fingerprint = digest(' '.join(body.split()))
        if fingerprint in fingerprints:
            duplicates.append(dict(source_id=sid, version=version, duplicate_of=fingerprints[fingerprint]))
            continue
        fingerprints[fingerprint] = sid
        metadata = source_metadata(entry, document)
        header = f"[source={sid} version={version} status={document['status']}]\n{entry['url']}\n{entry['title']}\n"
        if metadata['published_at']:
            header += f"Publication date (source/provider metadata): {metadata['published_at']}\n"
        elif metadata['publication_candidates']:
            header += f"Publication date: {metadata['publication_status']} (see source metadata)\n"
        if metadata['retrieved_at']:
            header += f"Retrieved at: {metadata['retrieved_at']}\n"
        documents.append(dict(source_id=sid, version=version, blocks=blocks, header=header,
                              metadata=metadata, full_chars=len(header)+len(body), source_status=document['status']))

    selected = [dict(source_id=d['source_id'], version=d['version'],
                     blocks=[i for i, _ in d['blocks']], header=d['header'],
                     metadata=d['metadata'], material_chars=d['full_chars'], source_status=d['source_status']) for d in documents]
    task = state.data['task']
    record = dict(mode='complete_sources', source_ids=source_ids, source_versions=selected_versions,
                  user_query=dict(query_text=task['query_text'], key_words=task.get('key_words', [])),
                  selected=selected, omitted=omitted, cleanup=cleanup, duplicates=duplicates,
                  gaps=list(gaps or []), reason=reason, material_chars=sum(d['full_chars'] for d in documents),
                  unselected_sources=sorted(set(state.data['sources'])-set(source_ids)), review_required=True,
                  scope='All retained saved bodies after cleanup; not a claim of complete source acquisition or fact verification')
    from .state import digest
    scope = task.get('research_scope', {})
    # Structured scope avoids promoting exclusions, planning prose and source-index
    # descriptions into positive retrieval terms. Do not ban those words in evidence.
    focus = (task.get('catalog', {}).get('event_name') or task['target_name']) + '. ' + scope.get('include', '')
    queries = [focus if scope.get('include') else task['query_text'], ' '.join(task.get('key_words', []))]
    trace = state.run_dir / 'trace.jsonl'
    if trace.exists():
        import json
        for line in trace.read_text(encoding='utf-8').splitlines():
            event = json.loads(line)
            if event.get('action') == 'provider_started' and event.get('query'):
                queries.append(event['query'])
    record['retrieval_queries'] = list(dict.fromkeys(q for q in queries if q.strip()))
    from .budget import BUDGET_POLICY
    record['budget_policy'] = BUDGET_POLICY
    record['complete_id'] = digest(record)
    return materialize_complete(state, record), record


def materialize_complete(state, record):
    """Reconstruct a fixed complete view from original versions, without recleaning."""
    from .state import digest
    if digest({k:v for k,v in record.items() if k!='complete_id'}) != record['complete_id']:
        raise ValueError('Complete material manifest integrity mismatch')
    store, samples = SourceStore(state), []
    for entry in record['selected']:
        doc = store.document(entry['source_id'], entry['version'])
        content = entry['header'] + '\n\n'.join(doc['blocks'][i]['text'] for i in entry['blocks'])
        if len(content) != entry['material_chars']:
            raise ValueError('Complete material length mismatch')
        samples.append(dict(sample_id=entry['source_id']+'-document',raw_data_id=entry['source_id'],content=content))
    return dict(user_query=record['user_query'], samples=samples)


def derive_input(state, complete, *, max_chars=None, budget_policy='balanced', allocation_policy=None):
    """Allocate source quotas and share remaining space within the input budget."""
    # Keep the caller-label alias; policy replay follows the manifest unless explicitly overridden.
    if budget_policy not in {'balanced', 'c2'}:
        raise ValueError('Unknown input budget policy')
    from .budget import LEGACY_POLICY, shared_input
    limit = state.config.max_builder_material_chars if max_chars is None else max_chars
    query = complete['user_query']
    queries = complete.get('retrieval_queries', [query['query_text'], ' '.join(query.get('key_words', []))])
    policy = allocation_policy or complete.get('budget_policy', LEGACY_POLICY)
    payload, allocation = shared_input(state, complete, limit, queries, policy=policy)
    entries = {e['source_id']: e for e in complete['selected']}
    selected = [dict(e, source_status=entries[e['source_id']]['source_status'],
                     **({'metadata':entries[e['source_id']]['metadata']} if 'metadata' in entries[e['source_id']] else {}))
                for e in allocation['selected']]
    omitted = list(complete['omitted']) + [dict(e, version=entries[e['source_id']]['version'],
        omission_reason=e.get('omission_reason','material_limit'), note='Retained in complete material; omitted only from this input')
        for e in allocation['omitted']]
    notes = list(complete['gaps'])
    if any(o['omission_reason'] == 'material_limit' for o in omitted):
        notes.append('Some complete paragraphs were omitted by the material limit; review the omission record.')
    if any(o['omission_reason'] == 'relevance_selection' for o in omitted):
        notes.append('Some saved text is outside the selected relevance windows; it remains in complete material for review.')
    record = dict(mode='sources', budget_policy=policy,
        complete_id=complete['complete_id'], complete_material_chars=complete['material_chars'],
        complete_source_count=len(complete['selected']), source_ids=complete['source_ids'],
        source_versions=complete['source_versions'], selected=selected, omitted=omitted,
        cleanup=complete['cleanup'], duplicates=complete['duplicates'],
        gaps=list(dict.fromkeys(notes)), reason=complete['reason'],
        material_chars=allocation['material_chars'], max_material_chars=limit,
        unselected_sources=complete['unselected_sources'], review_required=True,
        retrieval_queries=queries, allocation=allocation,
        scope='Budgeted input derived from independently retained complete material')
    return payload, record


def prepare_sources(state, source_ids, *, gaps=None, reason='', max_chars=None, versions=None):
    _, complete = prepare_complete_sources(state,source_ids,gaps=gaps,reason=reason,versions=versions)
    return derive_input(state,complete,max_chars=max_chars)


def assemble_sources(state, source_ids, *, complete_manifest=None, **options):
    limit = options.pop('max_chars',None)
    allocation_policy = options.pop('allocation_policy',None)
    if complete_manifest is None:
        _, complete_manifest = prepare_complete_sources(state,source_ids,**options)
    payload, record = derive_input(state,complete_manifest,max_chars=limit,allocation_policy=allocation_policy)
    from pathlib import Path
    from .state import digest
    record['assembly_code_sha256'] = digest({p.name:digest(p.read_bytes()) for p in Path(__file__).parent.glob('*.py')})
    import uuid
    revision = state.run_dir / 'handoffs' / uuid.uuid4().hex
    for folder in (revision,state.run_dir):
        # The full view is immutable metadata referencing existing originals, not a copied evidence tree.
        write_json(folder / 'complete_material.json',complete_manifest)
        write_json(folder / 'selection.json',record)
        write_json(folder / 'builder_input.json',payload)
    from .state import now
    state.data.update(handoff_revision=revision.name, handoff_updated_at=now())
    state.save()
    return payload
