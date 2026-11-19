"""Offline staging, recall and consistency checks. Never performs source research."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re
import shutil
import unicodedata
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlsplit

import catalog_core as catalog

TABLES = ('events.csv', 'sources.csv', 'event-sources.csv', 'curation-decisions.csv')
PAIR_LEDGER = 'research/duplicate-review.csv.gz'
H2EPR_AUDIT = ('events_H2EPR.csv', 'research/h2epr/review.csv', 'research/h2epr/duplicate-review.csv')
REVIEW_FIELDS = ['event_id', 'current_row_sha256', 'source_ids', 'identity_note', 'date_note',
                 'scope_note', 'fact_locators', 'review_method', 'verdict', 'reviewed_on', 'reviewer']
PAIR_FIELDS = ['left_event_id', 'right_event_id', 'scores', 'verdict', 'reason',
               'source_ids', 'source_locators', 'reviewed_on', 'reviewer']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    fields = dict(zip(TABLES, [c.CATALOG_FIELDS, c.SOURCE_FIELDS, c.LINK_FIELDS, c.DECISION_FIELDS]))
    # Inspect before creating anything. Existing mode requires all four tables.
    if basis == 'existing' and any(not (formal / n).is_file() for n in TABLES):
        raise ValueError('Existing mode requires all four current catalog CSVs')
    stage = run / 'stage'
    stage.mkdir(parents=True)
    baseline_hashes = {}
    if basis == 'existing':
        baseline = run / 'baseline'
        baseline.mkdir()
        ancillary = ('research/baseline.json', PAIR_LEDGER, *H2EPR_AUDIT)
        for name in (*TABLES, *(name for name in ancillary if (formal / name).is_file())):
            for directory in (baseline, stage):
                (directory / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(formal / name, directory / name)
            baseline_hashes[name] = digest(baseline / name)
    else:
        for name in TABLES:
            c.write(stage / name, fields[name], [])
    save_json(run / 'run.json', dict(basis=basis, created_at_utc=datetime.now(timezone.utc).isoformat(),
              source_catalog=str(formal), baseline_sha256=baseline_hashes,
              row_hash_algorithm='SHA256(UTF8(JSON(row, ensure_ascii=False, sort_keys=True)))',
              helper_sha256=digest(Path(__file__)), catalog_core_sha256=digest(Path(c.__file__))))
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


def stage_composition(c, run, inputs, sequential_ids=False):
    _, _, stage = context(c, run)
    output = stage / 'events.csv'
    groups = []
    provenance = []
    for source in inputs:
        if source.resolve() == output.resolve():
            raise ValueError('Freeze the composition input outside stage/events.csv before combining')
        expected = digest(source)
        rows = c.read(source)
        if digest(source) != expected:
            raise ValueError(f'Composition input changed during reading: {source}')
        if not rows or any(list(row) not in (c.FIELDS, c.CATALOG_FIELDS) for row in rows):
            raise ValueError(f'Expected a nonempty 23- or 24-column event CSV: {source}')
        groups.append(rows)
        provenance.append({'path': str(source.resolve()), 'rows': len(rows), 'sha256': expected})
    combined = [dict(row, duplicate_status=row.get('duplicate_status', '')) for rows in groups for row in rows]
    ids = list(c.keyed(combined, 'event_id'))
    if sequential_ids and ids != [f'event{i}' for i in range(1, len(combined)+1)]:
        raise ValueError('Composition does not form event1 through the final event in order')
    c.write(output, c.CATALOG_FIELDS, combined)
    save_json(run/'composition.json', {
        'inputs': provenance,
        'master_sha256':digest(output),
        'scope':'Master only; join and validate sources, decisions and audits before publication.',
    })
    print('COMPOSED', len(combined), 'rows in stage/events.csv; source/decision/audit assembly still required')


def sync_marks(c, run):
    _, _, stage = context(c, run)
    master = stage / 'events.csv'
    rows = c.read(master)
    ids = c.keyed(rows, 'event_id')
    pairs = c.read(stage / PAIR_LEDGER)
    keys = [frozenset((pair['left_event_id'], pair['right_event_id'])) for pair in pairs]
    if len(keys) != len(set(keys)) or any(len(key) != 2 or not key <= ids.keys() for key in keys):
        raise ValueError('Current pair ledger has an invalid or repeated event pair')
    marks = c.duplicate_marks(pairs)
    c.write(master, c.CATALOG_FIELDS, [dict(row, duplicate_status=marks.get(row['event_id'], '')) for row in rows])
    print('SYNCED', len(marks), 'marked rows; refresh stale row reviews and recall if needed')


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


def recall_signals(row):
    labels = [row['event_name_en'], row['event_name_zh'], *json.loads(row['aliases'] or '[]')]
    for label in labels:
        name = ''.join(ch for ch in unicodedata.normalize('NFKC', label).casefold() if ch.isalnum())
        if len(name) >= 4:
            yield 'exact_name', name
    for url in json.loads(row['source_hints'] or '[]'):
        parsed = urlsplit(url)
        host = (parsed.hostname or '').removeprefix('www.')
        if host and 'wikipedia' not in host and len(parsed.path) > 10:
            query = tuple(sorted((k, v) for k, v in parse_qsl(parsed.query) if not k.startswith('utm_')))
            yield 'shared_source', (host, parsed.path.rstrip('/'), query)
    for code in re.findall(r'\b(?:P\d{6}|DS\d{2,3}|\d{4}-\d{3}[A-Z]{1,3}|\d{2}V-?\d{3})\b',
                           ' '.join(labels + [row['description']]), flags=re.I):
        yield 'named_identifier', code.casefold().replace('-', '')


def recall(c, run, neighbors, archive_previous=False, compare_csv=None):
    import sklearn
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.neighbors import NearestNeighbors
    _, _, stage = context(c, run)
    if any((run / n).exists() for n in ['pair-review.csv','recall-method.json']):
        if not archive_previous:raise ValueError('Recall outputs exist; use --archive-previous-recall to preserve and regenerate them')
        archive(run,['pair-review.csv','recall-method.json'])
    rows = c.read(stage / 'events.csv')
    other = c.read(compare_csv) if compare_csv else []
    catalog_ids = set(c.keyed(rows, 'event_id'))
    if catalog_ids & c.keyed(other, 'event_id').keys():
        raise ValueError('Comparison CSV must use disjoint IDs. Compare an already integrated input within the master instead.')
    def normalized(value):
        return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())
    pairs = {}; methods=[]
    candidates = rows + other
    for mode, threshold, analyzer, grams in [('titles',.62,'char_wb',(3,5)),
                                             ('aliases_subjects',.82,'char_wb',(3,5))]:
        texts = []
        for row in candidates:
            text = row['event_name_zh']+' '+row['event_name_en']
            if mode == 'aliases_subjects':
                text += ' '+' '.join(json.loads(row['aliases']or'[]')+json.loads(row['participants']or'[]'))
            texts.append(normalized(text))
        if rows and len(candidates) >= 2:
            vectorizer=TfidfVectorizer(analyzer=analyzer,ngram_range=grams,max_features=160000)
            matrix=vectorizer.fit_transform(texts)
            windows = [(0, len(rows), neighbors + 1, mode)]
            if other:
                windows.append((len(rows), len(candidates), neighbors, mode + '_cross_catalog'))
            for first, end, limit, label in windows:
                model = NearestNeighbors(n_neighbors=min(limit,end-first), metric='cosine', n_jobs=2)
                distances, indices = model.fit(matrix[first:end]).kneighbors(matrix[:len(rows)])
                for i, (ds, js) in enumerate(zip(distances, indices)):
                    for d, offset in zip(ds,js):
                        j=first+offset
                        if i!=j and 1-float(d)>=threshold:
                            key=tuple(sorted((rows[i]['event_id'],candidates[j]['event_id'])))
                            pairs.setdefault(key,{})[label]=round(1-float(d),6)
        methods.append(dict(mode=mode,threshold=threshold,analyzer=analyzer,ngrams=grams,max_features=160000))
    index = collections.defaultdict(list)
    for row in candidates:
        for signal in set(recall_signals(row)):
            index[signal].append(row['event_id'])
    for (kind, _), matches in index.items():
        if not 2 <= len(matches) <= 20:
            continue
        for i, left in enumerate(matches):
            for right in matches[i+1:]:
                if left in catalog_ids or right in catalog_ids:
                    pairs.setdefault(tuple(sorted((left,right))),{})[kind]=True
    reviews=[dict(zip(PAIR_FIELDS,[a,b,c.encoded(scores),'pending','','[]','','',''])) for (a,b),scores in sorted(pairs.items())]
    c.write(run / 'pair-review.csv',PAIR_FIELDS,reviews)
    save_json(run / 'recall-method.json',dict(master_sha256=digest(stage/'events.csv'),
              comparison={'path':str(compare_csv.resolve()),'sha256':digest(compare_csv)} if compare_csv else None,
              indexed_signals=['exact_name','shared_source','named_identifier'], maximum_members_per_signal=20,
              methods=methods,neighbors=neighbors,sklearn_version=sklearn.__version__,pairs=len(reviews),
              candidate_ids=[list(k) for k in sorted(pairs)],
              limitation='Candidate signals only. Independently investigate subject, case, dates, scope, geography and source context.'))
    print('RECALLED',len(reviews),'pending pairs; no automatic verdicts')


def verify(c, run, target, finmy, final, allow_state_changes, allow_h2epr_audit_exceptions=False):
    manifest, baseline, stage = context(c, run)
    save_json(run/'validation.json',dict(result='RUNNING',final_records_checked=False))
    if final and allow_h2epr_audit_exceptions:
        raise ValueError('Final verification requires closing the recorded H2EPR exceptions')
    c.check(stage, target, baseline_catalog=baseline, finmy_root=finmy,
            allow_h2epr_audit_exceptions=allow_h2epr_audit_exceptions)
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
        delta={k:dict(old=before.get(k) if before else None,new=after.get(k) if after else None)
               for k in c.CATALOG_FIELDS if (before or {}).get(k)!=(after or {}).get(k)}
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
                        if field not in c.CATALOG_FIELDS or not isinstance(change,dict) or set(change)!={'old','new'} or replay.get(field)!=change['old']:
                            raise ValueError('Invalid old/new replay for '+eid+'/'+field)
                        if change['new'] is None:
                            replay.pop(field, None)
                        else:
                            replay[field]=change['new']
                if replay!=after:raise ValueError('Decision old/new values do not reproduce staged row: '+eid)
    if baseline:
        for name in manifest['baseline_sha256']:
            if digest(Path(manifest['source_catalog'])/name)!=manifest['baseline_sha256'][name]:
                raise ValueError('Formal catalog changed since snapshot; reconcile before publication: '+name)
    for row in rows:
        for field in ['aliases','participants','country_region','keywords','source_hints']:
            values=json.loads(row[field]or'[]')
            keys=[' '.join(unicodedata.normalize('NFKC',v).casefold().split()) for v in values]
            if len(keys)!=len(set(keys)) and (final or row != old.get(row['event_id'])):
                raise ValueError('Normalized array duplicates: '+row['event_id']+'/'+field)
        if (final or row != old.get(row['event_id'])) and re.search(r'&(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-f]+);',c.encoded(row),re.I):
            raise ValueError('Review unresolved HTML entities: '+row['event_id'])
        if not row['event_id'] in old and (row['status']!='planned' or row['owner'] or any(row[k]for k in ['epg_path','gantt_path','review_path'])):
            raise ValueError('New catalog entries must start planned, unassigned, without artifacts')
        if latest[row['event_id']]['canonical_event_id']!=row['event_id']:
            raise ValueError('Active identity must resolve to itself')
    verdict='STAGING_CHECKS_WITH_H2EPR_EXCEPTIONS' if allow_h2epr_audit_exceptions else 'STAGING_MACHINE_CHECKS_PASS'
    if final:
        published_pairs = c.read(stage / PAIR_LEDGER) if (stage / PAIR_LEDGER).is_file() else []
        if any(pair['verdict'] in {'duplicate','pending','possible_duplicate'} for pair in published_pairs):
            raise ValueError('Final verification requires resolving recorded duplicate and possible-duplicate pairs')
        retained_overlaps = {
            frozenset((pair['left_event_id'], pair['right_event_id']))
            for pair in published_pairs if pair['verdict'] == 'bounded_overlap'
        }
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
        comparison=method.get('comparison')
        if comparison and digest(Path(comparison['path']))!=comparison['sha256']:
            raise ValueError('Comparison CSV changed; rerun recall')
        reviews=c.read(run/'pair-review.csv');keys=[tuple(sorted((r['left_event_id'],r['right_event_id'])))for r in reviews]
        if len(keys)!=len(set(keys)) or set(keys)!={tuple(k)for k in method['candidate_ids']}:
            raise ValueError('Recall candidates dropped or duplicated')
        for r in reviews:
            if r['verdict']not in {'distinct','bounded_overlap','invalid_signal'} or any(not r[k].strip() for k in ['reason','source_locators','reviewed_on','reviewer']):
                raise ValueError('Unresolved pair; merge/remove then start a new recall run where necessary')
            review_day(r['reviewed_on'])
            pair = frozenset((r['left_event_id'], r['right_event_id']))
            if r['verdict'] == 'bounded_overlap' and pair <= by.keys() and pair not in retained_overlaps:
                raise ValueError('Materialize the reviewed overlap in stage/research/duplicate-review.csv.gz and sync its marks')
        verdict='RECORDED_FINAL_CHECKS_PASS'
    save_json(run/'revisions.json',revisions)
    report=dict(result=verdict,active=len(rows),target=target,revisions=len(revisions),
                master_sha256=digest(stage/'events.csv'),final_records_checked=final,
                catalog_core_sha256=digest(Path(c.__file__)),helper_sha256=digest(Path(__file__)),
                limitation='Checks enforce structural consistency and recorded review coverage, not the truth of agent-entered conclusions, exhaustive deduplication or independent human certification. No formal catalog files were published.')
    save_json(run/'validation.json',report)
    print(verdict,len(rows),'rows; no publication or truth certification')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['init','compose','sync-marks','ledger','recall','verify'])
    parser.add_argument('--dataset-root',type=Path,required=True)
    parser.add_argument('--finmy-root',type=Path,required=True)
    parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--basis',choices=['fresh','existing'],default='existing')
    parser.add_argument('--reuse-ledger',type=Path)
    parser.add_argument('--refresh-ledger',action='store_true')
    parser.add_argument('--archive-previous-recall',action='store_true')
    parser.add_argument('--neighbors',type=int,default=7)
    parser.add_argument('--compare-csv',type=Path,help='Additional catalog used only for cross-catalog candidate recall')
    parser.add_argument('--target',type=int)
    parser.add_argument('--final',action='store_true')
    parser.add_argument('--allow-workflow-state-changes',action='store_true')
    parser.add_argument('--allow-h2epr-audit-exceptions',action='store_true')
    parser.add_argument('--input-csv', action='append', type=Path, help='Frozen composition input, repeat in the intended order')
    parser.add_argument('--sequential-ids', action='store_true', help='Require event1 through eventN in composed order')
    args=parser.parse_args()
    try:
        dataset=args.dataset_root.resolve();finmy=args.finmy_root.resolve();run=run_path(dataset,args.run_dir)
        if args.neighbors<1:raise ValueError('neighbors must be positive')
        if args.final and args.target is None:raise ValueError('Final verification requires explicit --target')
        c=catalog
        if args.command=='init':initialize(c,dataset,run,args.basis)
        elif args.command=='compose':
            if len(args.input_csv or []) < 2:
                raise ValueError('Composition requires two or more --input-csv files')
            stage_composition(c,run,args.input_csv,args.sequential_ids)
        elif args.command=='sync-marks':sync_marks(c,run)
        elif args.command=='ledger':ledger(c,run,args.reuse_ledger,args.refresh_ledger)
        elif args.command=='recall':recall(c,run,args.neighbors,args.archive_previous_recall,args.compare_csv)
        else:verify(c,run,args.target,finmy,args.final,args.allow_workflow_state_changes,args.allow_h2epr_audit_exceptions)
    except (ValueError,KeyError,FileNotFoundError,ImportError) as exc:
        if args.command=='verify' and 'run' in locals() and run.is_dir():
            save_json(run/'validation.json',dict(result='FAILED',error=str(exc),final_records_checked=False))
        parser.exit(1,str(exc)+'\n')


if __name__=='__main__':main()
