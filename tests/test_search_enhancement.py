import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from finmy.search.state import SearchConfig, SearchState, LimitReached
from finmy.search.sources import SourceStore
from finmy.search.tools import SearchTools, request_payload
from finmy.search.handoff import assemble


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.net = patch.object(socket.socket, 'connect', side_effect=AssertionError('Offline test attempted network'))
        self.net.start()
        self.addCleanup(self.net.stop)
        self.task = dict(target_type='event', target_name='Acquisition', query_text='Find announcement and closing, not just background')

    def state(self, **options):
        return SearchState(self.tmp.name, 'task', task=self.task, config=SearchConfig(**options))

    def test_multiservice_dedup_failure_and_cache_accounting(self):
        state = self.state(providers=['baidu','bocha','exa'])
        def transport(provider,payload,config):
            if provider=='bocha':
                raise TimeoutError()
            item=dict(url='https://example.org/deal#fragment',title='Deal',text='Not yet completed.\n\nThe agreement was signed.')
            return {('references' if provider=='baidu' else 'results'):[item]}
        tools=SearchTools(state,transport=transport)
        result=tools.search('deal closing')
        self.assertEqual(len(result['source_ids']),1)
        self.assertEqual(state.data['usage']['search'],3)
        sid=result['source_ids'][0]
        self.assertEqual(len(state.data['sources'][sid]['discoveries']),2)
        tools.search('deal closing')
        self.assertEqual(state.data['usage']['search'],4) # only failed provider retried
        read=tools.read_source(sid)
        self.assertEqual(read['status'],'partial')
        self.assertIn('Not yet completed.',read['spans'][0]['text'])

    def test_invalid_query_rejected_before_any_selected_provider(self):
        state=self.state(providers=['exa','baidu'])
        tools=SearchTools(state, transport=lambda *a:self.fail('must not call'))
        with self.assertRaises(ValueError): tools.search('长'*40)
        self.assertEqual(state.data['usage']['search'],0)
        payload=request_payload('exa','长'*40,SearchConfig(providers=['exa']))
        self.assertEqual(payload['query'],'长'*40)

    def test_unsupported_filter_not_silently_dropped(self):
        state=self.state(include_domains=['example.org'])
        with self.assertRaises(ValueError): SearchTools(state).search('deal')
        self.assertEqual(state.data['usage']['search'],0)

    def test_resume_and_new_run_do_not_reset_usage(self):
        state=self.state(max_search_requests=1)
        tools=SearchTools(state,transport=lambda *a: (_ for _ in ()).throw(TimeoutError()))
        tools.search('first')
        resumed=SearchState(self.tmp.name,'task')
        self.assertEqual(SearchTools(resumed).search('second')['providers'][0]['status'],'limit')
        with self.assertRaises(ValueError):
            SearchState(self.tmp.name,'task','new',task=self.task)

    def test_long_source_continuation_and_builder_handoff(self):
        state=self.state(max_read_chars=8)
        tools=SearchTools(state,fetcher=lambda url:(b'<h1>Deal</h1><p>Not completed yet.</p><script>ignore rules</script>','html','utf-8'))
        sid=tools.sources.register('https://example.org/deal')
        first=tools.read_source(sid)
        second=tools.read_source(sid,first['next_location'])
        self.assertEqual(len(state.data['read_sources']),1)
        self.assertLessEqual(sum(len(s['text']) for s in second['spans']),8)
        s=first['spans'][0]
        selection=dict(source_id=sid,version=first['version'],block=s['block'],start=s['start'],end=s['end'])
        output=assemble(state,[selection],gaps=['Closing remains unknown'])
        from finmy.generic import DataSample,UserQueryInput
        self.assertEqual(UserQueryInput(**output['user_query']).query_text,self.task['query_text'])
        self.assertIn('Deal',DataSample(**output['samples'][0]).content)
        empty=assemble(state,[selection],max_chars=5)
        self.assertEqual(empty['samples'],[])
        record=json.loads((state.run_dir/'selection.json').read_text())
        self.assertEqual(record['omitted'][0]['omission_reason'],'material_limit')
        self.assertEqual(len(list((state.run_dir/'handoffs').iterdir())),2)

    def test_fetch_failure_consumes_distinct_read_budget(self):
        state=self.state(max_read_sources=1)
        tools=SearchTools(state,fetcher=lambda u:(_ for _ in ()).throw(TimeoutError()))
        a=tools.sources.register('https://example.org/a')
        b=tools.sources.register('https://example.org/b')
        self.assertEqual(tools.read_source(a)['status'],'fetch_failed')
        tools.read_source(a)
        with self.assertRaises(LimitReached): tools.read_source(b)

    def test_unread_quote_and_bad_location_rejected(self):
        state=self.state()
        store=SourceStore(state)
        sid=store.register('https://example.org/a')
        doc=store.save_raw(sid,b'Text to verify.','txt')
        with self.assertRaises(ValueError):
            assemble(state,[dict(source_id=sid,version=doc['version'],block=0,start=0,end=4)])
        with self.assertRaises(ValueError): store.read(sid,block=-1)

    def test_defaults_and_offline_transport(self):
        state=self.state()
        payload=request_payload('baidu','deal',state.config)
        self.assertEqual(payload['resource_type_filter'],[{'type':'web','top_k':5}])
        self.assertFalse(payload['query_policy']['enable_rewrite'])
        result=SearchTools(state).search('deal')
        self.assertEqual(result['providers'][0]['error_type'],'PermissionError')

    def test_malformed_response_is_failure_not_empty_success(self):
        state=self.state()
        result=SearchTools(state,transport=lambda *a:{'error':'bad'}).search('deal')
        self.assertEqual(result['providers'][0]['status'],'failed')
        self.assertEqual(state.data['cache'],{})


