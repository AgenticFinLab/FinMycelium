"""Offline collection lifecycle tests. All mutations are under pytest tmp_path."""
from copy import deepcopy
import csv
import io
import json
from pathlib import Path

import pytest

from test_event_collection import setup, finish, offline
from finmy.dataset import DatasetCatalog, catalog_event_directory
from finmy.search.state import digest
from finmy.workbench.build_tasks import BuildController
from finmy.workbench.catalog_actions import (confirm_search, collected_search, search_collection,
                                            withdraw_search, replace_folder)
from finmy.workbench.graph_collection import (review_template, collect_graph, graph_collection,
                                            withdraw_graph, build_collection)
from finmy.workbench.build_page import build_status
from finmy.workbench.workflow import search_status_code


@pytest.mark.parametrize('person', [True, False])
def test_independent_material_confirmation_withdrawal_and_recollection(setup, person):
    root, store, search, calls = setup
    tid, catalog = finish(setup, person=person)
    original = deepcopy(search.inspect(tid))
    with pytest.raises(ValueError, match='确认'):
        confirm_search(search, tid, expected_revision=original['handoff_revision'], reviewer='Reviewer')
    receipt = confirm_search(search, tid, expected_revision=original['handoff_revision'], reviewer='Reviewer', confirmed=True)
    assert BuildController(store).tasks() == [] and search.inspect(tid) == original
    assert calls == ['search']
    current = collected_search(original, tid)
    assert current and current['manifest']['build_task_id'] is None
    assert search_status_code({**original, 'task_id': tid}) == 'collected'
    assert current['manifest']['input_sample_count'] == 2
    with pytest.raises(ValueError, match='变化'):
        withdraw_search(catalog, expected_manifest='stale', reviewer='R', reason='Reconsider')
    withdrawn = withdraw_search(catalog, expected_manifest=current['sha256'], reviewer='R', reason='Reconsider')
    assert not (catalog_event_directory(catalog)/'search').exists()
    assert (root/'output/collections'/withdrawn['action_id']/'builder-input.json').exists()
    assert not collected_search(original, tid)
    confirm_search(search, tid, expected_revision=original['handoff_revision'], reviewer='R', confirmed=True)
    assert search.inspect(tid) == original


def test_independent_confirmation_then_build_keeps_exact_input(setup):
    root, store, search, _ = setup
    tid, catalog = finish(setup)
    data = search.inspect(tid)
    confirm_search(search, tid, expected_revision=data['handoff_revision'], reviewer='R', confirmed=True)
    before = search_collection(catalog)
    builds = BuildController(store)
    bid = builds.create_person(search, tid, confirmed=True)
    assert json.loads(before['files']['builder-input.json']) == builds.inspect(bid)['body']['input']
    after = search_collection(catalog)
    assert after['manifest']['build_task_id'] == bid
    withdraw_search(catalog, expected_manifest=after['sha256'], reviewer='R', reason='Remove from catalog')
    assert builds.current(builds.inspect(bid)) and builds.inspect(bid)['status'] == 'ready'
    assert before['files']['builder-input.json'] == after['files']['builder-input.json']


def test_material_confirmation_rejects_exclusion_stale_revision_and_manual_changes(setup):
    _, _, search, _ = setup
    tid, catalog = finish(setup)
    data = search.inspect(tid)
    with pytest.raises(ValueError, match='变化'):
        confirm_search(search, tid, expected_revision='old', reviewer='R', confirmed=True)
    search.set_build_disposition(tid, 'excluded')
    with pytest.raises(ValueError, match='不参与'):
        confirm_search(search, tid, expected_revision=data['handoff_revision'], reviewer='R', confirmed=True)
    search.set_build_disposition(tid, 'pending')
    confirm_search(search, tid, expected_revision=data['handoff_revision'], reviewer='R', confirmed=True)
    folder = catalog_event_directory(catalog)/'search'
    (folder/'sources.csv').write_text('User editing')
    with pytest.raises(ValueError):
        confirm_search(search, tid, expected_revision=data['handoff_revision'], reviewer='R', confirmed=True)
    assert (folder/'sources.csv').read_text() == 'User editing'


