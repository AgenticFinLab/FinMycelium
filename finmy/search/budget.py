"""Material budget allocation: BM25 windows, source quotas and shared remaining space.

No model calls, network, source-specific rules, or paragraph splitting.
"""
import math
import re
from collections import Counter

from .sources import SourceStore

BUDGET_POLICY = 'balanced_source_windows_v1'


def fair_quotas(lengths, budget):
    """Max-min fair integer quotas; unused short-source space flows to longer ones."""
    if type(budget) is not int or budget<=0:
        raise ValueError('Budget must be a positive integer')
    if any(type(n) is not int or n<0 for n in lengths.values()):
        raise ValueError('Lengths must be nonnegative integers')
    remaining=budget;active=dict(lengths);quotas={}
    while active:
        share=remaining//len(active)
        short=[sid for sid,n in active.items() if n<=share]
        if short:
            for sid in short:
                quotas[sid]=active.pop(sid);remaining-=quotas[sid]
        else:
            # Tie breaks are source-ID based, not accidental source insertion order.
            for i,sid in enumerate(sorted(active)):
                quotas[sid]=share+(i<remaining%len(active))
            break
    return quotas


def render(entry, document, blocks, markers=False):
    if not blocks:return ''
    parts=[entry['header']];previous=None
    for i in blocks:
        if previous is not None:
            parts.append('\n\n')
            if markers and i>previous+1:parts.append(f'[... omitted original blocks {previous+1}:{i} ...]\n')
        elif markers and i>entry['blocks'][0]:
            parts.append(f'[... omitted original blocks before {i} ...]\n')
        parts.append(document['blocks'][i]['text']);previous=i
    if markers and blocks[-1]<entry['blocks'][-1]:
        parts.append(f'\n[... omitted original blocks after {blocks[-1]} ...]')
    return ''.join(parts)


def allocate_input(state, complete, budget, queries=()):
    from .handoff import materialize_complete
    full=materialize_complete(state,complete)
    quotas=fair_quotas({e['source_id']:e['material_chars'] for e in complete['selected']},budget)
    store=SourceStore(state);samples=[];selected=[];omitted=[];decisions={}
    for entry in complete['selected']:
        sid=entry['source_id'];document=store.document(sid,entry['version']);quota=quotas[sid]
        if entry['material_chars']<=quota:
            blocks=list(entry['blocks']);decisions[sid]={'mode':'full_document'}
        else:
            blocks,decisions[sid]=retrieved_blocks(entry,document,quota,queries)
        content=render(entry,document,blocks,markers=len(blocks)<len(entry['blocks']))
        if blocks:
            selected.append(dict(source_id=sid,version=entry['version'],blocks=blocks,material_chars=len(content),quota=quota))
            samples.append(dict(sample_id=sid+'-document',raw_data_id=sid,content=content))
        excluded=[i for i in entry['blocks'] if i not in blocks]
        if excluded:omitted.append(dict(source_id=sid,blocks=excluded,omission_reason='material_limit',retained_in_complete=True))
    result=dict(user_query=complete['user_query'],samples=samples)
    if complete['material_chars']<=budget:assert result==full
    record=dict(mode='sources',budget_policy='fair_source_quotas_bm25_windows',
                complete_id=complete['complete_id'],source_ids=complete['source_ids'],source_versions=complete['source_versions'],
                quotas=quotas,decisions=decisions,selected=selected,omitted=omitted,material_chars=sum(len(s['content']) for s in samples),
                max_material_chars=budget,unused_reason='Whole blocks may leave quota unused; no mid-sentence cuts')
    return result,record


STOPWORDS=set("a an the and or of to in on for at by with from as is are was were be been being it its this that these those has have had will would can could should may must not into over under about through during after before their them they our we you your which who what when where how why all any each other both than then also such only no do does did trace preserve source attribution unresolved differences".split())


def tokens(text):
    """Lightweight lexical cues; no language model, stemming or translation."""
    result=[]
    for part in re.findall(r'[a-z0-9]+|[\u3400-\u9fff]+',text.casefold()):
        if '\u3400'<=part[0]<='\u9fff':
            result.extend(part[i:i+2] for i in range(len(part)-1))
            if len(part)==1:result.append(part)
        elif part not in STOPWORDS:result.append(part)
    return result


def rank_blocks(entry,document,queries):
    indexes=entry['blocks'];bags=[Counter(tokens(document['blocks'][i]['text'])) for i in indexes]
    n=len(bags);avg=sum(sum(b.values()) for b in bags)/max(n,1) or 1
    df=Counter(t for bag in bags for t in bag)
    rankings=[];seen=set()
    for query in queries:
        terms=tuple(sorted(set(tokens(query))))
        if not terms or terms in seen:continue
        seen.add(terms);scores=[]
        for index,bag in zip(indexes,bags):
            score=0.;length=sum(bag.values())
            for term in terms:
                tf=bag[term]
                if tf:
                    idf=math.log(1+(n-df[term]+0.5)/(df[term]+0.5))
                    score+=idf*tf*2.5/(tf+1.5*(0.25+0.75*length/avg))
            if score>0:scores.append((index,score))
        rankings.append(dict(query=query,ranking=sorted(scores,key=lambda x:(-x[1],x[0]))))
    return rankings


