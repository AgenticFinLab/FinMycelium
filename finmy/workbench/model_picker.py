"""Independent model service selection for search and construction."""
import streamlit as st

from finmy.model_config import MODEL_PROVIDERS, model_name
from finmy.workbench.domain import MODELS, TOKENHUB_MODELS


def model_picker(default, key, *, purpose, label='模型'):
    """Render outside forms so changing service refreshes the model field."""
    if purpose not in TOKENHUB_MODELS:
        raise ValueError('Model purpose must be search or build')
    try:
        current, identifier = model_name(default).split('/', 1)
    except ValueError:
        current, identifier = 'ark', ''
    services = ['ark', 'tokenhub']
    if current not in services:
        services.append(current)
    provider = st.selectbox(label + '服务', services, index=services.index(current),
                            format_func=MODEL_PROVIDERS.get, key=key + '-provider')
    value = identifier if provider == current else ''
    if provider == 'tokenhub':
        st.caption('读取本地 HUNYUAN_API_KEY 与 HUNYUAN_BASE_URL；不自动查询模型或调用接口。')
    presets = MODELS if provider == 'ark' else TOKENHUB_MODELS[purpose] if provider == 'tokenhub' else {}
    if presets:
        names = list(presets) + ['自定义']
        selected = next((name for name, mid in presets.items() if mid == value), '自定义')
        choice = st.selectbox(label, names, index=names.index(selected) if value else None,
                              placeholder='请选择模型', key=key + '-' + provider + '-preset')
        if choice is None:
            return ''
        if choice != '自定义':
            return provider + '/' + presets[choice]
    identifier = st.text_input(label + ' ID', value, key=key + '-' + provider + '-id',
        help='填写该服务控制台的调用模型 ID；服务名称或密钥备注不是模型 ID。')
    return provider + '/' + identifier.strip() if identifier.strip() else ''
