"""Replay saved long-block window allocations against immutable originals.

Allocation still uses the shared source/priority/threshold algorithm. Only the
working granularity changes; stored documents and the Builder contract do not.
New handoffs use whole-block allocation; this module supports saved window policies.
"""
from copy import deepcopy

from .sources import SourceStore, pdf_blocks


def original_ranges(document, indexes):
    ranges = []
    for index in sorted(indexes):
        item = dict(document['blocks'][index]['original_range'])
        if ranges and item['block'] == ranges[-1]['block'] and item['start'] == ranges[-1]['end']:
            ranges[-1]['end'] = item['end']
        else:
            ranges.append(item)
    return ranges


def render_windows(entry, document, indexes):
    """Merge contiguous views before labeling; never join across omitted text."""
    groups = []
    for index in sorted(indexes):
        block = document['blocks'][index]
        origin = block['original_range']
        if groups and origin['block'] == groups[-1]['block'] and origin['start'] == groups[-1]['end']:
            groups[-1]['end'] = origin['end']
            groups[-1]['text'] += block['text']
        else:
            groups.append(dict(origin, text=block['text']))
    if list(sorted(indexes)) == entry['blocks']:
        return entry['header'] + '\n\n'.join(g['text'] for g in groups)
    return entry['header'] + '\n\n'.join(
        f"[original block {g['block']} chars {g['start']}:{g['end']}]\n{g['text']}" for g in groups)


def allocate_windows(state, complete, budget, queries, *, policy):
    from .budget import _shared_input
    from .handoff import materialize_complete
    # Verify the frozen complete manifest before deriving any temporary view.
    materialize_complete(state, complete)
    store = SourceStore(state)
    documents, entries = {}, []
    for entry in complete['selected']:
        document = store.document(entry['source_id'], entry['version'])
        blocks = []
        for index in entry['blocks']:
            original = document['blocks'][index]
            parts = pdf_blocks(original['text'], original.get('page', 0)) if (
                len(original['text']) > 1600 and original.get('row') is None) else [
                dict(start=0, end=len(original['text']), text=original['text'])]
            for part in parts:
                blocks.append(dict(original, text=part['text'], original_range=dict(
                    block=index, start=part['start'], end=part['end'])))
        view = dict(document, blocks=blocks, temporary_windows=True)
        documents[entry['source_id']] = view
        projected = dict(entry, blocks=list(range(len(blocks))))
        projected['material_chars'] = len(render_windows(projected, view, projected['blocks']))
        entries.append(projected)
    projected = dict(complete, selected=entries, material_chars=sum(e['material_chars'] for e in entries))
    marks = []
    for number, passage in enumerate(complete.get('priority_passages', [])):
        document = documents.get(passage['source_id'])
        if not document or document['version'] != passage['version']:
            continue
        for index, block in enumerate(document['blocks']):
            origin = block['original_range']
            if origin['block'] != passage['block']:
                continue
            start, end = max(origin['start'], passage['start']), min(origin['end'], passage['end'])
            if start < end:
                marks.append(dict(passage, block=index, start=start-origin['start'],
                                  end=end-origin['start'], original_mark=number))
    projected['priority_passages'] = marks
    payload, allocation = _shared_input(state, projected, budget, queries, policy=policy, documents=documents)
    allocation['windowing'] = dict(soft_chars=1600, locator='original block and character offsets',
                                   source_storage_unchanged=True)

    def translate(entry):
        document = documents[entry['source_id']]
        entry['ranges'] = original_ranges(document, entry['blocks'])
        entry['blocks'] = sorted({r['block'] for r in entry['ranges']})

    for entry in allocation['selected'] + allocation['omitted']:
        translate(entry)
    for action in allocation.get('pool_actions', []):
        action['added_ranges'] = original_ranges(documents[action['source_id']], action['added_blocks'])
        action['added_blocks'] = sorted({r['block'] for r in action['added_ranges']})
    for stage in allocation.get('threshold_stages', []):
        stage['selected_ranges'] = {sid:original_ranges(documents[sid], indexes)
                                    for sid, indexes in stage['selected_blocks'].items()}
        stage['selected_blocks'] = {sid:sorted({r['block'] for r in ranges})
                                    for sid, ranges in stage['selected_ranges'].items()}
    for name in ('base_decisions', 'decisions'):
        for sid, decision in allocation.get(name, {}).items():
            for anchor in decision.get('anchors', []):
                origin = documents[sid]['blocks'][anchor['anchor']]['original_range']
                anchor['anchor'] = origin['block']
                anchor['anchor_range'] = dict(origin)
    outcomes = [[] for _ in complete.get('priority_passages', [])]
    for item in allocation.get('priority_decisions', []):
        outcomes[item['passage']['original_mark']].append(item['status'])
    allocation['priority_decisions'] = []
    for passage, statuses in zip(complete.get('priority_passages', []), outcomes):
        if not statuses or 'unavailable' in statuses:
            status = 'unavailable'
        elif 'material_limit' in statuses:
            status = 'material_limit'
        elif all(s == 'retained' for s in statuses):
            status = 'retained'
        elif all(s == 'with_context' for s in statuses):
            status = 'with_context'
        else:
            status = 'paragraph_only'
        allocation['priority_decisions'].append(dict(passage=deepcopy(passage),status=status))
    return payload, allocation
