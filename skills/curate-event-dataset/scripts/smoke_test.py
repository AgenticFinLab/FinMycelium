"""Regression checks using synthetic data under an isolated, deleted run directory."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile


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
        root=Path(tmp);mock=root/'dataset';(mock/'scripts').mkdir(parents=True)
        for name in ['curate_events.py','export_event_workbench.py']:
            shutil.copy2(dataset/'scripts'/name,mock/'scripts'/name)
        c=load('smoke_catalog',mock/'scripts/curate_events.py')
        fresh=mock/'output/fresh';helper.initialize(c,mock,fresh,'fresh');stage=fresh/'stage'
        rows=[];sources=[];links=[];decisions=[]
        for suffix in ['Alpha','Beta']:
            eid='EVT-'+suffix;sid='SRC-'+suffix
            r={k:'' for k in c.FIELDS}
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
        for name,rr,fields in zip(helper.TABLES,[rows,sources,links,decisions],[c.FIELDS,c.SOURCE_FIELDS,c.LINK_FIELDS,c.DECISION_FIELDS]):
            c.write(stage/name,fields,rr)
        helper.verify(c,fresh,2,finmy,False,False)
        c.summarize(2,finmy_root=finmy)
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
        c.write(fresh/'pair-review.csv',helper.PAIR_FIELDS,[])
        expect_error(lambda:helper.verify(c,fresh,2,finmy,True,False),'candidates dropped')
        c.write(fresh/'pair-review.csv',helper.PAIR_FIELDS,pairs)
        rows[0]['description']+=' Changed.';c.write(stage/'events.csv',c.FIELDS,rows)
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
        c.CAT=continued/'stage'
        c.write(c.CAT/'curation-decisions.csv',c.DECISION_FIELDS,decisions+[legacy])
        expect_error(lambda:c.check(2,finmy_root=finmy),'provide --baseline-catalog')
        print('PASS explicit snapshot guards identities; absent legacy metadata cannot silently bypass checks')
        staged=c.read(continued/'stage/events.csv');prior_value=staged[0]['description'];staged[0]['description']+=' Revised.'
        c.write(continued/'stage/events.csv',c.FIELDS,staged)
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
        expect_error(lambda:helper.run_path(mock,mock/'event-epg'),'below EPG-dataset/output')
        print('PASS output guard; all test data is synthetic and isolated')


if __name__=='__main__':main()
