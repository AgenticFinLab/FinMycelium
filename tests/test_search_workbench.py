from pathlib import Path
import socket

from streamlit.testing.v1 import AppTest
from finmy.search.control import SearchController
from finmy.workbench import search_page

APP=Path(__file__).resolve().parents[1]/'finmy/workbench/app.py'

def find(items,label):return next(x for x in items if x.label==label)

def test_search_page_offline_lifecycle(tmp_path,monkeypatch):
    monkeypatch.setenv('FINMY_WORKBENCH_HOME',str(tmp_path))
    def blocked(*args):raise AssertionError('Unexpected network')
    monkeypatch.setattr(socket.socket,'connect',blocked)
    calls=[]
    def transport(*args):
        calls.append(1)
        return {'data':{'webPages':{'value':[{'url':'https://example.org/deal','name':'Announcement'}]}}}
    controller=SearchController(tmp_path/'search',transport=transport,
        fetcher=lambda u:(b'The deal closed after approval.','txt','utf-8'))
    monkeypatch.setattr(search_page,'get_controller',lambda root:controller)
    app=AppTest.from_file(str(APP)).run(timeout=30)
    app.sidebar.radio[0].set_value('检索').run()
    assert not app.exception
    find(app.selectbox,'检索模式').set_value('simple')
    find(app.text_input,'研究对象').set_value('Deal')
    find(app.text_area,'研究要求').set_value('Trace the closing')
    find(app.button,'保存检索任务').click().run()
    assert not app.exception
    assert calls==[]
    tid=controller.tasks()[0]
    find(app.button,'开始／继续').click().run()
    controller.threads[tid].join(5)
    app.run()
    assert not app.exception
    assert controller.inspect(tid)['status']=='finished'
    assert calls==[1]
    assert controller.inspect(tid)['usage']['model']==0
    assert any(x.value=='资料与交接' for x in app.subheader)
    # The source-preview form has another input with the same visible label.
    # Reassembly reads the separately keyed existing-handoff budget.
    app.number_input(key='length-'+tid).set_value(1)
    find(app.button,'重新组装').click().run()
    assert not app.exception
    assert controller.inspect(tid)['builder_input']['samples']==[]
    assert controller.inspect(tid)['selection']['max_material_chars']==1
    assert controller.inspect(tid)['selection']['omitted']
    # Legacy passage manifests can restore excluded passages without new calls.
    controller.reassemble(tid,60000)
    assert controller.inspect(tid)['builder_input']['samples']
    assert calls==[1]
    assert controller.inspect(tid)['usage']['model']==0

def test_invalid_form_does_not_create_task(tmp_path,monkeypatch):
    monkeypatch.setenv('FINMY_WORKBENCH_HOME',str(tmp_path))
    c=SearchController(tmp_path/'search')
    monkeypatch.setattr(search_page,'get_controller',lambda root:c)
    app=AppTest.from_file(str(APP)).run(timeout=30)
    app.sidebar.radio[0].set_value('检索').run()
    find(app.multiselect,'搜索服务').set_value([])
    find(app.button,'保存检索任务').click().run()
    assert not app.exception
    assert app.error
    assert not c.tasks()


def test_adopt_preserves_review_and_deduplicates(tmp_path):
    from finmy.workbench.store import Store
    from finmy.workbench.search_bridge import adopt_sources
    store=Store(tmp_path/'workbench')
    eid=store.create_events([{'event_name_en':'Deal'}])[0]
    c=SearchController(tmp_path/'search',transport=lambda *a:{'data':{'webPages':{'value':[{'url':'https://example.org/a'}]}}},fetcher=lambda u:(b'Transaction closed.','txt','utf-8'))
    tid=c.create(dict(target_type='event',target_name='Deal',query_text='Closing',event_id=eid),{},'simple')
    c.start(tid);c.threads[tid].join(5)
    assert adopt_sources(c,tid,store)==1
    assert adopt_sources(c,tid,store)==0
    assert len(store.sources(eid))==1
    assert store.status(eid)=='待审核资料'
    assert store.decision(eid,'evidence') is None
