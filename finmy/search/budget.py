"""Material budget allocation: BM25 windows, source quotas and shared remaining space.

No model calls, network or case-specific rules. Original storage is immutable.
"""
import math
import re
from collections import Counter

from .sources import SourceStore

LEGACY_POLICY = 'balanced_source_windows_v1'
FIXED_POLICY = 'balanced_source_windows_v2'
ADAPTIVE_POLICY = 'balanced_source_windows_v3'
PRIORITY_POLICY = 'evidence_priority_windows_v1'
SOURCE_QUERY_POLICY = 'evidence_priority_windows_v2'
CONTEXT_POLICY = 'evidence_priority_windows_v3'
QUERY_COVERAGE_POLICY = 'evidence_priority_windows_v4'
BUDGET_POLICY = CONTEXT_POLICY
# Replay-only compatibility for saved window manifests; new handoffs use BUDGET_POLICY.
SAVED_WINDOW_POLICY = 'evidence_priority_windows_v5'
ASSEMBLY_THRESHOLDS = (0.5, 0.4, 0.3)
MIN_RELATIVE_SCORE = 0.4


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
    if document.get('temporary_windows'):
        from .assembly_windows import render_windows
        return render_windows(entry, document, blocks)
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


def allocate_input(state, complete, budget, queries=(), *, focused=False, min_relative_score=None, source_queries=None, documents=None, preserve_intro=False):
    from .handoff import materialize_complete
    full=materialize_complete(state,complete) if documents is None else None
    quotas=fair_quotas({e['source_id']:e['material_chars'] for e in complete['selected']},budget)
    store=SourceStore(state);samples=[];selected=[];omitted=[];decisions={}
    for entry in complete['selected']:
        sid=entry['source_id'];quota=quotas[sid]
        document=documents[sid] if documents is not None else store.document(sid,entry['version'])
        if entry['material_chars']<=quota:
            blocks=list(entry['blocks']);decisions[sid]={'mode':'full_document'}
        else:
            selected_queries=source_queries[sid] if source_queries is not None else queries
            blocks,decisions[sid]=retrieved_blocks(entry,document,quota,selected_queries,focused=focused,min_relative_score=min_relative_score,preserve_intro=preserve_intro)
        content=render(entry,document,blocks,markers=len(blocks)<len(entry['blocks']))
        if blocks:
            selected.append(dict(source_id=sid,version=entry['version'],blocks=blocks,material_chars=len(content),quota=quota))
            samples.append(dict(sample_id=sid+'-document',raw_data_id=sid,content=content))
        excluded=[i for i in entry['blocks'] if i not in blocks]
        if excluded:omitted.append(dict(source_id=sid,blocks=excluded,omission_reason='material_limit',retained_in_complete=True))
    result=dict(user_query=complete['user_query'],samples=samples)
    if complete['material_chars']<=budget and full is not None:assert result==full
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


def rank_blocks(entry,document,queries, *, focused=False, min_relative_score=None, query_coverage=False):
    indexes=entry['blocks'];bags=[Counter(tokens(document['blocks'][i]['text'])) for i in indexes]
    n=len(bags);avg=sum(sum(b.values()) for b in bags)/max(n,1) or 1
    df=Counter(t for bag in bags for t in bag)
    rankings=[];seen=set()
    for query in queries:
        terms=tuple(sorted(set(tokens(query))))
        if not terms or terms in seen:continue
        seen.add(terms);scores=[]
        weights={t:math.log(1+(n-df[t]+0.5)/(df[t]+0.5)) for t in terms if df[t]}
        total_weight=sum(weights.values())
        for index,bag in zip(indexes,bags):
            score=0.;length=sum(bag.values())
            for term in terms:
                tf=bag[term]
                if tf:
                    idf=math.log(1+(n-df[term]+0.5)/(df[term]+0.5))
                    score+=idf*tf*2.5/(tf+1.5*(0.25+0.75*length/avg))
            if score>0:
                if query_coverage:
                    # A match on generic report vocabulary alone should not
                    # outrank a paragraph covering the specific reading question.
                    # This is a soft lexical weight, never a semantic exclusion.
                    coverage=sum(w for t,w in weights.items() if bag[t])/total_weight
                    score*=coverage * coverage
                scores.append((index,score))
        if focused and scores:
            # Relative within each document/query, not a cross-document truth score.
            floor = max(score for _,score in scores) * (MIN_RELATIVE_SCORE if min_relative_score is None else min_relative_score)
            scores = [(index,score) for index,score in scores if score >= floor]
        ranking=sorted(scores,key=lambda x:(-x[1],x[0]))
        rankings.append(dict(query=query,ranking=ranking))
    return rankings


