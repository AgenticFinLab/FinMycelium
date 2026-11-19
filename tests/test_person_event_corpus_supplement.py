import json

import pytest

from finmy.person_epg.event.build import run_event
from finmy.person_epg.event.records import fingerprint
from finmy.person_epg.event.corpus_supplement import TASK_ID
from test_person_event_contract import payload
from test_person_event_pipeline import SyntheticEventModel


class CorpusModel(SyntheticEventModel):
    def __init__(self, invalid=False):
        super().__init__()
        self.supplements = []
        self.invalid = invalid

    def __call__(self, system, user, name):
        if name != TASK_ID:
            return super().__call__(system, user, name)
        task = json.loads(user)['task']
        self.supplements.append(task)
        if self.invalid:
            return {'read_requests': [{'tool': 'search', 'query': 'extra'}]}
        record = task['existing']['actions'][0]
        document = task['documents'][0]
        return dict(entities=[], actions=[], contexts=[], relation_candidates=[], evidence=[], pending=[],
                    support_additions=[dict(collection='actions', object_id=record['action_id'],
                                            target='/description', mode='A', reason='Second reading of the passage.',
                                            sample_id=document['sample_id'], quote=document['text'])])


@pytest.mark.parametrize('invalid', [False, True])
def test_fresh_full_corpus_run_preserves_quotations_and_one_call_on_resume(tmp_path, payload, invalid):
    model = CorpusModel(invalid)
    state = run_event(payload, tmp_path, dict(full_corpus_supplement=True, max_calls=30), model=model)
    assert state['execution_status'] == 'finished'
    assert state['corpus_supplement']['status'] == ('invalid_response' if invalid else 'processed')
    assert [d['text'] for d in model.supplements[0]['documents']] == [s['content'] for s in payload['samples']]
    assert state['coverage'] and all(v['body_status'] == 'processed' for v in state['coverage'])
    call = next(c for c in state['calls'] if c['task_id'] == TASK_ID)
    assert call['reasoning_effort'] == 'low'
    assert all(c['reasoning_effort'] == 'low' for c in state['calls'] if c['task_id'].startswith('extract.'))
    if not invalid:
        assert state['corpus_supplement']['accepted'] == 1
        snapshot = json.loads((tmp_path / state['organization_snapshot']).read_text())['snapshot']
        assert any(c['task_id'] == TASK_ID for c in snapshot['origin']['calls'])
    graph = json.loads((tmp_path / state['output']).read_text())
    resumed = run_event(payload, tmp_path, model=model, resume=True)
    assert len(model.supplements) == 1
    assert len([c for c in resumed['calls'] if c['task_id'] == TASK_ID]) == 1
    assert fingerprint(json.loads((tmp_path / resumed['output']).read_text())) == fingerprint(graph)
