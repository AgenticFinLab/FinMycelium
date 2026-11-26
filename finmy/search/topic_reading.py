"""Located topic reads, sharing the existing read/replay accounting."""
from .topic import select, POLICY, rankings


def read_topic(document, query, limit, read_ranges, plan, *, replay=True):
    from .reading import unread_ranges
    current=[r for r in read_ranges if r['version']==document['version']]
    items,groups=select(document,plan,[query])
    hints = []
    if plan.get('policy') == POLICY:
        # Rank current-question hits before nearby context. A large matched window
        # returns a bounded exact span plus a continuation cursor, not an empty read.
        matched = rankings(items,plan,[query])
        order = [i for row in matched for i,_ in row['ranking']]
        context = [i for group,_ in groups for i in sorted(group)]
        groups = [({i}, 'ranked') for i in dict.fromkeys(order+context)]
        if not groups:
            from .budget import rank_blocks
            raw = rank_blocks({'blocks':list(range(len(document['blocks'])))}, document, [query])
            for row in raw:
                for block,score in row['ranking'][:3]:
                    if score > 0: hints.append(dict(block=block, offset=0,
                        note='Lexical candidate only; entity/attribute match unconfirmed.'))
    chosen=[];remaining=limit
    for group,_ in groups:
        for i in sorted(group):
            w=items[i]
            for start,end in unread_ranges(w['block'],w['start'],w['end'],current+chosen):
                # Complete sentences/rows; explicit cursor reads handle large rows.
                if end-start>remaining:
                    if plan.get('policy') != POLICY: continue
                    if len(hints)<3:
                        hints.append(dict(block=w['block'],offset=start+remaining,
                                          note='Continue the matched original window.'))
                    if remaining <= 0: continue
                    end=start+remaining
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
                 matching_windows=len(groups),candidate_locations=hints,note='Entity and attribute lexical cues; explicit cursor reads remain available.')
    if spans:reading['preview_location']={k:spans[0][k] for k in ('block','start','end')}
    return spans,reading
