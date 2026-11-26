"""One lifecycle for shown originals: present, select or exclude, then advance.

The ledger stores locations, not another copy of evidence or fact status. Kept
ranges are derived from validated priority_passages; exclusions apply only to
explicitly shown ranges. Cached/read ranges alone never enter this ledger.
"""
import json

from .reading import unread_ranges, record_presented
from .sources import SourceStore
from .state import digest

LOCATION = ('source_id', 'version', 'block', 'start', 'end')


def passage_id(source_id, version, span):
    return 'p-' + digest(dict(source_id=source_id, version=version,
                             **{k: span[k] for k in ('block', 'start', 'end')}))[:20]


def context_passages(context):
    for source in context.get('sources', []):
        for span in source.get('read_evidence', []):
            yield dict(source_id=source['source_id'], version=source['version'], **span)
    for source in context.get('cached_evidence', []):
        for span in source['spans']:
            yield dict(source_id=source['source_id'], version=source['version'], **span)
    yield from context.get('pending_evidence', [])


def accept_presentation(state, context):
    """Call only after a successful model response, including malformed responses."""
    from .topic import POLICY
    if state.data.get('retrieval_plan', {}).get('policy') != POLICY:
        # Historical document-selection tasks do not require passage decisions.
        return record_presented(state, context.get('cached_evidence', []))
    rows = list(context_passages(context))
    candidates = [dict(source_id=r['source_id'], version=r['version'], spans=[r]) for r in rows]
    new_chars = record_presented(state, candidates)
    ledger = state.data.setdefault('passage_reviews', {})
    for row in rows:
        key = passage_id(row['source_id'], row['version'], row)
        ledger.setdefault(key, {k: row[k] for k in LOCATION})
    if rows:
        state.trace(dict(action='evidence_presented', model_call=state.data['usage']['model'],
                         passages=[dict(passage_id=passage_id(r['source_id'], r['version'], r),
                                        **{k: r[k] for k in LOCATION}) for r in rows]))
        state.save()
    return new_chars


def excluded_ranges(state, source_id, version):
    return [r for r in state.data.get('passage_reviews', {}).values()
            if r.get('excluded_reason') and r['source_id'] == source_id and r['version'] == version]


def pending_passages(state):
    """Subtract saved selections/exclusions, preserving unhandled sentence tails."""
    store, result, covered, documents = SourceStore(state), [], {}, {}
    for row in state.data.get('passage_reviews', {}).values():
        sid, version = row['source_id'], row['version']
        if state.data['sources'].get(sid, {}).get('version') != version:
            continue  # Old decisions cannot apply to a replacement original.
        key = (sid, version)
        if key not in covered:
            documents[key] = store.document(sid, version)
            covered[key] = [m for m in state.data.get('priority_passages', [])
                            if m['source_id'] == sid and m['version'] == version]
            covered[key] += excluded_ranges(state, sid, version)
        for start, end in list(unread_ranges(row['block'], row['start'], row['end'], covered[key])):
            ref = dict(source_id=sid, version=version, block=row['block'], start=start, end=end)
            covered[key].append(ref)
            if documents[key]['blocks'][row['block']]['text'][start:end].strip():
                result.append(ref)
    return result


def selected_prefix(state, ref, text):
    """Restore a nearby kept referent without exposing an uninspected gap."""
    marks = [m for m in state.data.get('priority_passages', [])
             if all(m[k] == ref[k] for k in ('source_id', 'version', 'block'))
             and m['start'] < m['end'] <= ref['start']]
    start = end = ref['start']
    for mark in sorted(marks, key=lambda m: (m['end'], m['start']), reverse=True):
        if mark['end'] < start and text[mark['end']:start].strip():
            break
        if end - mark['start'] > 800:
            break  # Keep complete marked ranges; do not invent a truncated prefix.
        start = min(start, mark['start'])
    if start < end and text[start:end].strip():
        return dict(block=ref['block'], start=start, end=end, text=text[start:end])
    return None


def pending_preview(state, pending, limit):
    """Replay only outstanding originals under the existing serialized text budget."""
    result, store, documents = [], SourceStore(state), {}
    for ref in pending:
        key = ref['source_id'], ref['version']
        if key not in documents:
            documents[key] = store.document(*key)
        text = documents[key]['blocks'][ref['block']]['text']
        row = dict(ref, passage_id=passage_id(ref['source_id'], ref['version'], ref), text='')
        prefix = selected_prefix(state, ref, text)
        # Undecided text has priority. Add its kept referent only when both fit,
        # charging all context text/coordinates to the same serialized allowance.
        if prefix and len(json.dumps(prefix, ensure_ascii=False)) <= limit // 4:
            trial = dict(row, text=text[ref['start']:ref['end']], selected_context_before=prefix)
            if len(json.dumps(result + [trial], ensure_ascii=False)) <= limit:
                row['selected_context_before'] = prefix
        room = limit - len(json.dumps(result + [row], ensure_ascii=False))
        if room < 1:
            break
        row['text'] = text[ref['start']:min(ref['end'], ref['start'] + room)]
        while row['text']:
            row['end'] = row['start'] + len(row['text'])
            row['passage_id'] = passage_id(row['source_id'], row['version'], row)
            excess = len(json.dumps(result + [row], ensure_ascii=False)) - limit
            if excess <= 0:
                result.append(row)
                break
            row['text'] = row['text'][:-excess]
    return result


def commit_evidence(state, action):
    """Commit independent evidence before validating or executing the next tool."""
    if not {'priority_passages', 'fact_checks', 'passage_exclusions'} & action.keys():
        return
    from .evidence import record_passages
    from .review import record_checks
    report = state.data['evidence_feedback'] = {}
    if 'priority_passages' in action:
        report['priority_passages'] = record_passages(state, action['priority_passages'])
    record_checks(state, action.get('fact_checks', []), mark_support=True)
    if 'passage_exclusions' in action:
        items = action['passage_exclusions']
        accepted, rejected = 0, []
        if not isinstance(items, dict):
            rejected.append(dict(reason='passage_exclusions must map shown passage IDs to reasons'))
        else:
            ledger = state.data.get('passage_reviews', {})
            for key, reason in items.items():
                if (key not in ledger or not isinstance(reason, str)
                        or not reason.strip() or len(reason) > 300):
                    rejected.append(dict(passage_id=key, reason='Use a shown passage ID and a brief nonempty reason'))
                    continue
                ledger[key]['excluded_reason'] = reason
                accepted += 1
        report['passage_exclusions'] = dict(accepted=accepted, rejected=rejected)
    state.save()


def require_decisions(state, action):
    """Use the same pending ranges for ordinary actions and finish, without reads."""
    pending = pending_passages(state)
    if not pending:
        return None
    if action['action'] == 'finish' and (state.data.get('finalization_trigger')
            or state.data['usage']['model'] >= state.config.max_model_calls):
        action['gaps'] = list(action['gaps']) + [
            f"Shown original left undecided: {r['source_id']} version={r['version']} "
            f"block={r['block']} chars={r['start']}:{r['end']}." for r in pending]
        if action['reason'] == 'supported':
            action['reason'] = 'low_gain'
        return None
    return dict(kind='pending_evidence', operation_deferred=True, pending_count=len(pending),
                hint='Judge pending_evidence against the whole confirmed event/person scope, not only the active question. '
                     'Use selected_context_before to resolve a kept referent; preserve distinct process facts. '
                     'Select useful ranges via fact_checks.evidence or priority_passages; '
                     'exclude the rest with passage_exclusions: {passage_id: reason}. '
                     'Submit those decisions with your next action. No reread is needed.')
