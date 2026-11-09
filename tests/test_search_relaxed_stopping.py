from finmy.search.agent import _catalog_stalled, _read_marker, _repeated_query_repair
from finmy.search.state import SearchState, SearchConfig


def test_fourfold_stagnation_and_rejected_query_threshold(tmp_path):
    state = SearchState(tmp_path, 'case', task=dict(target_type='event', target_name='Deal',
        query_text='Trace deal'), config=SearchConfig(early_stop_multiplier=4))
    state.data['catalog_progress'] = dict(offsets=[0])
    for i in range(12):
        assert _catalog_stalled(state, {}, dict(action='list_sources', offset=0),
                                _read_marker(state)) is (i == 11)
        assert _repeated_query_repair(state, dict(action='search', query='same'),
            dict(providers=[dict(status='invalid_query')])) is (i == 11)
    assert state.data['usage'] == dict(search=0, model=0)
