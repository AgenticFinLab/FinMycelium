"""Regression checks using synthetic data under an isolated, deleted run directory."""
import argparse
import importlib.util
import json
import gzip
from pathlib import Path
import shutil
import tempfile

import catalog_core as c
from seal_snapshot import seal
from snapshot_review import classification, validate
from workbench_export import export
from worked_example import replay


def load(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def expect_error(call, fragment):
    try:call()
    except ValueError as exc:
        assert fragment in str(exc),(fragment,str(exc))
    else:raise AssertionError('Expected error: '+fragment)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset-root',type=Path,required=True)
    p.add_argument('--finmy-root',type=Path,required=True)
    args=p.parse_args();dataset=args.dataset_root.resolve();finmy=args.finmy_root.resolve()
    helper=load('workflow_smoke',Path(__file__).with_name('catalog_workflow.py'))
    parent=dataset/'output/curation';parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='skill-smoke-',dir=parent) as tmp:
        root=Path(tmp);mock=root/'dataset'
        compressed=root/'audit.csv.gz'
        compressed.write_bytes(gzip.compress(b'event_id,note\nEVT-fixture,synthetic\n',mtime=0))
        expected=[dict(event_id='EVT-fixture',note='synthetic')]
        assert c.read(compressed)==expected and c.read(root/'audit.csv')==expected
        print('PASS gzip evidence reads explicitly and through the legacy logical CSV path')
        fresh=mock/'output/fresh';helper.initialize(c,mock,fresh,'fresh');stage=fresh/'stage'
        rows=[];sources=[];links=[];decisions=[]
        for suffix in ['Alpha','Beta']:
            eid='EVT-'+suffix;sid='SRC-'+suffix
            r={k:'' for k in c.CATALOG_FIELDS}
            r.update(event_id=eid,event_name_en='Acme solar project consent process '+suffix,
                     aliases='[]',description='Synthetic fixture, not a real event.',domain='Energy & Environment',
                     country_region='[]',participants='[]',keywords='[]',source_hints='[]',related_events='[]',
                     scope_include='Synthetic bounded project '+suffix,status='planned')
            rows.append(r)
            sources.append(dict(source_id=sid,title='Synthetic source',url='https://example.org/'+suffix,
                                publisher='Fixture',publication_info='',accessed_on='2020-01-01',locator='Synthetic fixture',reading_note='No real research claimed.'))
            links.append(dict(event_id=eid,source_id=sid,supported_fields=c.encoded(['description','scope_include']),
                              support_note='Synthetic fixture',verification_result='supported',verified_on='2020-01-01',reviewer='Fixture'))
            decisions.append(dict(record_id='KEEP-'+eid,event_id=eid,legacy_uid='',decision='retain',canonical_event_id=eid,
                                  reason='Synthetic fixture',source_ids=c.encoded([sid]),changed_fields='{}',reviewed_on='2020-01-01',reviewer='Fixture'))
        for name,rr,fields in zip(helper.TABLES,[rows,sources,links,decisions],[c.CATALOG_FIELDS,c.SOURCE_FIELDS,c.LINK_FIELDS,c.DECISION_FIELDS]):
            c.write(stage/name,fields,rr)
        helper.verify(c,fresh,2,finmy,False,False)
        c.summarize(stage,2,finmy_root=finmy)
        assert json.loads((stage/'research/coverage-summary.json').read_bytes())['historical_lexical_pairs'] is None
        print('PASS fresh summary without historical candidate CSV')
        helper.ledger(c,fresh,None);helper.recall(c,fresh,7)
        expect_error(lambda:helper.verify(c,fresh,2,finmy,True,False),'Pending/incomplete review')
        reviews=c.read(fresh/'row-review.csv')
        for r in reviews:
            for key in ['identity_note','date_note','scope_note','fact_locators','review_method']:r[key]='Synthetic fixture only'
            r.update(verdict='supported',reviewed_on='2020-01-01',reviewer='Fixture')
        c.write(fresh/'row-review.csv',helper.REVIEW_FIELDS,reviews)
        pairs=c.read(fresh/'pair-review.csv');assert pairs,'Fixture must exercise pair-review gate'
        expect_error(lambda:helper.verify(c,fresh,2,finmy,True,False),'Unresolved pair')
        for r in pairs:r.update(verdict='distinct',reason='Synthetic fixture',source_locators='Synthetic fixture',reviewed_on='2020-01-01',reviewer='Fixture')
        c.write(fresh/'pair-review.csv',helper.PAIR_FIELDS,pairs)
        helper.verify(c,fresh,2,finmy,True,False)
        assert json.loads((fresh/'validation.json').read_bytes())['result']=='RECORDED_FINAL_CHECKS_PASS'
        overlap=[{**r,'verdict':'bounded_overlap'} for r in pairs]
        c.write(fresh/'pair-review.csv',helper.PAIR_FIELDS,overlap)
        expect_error(lambda:helper.verify(c,fresh,2,finmy,True,False),'Materialize the reviewed overlap')
        c.write(fresh/'pair-review.csv',helper.PAIR_FIELDS,[])
        expect_error(lambda:helper.verify(c,fresh,2,finmy,True,False),'candidates dropped')
        c.write(fresh/'pair-review.csv',helper.PAIR_FIELDS,pairs)
        rows[0]['description']+=' Changed.';c.write(stage/'events.csv',c.CATALOG_FIELDS,rows)
        expect_error(lambda:helper.verify(c,fresh,2,finmy,True,False),'Stale row review')
        print('PASS pending readings/pairs, dropped pairs and stale review are rejected')
        formal=mock/'event-epg';shutil.copytree(stage,formal)
        legacy=dict(record_id='DEFER-OLD',event_id='H2EPR-0001',legacy_uid='',decision='defer',canonical_event_id='',
                    reason='Historical synthetic fixture',source_ids='[]',changed_fields='{}',reviewed_on='2020-01-01',reviewer='Fixture')
        c.write(formal/'curation-decisions.csv',c.DECISION_FIELDS,decisions+[legacy])
        (formal/'research/baseline.json').write_text(json.dumps({'identity_join_count':1}),encoding='utf8')
        continued=mock/'output/existing';helper.initialize(c,mock,continued,'existing')
        (continued/'stage/research/baseline.json').unlink()
        c.write(continued/'stage/curation-decisions.csv',c.DECISION_FIELDS,decisions)
        expect_error(lambda:helper.verify(c,continued,2,finmy,False,False),'missing historical dispositions')
        active_stage=continued/'stage'
        c.write(active_stage/'curation-decisions.csv',c.DECISION_FIELDS,decisions+[legacy])
        expect_error(lambda:c.check(active_stage,2,finmy_root=finmy),'provide --baseline-catalog')
        print('PASS explicit snapshot guards identities; absent legacy metadata cannot silently bypass checks')
        staged=c.read(continued/'stage/events.csv');prior_value=staged[0]['description'];staged[0]['description']+=' Revised.'
        c.write(continued/'stage/events.csv',c.CATALOG_FIELDS,staged)
        change=dict(record_id='REVISE-ALPHA',event_id=staged[0]['event_id'],legacy_uid='',decision='revise',
                    canonical_event_id=staged[0]['event_id'],reason='Synthetic fixture',source_ids='["SRC-Alpha"]',
                    changed_fields=c.encoded({'description':{'old':'Wrong old value','new':staged[0]['description']}}),
                    reviewed_on='2020-01-01',reviewer='Fixture')
        c.write(continued/'stage/curation-decisions.csv',c.DECISION_FIELDS,decisions+[legacy,change])
        expect_error(lambda:helper.verify(c,continued,2,finmy,False,False),'Invalid old/new replay')
        change['changed_fields']=c.encoded({'description':{'old':prior_value,'new':staged[0]['description']}})
        c.write(continued/'stage/curation-decisions.csv',c.DECISION_FIELDS,decisions+[legacy,change])
        helper.verify(c,continued,2,finmy,False,False)
        print('PASS wrong old/new values rejected; exact recorded revisions replay successfully')
        helper.ledger(c,fresh,fresh/'row-review.csv',refresh=True)
        assert c.read(fresh/'row-review.csv')[0]['verdict']=='pending'
        helper.recall(c,fresh,7,archive_previous=True)
        assert list((fresh/'history').rglob('row-review.csv')) and list((fresh/'history').rglob('pair-review.csv'))
        print('PASS changed-row ledger refresh and recall regeneration preserve earlier audit files')
        pair=dict(left_event_id='EVT-Alpha',right_event_id='EVT-Beta',verdict='bounded_overlap')
        c.write(stage/helper.PAIR_LEDGER,list(pair),[pair])
        expect_error(lambda:c.check(stage,2,finmy_root=finmy),'duplicate_status does not match')
        helper.sync_marks(c,fresh)
        assert [r['duplicate_status'] for r in c.read(stage/'events.csv')]==['overlap','overlap']
        c.check(stage,2,finmy_root=finmy)
        exported=export(stage/'events.csv',root/'workbench',finmy_root=finmy,chunk_size=1)
        assert exported['total_rows']==2 and 'duplicate_status' not in exported['fields']
        assert classification(stage/'events.csv',{'EVT-Alpha'})['baseline_rows']==1
        external={**rows[0],'event_id':'EVT-External'}
        comparison=root/'comparison.csv'
        c.write(comparison,c.CATALOG_FIELDS,[external])
        helper.recall(c,fresh,7,archive_previous=True,compare_csv=comparison)
        assert any('EVT-External' in (r['left_event_id'],r['right_event_id']) for r in c.read(fresh/'pair-review.csv'))
        first,second=root/'first.csv',root/'second.csv'
        c.write(first,c.CATALOG_FIELDS,[dict(rows[0],event_id='event1')])
        c.write(second,c.FIELDS,[dict({k:rows[1][k] for k in c.FIELDS},event_id='event2')])
        expect_error(lambda:helper.stage_composition(c,fresh,[second,first],True),'does not form event1')
        helper.stage_composition(c,fresh,[first,second],True)
        assert [r['event_id'] for r in c.read(stage/'events.csv')]==['event1','event2']
        assert c.read(stage/'events.csv')[1]['duplicate_status']==''
        print('PASS 24-column marks, compatible Workbench projection, classification and cross-catalog recall')
        expect_error(lambda:helper.run_path(mock,mock/'event-epg'),'below EPG-dataset/output')
        print('PASS output guard; all test data is synthetic and isolated')
        lesson = mock/'output/lesson'
        snapshot, manifest = replay(mock, finmy, lesson)
        summary = validate(snapshot, finmy, 2, allow_h2epr=False)
        assert summary['duplicate_status_counts'] == {'overlap': 2}
        assert len(manifest['full_parts']) == 2
        expect_error(lambda:seal(lesson,finmy,2,lesson/'evidence.jsonl'),'Snapshot already exists')
        snapshot.rename(lesson/'first-snapshot')
        existing_facts = (lesson/'evidence.jsonl').read_text(encoding='utf-8').splitlines()
        incomplete = lesson/'incomplete.jsonl'
        incomplete.write_text(existing_facts[0]+'\n',encoding='utf-8')
        expect_error(lambda:seal(lesson,finmy,2,incomplete),'exactly one record per current event ID')
        assert not snapshot.exists()
        print('PASS complete teaching fixture, published-format check, and no snapshot on missing evidence')


if __name__=='__main__':main()
