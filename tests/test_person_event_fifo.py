"""A stalled first request must not prevent queued work or adoption."""
import threading
from copy import deepcopy

import pytest

from test_person_event_contract import payload
from test_person_event_pipeline import SyntheticEventModel
from finmy.person_epg.event.build import Construction
from finmy.person_epg.event.records import seed_facts
from finmy.person_epg.event.runtime import Execution, EventBuildConfig


def test_fifo_refills_slot_and_adopts_before_slowest_returns(tmp_path, payload):
    third_adopted = threading.Event()

    class SlowFirst(SyntheticEventModel):
        def __call__(self, system, user, name):
            if name == 'extract.0':
                assert third_adopted.wait(5), 'third task could not finish while first task was running'
            return super().__call__(system, user, name)

    config = EventBuildConfig(extraction_workers=2)
    model = SlowFirst()
    run = Execution(tmp_path, payload, config, model)
    build = Construction(run)
    save = build.save_facts

    def save_and_release():
        save()
        if len(build.coverage) > 2 and build.coverage[2]['status'] == 'processed':
            third_adopted.set()

    build.save_facts = save_and_release
    build.stage('extraction', build.extract)
    assert third_adopted.is_set()
    assert [c['task_id'] for c in run.state['calls']] == ['extract.0', 'extract.1', 'extract.2']
    assert [r['task_id'] for r in build.reports] == ['extract.1', 'extract.2', 'extract.0']
    assert all(c['status'] == 'accepted' for c in run.state['calls'])
    facts = deepcopy(build.facts)
    replay_model = SyntheticEventModel()
    replay = Construction(Execution(tmp_path, payload, config, replay_model, resume=True))
    replay.stage('extraction', replay.extract)
    assert not replay_model.calls
    assert replay.facts == facts


def test_adoption_failure_retains_remaining_responses(tmp_path, payload):
    run = Execution(tmp_path, payload, EventBuildConfig(extraction_workers=2),
                    lambda *args: {'ok': True})
    facts = seed_facts(payload)
    jobs = [('extract.' + str(i), 'system', {'role': 'extraction'}, facts) for i in range(4)]

    def fail(task_id):
        raise ValueError('adoption failed')

    with pytest.raises(ValueError, match='adoption failed'):
        run.prefetch_tasks(jobs, on_ready=fail)
    assert len(run.state['calls']) == 2  # A fatal adoption error stops dispatch; in-flight replies survive.
    assert all(c['status'] == 'prefetched' for c in run.state['calls'])
    assert all((tmp_path / c['prefetched_response']).is_file() for c in run.state['calls'])
