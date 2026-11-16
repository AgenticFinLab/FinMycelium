"""Shared search form defaults and request preview, without service initialization."""
from dataclasses import asdict
import json
from pathlib import Path

from finmy.search.state import SearchConfig
from finmy.search.protocol import request_parameters, request_record
from finmy.model_config import generation_parameters

BUDGET_FIELDS = (
    ('max_search_requests','累计搜索请求上限'),
    ('max_read_sources','不同阅读来源上限'),
    ('max_model_calls','累计模型请求上限'),
    ('max_read_chars','单次正文字符上限'),
    ('max_builder_material_chars','交付材料字符总上限'),
    ('max_model_context_chars','模型上下文字符上限'),
    ('timeout','单次请求超时（秒）'),
)


def load_defaults(path):
    defaults = asdict(SearchConfig())
    if Path(path).exists():
        defaults.update(json.loads(Path(path).read_text()))
    return asdict(SearchConfig(**defaults))


def clear_search_controls(session):
    # Research scopes/drafts, historic tasks and network consent are not rewritten.
    names = {'providers','count','model','tokens'} | {field for field,_ in BUDGET_FIELDS}
    for key in list(session):
        if key in {'ui-search-'+name for name in names} or key.startswith(('ui-search-model-', 'ui-search-count-')):
            session.pop(key, None)


def request_preview(model, generation):
    if not model:
        return {}
    options = request_parameters(model, generation_parameters(model, generation))
    if 'max_new_tokens' in options:
        options['max_tokens'] = options.pop('max_new_tokens')
    return request_record(options)


def finalization_label(data):
    trigger = data.get('termination_trigger') or data.get('finalization_trigger')
    return {'context_limit':'模型上下文达到上限', 'model_call_budget':'保留调用用于收尾',
            'no_reading_progress':'连续操作未增加材料或有效重点标记',
            'model_decision':'模型主动结束研究'}.get(trigger, trigger or '')
