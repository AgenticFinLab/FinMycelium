"""Search-only request policy and unambiguous single-action JSON decoding."""
from copy import deepcopy
import json
import re

from finmy.model_config import model_name


# Verified TokenHub DeepSeek presets. The JSON-mode guide recommends disabled
# thinking. This policy is local to search; Builder parameters are independent.
# https://cloud.tencent.com/document/product/1823/132248
JSON_MODE_MODELS = {
    'tokenhub/deepseek/deepseek-flash',
    'tokenhub/deepseek-v4-pro-202606',
}


def request_parameters(lm_name, parameters):
    result = deepcopy(parameters)
    if model_name(lm_name) in JSON_MODE_MODELS:
        extra = result.get('extra_body', {})
        if not isinstance(extra, dict):
            raise ValueError('extra_body must be an object')
        # extra_body is merged last by the SDK. Remove conflicting spellings
        # before applying the search protocol, without mutating saved settings.
        for key in ('response_format', 'thinking', 'enable_thinking',
                    'thinking_budget', 'reasoning_effort'):
            result.pop(key, None)
            extra.pop(key, None)
        result['response_format'] = {'type': 'json_object'}
        extra['thinking'] = {'type': 'disabled'}
        result['extra_body'] = extra
    return result


def request_record(parameters):
    """Only execution controls, never keys, endpoint overrides or headers."""
    extra = parameters.get('extra_body')
    effective = {**parameters, **(extra if isinstance(extra, dict) else {})}
    fields = ('max_tokens', 'max_completion_tokens', 'temperature', 'top_p',
              'response_format', 'thinking', 'enable_thinking', 'reasoning_effort')
    return {key: deepcopy(effective[key]) for key in fields if key in effective}


class InvalidActionOutput(ValueError):
    pass


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidActionOutput('Duplicate JSON keys are not allowed')
        result[key] = value
    return result


def _invalid_constant(value):
    raise InvalidActionOutput('Action JSON must not contain NaN or Infinity')


def parse_action(raw):
    """Never pick a JSON prefix or translate model-specific tool markup."""
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        raise InvalidActionOutput('Empty action response; return one JSON object with an action')
    text = raw.strip()
    if text.startswith('```'):
        fenced = re.fullmatch(r'\x60{3}(?:json)?[ \t]*\r?\n(.*?)\r?\n\x60{3}', text, re.S | re.I)
        if not fenced:
            raise InvalidActionOutput('Return one JSON object, optionally inside a single JSON code fence')
        text = fenced[1].strip()
    try:
        action = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    except json.JSONDecodeError as exc:
        raise InvalidActionOutput(
            'Return exactly one JSON action object; no commentary, XML/DSML, or multiple actions') from exc
    if not isinstance(action, dict):
        raise InvalidActionOutput('Action must be one JSON object, not an array or scalar')
    return action
