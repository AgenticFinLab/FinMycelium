"""Unique frozen-source read accounting and task-local passage delivery."""
from copy import deepcopy

from .records import fingerprint, json_bytes, sha256


class Passages:
    def __init__(self, samples):
        self.samples = samples
        self.versions = {sid: sha256(s['content'].encode('utf-8')) for sid, s in samples.items()}
        self.ranges = {}

    def identify(self, value):
        if not isinstance(value, dict):
            return None
        sid, start, end = (value.get(k) for k in ('sample_id', 'start', 'end'))
        sample = self.samples.get(sid) if isinstance(sid, str) else None
        if (sample is None or type(start) is not int or type(end) is not int
                or not 0 <= start < end <= len(sample['content'])
                or value.get('text') != sample['content'][start:end]):
            return None
        return (sid, self.versions[sid]), start, end

    def add(self, value, version=None):
        """Return uncovered intervals; merge overlapping and adjacent ranges."""
        identity = self.identify(value)
        if identity is None:
            return None
        key, start, end = identity
        if version is not None:
            key = (key[0], version)
        prior = self.ranges.get(key, [])
        cursor, missing = start, []
        for left, right in prior:
            if right <= cursor:
                continue
            if left >= end:
                break
            if left > cursor:
                missing.append((cursor, min(left, end)))
            cursor = max(cursor, right)
        if cursor < end:
            missing.append((cursor, end))
        merged = []
        for left, right in sorted(prior + [(start, end)]):
            if merged and left <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], right))
            else:
                merged.append((left, right))
        self.ranges[key] = merged
        return missing


def read_charge(passages, request, result, versions=None):
    """Source text costs only new characters; other tool payloads retain accounting."""
    if request.get('tool') in ('read_sample', 'search'):
        items = result if isinstance(result, list) else [result]
        # Do not waive bytes for unknown or changed material in a historical log.
        if all(passages.identify(item) is not None for item in items):
            return sum(end - start for item in items for start, end in
                       passages.add(item, (versions or {}).get(item['sample_id'])))
    return len(json_bytes(result).decode('utf-8'))


def next_read_charge(samples, records, request, result):
    """Rebuild from immutable history, including runs saved before dedup existed."""
    passages = Passages(samples)
    spent = sum(read_charge(passages, r['request'], r['result'], r.get('sample_versions')) for r in records)
    return spent, read_charge(passages, request, result)


def compact_read_results(request, results, samples):
    """Keep original state untouched; send each source interval once per prompt."""
    passages = Passages(samples)
    body = request.get('body', {})
    for item in body if isinstance(body, list) else [body]:
        passages.add(item)
    compact, seen = [], set()

    def fragments(value):
        missing = passages.add(value)
        if missing is None:
            return [deepcopy(value)]
        if not missing:
            return [{k: value[k] for k in ('sample_id', 'source_id', 'start', 'end') if k in value} | dict(
                already_supplied=True,
                message='Text is already in task.body or earlier read_results; use it without rereading.')]
        return [dict(value, start=start, end=end,
                     text=value['text'][start-value['start']:end-value['start']])
                for start, end in missing]

    for entry in results:
        signature = fingerprint(entry)
        if signature in seen:
            continue
        seen.add(signature)
        tool = entry['request'].get('tool')
        if tool == 'read_sample':
            compact.extend(dict(request=deepcopy(entry['request']), result=part)
                           for part in fragments(entry['result']))
        elif tool == 'search' and isinstance(entry['result'], list):
            compact.append(dict(request=deepcopy(entry['request']), result=[
                part for item in entry['result'] for part in fragments(item)]))
        else:
            compact.append(deepcopy(entry))
    return compact
