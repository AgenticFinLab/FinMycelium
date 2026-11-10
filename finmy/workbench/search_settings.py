"""Reusable search defaults; never run services from settings."""
from dataclasses import asdict
import json

import streamlit as st

from finmy.search.state import SearchConfig, write_json


def search_settings(store):
    path = store.root / "search" / "profile.json"
    defaults = asdict(SearchConfig())
    if path.exists():
        defaults.update(json.loads(path.read_text()))
    with st.form("search-defaults"):
        providers = st.multiselect("默认搜索服务", ["baidu", "bocha", "exa"], default=defaults["providers"])
        model = st.text_input("默认搜索模型（provider/model）", defaults.get("lm_name") or "")
        values = {}
        columns = st.columns(2)
        for i, (key, label) in enumerate([("max_results", "每次查询每家结果数"), ("max_search_requests", "累计搜索请求上限"),
                           ("max_read_sources", "读取来源上限"), ("max_model_calls", "搜索模型请求上限"),
                           ("max_builder_material_chars", "交付正文字符预算")]):
            values[key] = columns[i % 2].number_input(label, min_value=1, value=defaults[key])
        st.caption("创建检索时可覆盖本次参数；已有任务保持原配置。")
        if st.form_submit_button("保存搜索默认配置", type="primary", icon=":material/save:"):
            try:
                config = SearchConfig(**{**defaults, **values, "providers": providers, "lm_name": model or None, "allow_network": False})
                write_json(path, asdict(config))
                # The next new task adopts these defaults; research drafts are retained.
                for key in ("providers", "count", "model", "max_search_requests", "max_read_sources", "max_model_calls", "max_builder_material_chars"):
                    st.session_state.pop("ui-search-"+key, None)
                st.success("搜索默认配置已保存；新任务将采用这些默认值")
            except (ValueError, TypeError) as exc:
                st.error(str(exc))
