"""One missing local seed must not discard other imported originals."""
from finmy.search.pipeline import run_search
from finmy.search.state import SearchState


def test_missing_seed_is_reported_and_valid_original_reaches_handoff(tmp_path):
    good = tmp_path / 'good.txt'
    good.write_text('A saved original describes the investment decision.')
    missing = tmp_path / 'missing.txt'
    task = dict(target_type='event', target_name='Investment', query_text='Investment history',
                local_files=[str(missing), str(good)])

    def model(context):
        entry = context['sources'][0]
        if not entry['reviewed']:
            return dict(action='read_source', source=entry['source_id'])
        return dict(action='finish', source_ids=[entry['source_id']], reason='supported', gaps=[])

    result = run_search(task, root=tmp_path / 'search', task_id='case', model=model)
    assert result['status'] == 'finished'
    assert result['seed_errors'] == [dict(kind='local_files', index=0, error_type='FileNotFoundError')]
    state = SearchState(tmp_path / 'search', 'case')
    assert len(state.data['sources']) == 1
    assert state.data['usage']['search'] == 0
    assert 'A saved original' in (state.run_dir / 'builder_input.json').read_text()


def test_explicit_resume_retries_only_missing_seed_without_resetting_usage(tmp_path):
    good, late = tmp_path / 'good.txt', tmp_path / 'late.txt'
    good.write_text('The first saved original.')
    task = dict(target_type='event', target_name='Investment', query_text='Investment history',
                local_files=[str(good), str(late)])
    read = lambda context: dict(action='read_source', source=context['sources'][0]['source_id'])
    first = run_search(task, root=tmp_path / 'search', task_id='case', model=read, max_steps=1)
    assert first['status'] == 'paused' and first['usage']['model'] == 1
    late.write_text('The previously missing original.')
    second = run_search(root=tmp_path / 'search', task_id='case', model=read, max_steps=1)
    assert second['seed_errors'] == []
    assert second['usage']['model'] == 2
    assert len(SearchState(tmp_path / 'search', 'case').data['sources']) == 2
