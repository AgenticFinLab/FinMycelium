from pathlib import Path

import pytest

from finmy.runner.configuration import load_builder_config


def test_cli_local_default_and_explicit_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    name = 'build_only_sparse.yml'
    assert load_builder_config(name, local_default=True)['builder_type'] == 'SparseRagBuilder'
    local = Path('configs', name)
    local.parent.mkdir()
    local.write_text('builder_config: {builder_type: local}\n')
    assert load_builder_config(name, local_default=True)['builder_type'] == 'local'
    assert load_builder_config(name)['builder_type'] == 'SparseRagBuilder'
    with pytest.raises(FileNotFoundError):
        load_builder_config(name, path='missing.yml', local_default=True)