def retrieved_blocks(entry,document,quota,queries):
    rankings=rank_blocks(entry,document,queries)
    picked=set();decisions=[];positions={i:k for k,i in enumerate(entry['blocks'])}
    def fits(candidate):
        return len(render(entry,document,sorted(candidate),markers=len(candidate)<len(entry['blocks'])))<=quota
    if not any(r['ranking'] for r in rankings):
        for i in entry['blocks']:
            if not fits(picked|{i}):break
            picked.add(i)
        return sorted(picked),dict(mode='no_lexical_match_prefix',anchors=[])
    cursors=[0]*len(rankings)
    while True:
        added=False
        for q,r in enumerate(rankings):
            while cursors[q]<len(r['ranking']):
                anchor,score=r['ranking'][cursors[q]];cursors[q]+=1
                if anchor in picked:continue
                pos=positions[anchor]
                window=set(entry['blocks'][max(0,pos-1):pos+2])
                candidate=picked|window;kind='anchor_and_neighbors'
                if not fits(candidate):candidate=picked|{anchor};kind='anchor_only'
                if fits(candidate):
                    picked=candidate;added=True
                    decisions.append(dict(query=r['query'],anchor=anchor,score=round(score,6),kind=kind))
                    break
        if not added:break
    # Use remaining quota to recover nearby original context, without synthesizing text.
    expanded=[]
    if picked:
        while True:
            available=sorted((i for i in entry['blocks'] if i not in picked),
                             key=lambda i:(min(abs(positions[i]-positions[j]) for j in picked),i))
            next_block=next((i for i in available if fits(picked|{i})),None)
            if next_block is None:break
            picked.add(next_block);expanded.append(next_block)
    return sorted(picked),dict(mode='bm25_round_robin_windows',anchors=decisions,context_expansion=expanded,
                              query_count=len(rankings),k1=1.5,b=0.75)


def shared_input(state,complete,budget,queries):
    if type(budget) is not int or budget<=0:raise ValueError('Positive integer budget required')
    if complete['material_chars']<=budget:
        return allocate_input(state,complete,budget,queries)
    _,base=allocate_input(state,complete,max(1,budget//2),queries)
    entries={e['source_id']:e for e in complete['selected']}
    store=SourceStore(state)
    docs={sid:store.document(sid,e['version']) for sid,e in entries.items()}
    picked={sid:set() for sid in entries}
    for e in base['selected']:picked[e['source_id']]=set(e['blocks'])
    def text(sid,blocks):
        return render(entries[sid],docs[sid],sorted(blocks),markers=len(blocks)<len(entries[sid]['blocks']))
    sizes={sid:len(text(sid,picked[sid])) for sid in entries}
    remaining=budget-sum(sizes.values());actions=[]
    def window(sid,index):
        blocks=entries[sid]['blocks'];p=blocks.index(index)
        return set(blocks[max(0,p-1):p+2])
    repairs={sid:[window(sid,a['anchor']) for a in base['decisions'].get(sid,{}).get('anchors',[])] for sid in entries}
    additions={}
    for sid,e in entries.items():
        ranks=rank_blocks(e,docs[sid],queries);seq=[];seen=set()
        for rank in range(max((len(r['ranking']) for r in ranks),default=0)):
            for r in ranks:
                if rank<len(r['ranking']):
                    anchor=r['ranking'][rank][0]
                    if anchor not in seen:seq.append(window(sid,anchor));seen.add(anchor)
        additions[sid]=seq
    for phase,queues in [('complete_anchor_context',repairs),('additional_ranked_windows',additions)]:
        while True:
            changed=False
            for sid in sorted(entries):
                while queues[sid]:
                    candidate=picked[sid]|queues[sid].pop(0)
                    if candidate==picked[sid]:continue
                    length=len(text(sid,candidate));cost=length-sizes[sid]
                    if cost>remaining:continue
                    actions.append(dict(phase=phase,source_id=sid,added_blocks=sorted(candidate-picked[sid]),incremental_chars=cost))
                    picked[sid]=candidate;sizes[sid]=length;remaining-=cost;changed=True;break
            if not changed:break
    selected=[];samples=[];omitted=[]
    for sid,e in entries.items():
        if picked[sid]:
            content=text(sid,picked[sid]);samples.append(dict(sample_id=sid+'-document',raw_data_id=sid,content=content))
            selected.append(dict(source_id=sid,version=e['version'],blocks=sorted(picked[sid]),material_chars=len(content)))
        excluded=sorted(set(e['blocks'])-picked[sid])
        if excluded:omitted.append(dict(source_id=sid,blocks=excluded,retained_in_complete=True))
    return dict(user_query=complete['user_query'],samples=samples),dict(budget_policy=BUDGET_POLICY,complete_id=complete['complete_id'],selected=selected,omitted=omitted,
        material_chars=sum(sizes.values()),max_material_chars=budget,base_fraction=0.5,base_quotas=base['quotas'],base_decisions=base['decisions'],pool_actions=actions,unused_chars=remaining)