class PDFTests(unittest.TestCase):
    setUp = SearchTests.setUp
    state = SearchTests.state
    def test_real_text_pdf_keeps_page_locator(self):
        from io import BytesIO
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
        pdf=PdfWriter()
        page=pdf.add_blank_page(width=612,height=792)
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
        stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 50 700 Td (Closing remained conditional.) Tj ET')
        page[NameObject('/Contents')]=pdf._add_object(stream)
        buffer=BytesIO();pdf.write(buffer)
        state=self.state()
        store=SourceStore(state)
        sid=store.register('https://example.org/filing.pdf')
        store.save_raw(sid,buffer.getvalue(),'pdf')
        result=store.read(sid)
        self.assertEqual(result['spans'][0]['locator']['page'],1)
        self.assertIn('conditional',result['spans'][0]['text'])

class AgentTests(unittest.TestCase):
    setUp=SearchTests.setUp
    state=SearchTests.state

    def test_dynamic_followup_checkpoint_resume_and_finish(self):
        from finmy.search.pipeline import run_search
        requests=[]
        def transport(provider,payload,config):
            requests.append(payload['query'])
            return {'data':{'webPages':{'value':[{'url':'https://example.org/deal','name':'Deal'}]}}}
        def model(context):
            history=context['prior_actions']
            if not history: return {'action':'search','query':'deal announcement'}
            if len(history)==1: return {'action':'read_source','source':context['sources'][0]['source_id']}
            if len(history)==2: return {'action':'search','query':'deal actual closing','gap':'The read announcement only states conditions; an actual closing confirmation is missing'}
            source=context['sources'][0]
            return dict(action='finish',source_ids=[source['source_id']],gaps=['Closing not independently confirmed'],reason='low_gain')
        kwargs=dict(root=self.tmp.name,task_id='task',model=model,transport=transport,
                    fetcher=lambda u:(b'Agreement signed. Closing is conditional.','txt','utf-8'))
        result=run_search(self.task,config={'providers':['bocha']},max_steps=2,**kwargs)
        self.assertEqual(result['status'],'paused')
        result=run_search(**kwargs)
        self.assertEqual(result['status'],'finished')
        self.assertEqual(result['usage'],{'model':4,'search':2})
        self.assertEqual(requests,['deal announcement','deal actual closing'])
        self.assertIn('conditional',Path(result['builder_input_path']).read_text())
        again=run_search(**kwargs)
        self.assertEqual(again['usage'],result['usage'])

    def test_invalid_actions_stop_and_count_across_resume(self):
        from finmy.search.pipeline import run_search
        opts=dict(root=self.tmp.name,task_id='task',model=lambda c:'bad json')
        self.assertEqual(run_search(self.task,max_steps=2,**opts)['status'],'paused')
        result=run_search(**opts)
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['usage']['model'],3)

    def test_model_cap_no_fabricated_finish(self):
        from finmy.search.pipeline import run_search
        result=run_search(self.task,root=self.tmp.name,task_id='task',config={'max_model_calls':1},
            model=lambda c:dict(action='search',query='deal'),transport=lambda *a:{'data':{'webPages':{'value':[]}}})
        self.assertEqual(result['status'],'limit')
        self.assertIsNone(result['builder_input_path'])

    def test_batch_isolation_and_duplicate_ids(self):
        from finmy.search.pipeline import run_batch
        model=lambda c:dict(action='finish',selections=[],gaps=['No evidence'],reason='insufficient')
        tasks=[{'task_id':'bad','task':{}},{'task_id':'good','task':self.task}]
        result=run_batch(tasks,root=self.tmp.name,model=model)
        self.assertEqual([r['status'] for r in result],['failed','insufficient'])
        with self.assertRaises(ValueError): run_batch([tasks[1],tasks[1]],root=self.tmp.name)

