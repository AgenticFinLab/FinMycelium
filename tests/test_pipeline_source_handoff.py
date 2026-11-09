"""Single-event content path binds agent provenance to raw IDs before matching.

Execute the real pipeline method with local stage doubles, without importing
optional PDF, database or model runtimes just to test the handoff contract.
"""
import ast
import copy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

def pipeline(registry):
    tree = ast.parse((Path(__file__).resolve().parents[1] / 'finmy/pipeline.py').read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'FinmyPipeline')
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef)
                  and node.name == 'lm_build_pipeline_with_contents')
    namespace = {'copy': copy}
    exec(compile(ast.Module(body=[method], type_ignores=[]), 'finmy/pipeline.py', 'exec'), namespace)
    query = SimpleNamespace(extras={'existing': 'metadata'})
    subject = SimpleNamespace(
        config={'source_registry': registry} if registry is not None else {},
        logger=Mock(), data_manager=Mock(),
        create_raw_data_records=Mock(return_value=[SimpleNamespace(raw_data_id='raw-B'), SimpleNamespace(raw_data_id='raw-A')]),
        store_raw_data=Mock(), create_and_store_user_query=Mock(return_value=query),
        summarize_user_query=Mock(), _process_matching=Mock(return_value=['second sample', 'first sample']),
        store_meta_samples=Mock(), create_build_input=lambda request, samples: SimpleNamespace(user_query=request, samples=samples),
        builder=SimpleNamespace(run=lambda build: build),
    )
    return subject, namespace['lm_build_pipeline_with_contents']


def test_event_provenance_follows_raw_ids_through_sample_reordering():
    registry = {'saved_0': {'source_id': 'S1', 'source_version': 'v1'},
                'saved_1': {'source_id': 'S2', 'source_version': 'v2'}}
    subject, run = pipeline(registry)
    result = run(subject, ['First body', 'Second body'], 'Deal', ['closing'])
    sources = result.user_query.extras['source_registry']
    assert sources == {'raw-B': registry['saved_0'], 'raw-A': registry['saved_1']}
    assert result.samples == ['second sample', 'first sample']
    assert result.user_query.extras['existing'] == 'metadata'
    sources['raw-B']['source_version'] = 'changed'
    assert registry['saved_0']['source_version'] == 'v1'


def test_event_inputs_without_registry_or_with_partial_metadata_still_build():
    subject, run = pipeline(None)
    assert run(subject, ['First', 'Second'], 'Deal', []).user_query.extras == {'existing': 'metadata'}
    subject, run = pipeline({'saved_0': {'source_id': 'S1'}, 'saved_1': None, 'saved_2': {'source_id': 'stale'}})
    result = run(subject, ['First', 'Second'], 'Deal', [])
    assert result.user_query.extras['source_registry'] == {'raw-B': {'source_id': 'S1'}}
    assert result.user_query.extras['source_registry_missing'] == ['raw-A']
    assert result.samples == ['second sample', 'first sample']
    subject.logger.warning.assert_called_once()
