"""Model service names and local configuration; no SDK imports or API calls."""
import os
import re
from copy import deepcopy
from urllib.parse import urlsplit


MODEL_PROVIDERS = {
    'ark': 'Volcengine Ark',
    'tokenhub': 'Tencent TokenHub',
    'deepseek': 'DeepSeek',
    'openai': 'OpenAI',
    'qwen': 'Qwen',
    'aihubmix': 'AIHubMix',
}
TOKENHUB_BASE_URL = 'https://tokenhub.tencentmaas.com/v1'

# Sampling policy for supported presets, applied after inherited Builder settings.
# Unlisted model IDs keep their supplied configuration.
# Ark Agent recommendations: https://docs.volcengine.com/docs/ark/agent-model-invocation-practice
# Ark model exceptions: https://docs.volcengine.com/docs/ark/chat-api
# GLM: https://cloud.tencent.com/document/product/1823/132061
# DeepSeek: https://cloud.tencent.com/document/product/1823/132248
# Hy4: https://intl.cloud.tencent.com/zh/document/product/1300/80695
# top_p=1 is the platform default where the model guide gives no override:
# https://cloud.tencent.com/document/product/1823/135872
# Kimi fixes its sampling values and recommends omitting them from requests.
MODEL_SAMPLING = {
    'ark/doubao-seed-2-0-pro-260215': {'temperature': 1.0, 'top_p': 0.95},
    'ark/doubao-seed-2-1-lite-260915': {'temperature': 1.0, 'top_p': 0.95},
    'ark/glm-5-2-260617': {'temperature': 1.0, 'top_p': 0.95},
    'ark/deepseek-v4-pro-ga-260813': {'temperature': 1.0, 'top_p': 0.95},
    'ark/deepseek-v4-1-flash-261017': {'temperature': 1.0, 'top_p': 0.95},
    'tokenhub/glm-5.3': {'temperature': 1.0, 'top_p': 0.95},
    'tokenhub/glm-5.3-flash': {'temperature': 1.0, 'top_p': 0.95},
    'tokenhub/deepseek-v4-pro-202606': {'temperature': 1.0, 'top_p': 1.0},
    'tokenhub/deepseek/deepseek-flash': {'temperature': 1.0, 'top_p': 1.0},
    'tokenhub/hy4': {'temperature': 0.9, 'top_p': 1.0},
    'tokenhub/kimi-k3.1-pro': {},
}



def model_name(value, *, default_provider='ark'):
    """Qualify legacy bare Ark IDs; preserve namespaced remote model IDs."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Specify a model ID')
    value = value.strip()
    provider, identifier = value.split('/', 1) if '/' in value else (default_provider, value)
    provider = provider.lower()
    if provider not in MODEL_PROVIDERS:
        raise ValueError('Unsupported model provider')
    if (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}', identifier)
            or any(part in {'', '.', '..'} for part in identifier.split('/'))
            or '://' in identifier):
        raise ValueError('Invalid model ID')
    return provider + '/' + identifier


def api_key_variable(provider):
    """TokenHub uses the existing HUNYUAN_API_KEY environment setting."""
    if provider not in MODEL_PROVIDERS:
        raise ValueError('Unsupported model provider')
    return 'HUNYUAN_API_KEY' if provider == 'tokenhub' else provider.upper() + '_API_KEY'


def generation_parameters(lm_name, parameters):
    """Apply preset sampling and protocol fields without changing caller limits."""
    name = model_name(lm_name)
    if parameters is None and name not in MODEL_SAMPLING:
        return None
    result = deepcopy(parameters) if parameters is not None else {}
    if name in MODEL_SAMPLING:
        extra = result.get('extra_body', {})
        if not isinstance(extra, dict):
            raise ValueError('extra_body must be an object')
        # The SDK merges extra_body last; remove inherited sampling there too.
        for key in ('temperature', 'top_p'):
            result.pop(key, None)
            extra.pop(key, None)
        result.update(MODEL_SAMPLING[name])
        if name == 'ark/deepseek-v4-1-flash-261017':
            # Ark fixes top_p=1 outside thinking mode. Respect caller controls;
            # do not enable/disable thinking or alter the requested effort.
            thinking = extra.get('thinking', result.get('thinking', {}))
            effort = extra.get('reasoning_effort', result.get('reasoning_effort'))
            if (isinstance(thinking, dict) and thinking.get('type') == 'disabled') or effort == 'none':
                result['top_p'] = 1.0
    if name == 'tokenhub/kimi-k3.1-pro':
        # https://cloud.tencent.com/document/product/1823/132232
        limits = [k for k in ('max_new_tokens', 'max_tokens', 'max_completion_tokens') if k in result]
        if len(limits) > 1:
            raise ValueError('Specify only one output token limit for Kimi K3.1 Pro')
        if limits:
            result['max_completion_tokens'] = result.pop(limits[0])
        # The service fixes these values; ordinary Builder defaults are not valid overrides.
        fixed = ('temperature', 'top_p', 'n', 'presence_penalty', 'frequency_penalty')
        for key in fixed:
            result.pop(key, None)
        extra = result.get('extra_body', {})
        if not isinstance(extra, dict):
            raise ValueError('extra_body must be an object')
        for key in fixed:
            extra.pop(key, None)
        if any(k in result or k in extra for k in ('thinking', 'enable_thinking', 'thinking_budget')):
            raise ValueError('Kimi K3.1 Pro uses reasoning_effort instead of thinking controls')
        effort = extra.get('reasoning_effort', result.get('reasoning_effort'))
        if effort is not None and effort not in {'low', 'high', 'max'}:
            raise ValueError('Kimi K3.1 Pro reasoning_effort must be low, high or max')
    return result


def tokenhub_base_url():
    """Accept an origin or /v1 SDK base; never guess a different region."""
    value = os.environ.get('HUNYUAN_BASE_URL', '').strip() or TOKENHUB_BASE_URL
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path.rstrip('/') not in {'', '/v1'}):
        raise ValueError('HUNYUAN_BASE_URL must be an HTTPS origin or /v1 API base')
    return value.rstrip('/') + ('/v1' if not parsed.path.rstrip('/') else '')
