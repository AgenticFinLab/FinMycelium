"""Copy located original passages into the unchanged Builder input contract."""
import copy

from finmy.subject_graph.runner import _publication_timestamp

from .state import write_json
from .sources import SourceStore, SourceIntegrityError, document_is_usable, quarantine_source
from .language_policy import assess


class SourceSelectionError(ValueError):
    """A repairable selection error, distinct from damaged evidence or offsets."""

    def __init__(self, invalid, eligible):
        self.invalid_source_ids = invalid
        self.eligible_source_ids = eligible
        first, reason = next(iter(invalid.items()))
        if reason == 'unknown_source':
            message = 'Unknown source ID: ' + first
        elif reason == 'not_inspected':
            message = 'Inspected source required: ' + first + '; remove this ID when finalizing'
        else:
            message = 'Source has no usable original body: ' + first
        super().__init__(message)


def source_selection_status(state, sid, version=None):
    """Check inspection and usable original text; integrity failures remain fatal."""
    entry = state.data['sources'].get(sid)
    if entry is None:
        return 'unknown_source'
    version = version or entry.get('version')
    if not version:
        return 'not_inspected'
    document = SourceStore(state).document(sid, version)
    if not assess(document, state.config.source_languages)['allowed']:
        return 'language_excluded'
    raw_ranges = entry.get('read_ranges', [])
    if not isinstance(raw_ranges, list) or any(not isinstance(r, dict) for r in raw_ranges):
        raise SourceIntegrityError(sid, 'Invalid inspected source range: ' + sid)
    ranges = [r for r in raw_ranges if r.get('version') == version]
    if not ranges:
        return 'not_inspected'
    inspected = False
    for row in ranges:
        block, start, end = (row.get(key) for key in ('block', 'start', 'end'))
        if (any(type(value) is not int for value in (block, start, end))
                or not 0 <= block < len(document['blocks'])
                or not 0 <= start <= end <= len(document['blocks'][block]['text'])):
            raise SourceIntegrityError(sid, 'Invalid inspected source range: ' + sid)
        inspected = inspected or end > start
    if not inspected:
        return 'not_inspected'
    return None if document_is_usable(document) else 'unusable_body'


def eligible_source_ids(state):
    """Audit every source independently, excluding corrupt versions explicitly.

    Selecting a corrupt source directly still raises; a catalog query must not
    discard other valid sources merely because one saved file was damaged.
    """
    eligible = []
    for sid, entry in state.data['sources'].items():
        try:
            status = source_selection_status(state, sid)
        except SourceIntegrityError as exc:
            quarantine_source(state, sid, exc)
            continue
        if entry.pop('quarantine', None) is not None:
            state.trace(dict(action='source_quarantine_cleared', source_id=sid,
                             version=entry.get('version')))
            state.save()
        if status is None:
            eligible.append(sid)
    return eligible


def _source_metadata(source, document, version):
    """Snapshot known source metadata beside, never inside, evidence text."""
    candidates = [document.get('published_at'), source.get('published_at')]
    if not any(value is not None for value in candidates):
        candidates = [item.get('published_at') for item in source.get('discoveries', [])
                      if isinstance(item, dict)]
    candidates = list(dict.fromkeys(value for value in candidates
                                   if isinstance(value, str) and value.strip()))
    publication = candidates[0] if len(candidates) == 1 else None
    metadata = dict(source_id=source['source_id'], version=version, source_version=version,
                    title=source.get('title'), url=source.get('url'), source_url=source.get('url'),
                    source_status=document['status'], published_at=_publication_timestamp(publication))
    if publication is not None:
        metadata['published_at_raw'] = publication
    elif candidates:
        metadata['publication_candidates'] = candidates
    if source.get('reused_from'):
        metadata['reused_from'] = copy.deepcopy(source['reused_from'])
    return metadata


