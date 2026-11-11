import csv
import socket

import pytest

from finmy.dataset import DatasetCatalog, dataset_root, save_dataset_root, search_task, within
from dataset_fixture import fixture_dataset, csv_file, EVENT_FIELDS


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('No network permitted'))


def test_shared_config_and_empty_catalog_do_not_fall_back(tmp_path):
    root = fixture_dataset(tmp_path / 'dataset')
    csv_file(root / 'event-epg/events.csv', EVENT_FIELDS, [])
    csv_file(root / 'data/events/events.csv', ['event_id', 'title'], [{'event_id':'OLD', 'title':'Must not import'}])
    c = save_dataset_root(tmp_path / 'workspace', str(root))
    assert dataset_root(tmp_path / 'workspace') == str(root)
    assert c.events() == []
    assert c.people()[0]['person_id'] == 'PERSON-TEST'
    assert not (root / 'event-epg/events').exists()


def test_event_snapshot_and_scope_are_separate(tmp_path):
    root = fixture_dataset(tmp_path)
    snapshot = DatasetCatalog(root).select('EVENT-TEST')
    task = search_task(snapshot, period='2021–2023', include='Closing only', exclude='Earlier negotiations')
    assert task['research_scope']['period'] == '2021–2023'
    assert 'Closing only' in task['query_text']
    assert 'Included: The synthetic deal and closing' not in task['query_text']
    assert task['catalog']['event_row']['scope_include'] == 'The synthetic deal and closing'
    assert task['key_words'] == ['deal, closing']
    assert 'publication_start' not in task
    assert task['catalog']['event_dir'] == 'event-epg/events/EVENT-TEST'
    csv_file(root / 'event-epg/events.csv', EVENT_FIELDS, [])
    assert task['catalog']['event_id'] == 'EVENT-TEST'


def test_person_plan_identity_sources_and_scope(tmp_path):
    root = fixture_dataset(tmp_path)
    snapshot = DatasetCatalog(root).select('PERSON-EVENT-TEST', 'PERSON-TEST')
    assert snapshot['period'] == '1990s; exact dates unknown.'
    assert snapshot['scope_include'] == 'The appointment and term.'
    assert snapshot['source_leads'][0]['id'] == 'SRC01'
    assert snapshot['seed_urls'] == ['https://example.org/appointment']
    assert len(snapshot['files']) == 3
    assert snapshot['event_dir'] == 'person-epg/Example Person/Public service/Example appointment'
    task = search_task(snapshot, period='1995', include='Appointment only', exclude='Later term')
    assert 'Included: Appointment only' in task['query_text']
    assert 'Activity period: 1995' in task['query_text']
    assert 'Activity period: 1990s' not in task['query_text']
    assert 'is not source evidence' in task['query_text']
    assert task['target_type'] == 'event'
    assert 'event_id' not in task  # Not a workbench Store ID.


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'person', 'storyline'])
def test_plan_mismatch_is_actionable(tmp_path, mutation):
    root = fixture_dataset(tmp_path)
    path = root / 'person-epg/Example Person/research-plan.md'
    text = path.read_text()
    if mutation == 'missing': text = text.replace('### PERSON-EVENT-TEST ·', '### DIFFERENT ·')
    elif mutation == 'duplicate': text += '\n### PERSON-EVENT-TEST · Duplicate\n'
    elif mutation == 'person': text = text.replace('| person_id | PERSON-TEST |', '| person_id | WRONG |')
    else: text = text.replace('**Primary storyline:** STORY-TEST', '**Primary storyline:** OTHER')
    path.write_text(text)
    with pytest.raises(ValueError): DatasetCatalog(root).select('PERSON-EVENT-TEST', 'PERSON-TEST')


def test_paths_are_confined_and_header_only_valid(tmp_path):
    root = fixture_dataset(tmp_path / 'dataset')
    with pytest.raises(ValueError): within(root, '../outside')
    (root / 'link').symlink_to(tmp_path)
    with pytest.raises(ValueError): within(root, 'link/outside')
    with pytest.raises(ValueError): DatasetCatalog(tmp_path / 'missing')
    csv_file(root / 'event-epg/events.csv', EVENT_FIELDS, [dict(event_id='../bad', event_name='Bad', description='Example', scope_include='Example')])
    with pytest.raises(ValueError): DatasetCatalog(root).select('../bad')


def test_duplicate_ids_are_not_silently_selected(tmp_path):
    root = fixture_dataset(tmp_path)
    path = root / 'event-epg/events.csv'
    with path.open() as stream: rows = list(csv.DictReader(stream))
    csv_file(path, EVENT_FIELDS, rows + rows)
    with pytest.raises(ValueError, match='重复'): DatasetCatalog(root).events()


def test_person_events_cannot_share_a_summary_directory(tmp_path):
    from dataset_fixture import PROGRESS_FIELDS
    root = fixture_dataset(tmp_path)
    path = root / 'person-epg/Example Person/events.csv'
    with path.open() as stream: rows = list(csv.DictReader(stream))
    csv_file(path, PROGRESS_FIELDS, rows + [{**rows[0], 'event_id':'ANOTHER-EVENT'}])
    with pytest.raises(ValueError, match='目录重名'):
        DatasetCatalog(root).events('PERSON-TEST')
