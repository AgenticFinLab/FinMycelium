"""Explicit finish checks and source-lead accounting, independent of domain."""
from .sources import canonical_url


def lead_reviews(state, decisions=None):
    decisions = decisions or {}
    if not isinstance(decisions, dict) or any(not isinstance(v,str) or not v.strip() for v in decisions.values()):
        raise ValueError('source_lead_decisions maps source IDs or seed URLs to concrete reasons')
    rows = []
    for url in state.data['task'].get('seed_urls', []):
        sid, entry = next(((sid,e) for sid,e in state.data['sources'].items()
                           if e['url']==canonical_url(url)), (None,{}))
        read = any(r['version']==entry.get('version') and r['end']>r['start'] for r in entry.get('read_ranges', []))
        reason = decisions.get(sid) or decisions.get(url)
        status = 'read' if read else 'skipped' if reason else 'unresolved'
        rows.append(dict(url=url,source_id=sid,status=status,reason=reason))
    return rows


def finish_review(state, action):
    rows = lead_reviews(state, action.get('source_lead_decisions'))
    state.data['source_lead_review'] = rows
    gaps = list(action['gaps'])
    for row in rows:
        if row['status'] != 'read':
            gaps.append('Source lead '+row['url']+': '+(row['reason'] or 'not inspected; no skip reason supplied'))
    checks = action.get('fact_checks', [])
    if not isinstance(checks, list): raise ValueError('fact_checks must be a list')
    for check in checks:
        if (not isinstance(check,dict) or set(check) != {'question','status','source_ids','detail'}
                or check['status'] not in {'supported','planned','missing','conflicting'}
                or not isinstance(check['question'],str) or not check['question'].strip()
                or not isinstance(check['detail'],str) or not check['detail'].strip()
                or not isinstance(check['source_ids'],list)):
            raise ValueError('Each fact check needs question, status, inspected source_ids, detail')
        for sid in check['source_ids']:
            entry=state.data['sources'].get(sid,{}) if isinstance(sid,str) else {}
            if not any(r['version']==entry.get('version') and r['end']>r['start'] for r in entry.get('read_ranges',[])):
                raise ValueError('Fact checks must cite inspected source IDs')
        if check['status']=='supported' and not check['source_ids']:
            raise ValueError('A supported fact requires an inspected source')
        if check['status']!='supported':
            gaps.append(check['question']+': '+check['status']+'; '+check['detail'])
    state.data['fact_checks'] = checks
    if action['reason']=='supported' and (any(r['status']=='unresolved' for r in rows)
                                         or any(c['status']!='supported' for c in checks)):
        action['reason']='low_gain'
    action['gaps']=list(dict.fromkeys(gaps))
