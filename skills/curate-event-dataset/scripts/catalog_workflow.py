"""Offline staging, recall and consistency checks. Never performs source research."""
import argparse
import collections
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import unicodedata
from datetime import datetime, timezone

TABLES = ('events.csv', 'sources.csv', 'event-sources.csv', 'curation-decisions.csv')
REVIEW_FIELDS = ['event_id', 'current_row_sha256', 'source_ids', 'identity_note', 'date_note',
                 'scope_note', 'fact_locators', 'review_method', 'verdict', 'reviewed_on', 'reviewer']
PAIR_FIELDS = ['left_event_id', 'right_event_id', 'scores', 'verdict', 'reason',
               'source_locators', 'reviewed_on', 'reviewer']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')


def row_hash(c, row):
    return hashlib.sha256(c.encoded(row).encode('utf-8')).hexdigest()


def review_day(value):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):
        raise ValueError('Review date must be YYYY-MM-DD')
    datetime.strptime(value,'%Y-%m-%d')


def run_path(dataset, path):
    path = path.resolve()
    allowed = (dataset / 'output').resolve()
    if not path.is_relative_to(allowed) or path == allowed:
        raise ValueError('Run directory must be below EPG-dataset/output/')
    return path


def initialize(c, dataset, run, basis):
    if run.exists():
        raise ValueError('Run directory already exists; resume it or choose a new run ID')
    formal = dataset / 'event-epg'
    fields = dict(zip(TABLES, [c.FIELDS, c.SOURCE_FIELDS, c.LINK_FIELDS, c.DECISION_FIELDS]))
    # Inspect before creating anything. Existing mode requires all four tables.
    if basis == 'existing' and any(not (formal / n).is_file() for n in TABLES):
        raise ValueError('Existing mode requires all four current catalog CSVs')
    stage = run / 'stage'
    stage.mkdir(parents=True)
    baseline_hashes = {}
    if basis == 'existing':
        baseline = run / 'baseline'
        baseline.mkdir()
        for name in TABLES:
            shutil.copy2(formal / name, baseline / name)
            shutil.copy2(formal / name, stage / name)
            baseline_hashes[name] = digest(baseline / name)
        retained = formal / 'research/baseline.json'
        if retained.is_file():
            for directory in (baseline, stage):
                (directory / 'research').mkdir(exist_ok=True)
                shutil.copy2(retained, directory / 'research/baseline.json')
            baseline_hashes['research/baseline.json'] = digest(retained)
    else:
        for name in TABLES:
            c.write(stage / name, fields[name], [])
    save_json(run / 'run.json', dict(basis=basis, created_at_utc=datetime.now(timezone.utc).isoformat(),
              source_catalog=str(formal), baseline_sha256=baseline_hashes,
              row_hash_algorithm='SHA256(UTF8(curate_events.encoded(row))); implementation version must be retained',
              helper_sha256=digest(Path(__file__)), curate_events_sha256=digest(dataset / 'scripts/curate_events.py')))
    print('INITIALIZED',run,'No event is verified by initialization.')


def context(c, run):
    manifest = json.loads((run / 'run.json').read_text(encoding='utf-8'))
    baseline = run / 'baseline' if manifest['basis'] == 'existing' else None
    for name, expected in manifest['baseline_sha256'].items():
        if digest(baseline / name) != expected:
            raise ValueError('Frozen baseline changed: ' + name)
    return manifest, baseline, run / 'stage'


def archive(run, names):
    destination=run/'history'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    destination.mkdir(parents=True)
    for name in names:
        if (run/name).is_file():shutil.copy2(run/name,destination/name)