def assemble(state, selections, *, gaps=None, reason='', max_chars=None):
    limit = state.config.max_builder_material_chars if max_chars is None else max_chars
    if type(limit) is not int or limit <= 0:
        raise ValueError('Material character limit must be positive')
    store = SourceStore(state)
    samples, adopted, omitted, seen = [], [], [], set()
    registry = {}
    used = 0
    for selection in selections:
        sid, version = selection['source_id'], selection['version']
        entry = state.data['sources'][sid]
        doc = store.document(sid, version)
        if not assess(doc, state.config.source_languages)['allowed']:
            raise SourceSelectionError({sid: 'language_excluded'}, eligible_source_ids(state))
        if not document_is_usable(doc):
            raise ValueError('Selected source has no usable original body: ' + sid)
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
        metadata = registry.setdefault(sid, _source_metadata(entry, doc, version))
        metadata.setdefault('sample_versions', {})[samples[-1]['sample_id']] = version
        versions = list(dict.fromkeys(metadata['sample_versions'].values()))
        if len(versions) > 1:
            # Legacy passage selections can contain multiple versions of one URL.
            metadata.pop('version', None)
            metadata.pop('source_version', None)
            metadata['versions'] = versions
            metadata['published_at'] = None
        adopted.append(selection)
    task = state.data['task']
    payload = dict(user_query=dict(query_text=task['query_text'],key_words=task.get('key_words',[]),
                                   extras=dict(source_registry=registry)), samples=samples)
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
    invalid = {sid: status for sid in source_ids
               if (status := source_selection_status(state, sid, (versions or {}).get(sid))) is not None}
    if invalid:
        raise SourceSelectionError(invalid, eligible_source_ids(state))
    store = SourceStore(state)
    documents, cleanup, duplicates, omitted, fingerprints = [], [], [], [], {}
    selected_versions, registry = {}, {}
    for sid in source_ids:
        entry = state.data['sources'][sid]
        version = (versions or {}).get(sid) or entry.get('version')
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
        header = f"[source={sid} version={version} status={document['status']}]\n{entry['url']}\n{entry['title']}\n"
        documents.append(dict(source_id=sid, version=version, blocks=blocks, header=header,
                              full_chars=len(header)+len(body), source_status=document['status']))
        registry[sid] = _source_metadata(entry, document, version)

    selected = [dict(source_id=d['source_id'], version=d['version'],
                     blocks=[i for i, _ in d['blocks']], header=d['header'],
                     material_chars=d['full_chars'], source_status=d['source_status']) for d in documents]
    task = state.data['task']
    record = dict(mode='complete_sources', source_ids=source_ids, source_versions=selected_versions,
                  user_query=dict(query_text=task['query_text'], key_words=task.get('key_words', []),
                                  extras=dict(source_registry=registry)),
                  selected=selected, omitted=omitted, cleanup=cleanup, duplicates=duplicates,
                  gaps=list(gaps or []), reason=reason, material_chars=sum(d['full_chars'] for d in documents),
                  unselected_sources=sorted(set(state.data['sources'])-set(source_ids)), review_required=True,
                  scope='All retained saved bodies after cleanup; not a claim of complete source acquisition or fact verification')
    from .state import digest
    queries = [task['query_text'], ' '.join(task.get('key_words', []))]
    trace = state.run_dir / 'trace.jsonl'
    if trace.exists():
        import json
        # JSONL records end at literal newlines. Unicode paragraph/line separators
        # inside a saved source string are data, not additional record boundaries.
        with trace.open(encoding='utf-8') as stream:
            for line in stream:
                if not line.strip():
                    continue
                event = json.loads(line)
                if event.get('action') == 'provider_started' and event.get('query'):
                    queries.append(event['query'])
    record['retrieval_queries'] = list(dict.fromkeys(q for q in queries if q.strip()))
    record['complete_id'] = digest(record)
    return materialize_complete(state, record), record


