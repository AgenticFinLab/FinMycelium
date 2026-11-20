# 文件契约与排错

用本表查找一项产物在哪里、何时更新、关联到什么。字段字典见[主表规范](catalog-spec.md)，来源和裁决口径见[来源、去重与终检](research-and-audit.md)，可运行样例见[完整教学案例](worked-example.md)。

## 目录与产物

| 路径 | 内容及用途 | 更新时机 |
| --- | --- | --- |
| `run.json`、`baseline/` | 冻结输入、脚本哈希和运行参数，作为重放与并发检查依据。 | 初始化，后续保持冻结。 |
| `stage/events.csv` | 待验收的事件主表，现行表头为 24 列。 | 每次增删、修订、合并或标记更新。 |
| `stage/{sources,event-sources,curation-decisions}.csv` | 保留来源索引、支持链接和决策前缀。 | 入账相关事实、身份或范围变化时。 |
| `composition.json`、`revisions.json` | 合并输入顺序/哈希，及本次与冻结基线的 old/new 差异。 | 分别由 `compose`、`verify` 写入。 |
| `pair-review.csv`、`recall-method.json` | 待判配对与方法版本、输入哈希。 | 主表、比较表或召回参数变化后刷新。 |
| `row-review.csv` | 逐行留证及事实结论。 | 按当前主表行哈希核对。 |
| `evidence.jsonl` | 待物化的事实摘要、日期、定位和限制。 | 读原文后写入。合并或改号时同步。 |
| `validation.json` | 本次结构或严格验收实际结果。 | 每次 `verify`。运行失败后按实际报错修复。 |
| `snapshot/` | 经严格验收的待发布目录。 | `seal_snapshot.py` 一次生成。 |
| `snapshot/research/{row-review.csv.gz,duplicate-review.csv.gz,evidence.jsonl.gz}` | 现行逐行审核、逐对判定及可定位事实。 | 快照物化，保留当前有效身份。 |
| `snapshot/research/{baseline,checkpoint}.json` | 当前身份集与内容哈希、有效数及核验范围。 | 创建或发布快照后与实际文件核对。 |
| `workbench/manifest.json` | 业务字段、源哈希、分片与增量视图。 | 按最终主表重新导出。 |

`run` 是命令参数指定的运行目录。正式仓库可将经核验的 `snapshot/` 内容物化到 `event-epg/`。原始网页响应、索引缓存、候选池和历史记录按用户要求留在运行区或清理。可访问的材料与确证范围应记录在当前审计中。

## 连接键和序列化

- **事件主键**：`events.csv.event_id` 全表唯一。逐行审核、事实档案及当前决策覆盖同一 ID 集。逐对审查的两个 ID 必须不同，按无向对去重。跨表候选仅在双方纳入同一主表后进入当前逐对账。
- **来源主键**：`sources.csv.source_id` 唯一。一个事件可有多个支持来源。同一来源可支持多个事件，但要分别写明支持字段和事实范围。一个集合链接用于多个官方成员时须写成员级定位。
- **证据 JSONL**：每个非空行是一个 JSON 对象。至少含 `event_id`、`source_ids`（JSON 数组）、`object_claims`、`date_claims`、`limitation`。当前快照的 `source_ids` 与该事件的已登记链接集合一致。未知日期可在 `date_claims` 写空值并说明原因。
- **逐对审查 CSV**：`left_event_id,right_event_id,scores,verdict,reason,source_ids,source_locators,reviewed_on,reviewer`。CSV 中的 `scores` 用 JSON 对象，`source_ids` 用 JSON 数组。`source_locators` 写读到的材料位置，多个位置可用 JSON 字符串数组。引用快照事实时可写 `research/evidence.jsonl.gz#event1`，其中 `#event1` 指 JSONL 的 ID 字段。
- **行哈希**：使用 `sha256(json.dumps(row, ensure_ascii=False, sort_keys=True).encode("utf-8"))`。包含现行 24 个字段，空值仍是空字符串。源文件哈希直接按原始字节计算。换行、BOM 或重写序列化可改变文件哈希。快照输出路径使用相对路径，检查点本身排除在其哈希清单之外。
- **证据状态**：`supported` 的边界以审核内容为准。`partially_supported` 和 `pending` 各自记录缺口。`duplicate_status` 从现行逐对审查派生，`status` 仍负责工作流进展。

## 常见问题

| 报错或现象 | 检查与处理 |
| --- | --- |
| `master header mismatch` | 用模板核对列名、顺序和表头重复。旧 23 列可在组装时补末列；其值来自当前配对审核。 |
| `duplicate_status does not match` | 按两侧 ID 对照当前逐对账，修复错误关系后重新 `sync-marks`。刷新行审核和召回，记录派生变更。 |
| `Stale row review` 或 `Recall is stale` | 检查主表是否改过。刷新相关审查，证据和范围仍适用的未变项可以按原阅读时间复用。 |
| `Invalid old/new replay` | 将变化按实际顺序重放，旧值必须与冻结表或上一步新值一致。新列的原值是 JSON `null`，空单元格是空字符串。 |
| `unresolved canonical decision` 或缺少证据覆盖 | 复查 ID 去向、来源关联、查明受影响字段。既有 H2EPR 已登记例外只用于明确的合并保留场景，严格验收前解决。 |
| `Materialize the reviewed overlap` | 将表内重叠写入现行配对账，重新派生标记并绑定最新行与召回。 |
| `Invalid or stale checkpoint output` | 对照预检报告与冻结版本定位变化，先核实差异，再更新依赖产物与哈希。 |
| 整表上传或原生直读失败 | 读取目标 checkout 的实际报错。用 [已验证的业务字段分片](workbench.md)处理上传大小约束。直读依赖其独立 schema。 |