@pytest.fixture
def draft(setup):
    root, store, _, _ = setup
    catalog = DatasetCatalog(root).select('PERSON-EVENT-TEST', 'PERSON-TEST')
    fixture = Path(__file__).parent/'fixtures/person_event'
    replacements = {'DEMO-PERSON-0001': 'PERSON-TEST', 'DEMO-STORYLINE-01': 'STORY-TEST',
                    'DEMO-EVENT-01': 'PERSON-EVENT-TEST'}
    def read(name):
        text = (fixture/name).read_text()
        for old, new in replacements.items(): text = text.replace(old, new)
        return json.loads(text)
    graph, payload = read('graph.json'), read('input.json')
    from finmy.person_epg.event.records import json_bytes
    from finmy.person_epg.event.validation import check_graph
    from finmy.person_epg.rendering import save_gantt
    from finmy.workbench.store import now
    bid = 'PBUILD-offline'
    directory = root/'output/builds'/bid
    out = directory/'attempts/0001'; out.mkdir(parents=True)
    gbytes, pbytes = json_bytes(graph), json_bytes(payload)
    (out/'epg.json').write_bytes(gbytes); (directory/'input.json').write_bytes(pbytes)
    report = check_graph(graph, payload)
    assert report['valid'], report
    report.update(input_sha256=digest(pbytes), graph_sha256=digest(gbytes))
    (out/'checks.json').write_bytes(json_bytes(report))
    visual = save_gantt(graph, directory, out/'epg.json', result_status='draft')
    assert visual['status'] == 'completed'
    state = dict(execution_status='finished', result_status='draft', render_status='completed',
        output='attempts/0001/epg.json', checks='attempts/0001/checks.json',
        graph_sha256=digest(gbytes), input_sha256=digest(pbytes), checks_sha256=digest(json_bytes(report)), visualization=visual)
    (directory/'state.json').write_text(json.dumps(state))
    body = dict(kind='person_event', catalog=catalog, artifact_directory=str(directory), input=payload,
                input_hash=digest(payload), event=dict(event_id=catalog['event_id']), run_state=state)
    builds = BuildController(store)
    (builds.root/bid).mkdir(parents=True, exist_ok=True)
    with store.connection() as db:
        db.execute('INSERT INTO build_tasks VALUES(?,?,?,?,?)', (bid, catalog['event_id'], json.dumps(body), 'completed', now()))
    return root, builds, bid, catalog


def approved(builds, bid):
    import yaml
    template = review_template(builds.inspect(bid))
    meta = yaml.safe_load(template.split('---')[1])
    meta.update(decision='accepted', reviewer='Offline reviewer', reviewed_at='2026-11-17')
    return ('---\n'+yaml.safe_dump(meta)+'---\n\nChecked attribution, evidence and relations; remaining unknowns are explicit.\n').encode()


def test_graph_collection_withdrawal_and_recollection_preserve_run(draft):
    root, builds, bid, catalog = draft
    original = deepcopy(builds.inspect(bid)); directory = Path(original['body']['artifact_directory'])
    runtime = {p: p.read_bytes() for p in directory.rglob('*') if p.is_file()}
    review = approved(builds, bid)
    with pytest.raises(ValueError, match='确认'):
        collect_graph(builds, bid, review)
    receipt = collect_graph(builds, bid, review, confirmed=True)
    assert build_status(builds.inspect(bid)) == ('accepted', '已收录')
    assert graph_collection(catalog)['review']['build_task_id'] == bid
    assert DatasetCatalog(root).events('PERSON-TEST')[0]['status'] == 'accepted'
    with pytest.raises(ValueError, match='撤回'):
        builds.set_disposition(bid, 'discarded', reason='Use another graph')
    current = graph_collection(catalog)
    withdraw_graph(catalog, expected_review=current['review_sha256'], reviewer='R', reason='Re-review')
    assert not (catalog_event_directory(catalog)/'epg').exists()
    assert DatasetCatalog(root).events('PERSON-TEST')[0]['status'] == 'in_review'
    assert build_status(builds.inspect(bid))[0] == 'completed'
    collect_graph(builds, bid, review, confirmed=True)
    assert builds.inspect(bid) == original
    assert all(p.read_bytes() == raw for p, raw in runtime.items())
    assert len(list((root/'workbench/collections').glob('*.json'))) == 3


def test_discard_is_reversible_and_does_not_fake_execution_status(draft):
    _, builds, bid, _ = draft
    before = builds.inspect(bid)
    builds.set_disposition(bid, 'discarded', reason='Alternative experiment')
    row = builds.inspect(bid)
    assert row['status'] == 'completed' and row['body']['run_state'] == before['body']['run_state']
    assert build_status(row)[0] == 'discarded'
    with pytest.raises(ValueError, match='舍弃'):
        collect_graph(builds, bid, approved_from_before(before), confirmed=True)
    builds.set_disposition(bid, 'pending')
    assert build_status(builds.inspect(bid))[0] == 'completed'
    assert len(builds.inspect(bid)['body']['disposition_history']) == 2


def approved_from_before(row):
    import yaml
    meta = yaml.safe_load(review_template(row).split('---')[1])
    meta.update(decision='accepted', reviewer='R', reviewed_at='2026-11-17')
    return ('---\n'+yaml.safe_dump(meta)+'---\n\nChecked.\n').encode()


