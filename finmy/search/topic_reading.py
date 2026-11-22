"""Located topic reads, sharing the existing read/replay accounting."""
from .topic import select


def read_topic(document, query, limit, read_ranges, plan, *, replay=True):
    from .reading import unread_ranges
    current=[r for r in read_ranges if r['version']==document['version']]
    items,groups=select(document,plan,[query])
    chosen=[];remaining=limit
    for group,_ in groups:
        for i in sorted(group):
            w=items[i]
            for start,end in unread_ranges(w['block'],w['start'],w['end'],current+chosen):
                # Complete sentences/rows; explicit cursor reads handle large rows.
                if end-start>remaining: continue
                chosen.append(dict(block=w['block'],start=start,end=end));remaining-=end-start
    unread=any(list(unread_ranges(items[i]['block'],items[i]['start'],items[i]['end'],current)) for g,_ in groups for i in g)
    status='matched' if chosen else 'over_limit' if unread else 'already_read' if groups else 'no_match'
    replayed=False
    if not chosen and groups and replay and current:
        old, _=read_topic(document,query,limit,[],plan,replay=False)
        for span in old:
            for r in current:
                if r['block']!=span['block']:continue
                a,z=max(r['start'],span['start']),min(r['end'],span['end'])
                for start,end in unread_ranges(r['block'],a,z,chosen):
                    chosen.append(dict(block=r['block'],start=start,end=end))
        replayed=bool(chosen)
    spans=[dict(r,text=document['blocks'][r['block']]['text'][r['start']:r['end']],
                locator={k:v for k,v in document['blocks'][r['block']].items() if k!='text'})
           for r in sorted(chosen,key=lambda r:(r['block'],r['start']))]
    reading=dict(mode='topic_query',query=query,match_status=status,replayed=replayed,
                 matching_windows=len(groups),note='Entity and attribute lexical cues; explicit cursor reads remain available.')
    if spans:reading['preview_location']={k:spans[0][k] for k in ('block','start','end')}
    return spans,reading
