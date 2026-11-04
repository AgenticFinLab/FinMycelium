# 人物模式已迁移到原生主体图

`reconstruction.mode: person` 现在直接生成 `SubjectGraph`；同时支持 `company` 模式。默认的 `event` 模式保留原流程。

完整结构、配置、运行命令和验证边界见 [subject_graph.md](subject_graph.md)。

与前一版的变化：

- 原生主结果为 `FinalSubjectGraph.json`，含统一实体、独立事件、参与角色、具体行为和有时效的关系。
- 每个事件都有证据支持的 `subject_relevance`，个人与公司行为分别归属。
- 前端优先显示主体经历视图，并提供原生 JSON / HTML 下载。
- `FinalEventCascade.json` 仅作旧工具兼容投影；新流程不再依靠 `person_index.json` 建立人物中心。
- `scope` 可留空，覆盖人物在指定时期内有资料支持的活动；原 OXY 配置仍可主动限定专题。
- 复用已有输入的 CLI 不补搜，但构图仍调用已配置的模型 API。
