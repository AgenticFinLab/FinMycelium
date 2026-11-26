"""Task-derived lexical topic retrieval over immutable original coordinates.

No model, embedding, network, or case-specific entity list. Saved policies remain
replayable; this policy is attached only when a new task has a positive entity cue.
"""
import re
from .budget import tokens, rank_blocks

POLICY = 'entity_attribute_windows_v2'
GENERIC = set('crisis investment investments financing acquisition event transaction process research company person stock stocks shares securities preferred common commitment commitments decision decisions'.split())
WEAK = GENERIC - {'preferred','common','commitment','commitments','decision','decisions'}
SYNONYMS = [set('redeem redeemed redemption repaid repayment'.split()),
            set('settle settled settlement deliver delivered delivery'.split()),
            set('negotiate negotiated negotiation renegotiate renegotiated'.split()),
            set('authorize authorized authorization approve approved approval'.split()),
            set('warrant warrants'.split()), set('floor floors storey storeys level levels'.split())]


def words(text):
    terms = set(tokens(text))
    for group in SYNONYMS:
        if terms & group:
            terms |= group
    return terms


def contains(text, phrase):
    # Whitespace folding handles PDF line wraps; Latin aliases need word boundaries.
    text, phrase = ' '.join(text.casefold().split()), ' '.join(phrase.casefold().split())
    return bool(re.search(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', text)) if phrase.isascii() else phrase in text


def plan_for(task):
    catalog, scope = task.get('catalog', {}), task.get('research_scope', {})
    title = catalog.get('event_name') or task.get('target_name', '')
    keywords = task.get('key_words', [])
    # Positive names already supplied by the caller, not names from exclusions/leads.
    entities = [k for k in keywords if contains(title, k)
                and (set(tokens(k))-GENERIC) and not k.isdigit()]
    if not entities:
        names = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b|\b[A-Z]{2,}\b', title)
        entities = [n for n in names if set(tokens(n))-GENERIC]
    # An event's focal person alone does not identify its business counterparty.
    if catalog.get('kind') == 'person_event':
        person = catalog.get('person_name', '') or (task.get('target_name','') if task.get('target_type')=='person' else '')
        entities = [e for e in entities if not contains(person, e)]
    facets = [x.strip(' .') for x in re.split(r',|;|，|；|\band\b', scope.get('include', '')) if x.strip(' .')]
    if not facets:
        facets = [k for k in keywords if k not in entities] or [task.get('query_text', title)]
    if task.get('target_type') == 'person':
        entities += [e.split()[0] for e in entities if len(e.split()) > 1]
    # Exclusions remain distinct constraints. Only explicit names gate candidates;
    # an excluded entity in a mixed paragraph never vetoes positive target evidence.
    excluded = re.findall(r'\b[A-Z]{2,}\b|\b[A-Z][a-z]+(?:\s+(?:of\s+)?[A-Z][a-z]+)+\b', re.sub(r'\b(?:Exclude|Excluded|Except)\b[: ]*', '', scope.get('exclude', '')))
    person = catalog.get('person_name', '') or (task.get('target_name','') if task.get('target_type')=='person' else '')
    if not person:
        match = re.search(r'(?:^|\n)Person:\s*([^\n(]+)', task.get('query_text', ''))
        person = match.group(1).strip() if match else ''
    return dict(policy=POLICY, focal_people=[person] if person else [], entities=list(dict.fromkeys(entities)), facets=list(dict.fromkeys(facets)),
                excluded_entities=excluded, exclusion_text=scope.get('exclude', ''),
                activity_period=scope.get('period', ''), publication_filter=False,
                basis='positive task names and scope; lexical cues, not factual attribution')


def noise(text):
    s = text.strip()
    return (not s or s.isdigit() or s.casefold() in {'home','sign in','log in','back to top','首页','登录'}
            or bool(re.match(r'^(?:you can unsubscribe|our weekly newsletter|subscribe to our newsletter)\b', s, re.I)))


def heading(block):
    s = block['text'].strip()
    return (block.get('heading_level') is not None or
            (len(s) < 85 and '\n' not in s and not re.search(r'[.!?。！？:：|\d]', s)
             and len(s.split()) <= 10))


def windows(document, indexes=None):
    result, section, table_headers = [], '', {}
    allowed = set(indexes) if indexes is not None else None
    for i, block in enumerate(document['blocks']):
        text = block['text']
        if heading(block): section = text.strip()
        if block.get('cells') and any(c.get('header') for c in block['cells']):
            table_headers.setdefault(block.get('table'), []).append(i)
        if allowed is not None and i not in allowed: continue
        if noise(text): continue
        # Sentence boundaries within each original paragraph. Table rows stay intact.
        cuts = [0] + ([] if block.get('cells') else [m.end() for m in re.finditer(r'(?<=[.!?。！？])\s+', text)]) + [len(text)]
        start = 0
        for j in range(1,len(cuts)):
            end = cuts[j]
            if end-start < 1200 and j < len(cuts)-1: continue
            if text[start:end].strip():
                result.append(dict(block=i,start=start,end=end,text=text[start:end],section=section,
                                   heading=heading(block), table=block.get('table'),
                                   headers=list(table_headers.get(block.get('table'), []))))
            start=end
    return result


def linked(w, plan):
    return w.get('entity_context', False) or any(contains(w['text'],e) or contains(w.get('section',''),e) for e in plan['entities'])


def excluded(w, plan):
    return any(contains(w['text'], e) for e in plan['excluded_entities']) and not linked(w, plan)


def continuation(text):
    return bool(re.match(r'^\s*(?:this|that|these|those|it|they|he|she|we|our|but|however|instead|in addition|as a result|这些|该|其|因此|他|她|我们)\b', text, re.I))


def neighbors(items, i, plan):
    chosen={i}
    for j in (i-1,i+1):
        if not 0<=j<len(items): continue
        a,b=items[i],items[j]
        if abs(a['block']-b['block'])>1 or a['section']!=b['section'] or excluded(b,plan): continue
        qualification = len(b['text']) <= 350 and bool(re.search(r'\b(?:not (?:reported|disclosed|known)|unknown|uncertain|undisclosed)\b', b['text'], re.I))
        legacy_continuation = plan.get('policy') != POLICY and ((j>i and continuation(b['text'])) or (j<i and continuation(a['text'])))
        if linked(b,plan) or qualification or legacy_continuation:
            chosen.add(j)
    return chosen


def rankings(items, plan, queries):
    if not items: return []
    def searchable(w):
        headers=' '.join(x['text'] for x in items if x['block'] in w['headers'])
        return w['text']+' '+w['section']+' '+headers
    search_items=[dict(w,text=searchable(w)) for w in items]
    raw=rank_blocks({'blocks':list(range(len(items)))},{'blocks':search_items},queries)
    result=[]
    entity_terms=set().union(*(words(e) for e in plan['entities'])) if plan['entities'] else set()
    for row in raw:
        attributes=words(row['query'])-entity_terms-WEAK
        attributes={t for t in attributes if not t.isdigit()}
        if not attributes:
            attributes=set().union(*(words(f) for f in plan['facets']))-entity_terms-WEAK if plan['facets'] else set()
        scores=[]
        for i,score in row['ranking']:
            w=items[i]
            if w['heading'] or excluded(w,plan): continue
            link=linked(w,plan)
            if not link and continuation(w['text']) and i and i in neighbors(items,i-1,plan):
                link=linked(items[i-1],plan)
            if plan['entities'] and not link: continue
            matched=words(searchable(w)) & attributes
            if attributes and not matched: continue
            # Generic vocabulary/numbers cannot independently qualify a passage.
            if not attributes and not (words(w['text'])-GENERIC-entity_terms): continue
            score *= (len(matched)/max(1,len(attributes))) if attributes else 1
            scores.append((i,score))
        if scores:
            floor=max(s for _,s in scores)*.3
            scores=[(i,s) for i,s in scores if s>=floor]
        result.append(dict(query=row['query'],ranking=sorted(scores,key=lambda p:(-p[1],p[0]))))
    return result


def queries_for(plan, query=None):
    entity=' '.join(plan['entities'])
    return ([query] if query else []) + [entity+' '+f for f in plan['facets']]


def select(document, plan, queries, indexes=None, priorities=()):
    items=windows(document,indexes)
    if plan.get('policy') == POLICY:
        from .topic_context import enrich
        enrich(document, items, plan)
    ranks=rankings(items,plan,queries)
    groups=[];seen=set()
    # Validated action anchors bypass lexical gates, including personal statements.
    for p in priorities:
        for i,w in enumerate(items):
            if w['block']==p['block'] and w['start']<p['end'] and w['end']>p['start']:
                groups.append(({i},'priority'));groups.append((neighbors(items,i,plan),'ranked'));seen.add(i)
    for n in range(max((len(r['ranking']) for r in ranks),default=0)):
        for r in ranks:
            if n<len(r['ranking']):
                i=r['ranking'][n][0]
                if i not in seen: groups.append((neighbors(items,i,plan),'ranked'));seen.add(i)
    if plan.get('policy') == POLICY:
        from .topic_context import protected
        for i,w in enumerate(items):
            if i not in seen and protected(w, plan):
                groups.insert(0, ({i}, 'ranked'))
                seen.add(i)
    # Keep source-local titles and dates when the opening explicitly names the target.
    # This metadata never turns a whole mixed report into target evidence.
    front=set()
    if items and linked(items[0],plan) and len(items[0]['text'])<=400:
        for i,w in enumerate(items[:4]):
            if len(w['text'])>400: break
            if linked(w,plan) or re.search(r'\b(?:19|20)\d{2}\b',w['text']): front.add(i)
    for group,_ in groups: group.update(front)
    # A selected table row carries its original header rows, never synthesized text.
    for group,_ in groups:
        headers={b for i in group for b in items[i]['headers']}
        group.update(i for i,w in enumerate(items) if w['block'] in headers)
    return items,groups


def marked_table_ranges(document, mark, marks, entities):
    """Trim a broad holdings table only with explicitly selected column context."""
    if mark.get('evidence_role') == 'contradiction' or not entities:
        return None
    text = document['blocks'][mark['block']]['text']
    rows, offset = [], 0
    for line in text.splitlines(keepends=True):
        end = offset+len(line)
        if mark['start'] <= offset and end <= mark['end'] and line.count('|') >= 3:
            rows.append(dict(block=mark['block'],start=offset,end=end,text=line))
        offset = end
    data = [r for r in rows if re.search(r'\d',r['text'])]
    target = [r for r in data if any(contains(r['text'],e) for e in entities)]
    if len(data) < 2 or not target or len(target) == len(data):
        return None
    # PDF-to-Markdown may label its first DATA row as a header. Numeric rows
    # never become column context merely because a separator follows them.
    headers = [r for r in rows if r['start'] < data[0]['start'] and not re.search(r'\d',r['text'])
               and re.search(r'[A-Za-z\u4e00-\u9fff]',r['text'])]
    for p in marks:
        if p['block'] not in (mark['block']-2,mark['block']-1):
            continue
        body = document['blocks'][p['block']]['text']
        if (p['start']==0 and p['end']==len(body) and len(body)<=120
                and not re.search(r'\d|[.!?。！？]',body)):
            headers.append(dict(block=p['block'],start=0,end=len(body),text=body))
    if not headers:
        return None  # Keep units/column meaning until the Agent marks its header.
    return sorted(headers+target,key=lambda r:(r['block'],r['start']))


def allocate(state, complete, budget):
    from .sources import SourceStore
    from .handoff import materialize_complete
    from .assembly_windows import render_windows, original_ranges
    if type(budget) is not int or budget <= 0:
        raise ValueError('Positive integer budget required')
    materialize_complete(state,complete)
    plan=complete.get('retrieval_plan') or plan_for(state.data['task'])
    store=SourceStore(state); entries={};docs={};queues={};picked={};sizes={}
    for e in complete['selected']:
        sid=e['source_id'];doc=store.document(sid,e['version'])
        marks=[p for p in complete.get('priority_passages',[]) if p['source_id']==sid and p['version']==e['version']]
        own=[q['query'] for q in complete.get('reading_queries',[]) if q['source_id']==sid and q['version']==e['version']]
        if plan.get('policy') == POLICY:
            # Lexical hits are reading candidates, not delivery decisions.
            # Metadata is already in the source header; body context must be marked.
            items,groups=[],[]
        else:
            items,groups=select(doc,plan,queries_for(plan)+own,e['blocks'],marks)
            groups=[(g,phase) for g,phase in groups if phase != 'priority']
        # Preserve the exact validated span even when a lexical/noise rule excluded it.
        for p in marks:
            if p['block'] in e['blocks']:
                item = dict(block=p['block'],start=p['start'],end=p['end'],text=doc['blocks'][p['block']]['text'][p['start']:p['end']],mark=p)
                if complete.get('evidence_policy') in {'located_delivery_v1','located_support_v2','question_flow_v3'}:
                    ranges = marked_table_ranges(doc,p,marks,plan['entities'])
                    if ranges:
                        item.update(ranges=ranges,text='\n'.join(r['text'] for r in ranges))
                items.append(item)
                if plan.get('policy') == POLICY:
                    groups.append(({len(items)-1},'priority'))
                else:
                    groups.insert(0,({len(items)-1},'priority'))
        # Merge coordinates before rendering; overlapping priority spans count once.
        docs[sid]=doc;entries[sid]=(e,items);queues[sid]=groups;picked[sid]=set();sizes[sid]=0
    def render(sid,chosen):
        e,items=entries[sid];ranges={}
        for i in chosen:
            for w in items[i].get('ranges',[items[i]]):
                ranges.setdefault(w['block'],[]).append((w['start'],w['end']))
        blocks=[]
        for b,rr in sorted(ranges.items()):
            merged=[]
            for a,z in sorted(rr):
                if merged and a<=merged[-1][1]: merged[-1]=(merged[-1][0],max(z,merged[-1][1]))
                else: merged.append((a,z))
            for a,z in merged: blocks.append(dict(text=docs[sid]['blocks'][b]['text'][a:z],original_range=dict(block=b,start=a,end=z)))
        view=dict(blocks=blocks)
        entry=dict(e,blocks=list(range(len(blocks))))
        return render_windows(entry,view,entry['blocks']) if blocks else '', original_ranges(view,entry['blocks'])
    remaining=budget
    coverage_decisions = None
    if plan.get('policy') == POLICY:
        from .coverage import choose
        support = [ref for check in complete.get('fact_checks', []) if check['status'] == 'supported'
                   for ref in check.get('evidence', []) if isinstance(ref,dict)
                   and ref.get('source_id') in check['source_ids']
                   ] if complete.get('evidence_policy') in {'located_support_v2','question_flow_v3'} else []
        remaining, coverage_decisions = choose(entries, render, picked, sizes, budget,
            deduplicate=complete.get('evidence_policy') in {'located_delivery_v1','located_support_v2','question_flow_v3'}, support=support)
    else:
        for phase in ('priority','ranked'):
            pending={sid:[g for g,p in queues[sid] if p==phase] for sid in queues}
            while any(pending.values()):
                for sid in sorted(pending):
                    if not pending[sid]:continue
                    group=pending[sid].pop(0);candidate=picked[sid]|group
                    content,_=render(sid,candidate);cost=len(content)-sizes[sid]
                    if cost<=remaining: picked[sid]=candidate;sizes[sid]=len(content);remaining-=cost
    samples=[];selected=[];omitted=[]
    for sid,(e,items) in entries.items():
        content,ranges=render(sid,picked[sid])
        if content:
            samples.append(dict(sample_id=sid+'-document',raw_data_id=sid,content=content))
            selected.append(dict(source_id=sid,version=e['version'],ranges=ranges,blocks=sorted({r['block'] for r in ranges}),material_chars=len(content)))
        missing=[]
        for b in e['blocks']:
            cursor=0
            for r in [r for r in ranges if r['block']==b]:
                if cursor<r['start']:missing.append(dict(block=b,start=cursor,end=r['start']))
                cursor=r['end']
            if cursor<len(docs[sid]['blocks'][b]['text']): missing.append(dict(block=b,start=cursor,end=len(docs[sid]['blocks'][b]['text'])))
        if missing: omitted.append(dict(source_id=sid,blocks=sorted({r['block'] for r in missing}),ranges=missing,omission_reason='unmarked_or_material_limit' if plan.get('policy') == POLICY else 'topic_or_material_limit',retained_in_complete=True))
    ranges_by_source = {e['source_id']: e['ranges'] for e in selected}
    decisions = []
    for p in complete.get('priority_passages', []):
        ranges = [(r['start'], r['end']) for r in ranges_by_source.get(p['source_id'], []) if r['block'] == p['block']]
        decisions.append(dict(passage=p, status='retained' if any(a <= p['start'] and b >= p['end'] for a, b in ranges) else 'material_limit'))
    if coverage_decisions is not None:
        decisions = coverage_decisions
    return dict(user_query=complete['user_query'],samples=samples),dict(selection_policy='marginal_evidence_v1' if coverage_decisions is not None else 'legacy',budget_policy=plan['policy'],retrieval_plan=plan,selected=selected,omitted=omitted,material_chars=sum(sizes.values()),max_material_chars=budget,unused_chars=remaining,priority_decisions=decisions)
