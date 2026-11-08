"""Minimal container doubles for offline tests when lmbase is not installed.

This is not a provider/transport implementation. Tests must supply their own
inference object. A real installation is always left untouched.
"""

import dataclasses
from importlib.machinery import PathFinder
import sys
import types


def install_missing_lmbase_containers():
    if PathFinder.find_spec("lmbase") is not None:
        return False

    names = ("lmbase", "lmbase.inference", "lmbase.inference.base",
             "lmbase.inference.api_call", "lmbase.utils", "lmbase.utils.tools")
    modules = {name: sys.modules.setdefault(name, types.ModuleType(name)) for name in names}

    class InferInput:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class InferCost:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class InferOutput:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

        def to_dict(self):
            return dict(self.__dict__)

    class LangChainAPIInference:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Offline container double cannot initialize an API transport")

    class BaseContainer:
        def export(self):
            return dataclasses.asdict(self) if dataclasses.is_dataclass(self) else dict(self.__dict__)

    base = modules["lmbase.inference.base"]
    api = modules["lmbase.inference.api_call"]
    util = modules["lmbase.utils.tools"]
    # Upgrade previously installed legacy test containers in place, so modules
    # that already imported their classes keep working. No real package exists.
    for owner, name, cls in ((base, "InferInput", InferInput), (base, "InferCost", InferCost),
                             (base, "InferOutput", InferOutput), (util, "BaseContainer", BaseContainer)):
        previous = getattr(owner, name, None)
        if previous is None:
            setattr(owner, name, cls)
        else:
            for attr in ("__init__", "export", "to_dict"):
                if attr in cls.__dict__:
                    setattr(previous, attr, cls.__dict__[attr])
    if not hasattr(api, "LangChainAPIInference"):
        api.LangChainAPIInference = LangChainAPIInference
    api.InferInput = base.InferInput
    for name in ("InferInput", "InferOutput", "InferCost"):
        setattr(modules["lmbase.inference"], name, getattr(base, name))
    return True
