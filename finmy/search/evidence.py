"""Located selection advice from the Search Agent, separate from source evidence."""
from .sources import SourceStore


def source_pool(state, proposed, exclusions=None):
    """Account for every inspected current version before character allocation.

    An inspected body is a candidate, not verified evidence. Explicit reasoned
    exclusions win; merely forgetting an ID cannot silently discard its body.
    """
    if not isinstance(proposed, list) or any(not isinstance(s, str) for s in proposed):
        raise ValueError('Finish needs source_ids: a list of inspected source IDs')
    exclusions = {} if exclusions is None else exclusions
    if (not isinstance(exclusions, dict)
            or any(not isinstance(sid, str) or not isinstance(reason, str)
                   or not reason.strip() or len(reason) > 300 for sid, reason in exclusions.items())):
        raise ValueError('source_exclusions must map inspected source IDs to brief nonempty reasons (up to 300 characters)')
    sources = state.data['sources']
    inspected = {sid:entry['version'] for sid,entry in sources.items()
                 if entry.get('version') and entry.get('status') in {'success','partial'}
                 and any(r['version']==entry['version'] and r['end']>r['start']
                         for r in entry.get('read_ranges',[]))}
    for sid in set(proposed) | set(exclusions):
        if sid not in sources:
            raise ValueError('Unknown source ID: ' + sid)
        if sid not in inspected:
            raise ValueError('Inspect this source before deciding retention: ' + sid)
    if set(proposed) & set(exclusions):
        raise ValueError('A source cannot appear in both source_ids and source_exclusions')
    proposed = list(dict.fromkeys(proposed))
    recovered = sorted(set(inspected) - set(proposed) - set(exclusions))
    retained = proposed + recovered
    review = dict(policy='inspected_source_pool_v1', proposed_source_ids=proposed,
                  automatically_retained=recovered, exclusions=dict(exclusions),
                  inspected_versions=inspected,
                  note='Inspected candidates, not factual verification; cleanup and character allocation follow')
    return retained, review


def validate_passage(state, item, *, versions=None):
    if not isinstance(item,dict) or set(item)-{'source_id','version','block','start','end','reason'}:
        raise ValueError('Use source_id, block, start, end and a short reason')
    sid = item.get('source_id')
    if not isinstance(sid,str) or sid not in state.data['sources']:
        raise ValueError('Unknown passage source')
    entry = state.data['sources'][sid]
    version = (versions or {}).get(sid) or entry.get('version')
    if not version or item.get('version',version) != version:
        raise ValueError('Passage source version differs')
    block,start,end = (item.get(k) for k in ('block','start','end'))
    if any(type(v) is not int for v in (block,start,end)):
        raise ValueError('Passage block/start/end must be integers copied from a read')
    doc = SourceStore(state).document(sid,version)
    if not 0<=block<len(doc['blocks']) or not 0<=start<end<=len(doc['blocks'][block]['text']):
        raise ValueError('Passage lies outside the saved original')
    covered = start
    for r in sorted(entry.get('read_ranges',[]),key=lambda r:r['start']):
        if r['version']==version and r['block']==block and r['start']<=covered:
            covered = max(covered,r['end'])
    if covered<end:
        raise ValueError('Priority passage was not inspected in this version')
    reason = item.get('reason','')
    if not isinstance(reason,str) or len(reason)>300:
        raise ValueError('Passage reason must be text of at most 300 characters')
    return dict(source_id=sid,version=version,block=block,start=start,end=end,reason=reason)


def record_passages(state, items):
    """Reject individual bad annotations without rejecting a valid tool action."""
    accepted, rejected = [], []
    if not isinstance(items,list):
        rejected.append(dict(index=None,reason='priority_passages must be a list'))
    else:
        for index,item in enumerate(items):
            try:
                accepted.append(validate_passage(state,item))
            except (ValueError,KeyError,IndexError,TypeError,OSError) as exc:
                rejected.append(dict(index=index,reason=str(exc) if isinstance(exc,ValueError)
                                     else 'Passage cannot be resolved in the saved source'))
    saved = state.data.setdefault('priority_passages',[])
    for item in accepted:
        identity = tuple(item[k] for k in ('source_id','version','block','start','end'))
        old = next((x for x in saved if tuple(x[k] for k in
                    ('source_id','version','block','start','end'))==identity),None)
        if old is None:
            saved.append(item)
        else:
            old['reason'] = item['reason']
    report = dict(accepted=len(accepted),rejected=rejected)
    state.data['priority_feedback'] = report
    state.trace(dict(action='priority_passages',**report))
    return report


def retained_passages(state, versions):
    """Freeze only advice applicable to the explicitly retained source versions."""
    accepted, omitted = [], []
    for item in state.data.get('priority_passages',[]):
        try:
            if item['source_id'] not in versions:
                raise ValueError('Source not retained by final selection')
            accepted.append(validate_passage(state,item,versions=versions))
        except (ValueError,KeyError,IndexError,TypeError,OSError) as exc:
            omitted.append(dict(passage=item,reason=str(exc) if isinstance(exc,ValueError)
                                else 'Saved annotation is unavailable'))
    return accepted,omitted