def retrieved_blocks(entry,document,quota,queries, *, focused=False, min_relative_score=None, preserve_intro=False):
    rankings=rank_blocks(entry,document,queries,focused=focused,min_relative_score=min_relative_score)
    picked=set();decisions=[];positions={i:k for k,i in enumerate(entry['blocks'])}
    def fits(candidate):
        return len(render(entry,document,sorted(candidate),markers=len(candidate)<len(entry['blocks'])))<=quota
    if not any(r['ranking'] for r in rankings):
        for i in entry['blocks']:
            if not fits(picked|{i}):break
            picked.add(i)
            if focused:break  # Bounded preview when lexical evidence is absent.
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
    # Keep a short source introduction when it fits the same core quota.
    # Broad scope words must not pull unrelated sections into this source.
    intro = entry['blocks'][0] if entry['blocks'] else None
    if preserve_intro and intro is not None and len(document['blocks'][intro]['text']) <= 600 and fits(picked|{intro}):
        picked.add(intro)
    # Use remaining quota to recover nearby original context, without synthesizing text.
    expanded=[]
    if picked and not focused:
        while True:
            available=sorted((i for i in entry['blocks'] if i not in picked),
                             key=lambda i:(min(abs(positions[i]-positions[j]) for j in picked),i))
            next_block=next((i for i in available if fits(picked|{i})),None)
            if next_block is None:break
            picked.add(next_block);expanded.append(next_block)
    return sorted(picked),dict(mode='bm25_round_robin_windows',anchors=decisions,context_expansion=expanded,
                              query_count=len(rankings),k1=1.5,b=0.75)


def source_query_plan(state,complete, *, source_core=False):
    """Bind inspected questions to their saved source/version; freeze the fallback."""
    fallback=complete.get('scope_queries')
    if fallback is None:
        # Explicitly upgrading an old manifest uses its saved research task,
        # never new search history. Ordinary replay still selects the old policy.
        from .handoff import research_scope_queries
        fallback=research_scope_queries(state.data['task'])
    plan={}
    for entry in complete['selected']:
        sid,version=entry['source_id'],entry['version']
        own=list(dict.fromkeys(q['query'].strip() for q in complete.get('reading_queries',[])
            if q.get('source_id')==sid and q.get('version')==version
            and isinstance(q.get('query'),str) and q['query'].strip()))
        plan[sid]=dict(version=version,basis='source_reading' if own else 'research_scope',
                       queries=own or list(fallback),
                       core_queries=(own or list(fallback)) if source_core else list(dict.fromkeys(own+list(fallback))))
    return plan


def refers_to_previous(text):
    """A bounded cue for missing antecedents; it never certifies interpretation."""
    lead = text.strip()[:180]
    return bool(re.match(r'(?:This|That|These|Those|It|They|He|She|But|However|Instead)\b', lead, re.I)
                or re.search(r'\b(?:all of this|at that point|as a result|in response)\b', lead, re.I)
                or re.match(r'(?:这|那|他|她|它|但|然而|因此|对此)', lead))


def shared_input(state,complete,budget,queries, *, policy=LEGACY_POLICY):
    if policy == SAVED_WINDOW_POLICY and complete['material_chars'] > budget:
        from .assembly_windows import allocate_windows
        return allocate_windows(state, complete, budget, queries, policy=policy)
    return _shared_input(state, complete, budget, queries, policy=policy)


