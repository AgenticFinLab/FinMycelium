"""Shared presentation for the local workbench; no execution or data mutation."""
from datetime import datetime
from zoneinfo import ZoneInfo
from html import escape
from pathlib import Path

import streamlit as st

THEME = {
    "base": "light", "primaryColor": "#187968", "backgroundColor": "#f6f8f7",
    "secondaryBackgroundColor": "#eef2f0", "textColor": "#243630",
    "font": 'system-ui, "WenQuanYi Zen Hei", "Microsoft YaHei", sans-serif',
    "baseFontSize": 15, "baseRadius": "0.5rem", "buttonRadius": "0.5rem",
    "borderColor": "#dce4df", "showWidgetBorder": True,
    "sidebar.backgroundColor": "#edf2ef", "sidebar.secondaryBackgroundColor": "#e3ebe6",
}


def theme_args():
    args = []
    for name, value in THEME.items():
        args.extend(["--theme." + name, str(value).lower() if isinstance(value, bool) else str(value)])
    return args


def apply_style():
    st.markdown("<style>" + Path(__file__).with_name("style.css").read_text() + "</style>", unsafe_allow_html=True)


def heading(title, subtitle=None):
    st.title(title)
    if subtitle:
        st.caption(subtitle)


def tone(label):
    if any(word in label for word in ("失败", "修订", "退回", "中断", "问题")):
        return "danger"
    if label in {"已通过", "已收录", "已确认", "已确认用于构建"}:
        return "success"
    if any(word in label for word in ("运行中", "构建中", "检索中", "启动中")):
        return "active"
    if any(word in label for word in ("检查", "审核", "待审", "不足", "上限", "暂停", "更新")):
        return "attention"
    return "neutral"


def badge(label):
    kind = tone(label)
    icon = {"success": "✓", "active": "◉", "attention": "◷", "danger": "!", "neutral": "○"}[kind]
    return f'<span class="fm-badge fm-{kind}">{icon} {escape(str(label))}</span>'


def status(label, detail=""):
    st.markdown('<div class="fm-status">' + badge(label) + '<span class="fm-muted">' + escape(str(detail)) + '</span></div>', unsafe_allow_html=True)


def table_status(label):
    icons = {"success": "✓", "active": "◉", "attention": "◷", "danger": "!", "neutral": "○"}
    return icons[tone(label)] + " " + label


def stats(items):
    """Label, value, explanatory text; values are observations, never quality scores."""
    content = ''.join(f'<div class="fm-stat"><span>{escape(str(label))}</span><strong>{escape(str(value))}</strong><small>{escape(str(note))}</small></div>' for label, value, note in items)
    st.markdown('<div class="fm-stats">' + content + '</div>', unsafe_allow_html=True)


def step_strip(labels, current):
    parts = []
    for i, label in enumerate(labels):
        cls = "current" if i == current else "past" if i < current else "future"
        aria = ' aria-current="step"' if i == current else ''
        parts.append(f'<li class="{cls}"{aria}><span>{i+1:02}</span>{escape(label)}</li>')
    st.markdown('<ol class="fm-steps" aria-label="事件工作流程">' + ''.join(parts) + '</ol>', unsafe_allow_html=True)


def empty(title, description):
    st.markdown(f'<div class="fm-empty"><strong>{escape(title)}</strong><p>{escape(description)}</p></div>', unsafe_allow_html=True)


def keep_ui_state():
    # Explicitly retain keyed filters and drafts while their page is not rendered.
    for key in list(st.session_state):
        if key.startswith("ui-"):
            st.session_state[key] = st.session_state[key]


def local_timestamp(value):
    try:
        return datetime.fromisoformat(value).astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return "未记录"
