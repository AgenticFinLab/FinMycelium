"""Show the person drafts the team has explicitly picked for content review."""
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import streamlit as st

from finmy.dataset import dataset_root
from finmy.workbench.build_tasks import BuildController
from finmy.workbench.graph_collection import reviewed_artifacts, template_for_binding
from finmy.workbench.workflow import navigate


def _review_bundle(artifacts):
    buffer = BytesIO()
    with ZipFile(buffer, 'w', compression=ZIP_DEFLATED) as archive:
        for key, name in [('epg', 'epg.json'), ('gantt', 'gantt.html'), ('input', 'input.json')]:
            archive.writestr(name, artifacts[key])
        archive.writestr('review.md', template_for_binding(artifacts['binding']))
    return buffer.getvalue()


def person_review_panel(store, item):
    root = dataset_root(store.root)
    binding = item['binding']
    task_id = binding['build_task_id']
    st.write(f"{task_id} · 图 {binding['graph_sha256'][:12]} · 输入 {binding['input_sha256'][:12]}")
    controller = BuildController(store)
    try:
        row = controller.inspect(task_id)
    except ValueError:
        st.info('这台机器只有共享送审记录。请从保存草稿的工作台下载审核包。')
        return
    try:
        artifacts = reviewed_artifacts(row)
        if artifacts['binding'] != binding or Path(row['body']['catalog']['root']).resolve() != Path(root).resolve():
            raise ValueError('本机产物与送审版本不符，请到「数据集 → 人物事件」核对版本。')
        st.download_button('下载审核包', _review_bundle(artifacts), task_id+'-review.zip',
                           mime='application/zip', on_click='ignore')
        st.caption('压缩包内含事件图、Gantt、固定输入和 review.md 模板。完成内容审核后，在构建任务中提交审核记录。')
    except (ValueError, OSError, KeyError) as exc:
        st.warning(str(exc))
    if st.button('打开送审构建'):
        navigate('任务', **{'task-selected': task_id, 'task_event_filter': '', 'ui-task-view': '待处理'})