def ledger(c, run, reuse, refresh=False):
    _, _, stage = context(c, run)
    path = run / 'row-review.csv'
    if path.exists() and not refresh:
        raise ValueError('row-review.csv already exists; preserve and edit existing readings')
    previous = {}
    if reuse:
        for r in c.read(reuse):
            if set(REVIEW_FIELDS) - set(r):
                raise ValueError('Reuse requires the helper ledger schema; migrate older ledgers explicitly')
            if r['event_id'] in previous:
                raise ValueError('Duplicate reused review ID')
            previous[r['event_id']] = r
    if path.exists():archive(run,['row-review.csv'])
    links = collections.defaultdict(set)
    for link in c.read(stage / 'event-sources.csv'):
        links[link['event_id']].add(link['source_id'])
    result = []
    for event in c.read(stage / 'events.csv'):
        eid = event['event_id']; h = row_hash(c, event)
        old = previous.get(eid)
        if old and old['current_row_sha256'] == h and old['verdict'] == 'supported':
            row = {k: old[k] for k in REVIEW_FIELDS}
            row['review_method'] += ' Unchanged-row evidence reused; original reading date and limits retained.'
        else:
            row = {k: '' for k in REVIEW_FIELDS}
            row.update(event_id=eid, current_row_sha256=h, source_ids=c.encoded(sorted(links[eid])),
                       verdict='pending')
        result.append(row)
    c.write(path, REVIEW_FIELDS, result)
    print('LEDGER',len(result),'rows; pending',sum(r['verdict']=='pending' for r in result))


def recall(c, run, neighbors, archive_previous=False):
    import sklearn
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.neighbors import NearestNeighbors
    _, _, stage = context(c, run)
    if any((run / n).exists() for n in ['pair-review.csv','recall-method.json']):
        if not archive_previous:raise ValueError('Recall outputs exist; use --archive-previous-recall to preserve and regenerate them')
        archive(run,['pair-review.csv','recall-method.json'])
    rows = c.read(stage / 'events.csv')
    def normalized(value):
        return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())
    pairs = {}; methods=[]
    for mode, threshold, analyzer, grams in [('titles',.62,'char_wb',(3,5)),
                                             ('aliases_subjects',.82,'char_wb',(3,5))]:
        texts = []
        for row in rows:
            text = row['event_name_zh']+' '+row['event_name_en']
            if mode == 'aliases_subjects':
                text += ' '+' '.join(json.loads(row['aliases']or'[]')+json.loads(row['participants']or'[]'))
            texts.append(normalized(text))
        if len(rows) >= 2:
            vectorizer=TfidfVectorizer(analyzer=analyzer,ngram_range=grams,max_features=160000)
            matrix=vectorizer.fit_transform(texts)
            count=min(neighbors+1,len(rows))
            distances,indices=NearestNeighbors(n_neighbors=count,metric='cosine',n_jobs=2).fit(matrix).kneighbors(matrix)
            for i,(ds,js) in enumerate(zip(distances,indices)):
                for d,j in zip(ds,js):
                    if i!=j and 1-float(d)>=threshold:
                        key=tuple(sorted((rows[i]['event_id'],rows[j]['event_id'])))
                        pairs.setdefault(key,{})[mode]=round(1-float(d),6)
        methods.append(dict(mode=mode,threshold=threshold,analyzer=analyzer,ngrams=grams,max_features=160000))
    reviews=[dict(zip(PAIR_FIELDS,[a,b,c.encoded(scores),'pending','','','',''])) for (a,b),scores in sorted(pairs.items())]
    c.write(run / 'pair-review.csv',PAIR_FIELDS,reviews)
    save_json(run / 'recall-method.json',dict(master_sha256=digest(stage/'events.csv'),
              methods=methods,neighbors=neighbors,sklearn_version=sklearn.__version__,pairs=len(reviews),
              candidate_ids=[list(k) for k in sorted(pairs)],
              limitation='Lexical candidates only. Independently investigate subject, case, dates, scope, geography and source-context signals. Zero lexical candidates is not semantic clearance.'))
    print('RECALLED',len(reviews),'pending pairs; no automatic verdicts')


