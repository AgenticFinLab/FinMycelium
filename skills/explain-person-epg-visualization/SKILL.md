---
name: explain-person-epg-visualization
description: 讲解 PersonBuilder 优化版事件关系图的数据组织、卡片布局、SVG 布线和浏览器交互，供设计其他可滚动流程图或依赖图时参考。
---

# PersonBuilder 可滚动事件关系图的画法

这套画法让读者沿着一项行动，找到参与方、前置条件、结果和支持它的证据。Python 在导出时决定卡片的分组和初始位置；浏览器用 HTML/CSS 排卡片，用 SVG 画关系线，再由原生 JavaScript 处理展开、避让和高亮。整张图可以保存为一个离线 HTML 文件。

## 可滚动关系图如何实现

1. **把业务记录转换成节点和边。** `build_views()` 按 ID 将行动、参与方、背景、来源等记录关联起来。例如，一项行动引用一段证据，证据又指向一份报告，图上就可以画「报告 → 行动」的支持关系。原文和日期保存在按记录 ID 索引的 `details` 中，卡片先显示短标题，展开时再取全文。[数据转换](../../finmy/person_epg/event/graph_view.py)
2. **在 Python 中算好初始位置。** `arrange_graph()` 为每个阶段生成一张图。相连的行动放在一起，明确的先后或促成关系决定组内的排列顺序。每项行动占一列，前置背景放在上方，结果放在下方，来源集中到底部。每张卡片得到一个 `box = [x, y, width, height]`；行动越多，整张图就越宽。这里的列表示排列顺序，列间距没有时间单位。[布局算法](../../finmy/person_epg/event/graph_layout.py)
3. **在浏览器里叠放卡片和连线。** `render_graph_html()` 把数据、布局和模板写入同一个 HTML 文件。打开后，`paintCard()` 创建可点击的 HTML 卡片，`position()` 按 `box` 设置位置和大小。卡片层和 SVG 连线层共用同一坐标系，外层容器用 CSS 的 `overflow: auto` 提供滚动。这样可以保持文字大小，沿水平方向浏览整张图。[HTML 导出](../../finmy/person_epg/event/graph_html.py) · [前端模板](../../finmy/person_epg/event/graph.html)
4. **根据卡片的实际边界画线。** `drawEdges()` 用边的 `from_key` 和 `to_key` 找到两张卡片，读取它们在页面上的位置，从卡片边缘选择出入口。`routingGrid()` 将卡片和标题作为障碍，`route()` 在网格中寻找只走水平或垂直方向的路径。最后把路径上的点交给 SVG 的 `polyline` 画折线，用 `marker-end` 加箭头。关系类型决定颜色和线型，顺序未知的关系省略箭头。[连线实现](../../finmy/person_epg/event/graph.html)
5. **跟随交互更新图形。** 点击卡片后，`toggle()` 读取详情高度，`layoutCards()` 按新增高度下移后续行，随后 `drawEdges()` 重新计算端点和路径。收起时从原始 `box` 恢复位置。悬停或键盘聚焦时，`highlight()` 根据边的端点高亮直接相连的节点，让读者在密集图中追踪一条关系。[交互实现](../../finmy/person_epg/event/graph.html)

## 迁移到另一张图

例如画项目交付依赖图，可以把任务作为卡片，用任务 ID 保存依赖边，把负责人和交付物放进详情。先按里程碑分组，再按依赖顺序排任务列。一项任务有三个后续任务时，画一个起点、三条出边，展开任务说明后按新的卡片边界重画三条线。换题材时，主要改动是**哪些记录成为节点、边表示什么、节点按什么规则排列**；卡片定位、滚动、连线路由和展开交互都可以参考同一套实现。
