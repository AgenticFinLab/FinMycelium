# 人物模式

当前维护的流程是 Person 与单事件 Event；人物默认使用 `SparseRagBuilder`，原生输出为 `FinalPersonEPG.json` 和 `FinalPersonEPG.html`。

## 从人物与时期开始

Pipeline 的 Person 输入人名和时期，例如 `Buffett 2022-2023`。时期可以是时间点或时间段。
系统先发现 domain、storyline 和候选 event，再逐 event 调用同一个搜索 Agent。
单事件、人物初搜和工作台搜索共用 `finmy/search`，没有 simple/scoped 搜索回退。

搜索配置位于仓库根目录下的 `configs/search_pipeline.yml`：

- `search_config.enhancement`：模型、provider、搜索/阅读额度和语言偏好。
- `search_config.event_search`：逐事件额度与并发。
- `all_content_config.max_content_length`：初版输入字符预算，默认 120,000。

显式搜索配置优先。旧 `mode: simple` 会迁移到 agent；旧搜索开关不再选择另一个执行器。
Bocha、Baidu、Exa 是 provider 适配器，是否启用由配置决定。当前示例仅启用 Bocha。
独立的旧 relevance filtering 已移除，选中的原文直接进入证据归档和预算分配。

## 构图与恢复

流程为人物与时期 → 主线发现 → 逐事件 Agent 搜索 → 原文交接 → 一次人物构建 → JSON/HTML。
构图后的补搜与增补链路已删除，旧 `event_followup` 配置会提示并忽略。
Agent 在初次搜索期间按缺口继续查询、阅读和选择来源的能力保留。

人物构建先从原文抽取、核对事实，再组织 event/stage、关系和概括描述。
同一活动可被多个相关事件引用，详细事实保留在活动中；局部无效项记录待处理，不回滚其他成功部分。
具体流程与免检索续跑命令见 [canonical person build](workflows/canonical-person-build.md)。

已有资料可以重新构图；已有图也可以直接重新渲染。两者均不要求重新搜索。
旧 `FinalSubjectGraph.json` 和 EventCascade 结果继续支持读取、转换与历史回看；它们不决定当前搜索算法。
规范 JSON/HTML 的输出与旧格式兼容投影独立，兼容投影失败不删除原生人物结果。

详见 [搜索与证据交接](workflows/search-enhancement.md) 和 [人物 EPG Schema](person_epg_schema.md)。
