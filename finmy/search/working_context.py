"""Serialized decision-context size accounting."""
import json


def context_sizes(context, serialize):
    return dict(total_chars=len(serialize(context)), components={
        k: len(json.dumps(v, ensure_ascii=False)) for k, v in context.items()})
