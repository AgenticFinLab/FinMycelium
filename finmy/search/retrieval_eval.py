"""Compare retrieval stages against fixed original-range labels, without web search."""
import argparse
import json
from dataclasses import asdict
from pathlib import Path
from .state import SearchConfig, SearchState, digest, write_json
from .sources import SourceStore
from .reading import targeted_spans
from .hybrid import MODES, RetrievalSession, read_retrieved
from .eval_metrics import merge_ranges


def scores(spans, expected):
    total = hit = 0
    for block in {r['block'] for r in expected}:
        gold = merge_ranges((r['start'], r['end']) for r in expected if r['block'] == block)
        retrieved = merge_ranges((r['start'], r['end']) for r in spans if r['block'] == block)
        for a,b in gold:
            total += b-a
            hit += sum(max(0,min(b,y)-max(a,x)) for x,y in retrieved)
    return dict(expected_chars=total, retained_chars=hit, evidence_char_recall=hit/total if total else None,
                delivered_chars=sum(s['end']-s['start'] for s in spans))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True, type=Path)
    parser.add_argument('--cases', required=True, type=Path)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--modes', nargs='+', choices=sorted(MODES), default=['topic','bm25'])
    parser.add_argument('--output', required=True, type=Path)
    args=parser.parse_args()
    original=json.loads((args.run_dir/'run.json').read_text())
    task_root=args.run_dir.parent.parent
    source=SearchState(task_root.parent,task_root.name,run_id=args.run_dir.name)
    store=SourceStore(source)
    cases=json.loads(args.cases.read_text())
    if not isinstance(cases,list) or not cases:
        raise ValueError('Provide a nonempty fixed case list')
    prepared=[]
    for case in cases:
        if not isinstance(case.get('query'),str) or not case['query'].strip():
            raise ValueError('Each case needs a query')
        doc=store.document(case['source_id'],case['version'])
        ranges=case.get('expected_ranges')
        if not isinstance(ranges,list) or not ranges:
            raise ValueError('Provide independently reviewed expected_ranges for each case')
        for r in ranges:
            if (any(type(r.get(k)) is not int for k in ('block','start','end'))
                    or not 0<=r['block']<len(doc['blocks'])
                    or not 0<=r['start']<r['end']<=len(doc['blocks'][r['block']]['text'])):
                raise ValueError('Expected range outside original')
        prepared.append((case,doc))
    base=asdict(source.config)
    if args.config:
        base.update(json.loads(args.config.read_text()))
    outputs=[]; args.output.parent.mkdir(parents=True,exist_ok=True)
    for mode in args.modes:
        values=dict(base,retrieval=dict(base.get('retrieval',{}),mode=mode))
        config=SearchConfig(**values)
        identity=digest(dict(mode=mode,config=values,cases=cases,task=original['task'],
                             code={p.name:digest(p.read_bytes()) for p in Path(__file__).parent.glob('*.py')}))[:16]
        trial=SearchState(args.output.parent/(args.output.stem+'-runs'), 'comparison-'+identity,
                          task=original['task'], config=config)
        session=RetrievalSession(trial); rows=[]
        for case,doc in prepared:
            if mode=='topic':
                spans,reading=targeted_spans(doc,case['query'],config.max_read_chars,[],
                    topic_plan=original.get('retrieval_plan'))
            else:
                from .metadata import source_metadata
                spans,reading=read_retrieved(session,doc,case['query'],config.max_read_chars,[],
                    source_id=case['source_id'],metadata=source_metadata(source.data['sources'][case['source_id']],doc))
            rows.append(dict(source_id=case['source_id'],version=doc['version'],query=case['query'],
                metrics=scores(spans,case['expected_ranges']),
                returned_ranges=[{k:s[k] for k in ('block','start','end')} for s in spans],reading=reading))
        from .eval import search_usage
        outputs.append(dict(mode=mode,cases=rows,usage=search_usage(trial)))
        write_json(args.output,dict(scope='Fixed saved originals and independently supplied labels; no web retrieval or Builder execution.',
                                   comparisons=outputs))
    print(args.output)


if __name__=='__main__':
    main()
