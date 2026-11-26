"""Read-only retrieval from the confirmed handoff and versioned Search documents."""
import re
from copy import deepcopy
from pathlib import Path

from finmy.search.budget import rank_blocks
from finmy.search.metadata import source_metadata
from finmy.search.sources import SourceStore
from finmy.search.state import SearchState, digest
from .records import fingerprint, validate_input

MAX_ADDITION = 8000


def windows(text):
    """Split at paragraph or sentence boundaries and retain exact code-point offsets."""
    pos = 0
    while pos < len(text):
        end = min(pos + 1200, len(text))
        if end < len(text):
            breaks = list(re.finditer(r'\n\s*\n|(?<=[.!?。！？])\s+', text[pos + 480:end]))
            if breaks:
                end = pos + 480 + breaks[-1].end()
        left = pos + len(text[pos:end]) - len(text[pos:end].lstrip())
        right = pos + len(text[pos:end].rstrip())
        if left < right:
            yield left, right
        pos = end


def frozen_passages(payload):
    registry = payload['user_query']['extras']['source_registry']
    for sample in payload['samples']:
        sid, content = sample['raw_data_id'], sample['content']
        # Search headers/omission notices are navigation, never source testimony.
        offset = 0
        if content.startswith('[source='):
            lines = content.splitlines(keepends=True)
            offset = sum(map(len, lines[:3]))
            for line in lines[3:]:
                if not line.startswith(('Publication date (', 'Retrieved at:')):
                    break
                offset += len(line)
        cursor = offset
        for marker in [*re.finditer(r'^\[\.\.\. omitted[^\n]*\](?:\n|$)', content[offset:], re.M), None]:
            boundary = offset + marker.start() if marker else len(content)
            for start, end in windows(content[cursor:boundary]):
                i, j = cursor + start, cursor + end
                yield dict(origin='frozen', source_id=sid, sample_id=sample['sample_id'], start=i, end=j,
                           text=content[i:j], metadata=registry[sid])
            if marker:
                cursor = offset + marker.end()


def original_search(provenance):
    from finmy.dataset import output_directory
    tid, revision = provenance.get('search_task_id'), provenance.get('handoff_revision')
    if not all(isinstance(v, str) and re.fullmatch(r'[A-Za-z0-9_-]+', v) for v in (tid, revision)):
        return None
    if provenance.get('source_root'):
        task_root = Path(provenance['source_root'])
        if task_root.name != tid:
            raise ValueError('Search cache identity differs from confirmed handoff')
    elif provenance.get('catalog', {}).get('root'):
        task_root = output_directory(provenance['catalog']['root'], 'workbench', 'search', tid)
    else:
        return None
    from json import loads
    frozen = task_root / 'runs' / 'initial' / 'handoffs' / revision / 'builder_input.json'
    if not frozen.is_file():
        return None
    if digest(loads(frozen.read_bytes())) != provenance['search_input_sha256']:
        raise ValueError('Original Search cache belongs to a different handoff')
    return SearchState(task_root.parent, tid)


def source_passages(state, origin, *, source_ids=None):
    store = SourceStore(state)
    ids = sorted(state.data['sources'] if source_ids is None else source_ids)
    for sid in ids:
        entry = state.data['sources'][sid]
        version = entry.get('version')
        if not version:
            continue
        document = store.document(sid, version)  # verifies raw and parsed content hashes
        metadata = source_metadata(entry, document)
        metadata = {key:metadata.get(key) for key in
                    ('source_url','title','retrieved_at','content_status','published_at')}
        for n, block in enumerate(document['blocks']):
            for start, end in windows(block['text']):
                yield dict(origin=origin, source_id=sid, version=version, parsed_sha256=entry['parsed_hashes'][version],
                           block=n, page=block.get('page'), paragraph=block.get('paragraph'),
                           start=start, end=end, text=block['text'][start:end], metadata=metadata)


def shortlist(passages, questions, *, frozen=None):
    """Rank across sources for each question; a model checks the actual original passage."""
    rows, seen = [], set()
    for row in passages:
        text = row['text']
        if len(text) < 24:
            continue
        normalized = ' '.join(text.split()).casefold()
        if normalized in seen or (frozen is not None and normalized in frozen):
            continue
        seen.add(normalized)
        rows.append(row)
    if not rows:
        return {}
    queries = [q['question'] for q in questions]
    rankings = rank_blocks({'blocks': list(range(len(rows)))}, {'blocks':rows}, queries, query_coverage=True)
    found = {}
    for result in rankings:
        counts = {}
        for i, _ in result['ranking']:
            row = rows[i]
            sid = row['source_id']
            if counts.get(sid, 0) >= 3:
                continue
            found.setdefault('P-' + fingerprint(row)[:16], row)
            counts[sid] = counts.get(sid, 0) + 1
            if sum(counts.values()) >= 10:
                break
    return found


def added_input(base, selections):
    """Keep the parent byte-for-byte as the initial sample sequence. Charge every new character."""
    payload = deepcopy(base)
    registry = payload['user_query']['extras']['source_registry']
    initial = '\n'.join(' '.join(s['content'].split()).casefold() for s in base['samples'])
    delivered, included, skipped, samples = 0, [], [], {s['sample_id'] for s in base['samples']}
    sources = set()
    for row in selections:
        text = row['text']
        key = ' '.join(text.split()).casefold()
        if not key or key in initial:
            skipped.append(dict(passage=row['id'], reason='already_present'))
            continue
        sid, meta = row['source_id'], row['metadata']
        url = meta['source_url']
        existing = next((s for s, m in registry.items() if m.get('source_url') == url), None)
        if existing:
            sid = existing
        elif sid in registry:
            raise ValueError('A supplementary source ID refers to a different URL')
        header = (f"[source={sid} version={row['version']} block={row['block']} chars={row['start']}:{row['end']}]\n"
                  f"{url}\n{meta.get('title') or ''}\n")
        content = header + text
        if sid not in sources and len(sources) >= 4:
            skipped.append(dict(passage=row['id'], reason='additional_source_limit'))
            continue
        if delivered + len(content) > MAX_ADDITION:
            skipped.append(dict(passage=row['id'], reason='additional_character_limit'))
            continue
        sample_id = 'supplement-' + fingerprint([sid, row['version'], row['block'], row['start'], row['end']])[:24]
        if sample_id in samples:
            raise ValueError('Supplementary sample ID collision')
        registry.setdefault(sid, deepcopy(meta))
        payload['samples'].append(dict(sample_id=sample_id, raw_data_id=sid, content=content))
        included.append({k:v for k,v in row.items() if k not in ('text','metadata')} |
                        dict(sample_id=sample_id, source_id=sid, text_sha256=fingerprint(text),
                             source_url=url, sample_text_start=len(header), sample_text_end=len(content)))
        delivered += len(content)
        sources.add(sid)
        samples.add(sample_id)
        initial += '\n' + key
    validate_input(payload)
    return payload, included, skipped