def materialize_complete(state, record, *, source_errors=None):
    """Reconstruct a fixed complete view from original versions, without recleaning."""
    from .state import digest
    if digest({k:v for k,v in record.items() if k!='complete_id'}) != record['complete_id']:
        raise ValueError('Complete material manifest integrity mismatch')
    selected = record.get('selected')
    if not isinstance(selected, list) or any(
            not isinstance(entry, dict)
            or not isinstance(entry.get('source_id'), str)
            or not isinstance(entry.get('version'), str)
            or not isinstance(entry.get('header'), str)
            or type(entry.get('material_chars')) is not int
            or not isinstance(entry.get('blocks'), list)
            or any(type(index) is not int or index < 0 for index in entry['blocks'])
            for entry in selected):
        raise ValueError('Invalid complete material manifest')
    store, samples = SourceStore(state), []
    for entry in selected:
        try:
            doc = store.document(entry['source_id'], entry['version'])
            if not assess(doc, state.config.source_languages)['allowed']:
                if source_errors is None:
                    raise SourceSelectionError({entry['source_id']: 'language_excluded'}, [])
                source_errors.append(dict(source_id=entry['source_id'], version=entry['version'],
                    error_type='language_excluded', stage='language_policy'))
                continue
            if any(i >= len(doc['blocks']) for i in entry['blocks']):
                raise SourceIntegrityError(entry['source_id'], 'Invalid complete material block')
            content = entry['header'] + '\n\n'.join(doc['blocks'][i]['text'] for i in entry['blocks'])
            if len(content) != entry['material_chars']:
                raise SourceIntegrityError(entry['source_id'], 'Complete material length mismatch')
        except SourceIntegrityError as exc:
            if source_errors is None:
                raise
            source_errors.append(dict(source_id=entry['source_id'], version=entry['version'],
                error_type=type(exc).__name__, stage='source_integrity'))
            continue
        samples.append(dict(sample_id=entry['source_id']+'-document',raw_data_id=entry['source_id'],content=content))
    return dict(user_query=copy.deepcopy(record['user_query']), samples=samples)


def derive_input(state, complete, *, max_chars=None, budget_policy='balanced'):
    """Allocate source quotas and share remaining space within the input budget."""
    # Accept the previous argument as an alias; always write the current policy ID.
    if budget_policy not in {'balanced', 'c2'}:
        raise ValueError('Unknown input budget policy')
    from .budget import BUDGET_POLICY, shared_input
    limit = state.config.max_builder_material_chars if max_chars is None else max_chars
    query = complete['user_query']
    queries = complete.get('retrieval_queries', [query['query_text'], ' '.join(query.get('key_words', []))])
    payload, allocation = shared_input(state, complete, limit, queries)
    payload['user_query'] = copy.deepcopy(payload['user_query'])
    entries = {e['source_id']: e for e in complete['selected']}
    selected = [dict(e, source_status=entries[e['source_id']]['source_status']) for e in allocation['selected']]
    omitted = list(complete['omitted']) + [dict(e, version=entries[e['source_id']]['version'],
        omission_reason='material_limit', note='Retained in complete material; omitted only from this input')
        for e in allocation['omitted']]
    notes = list(complete['gaps'])
    if any(o['omission_reason'] == 'material_limit' for o in omitted):
        notes.append('Some complete paragraphs were omitted by the material limit; review the omission record.')
    record = dict(mode='sources', budget_policy=BUDGET_POLICY,
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
    if complete_manifest is None:
        _, complete_manifest = prepare_complete_sources(state,source_ids,**options)
    payload, record = derive_input(state,complete_manifest,max_chars=limit)
    import uuid
    revision = state.run_dir / 'handoffs' / uuid.uuid4().hex
    for folder in (revision,state.run_dir):
        # The full view is immutable metadata referencing existing originals, not a copied evidence tree.
        write_json(folder / 'complete_material.json',complete_manifest)
        write_json(folder / 'selection.json',record)
        write_json(folder / 'builder_input.json',payload)
    return payload