def _shared_input(state,complete,budget,queries, *, policy, documents=None):
    if policy not in {LEGACY_POLICY, FIXED_POLICY, ADAPTIVE_POLICY, PRIORITY_POLICY, SOURCE_QUERY_POLICY, CONTEXT_POLICY, QUERY_COVERAGE_POLICY, SAVED_WINDOW_POLICY}:raise ValueError('Unknown saved budget policy')
    focused = policy != LEGACY_POLICY
    priority = policy in {PRIORITY_POLICY,SOURCE_QUERY_POLICY,CONTEXT_POLICY,QUERY_COVERAGE_POLICY,SAVED_WINDOW_POLICY}
    query_coverage = policy in {QUERY_COVERAGE_POLICY,SAVED_WINDOW_POLICY}
    context_retention = policy in {CONTEXT_POLICY,QUERY_COVERAGE_POLICY,SAVED_WINDOW_POLICY}
    progressive = priority or policy == ADAPTIVE_POLICY
    plan=source_query_plan(state,complete,source_core=policy==SAVED_WINDOW_POLICY) if policy in {SOURCE_QUERY_POLICY,CONTEXT_POLICY,QUERY_COVERAGE_POLICY,SAVED_WINDOW_POLICY} else None
    core_queries={sid:p['core_queries'] for sid,p in plan.items()} if plan is not None else None
    thresholds = ASSEMBLY_THRESHOLDS if progressive else (0.5,)
    initial_threshold = thresholds[0]
    if type(budget) is not int or budget<=0:raise ValueError('Positive integer budget required')
    if complete['material_chars']<=budget:
        payload, record = allocate_input(state,complete,budget,queries,focused=focused,min_relative_score=initial_threshold,
                                         source_queries=core_queries,documents=documents,preserve_intro=policy==SAVED_WINDOW_POLICY)
        if progressive:
            record.update(thresholds=list(thresholds), threshold_stages=[], full_material_retained=True)
        if priority:
            record['priority_decisions'] = [dict(passage=p,status='retained')
                                            for p in complete.get('priority_passages',[])]
        if plan is not None:record['query_plan']=plan
        return payload, record
    _,base=allocate_input(state,complete,max(1,budget//2),queries,focused=focused,min_relative_score=initial_threshold,
                         source_queries=core_queries,documents=documents,preserve_intro=policy==SAVED_WINDOW_POLICY)
    entries={e['source_id']:e for e in complete['selected']}
    store=SourceStore(state)
    docs=documents if documents is not None else {sid:store.document(sid,e['version']) for sid,e in entries.items()}
    picked={sid:set() for sid in entries}
    for e in base['selected']:picked[e['source_id']]=set(e['blocks'])
    compact_sources=[]
    if focused:
        # Preserve a complete compact source when it fits its final fair share.
        # Long sources use bounded windows; their spare space is not a fill target.
        final_quotas=fair_quotas({sid:e['material_chars'] for sid,e in entries.items()},budget)
        for sid,e in entries.items():
            if e['material_chars']<=final_quotas[sid]:
                picked[sid]=set(e['blocks']);compact_sources.append(sid)
    def text(sid,blocks):
        return render(entries[sid],docs[sid],sorted(blocks),markers=len(blocks)<len(entries[sid]['blocks']))
    sizes={sid:len(text(sid,picked[sid])) for sid in entries}
    remaining=budget-sum(sizes.values());actions=[]
    def window(sid,index,radius=1):
        blocks=entries[sid]['blocks'];p=blocks.index(index)
        start=max(0,p-radius)
        if context_retention and radius==1 and start and refers_to_previous(docs[sid]['blocks'][blocks[start]]['text']):
            start-=1  # One antecedent paragraph, not recursive document expansion.
        return set(blocks[start:p+radius+1])
    repairs={sid:[window(sid,a['anchor']) for a in base['decisions'].get(sid,{}).get('anchors',[])] for sid in entries}
    def additions(threshold):
        queues = {}
        for sid,e in entries.items():
            selected_queries=plan[sid]['queries'] if plan is not None else queries
            ranks=rank_blocks(e,docs[sid],selected_queries,focused=focused,min_relative_score=threshold,query_coverage=query_coverage)
            seq=[];seen=set()
            for rank in range(max((len(r['ranking']) for r in ranks),default=0)):
                for r in ranks:
                    if rank<len(r['ranking']):
                        anchor=r['ranking'][rank][0]
                        if anchor not in seen:seq.append(window(sid,anchor));seen.add(anchor)
            queues[sid]=seq
        return queues

    def consume(phase, queues, threshold):
        nonlocal remaining
        while True:
            changed=False
            for sid in sorted(entries):
                while queues[sid]:
                    candidate=picked[sid]|queues[sid].pop(0)
                    if candidate==picked[sid]:continue
                    length=len(text(sid,candidate));cost=length-sizes[sid]
                    if cost>remaining:continue
                    actions.append(dict(phase=phase,source_id=sid,added_blocks=sorted(candidate-picked[sid]),
                                        incremental_chars=cost,threshold=threshold))
                    picked[sid]=candidate;sizes[sid]=length;remaining-=cost;changed=True;break
            if not changed:break

    priority_decisions=[]
    if priority:
        for passage in complete.get('priority_passages',[]):
            sid = passage['source_id'];anchor = passage['block']
            if sid not in entries or passage['version']!=entries[sid]['version'] or anchor not in entries[sid]['blocks']:
                priority_decisions.append(dict(passage=passage,status='unavailable'))
                continue
            # Source core coverage remains protected. Priority hints add whole
            # original paragraphs and, where possible, their neighboring context.
            status='material_limit'
            candidates=[(picked[sid]|window(sid,anchor),'with_context'),
                        (picked[sid]|{anchor},'paragraph_only')]
            if context_retention:
                candidates.insert(0,(picked[sid]|window(sid,anchor,radius=2),'with_context'))
            for candidate,kind in candidates:
                length=len(text(sid,candidate));cost=length-sizes[sid]
                if cost>remaining:continue
                actions.append(dict(phase='priority_passage',source_id=sid,
                                    added_blocks=sorted(candidate-picked[sid]),incremental_chars=cost))
                picked[sid]=candidate;sizes[sid]=length;remaining-=cost
                status=kind
                break
            priority_decisions.append(dict(passage=passage,status=status))
    stages=[]
    consume('complete_anchor_context',repairs,initial_threshold)
    for threshold in thresholds:
        # Lower thresholds append to the existing selection, never reallocate it.
        consume('additional_ranked_windows',additions(threshold),threshold)
        stages.append(dict(threshold=threshold,material_chars=sum(sizes.values()),
                           selected_blocks={sid:sorted(blocks) for sid,blocks in picked.items()}))
    selected=[];samples=[];omitted=[]
    for sid,e in entries.items():
        if picked[sid]:
            content=text(sid,picked[sid]);samples.append(dict(sample_id=sid+'-document',raw_data_id=sid,content=content))
            selected.append(dict(source_id=sid,version=e['version'],blocks=sorted(picked[sid]),material_chars=len(content)))
        excluded=sorted(set(e['blocks'])-picked[sid])
        if excluded:
            if focused:
                selected_queries=plan[sid]['queries'] if plan is not None else queries
                ranks=rank_blocks(e,docs[sid],selected_queries,focused=True,min_relative_score=thresholds[-1],query_coverage=query_coverage)
                eligible=set().union(*(window(sid,index) for r in ranks for index,_ in r['ranking']))
                if not eligible:eligible=set(e['blocks'][:1])
                for reason,blocks in [('material_limit', sorted(set(excluded)&eligible)),
                                      ('relevance_selection', sorted(set(excluded)-eligible))]:
                    if blocks:omitted.append(dict(source_id=sid,blocks=blocks,retained_in_complete=True,omission_reason=reason))
            else:
                omitted.append(dict(source_id=sid,blocks=excluded,retained_in_complete=True))
    result = dict(budget_policy=policy,complete_id=complete['complete_id'],selected=selected,omitted=omitted,
        material_chars=sum(sizes.values()),max_material_chars=budget,base_fraction=0.5,base_quotas=base['quotas'],base_decisions=base['decisions'],pool_actions=actions,unused_chars=remaining)
    if focused:
        result.update(min_relative_score=thresholds[-1],context_neighbors=1,
                      compact_source_ids=sorted(compact_sources),
                      unused_reason='Budget is a ceiling; no expansion beyond eligible original-text windows')
    if progressive:
        result.update(thresholds=list(thresholds),threshold_stages=stages,full_material_retained=False)
    if plan is not None:result['query_plan']=plan
    if query_coverage:
        result['ranking_policy']='bm25_idf_query_coverage_shared'
    if context_retention:
        result['context_policy']=dict(priority_neighbors=2, ordinary_neighbors=1,
                                      preceding_antecedent_extra=1, recursive=False)
    if priority:
        # A passage that did not fit early may have been included by later passes.
        for item in priority_decisions:
            p=item['passage'];sid=p['source_id']
            if item['status']=='material_limit' and p['block'] in picked.get(sid,set()):
                item['status']='retained'
        result['priority_decisions']=priority_decisions
    return dict(user_query=complete['user_query'],samples=samples),result
