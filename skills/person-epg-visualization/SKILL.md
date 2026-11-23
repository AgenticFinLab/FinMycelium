---
name: person-epg-visualization
description: 从人物 Event 的 JSON 或 SVG 草图设计与验证交互式关系图，使用 FinMycelium 的自动布局、证据详情和独立 HTML 导出。
---

# 人物 Event 关系图

先确定读者要追踪的行动、关系和出处。用少量记录试读布局，再替换成完整事件。图中每个对象沿用输入 ID。对时间、关系方向和证据的解释以结构与绘图设计为准。[绘图设计](../../docs/person-event-visualization/0-overview.md)

## 从草图到可操作的页面

1. 用有代表性的行动、背景和引文画 SVG 草图。预览背景的作用范围、连线方向，以及从一个事实回到原文的路径。仓库保留了一份早期布局草图，可作构图参考。[高盛案例 SVG](assets/goldman-event-subgraph-v2.svg)
2. 导出一份有字段和引用的合成图。已有冻结输入时，可向导出器传入 `--input /path/to/input.json`，以便同时核对引文位置。
3. 在不同 Phase、窄窗口和阅读缩放下，检查同一 Action 的行列、跨页连线、字段依据与返回导航。验收用例覆盖单行动、多行、时间不明和证据复用。[示例与验收](../../docs/person-event-visualization/5-examples-and-checks.md)

```bash
mkdir -p output
python -m finmy.person_epg.event.graph_html tests/fixtures/person_event/graph.json -o output/person-event-preview.html
```

## 自动布局和交互

| 读者看到的内容 | 绘图依据 |
| --- | --- |
| 每个 Phase 有自己的行动区。能比较先后的行动按序排列，可同列的行动按行排布。 | `build_views()` 将对象和引用按 ID 关联，时间与偏序决定可用的位置。排完行动后再放背景、参与方和连线。缩放保留逻辑行列。[行动排布](../../docs/person-event-visualization/1-action-layout.md) |
| 同一个 Context 可以出现在多个 Phase。相同颜色和线型在各页含义一致。 | 区分 Phase 共享、Action 引用和本页其他背景。跨 Phase 的 Action 关系连接到已有 Phase 标签，标签说明两端行动和关系。[连线与背景](../../docs/person-event-visualization/2-relations-and-context.md) |
| 点行动卡、背景卡或关系标签会打开详情面板。选择具体字段可看到支持方式、原文引文和来源。 | `inspectRecord()` 按 ID 和字段读取记录。Evidence 保存片段，每段指向一份 Source，一份 Source 可以收录多段引文。用 Back 返回上一级，用 Escape 关闭面板。[详情实现](../../finmy/person_epg/event/graph_inspector.js) |
| 打开 Phase 时先看全图，放大后可滚动，选择记录可突出相关连线。 | HTML 卡片和 SVG 连线共享页面坐标。窗口或面板尺寸改变时重新计算显示比例与端点，操作指南列出首屏、缩放和下载行为。[自动模板](../../finmy/person_epg/event/graph.html) · [操作指南](../../docs/workflows/person-event-visualization.md) |

如已制作与某份图绑定的手工版式，可通过 `--layout` 提供对应图指纹和页面坐标。自动导出和手工版式分别选用各自的模板。[导出入口](../../finmy/person_epg/event/graph_html.py) · [手工模板](../../finmy/person_epg/event/graph_authored.html)