@pytest.mark.parametrize('field', ['build_task_id', 'event_id', 'graph_sha256', 'input_sha256', 'gantt_sha256', 'decision'])
def test_review_must_bind_the_exact_accepted_artifacts(draft, field):
    _, builds, bid, catalog = draft
    import yaml
    review = approved(builds, bid)
    meta = yaml.safe_load(review.decode().split('---')[1])
    meta[field] = '0'*64 if field.endswith('sha256') else 'other'
    raw = ('---\n'+yaml.safe_dump(meta)+'---\n\nReviewed.\n').encode()
    with pytest.raises(ValueError): collect_graph(builds, bid, raw, confirmed=True)
    assert not (catalog_event_directory(catalog)/'epg').exists()


def test_partial_is_not_accepted_and_tampering_is_not_silently_withdrawn(draft):
    _, builds, bid, catalog = draft
    review = approved(builds, bid)
    row = builds.inspect(bid); builds.save(bid, 'partial', row['body'])
    with pytest.raises(ValueError): collect_graph(builds, bid, review, confirmed=True)
    builds.save(bid, 'completed', row['body'])
    collect_graph(builds, bid, review, confirmed=True)
    old = graph_collection(catalog)
    (catalog_event_directory(catalog)/'epg/gantt.html').write_text('manual change')
    assert not build_collection(builds.inspect(bid))
    with pytest.raises(ValueError): withdraw_graph(catalog, expected_review=old['review_sha256'], reviewer='R', reason='Withdraw')


def test_collection_rolls_back_when_record_write_fails(draft, monkeypatch):
    _, builds, bid, catalog = draft
    from finmy.workbench import graph_collection as module
    path = Path(catalog['root'])/'person-epg/Example Person/events.csv'; original = path.read_bytes()
    def failed(*a, **k): raise OSError('Synthetic disk error')
    monkeypatch.setattr(module, 'save_action', failed)
    with pytest.raises(OSError): collect_graph(builds, bid, approved(builds, bid), confirmed=True)
    assert path.read_bytes() == original and not (catalog_event_directory(catalog)/'epg').exists()


def test_external_collection_is_recognized_and_other_task_is_not(draft):
    root, builds, bid, catalog = draft
    # External review/collection may write the same three files and registry,
    # without a workbench receipt. Recognition still verifies their bindings.
    from finmy.workbench.graph_collection import reviewed_artifacts
    from finmy.dataset import accepted_artifact_paths
    row = builds.inspect(bid); item = reviewed_artifacts(row)
    folder = catalog_event_directory(catalog)/'epg'; folder.mkdir(parents=True)
    (folder/'epg.json').write_bytes(item['epg'])
    (folder/'gantt.html').write_bytes(item['gantt'])
    (folder/'review.md').write_bytes(approved(builds, bid))
    table = root/'person-epg/Example Person/events.csv'
    rows = list(csv.DictReader(io.StringIO(table.read_text())))
    rows[0].update(status='accepted', **accepted_artifact_paths(catalog))
    with table.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    assert build_collection(row)
    other = deepcopy(row); other['id'] = 'PBUILD-other'
    assert not build_collection(other)
    assert not (root/'workbench/collections').exists()


def test_search_receipt_failure_rolls_back_previous_collection(setup, monkeypatch):
    _, store, search, _ = setup
    from finmy.workbench import catalog_actions
    tid, catalog = finish(setup)
    BuildController(store).create_person(search, tid, confirmed=True)
    before = search_collection(catalog)
    def failed(*a, **k): raise OSError('Synthetic archive failure')
    monkeypatch.setattr(catalog_actions, 'save_action', failed)
    with pytest.raises(OSError):
        confirm_search(search, tid, expected_revision=search.inspect(tid)['handoff_revision'], reviewer='R', confirmed=True)
    assert search_collection(catalog)['files'] == before['files']


def test_symlink_collection_protected(draft, tmp_path):
    _, builds, bid, catalog = draft
    other = tmp_path/'elsewhere'; other.mkdir()
    parent = catalog_event_directory(catalog); parent.mkdir(parents=True)
    (parent/'epg').symlink_to(other, target_is_directory=True)
    with pytest.raises(ValueError): collect_graph(builds, bid, approved(builds, bid), confirmed=True)
    assert list(other.iterdir()) == []


def test_folder_swap_failure_keeps_original(tmp_path, monkeypatch):
    folder = tmp_path/'epg'; folder.mkdir(); (folder/'epg.json').write_bytes(b'original')
    rename = Path.rename
    def fail_pending(self, target):
        if self.name.startswith('.collection-'): raise OSError('Synthetic rename failure')
        return rename(self, target)
    monkeypatch.setattr(Path, 'rename', fail_pending)
    with pytest.raises(OSError):
        with replace_folder(folder, {'epg.json':b'new'}): pass
    assert (folder/'epg.json').read_bytes() == b'original'
