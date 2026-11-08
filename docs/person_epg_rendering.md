# Person EPG：JSON → HTML

本功能读取 `person-epg-3.0`，生成可离线打开的独立 HTML，沿用已确认的 Plotly Gantt 外观和原生悬浮框。

## 使用

当前分支已包含 schema 和渲染器。在仓库根目录、当前 Python 环境中执行：

```sh
python -m pip install 'plotly>=5.15,<7' 'jsonschema>=4.18,<5'
python -m finmy.person_epg validate tests/fixtures/buffett_person_epg_preview.json
python -m finmy.person_epg render tests/fixtures/buffett_person_epg_preview.json --output buffett_person_epg.html
```

校验应返回 `{"valid": true, "errors": []}`，渲染命令输出 HTML 路径。直接用浏览器打开 `buffett_person_epg.html`；不需要 API、数据库、Web 服务或网络连接。Plotly JS 和输入 JSON 均嵌入文件。

Python 调用：

```python
import json
from pathlib import Path
from finmy.person_epg.visualizer import render_person_epg

package = json.loads(Path('tests/fixtures/buffett_person_epg_preview.json').read_text(encoding='utf-8'))
html = render_person_epg(package, 'buffett_person_epg.html')
```

Web UI 的 Results → Load Historical Results 可以输入任意命名的 Person EPG JSON 路径，然后下载 JSON 和 Gantt HTML。页面不嵌入新的展示组件。

目录加载优先选择 `FinalPersonEPG.json`，其次为 `FinalSubjectGraph.json` 和 `FinalEventCascade.json`。显式指定文件路径仍加载指定文件；无效的 Person EPG 会明确报错，不会静默回退到旧格式。

## 存储字段与画面

| 输入 | 渲染用途 |
| --- | --- |
| `graph.subject_entity_id`、`entity` | 人物中心、名称、颜色及人物／机构图例 |
| `domain`、`event` | 左侧保留名称；点击名称或 Event 汇总框折叠／展开 |
| `stage` | 分阶段汇总框；名称、摘要、划分依据和证据放在 hover 中 |
| `event_activity` | 指定活动归属及顺序；同一 Activity 可出现在多个 Event 中 |
| `event_activity_detail`、`activity_detail` | 按 `detail_mode` 展示全部或选定的细节 |
| `activity` → `action` / `financial_transaction` / `occurrence` | 活动点及行为、交易、背景内容，保留原主体 |
| `time_value` | 原始时间及定位范围；不修改或重新推断时间 |
| `entity_relation`、`relation_occurrence` | 相关人物／机构连线，hover 显示有效时间及证据 |
| `activity_relation` | 同一展开 Event 内、两个已定位活动之间的连线；其余关联仍见活动 hover |
| `evidence_set`、`evidence_link`、`evidence_span`、`source_document` | 引文与已有的来源标题、链接 |

渲染按保存的 `sort_order` 和归属关系排列。默认展开首个 Event；展开后显示全部 Stage / Activity，后两层不再折叠，也不在左侧显示标题。未分配到 Stage 的背景及后续记录仍按 Event 内的顺序展示。

悬浮框完全使用 Plotly 原生 `hovertext` / `hovertemplate`，沿用节点颜色。没有独立浮层、固定面板、关闭按钮或鼠标锁定行为。

汇总框使用斜线填充并保留时间点；近似时间范围使用透明虚线框；精确单日记录使用点。框的显示边距和关系端点的微小横向偏移仅用于排版，不是新增的持续时间。范围外及未定日期记录放在右侧专列，hover 保留其原始时间。

## 与构建器的边界

`render` 只消费已存储的组织，不分类、不补搜、不生成 Stage。旧版 `SubjectGraph` 的 `convert` 命令只迁移事实，其 `domain/event/stage/event_activity` 通常为空。此时渲染命令明确提示先填写组织关系，不会生成看似成功的空图。

Sparse 人物构建完成组织后，直接将完整 Person EPG 传给 `render_person_epg`，保存 `FinalPersonEPG.html`；两个构建 CLI 的 `--gantt` 同样使用新版渲染器。Web 服务优先返回 `extras.person_epg`，供既有 Results 页面分支下载新版 JSON 和 HTML。旧 SubjectGraph 和事件结果继续使用各自的渲染器。

已有运行无需重新搜索或调用模型：直接加载 `FinalPersonEPG.json`，或执行 `python -m finmy.person_epg render path/to/FinalPersonEPG.json --output person_timeline.html`。

## 样例与内容来源

当前可运行的固定输入为 `tests/fixtures/buffett_person_epg_preview.json`：3 个 Domain、10 个 Event、6 个 Stage、45 条活动归属（43 个独立展示 Activity）。西方石油部分有 16 条展示记录、3 个 Stage 和 9 条行为联系。

西方石油补充内容来自用户提供的中文 PDF 校对转录，`field_metadata.provenance = supplied_pdf`。来源编号原样保留，转录不冒充原始网页引文。其余内容保留既有 JSON。两个未纳入新版西方石油组织的旧事实仍留在数据中，但不会作为额外行绘制。部分旧测试引用的 `examples/data/person_epg/` 未包含在当前提交中；本轮路由回归使用已提交的固定 fixture，不以替换原样例的方式声称这些旧测试通过。

## 验证

```sh
python -m unittest discover -s tests -p 'test_person_*render*.py' -v
python -m unittest discover -s tests -p 'test_subject_graph_ui.py' -v
python -m unittest discover -s tests -p 'test_sparse_person_full_flow.py' -v
```

测试覆盖构建器自动导出、两种 CLI 实际导出、嵌入数据无损、Web 结果分发、三种结果文件共存时的历史选择，以及旧格式回退和无效输入。Node.js 可用时，还会执行随补丁提供的 JS 运行测试，核对全部活动归属与折叠状态；Node.js 仅用于测试，不是生成或浏览 HTML 的依赖。

2026-11-08 的选定离线回归共 76 项测试通过，包括上述路径及既有事实转换、组织、投影和 Sparse 流程测试。模型响应使用测试替身；未进行真实模型或真实浏览器 SVG/hover 验证。

浏览器检查：

1. 首个 Event 展开，其余 Event 折叠；左侧仅有 Domain / Event 文字。
2. 点击 Event 名称或汇总框，再点 Domain，验证折叠和恢复。
3. 点 `Expand events` 后核对全部活动；`Collapse events` 收起事件细节。
4. 在“巴菲特阅读业绩说明材料”的点上悬浮，核对细节、时间说明和证据；移开后原生悬浮框消失。
5. 检查斜线汇总框、透明虚线时间范围，以及下方时间范围控件。

自动化测试验证数据与交互状态；实际浏览器验证 SVG 排版及原生 hover。
