"""Resolve ordinary event builder settings in a checkout or installed wheel."""
from importlib.resources import files
from pathlib import Path

import yaml


def load_builder_config(filename, *, path=None, local_default=False):
    if path is not None:
        source = Path(path)
    elif local_default and (local := Path("configs") / filename).exists():
        source = local
    else:
        source = files("configs").joinpath(filename)
    return yaml.safe_load(source.read_text(encoding="utf-8"))["builder_config"]
