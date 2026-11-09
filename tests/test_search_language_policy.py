import pytest
from finmy.search.language_policy import assess
from finmy.search.sources import SourceStore
from finmy.search.state import SearchConfig, SearchState
from finmy.search.handoff import assemble_sources, SourceSelectionError, eligible_source_ids
from finmy.search.agent import context_for


TEXTS = {
 'en': 'Berkshire Hathaway increased its investment in the oil company. Warren Buffett explained the purchase to shareholders during the annual meeting.',
 'zh': '伯克希尔公司增加了对西方石油公司的投资。巴菲特在年度股东大会上解释了购买这些股票的原因，并讨论了公司的长期投资计划。',
 'ru': 'Инвестиционная компания увеличила долю в нефтяной компании. Уоррен Баффет рассказал акционерам о долгосрочной стратегии инвестиций.',
 'fr': "La société a augmenté sa participation dans une entreprise pétrolière. Les actionnaires ont discuté de la stratégie financière et des investissements à long terme.",
 'de': 'Das Unternehmen erhöhte seine Beteiligung am Ölkonzern. Die Aktionäre diskutierten über die langfristige Anlagestrategie und die wirtschaftliche Entwicklung.',
 'ja': '同社は石油会社への投資を増やしました。株主総会で長期的な投資戦略について説明しました。今後の事業展開にも注目しています。',
}


@pytest.mark.parametrize('language', list(TEXTS))
def test_body_admission(language):
    doc = dict(blocks=[dict(text=TEXTS[language]*3)])
    result = assess(doc, ['en', 'zh'])
    assert result['allowed'] is (language in {'en', 'zh'})


def test_foreign_cached_source_excluded_without_losing_english(tmp_path):
    state = SearchState(tmp_path, 'case', task=dict(target_type='event', target_name='Investment',
        query_text='Buffett investment'), config=SearchConfig(source_languages=['en','zh']))
    store = SourceStore(state)
    ids = {}
    for lang in ('en','ru'):
        sid = store.register('https://example.test/'+lang, title='English misleading title')
        store.save_raw(sid, (TEXTS[lang]*3).encode(), 'txt')
        response = store.read(sid)
        ids[lang] = sid
        if lang == 'ru':
            assert response['status'] == 'language_excluded'
            assert response['spans'] == []
    assert eligible_source_ids(state) == [ids['en']]
    ctx = context_for(state)
    assert ctx['language_policy']['preference'] == ['en','zh']
    assert all(s['source_id'] != ids['ru'] for s in ctx['sources'])
    with pytest.raises(SourceSelectionError):
        assemble_sources(state, [ids['ru']], reason='supported', gaps=[])
    assemble_sources(state, [ids['en']], reason='supported', gaps=[])
    assert TEXTS['ru'] not in (state.run_dir/'builder_input.json').read_text()
    assert store.document(ids['ru'])['blocks']  # Raw/parsed original remains intact.
