"""Reusable search defaults; never run services from settings."""
from dataclasses import asdict

import streamlit as st

from finmy.search.state import SearchConfig, write_json
from finmy.workbench.model_picker import model_picker
from finmy.workbench.search_defaults import BUDGET_FIELDS, clear_search_controls, load_defaults, request_preview


def search_settings(store):
    path = store.root / "search" / "profile.json"
    defaults = load_defaults(path)
    model = model_picker(defaults.get("lm_name") or "", "ui-default-search-model", purpose="search", label="默认搜索模型")
    with st.form("search-defaults"):
        providers = st.multiselect("默认搜索服务", ["baidu", "bocha", "exa"], default=defaults["providers"])
        limits = defaults['max_results']
        counts = dict(limits) if isinstance(limits, dict) else {p: limits for p in ('baidu', 'bocha', 'exa')}
        for provider, label in [('baidu', '百度'), ('bocha', '博查'), ('exa', 'Exa')]:
            counts[provider] = st.number_input(label+' 每次查询结果上限', min_value=1, max_value=50,
                value=counts.get(provider, SearchConfig().results_for(provider)))
        values = {'max_results': counts}
        columns = st.columns(2)
        for i, (key, label) in enumerate(BUDGET_FIELDS):
            values[key] = columns[i % 2].number_input(label, min_value=1, value=defaults[key])
        output_tokens = st.number_input('模型单次输出 token 上限', min_value=1,
            value=defaults['generation_config'].get('max_tokens', SearchConfig().generation_config['max_tokens']))
        values['generation_config'] = {**defaults['generation_config'], 'max_tokens':output_tokens}
        st.caption('默认 Ark DeepSeek 的输出上限包含思考与答案；各任务仍累计计数，不要求用满预算。')
        with st.expander('模型预设请求参数'):
            try:
                st.json(request_preview(model, values['generation_config']))
            except ValueError as exc:
                st.caption(str(exc))
        st.caption("创建检索时可覆盖本次参数；已有任务保持原配置。")
        if st.form_submit_button("保存搜索默认配置", type="primary", icon=":material/save:"):
            try:
                config = SearchConfig(**{**defaults, **values, "providers": providers, "lm_name": model or None, "allow_network": False})
                write_json(path, asdict(config))
                # The next new task adopts these defaults; research drafts are retained.
                clear_search_controls(st.session_state)
                st.success("搜索默认配置已保存；新任务将采用这些默认值")
            except (ValueError, TypeError) as exc:
                st.error(str(exc))