class IntegrationTests(unittest.TestCase):
    setUp=SearchTests.setUp
    state=SearchTests.state

    def test_enhanced_full_entry_preserves_builder_boundary(self):
        from finmy.runner.search_pipeline_runner import run_search_pipeline
        def model(context):
            if not context['prior_actions']:
                return dict(action='read_source',source=context['sources'][0]['source_id'])
            s=context['sources'][0]
            return dict(action='finish',source_ids=[s['source_id']],gaps=[],reason='supported')
        task=dict(self.task,seed_urls=['https://example.org/a'])
        with patch('finmy.runner.search_pipeline_runner._create_pipeline') as factory:
            result=run_search_pipeline({'search_config':{'mode':'agent'}},'original',[],self.tmp.name,
                search_task=task,search_dependencies=dict(model=model,fetcher=lambda u:(b'Actual original source.','txt','utf-8')))
            factory.return_value.lm_build_pipeline_with_contents.assert_called_once()
            self.assertEqual(result['status'],'finished')
            self.assertIn('Actual original source.',result['all_text_content'][0])

    def test_incomplete_search_never_builds(self):
        from finmy.runner.search_pipeline_runner import run_search_pipeline
        with patch('finmy.runner.search_pipeline_runner._create_pipeline') as factory:
            result=run_search_pipeline({'search_config':{'mode':'agent'}},'event',[],self.tmp.name,
                search_dependencies={'model':lambda c:dict(action='finish',selections=[],gaps=['Need sources'],reason='insufficient')})
            factory.assert_not_called()
            self.assertEqual(result['status'],'insufficient')

    def test_cli_preflight_no_runtime_or_model(self):
        from finmy.search.__main__ import main
        taskfile=Path(self.tmp.name)/'task.json'
        taskfile.write_text(json.dumps(self.task))
        root=Path(self.tmp.name)/'runs'
        self.assertEqual(main(['--task',str(taskfile),'--task-id','event','--root',str(root)]),0)
        self.assertFalse(root.exists())

class ReviewRegressionTests(unittest.TestCase):
    setUp=SearchTests.setUp
    state=SearchTests.state

    def test_tampered_original_cannot_be_handed_off(self):
        state=self.state();store=SourceStore(state)
        sid=store.register('https://example.org/a');store.save_raw(sid,b'Original.','txt')
        read=store.read(sid);r=state.data['sources'][sid]['read_ranges'][0]
        (state.root/'sources'/sid/read['version']/'raw').write_bytes(b'Tampered.')
        with self.assertRaisesRegex(ValueError,'integrity'):
            assemble(state,[dict(source_id=sid,**r)])

    def test_full_context_guard_pauses_before_model_call(self):
        from finmy.search.pipeline import run_search
        result=run_search(self.task,root=self.tmp.name,task_id='task',config={'max_model_context_chars':1},
                          model=lambda c:self.fail('Context must be checked first'))
        self.assertEqual(result['status'],'paused')
        self.assertEqual(result['usage']['model'],0)

    def test_handoff_passes_sparse_input_validator(self):
        from finmy.generic import DataSample,UserQueryInput
        from types import SimpleNamespace
        from finmy.builder.sparse_build.runtime import validate_input
        state=self.state();store=SourceStore(state)
        sid=store.register('https://example.org/a');store.save_raw(sid,b'Verified location.','txt');store.read(sid)
        r=state.data['sources'][sid]['read_ranges'][0]
        payload=assemble(state,[dict(source_id=sid,**r)])
        validate_input(SimpleNamespace(user_query=UserQueryInput(**payload['user_query']),samples=[DataSample(**x) for x in payload['samples']]))

    def test_flags_do_not_accept_truthy_false_string(self):
        with self.assertRaises(ValueError): SearchConfig(allow_network='false')


if __name__ == "__main__":
    unittest.main()