def verify(c, run, target, finmy, final, allow_state_changes):
    manifest, baseline, stage = context(c, run)
    save_json(run/'validation.json',dict(result='RUNNING',final_records_checked=False))
    c.CAT = stage
    c.check(target,baseline_catalog=baseline,finmy_root=finmy)
    rows=c.read(stage/'events.csv'); by={r['event_id']:r for r in rows}
    old={r['event_id']:r for r in c.read(baseline/'events.csv')} if baseline else {}
    decisions=c.read(stage/'curation-decisions.csv'); latest={r['event_id']:r for r in decisions}
    if baseline:
        prior=c.read(baseline/'curation-decisions.csv')
        if decisions[:len(prior)]!=prior:raise ValueError('Historical decisions must remain an unchanged prefix')
        appended=decisions[len(prior):]
        prior_sources=c.read(baseline/'sources.csv')
        if c.read(stage/'sources.csv')[:len(prior_sources)]!=prior_sources:
            raise ValueError('Source history changed; append corrected source records instead')
    revisions=[]
    for eid in sorted(set(old)|set(by)):
        before,after=old.get(eid),by.get(eid)
        if before==after:continue
        delta={k:dict(old=before[k]if before else None,new=after[k]if after else None)
               for k in c.FIELDS if before is None or after is None or before[k]!=after[k]}
        revisions.append(dict(event_id=eid,action='add'if before is None else 'remove'if after is None else 'revise',changed_fields=delta))
        if before and after and not allow_state_changes:
            if any(k in delta for k in ['owner','status','epg_path','gantt_path','review_path']):
                raise ValueError('Workflow state changed; requires an intentional --allow-workflow-state-changes run')
        if baseline and (eid not in latest or (before and not after and latest[eid]['decision']not in {'merge','exclude','defer'})):
            raise ValueError('Missing disposition for changed identity: '+eid)
        if baseline:
            changes=[d for d in appended if d['event_id']==eid]
            if not changes:raise ValueError('Changed identity needs an appended decision: '+eid)
            if before and after:
                replay=dict(before)
                for decision in changes:
                    for field,change in json.loads(decision['changed_fields']).items():
                        if field not in c.FIELDS or not isinstance(change,dict) or set(change)!={'old','new'} or replay[field]!=change['old']:
                            raise ValueError('Invalid old/new replay for '+eid+'/'+field)
                        replay[field]=change['new']
                if replay!=after:raise ValueError('Decision old/new values do not reproduce staged row: '+eid)
    if baseline:
        for name in TABLES:
            if digest(Path(manifest['source_catalog'])/name)!=manifest['baseline_sha256'][name]:
                raise ValueError('Formal catalog changed since snapshot; reconcile before publication: '+name)
    for row in rows:
        for field in ['aliases','participants','country_region','keywords','source_hints']:
            values=json.loads(row[field]or'[]')
            keys=[' '.join(unicodedata.normalize('NFKC',v).casefold().split()) for v in values]
            if len(keys)!=len(set(keys)):raise ValueError('Normalized array duplicates: '+row['event_id']+'/'+field)
        if re.search(r'&(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-f]+);',c.encoded(row),re.I):
            raise ValueError('Review unresolved HTML entities: '+row['event_id'])
        if not row['event_id'] in old and (row['status']!='planned' or row['owner'] or any(row[k]for k in ['epg_path','gantt_path','review_path'])):
            raise ValueError('New catalog entries must start planned, unassigned, without artifacts')
        if latest[row['event_id']]['canonical_event_id']!=row['event_id']:
            raise ValueError('Active identity must resolve to itself')
    verdict='STAGING_MACHINE_CHECKS_PASS'
    if final:
        ledger_rows=c.read(run/'row-review.csv')
        if len(ledger_rows)!=len(by) or {r['event_id']for r in ledger_rows}!=set(by):
            raise ValueError('Final ledger must cover every active ID exactly once')
        linked=collections.defaultdict(set)
        for l in c.read(stage/'event-sources.csv'):linked[l['event_id']].add(l['source_id'])
        for r in ledger_rows:
            if r['current_row_sha256']!=row_hash(c,by[r['event_id']]):raise ValueError('Stale row review: '+r['event_id'])
            if r['verdict']!='supported' or any(not r[k].strip() for k in REVIEW_FIELDS) or r['fact_locators'].strip()in {'[]','{}'}:
                raise ValueError('Pending/incomplete review: '+r['event_id'])
            review_day(r['reviewed_on'])
            ids=json.loads(r['source_ids'])
            if not isinstance(ids,list) or not ids or not set(ids)<=linked[r['event_id']]:raise ValueError('Unlinked review evidence')
        method=json.loads((run/'recall-method.json').read_text(encoding='utf8'))
        if method['master_sha256']!=digest(stage/'events.csv'):raise ValueError('Recall is stale; rerun against current master')
        reviews=c.read(run/'pair-review.csv');keys=[tuple(sorted((r['left_event_id'],r['right_event_id'])))for r in reviews]
        if len(keys)!=len(set(keys)) or set(keys)!={tuple(k)for k in method['candidate_ids']}:
            raise ValueError('Recall candidates dropped or duplicated')
        for r in reviews:
            if r['verdict']not in {'distinct','bounded_overlap','invalid_signal'} or any(not r[k].strip() for k in ['reason','source_locators','reviewed_on','reviewer']):
                raise ValueError('Unresolved pair; merge/remove then start a new recall run where necessary')
            review_day(r['reviewed_on'])
        verdict='RECORDED_FINAL_CHECKS_PASS'
    save_json(run/'revisions.json',revisions)
    report=dict(result=verdict,active=len(rows),target=target,revisions=len(revisions),
                master_sha256=digest(stage/'events.csv'),final_records_checked=final,
                curate_events_sha256=digest(c.ROOT/'scripts/curate_events.py'),helper_sha256=digest(Path(__file__)),
                limitation='Checks enforce structural consistency and recorded review coverage, not the truth of agent-entered conclusions, exhaustive deduplication or independent human certification. No formal catalog files were published.')
    save_json(run/'validation.json',report)
    print(verdict,len(rows),'rows; no publication or truth certification')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['init','ledger','recall','verify'])
    parser.add_argument('--dataset-root',type=Path,required=True)
    parser.add_argument('--finmy-root',type=Path,required=True)
    parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--basis',choices=['fresh','existing'],default='existing')
    parser.add_argument('--reuse-ledger',type=Path)
    parser.add_argument('--refresh-ledger',action='store_true')
    parser.add_argument('--archive-previous-recall',action='store_true')
    parser.add_argument('--neighbors',type=int,default=7)
    parser.add_argument('--target',type=int)
    parser.add_argument('--final',action='store_true')
    parser.add_argument('--allow-workflow-state-changes',action='store_true')
    args=parser.parse_args()
    try:
        dataset=args.dataset_root.resolve();finmy=args.finmy_root.resolve();run=run_path(dataset,args.run_dir)
        if args.neighbors<1:raise ValueError('neighbors must be positive')
        if args.final and args.target is None:raise ValueError('Final verification requires explicit --target')
        c=load_module('workflow_catalog',dataset/'scripts/curate_events.py')
        if args.command=='init':initialize(c,dataset,run,args.basis)
        elif args.command=='ledger':ledger(c,run,args.reuse_ledger,args.refresh_ledger)
        elif args.command=='recall':recall(c,run,args.neighbors,args.archive_previous_recall)
        else:verify(c,run,args.target,finmy,args.final,args.allow_workflow_state_changes)
    except (ValueError,KeyError,FileNotFoundError,ImportError) as exc:
        if args.command=='verify' and 'run' in locals() and run.is_dir():
            save_json(run/'validation.json',dict(result='FAILED',error=str(exc),final_records_checked=False))
        parser.exit(1,str(exc)+'\n')


if __name__=='__main__':main()
