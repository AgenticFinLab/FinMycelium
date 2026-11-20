# 合并、编号与发布

本流程依据 EPG-dataset 的现行目录、`research/deduplication.md`、H2EPR 审核和快照检查点整理。用户的合并、替换或改号授权决定所需迁移。先在运行区冻结各输入和哈希，确定每一份原始表承担的角色。

## 合并与替换的顺序

1. **按段定位。** 用 ID 集与用户指定的排列次序检查两表，保留表头、数据类型、核查标记、原始位置及来源。以现行项目为例，`event1`–`event3000` 来自保留的 H2EPR 副表，`event3001`–`event13000` 来自原万条表。保持前 3,000 行与副表逐字段相同，重复标记和待核状态随审计保留。
2. **先裁决、再补行。** 如果任务要求去重替换，对全表、本批和另一张表召回。用具体事项和证据确认重复，决定保留哪一侧。替代事件必须有新的独立身份、来源、范围和可靠证据。记录原行 ID、保留对应方、理由、新行及其来源。按净变化验收数量。
3. **仅按明确指令改号。** 输出旧身份到新身份的映射。被替换行的新 ID 属于新事件，原事件的内部引用指向经核实的保留身份或明确移除。用结构化字段或精确 ID 锚点更新引用，避免字符串替换误命中 `event12` 和 `event123`。核对编号连续性和顺序。
4. **按同一 ID 集更新。** 更新 `related_events`、事件–来源、当前决策、证据 JSONL、逐行审核、逐对审查及正式成果指针。合并共享 `source_id` 时比较真实来源对象和定位，若 ID 冲突且内容不同先在暂存区另设来源 ID，再同步所有引用。材料缺口和重复不因合并而消失。
5. **按配对重算末列。** 将配对投影为 `duplicate_status` 后刷新受影响行哈希。验证合并前后全量字段差异，据实际授权保留原字段。来源、备注和流程字段有改动时记录是哪一项授权或证据导致。

已冻结两张输入表时，可用运行手册中的变量执行以下命令。第一条只写 `stage/events.csv`，来源及审计关联仍需按上述步骤组装。第二条在 `stage/research/duplicate-review.csv.gz` 就绪后执行。只有用户要求连续编号时启用 `--sequential-ids`。该选项验证现有编号和顺序。

```powershell
python -X utf8 -B "$Skill/scripts/catalog_workflow.py" compose @ArgsForRun --input-csv "$Run/first.csv" --input-csv "$Run/second.csv" --sequential-ids
python -X utf8 -B "$Skill/scripts/catalog_workflow.py" sync-marks @ArgsForRun
```

物化当前审计时，`row-review.csv.gz` 保留 [逐行审核字段](research-and-audit.md#四表及逐行审核)及当前行哈希。`duplicate-review.csv.gz` 保存当前有效 ID 的配对。以本次 `pair-review.csv` 及仍适用的旧裁决为输入，按无向 ID 对去重，增加 `source_ids` 列作为证据索引。保留外部配对在运行审计，除非两侧已合并进入主表。`evidence.jsonl.gz` 每行记录一个当前事件，至少有 `event_id` 与 `source_ids`，并附实际事实、日期定位和局限。使用随附 `catalog_core.write` 写 CSV 或 CSV.gz，JSONL 使用标准库 gzip。

先保存现行配对并同步末列，再刷新行审核与召回。候选范围未变时，可逐对复用仍适用的证据、限制与裁决，保留实际审核时间。最后检查当前表哈希和比较表哈希都匹配。严格验收需保证新裁定的表内范围重叠已物化进当前配对账。

## 对现行 13,000 条复算

```powershell
python -X utf8 -B "$Skill/scripts/snapshot_review.py" check --catalog "$Dataset/event-epg" --finmy-root $Finmy --target 13000 --allow-h2epr-audit-exceptions
```

该命令检查主表、当前来源链接、审核行、配对投影和检查点。目前的例外以实际快照输出为准。项目的一次整合验收记录为 13,000 条、24 列、194 行标记重复和 102 行标记重叠。前段含既有待核事实及确认重复，因此这次验收属于合并与审计一致性。用户允许保留原 3,000 条时，勿用严格的去重或全真终检标签替代事实状态。

如果工作只要求核对结构和现有审计，用本命令即可。若要继续做事实终检，读取所有 `pending` 与 `partially_supported` 记录，根据原来源缺口或新线索修订，只有证实后才提升状态。修订后的源字段必须出现在支持链接和逐行审核中。

## 物化待发布快照

1. 在 `stage/` 完成四表。保留或更新逐对账后执行 `sync-marks`。如果有行变化，刷新行审核和召回，确认已读裁决仍适用。
2. 用[文件契约](artifact-contract.md)填写本次事实 JSONL。字段与审计必须指向当前事件，源 ID 和事件–来源表一致。读源范围与日期精度以真实记录为准。
3. 执行下面的物化命令。它重跑严格验收，在本次运行目录生成 `snapshot/`，写出当前决策、压缩审计、身份基线和检查点。显式授权的工作流状态变更可使用与 `verify` 相同的 `--allow-workflow-state-changes`。有保留例外的快照按已授权的合并范围单独交付，并用相应例外模式复查。
4. 对新快照运行结构复查与 Workbench 导出。比较新旧公开 ID、差异清单及资源路径。决定发布时，再把已核准的当前快照部署至正式目录。

```powershell
python -X utf8 -B "$Skill/scripts/seal_snapshot.py" @ArgsForRun --target 10000 --evidence-jsonl "$Run/evidence.jsonl"
python -X utf8 -B "$Skill/scripts/snapshot_review.py" check --catalog "$Run/snapshot" --finmy-root $Finmy --target 10000
```

把示例中的 10,000 换为本次目标。当前快照仅物化可见有效行的最新决策，冻结前缀及变更重放仍可在本次运行的 `baseline/`、`stage/` 和 `revisions.json` 查阅。重新生成时使用新的运行目录，避免覆盖已有的可复核快照。

## 暂存发布清单

- 发布前确认正式文件仍匹配冻结哈希。先检查数据、派生标记、相对路径、逐行证据和结构。
- 最小正式成果是主表、来源表、支撑表、决策表及当前审计。可复现的发布说明应包含目标和实际数量、执行日期、工具版本、来源阅读限制、分类/覆盖变化、重复去向和待核事项。
- 检查点的 `output_sha256` 用目录内相对路径记录实际文件；排除检查点自身。逐行哈希以发布后的完整字段计算。身份基线用排序 ID 集，验证目标数量与链路。
- 标明 `active`、`target`、`remaining`、逐行结论与配对记录路径、配对待判定数、源文件哈希和验收范围。存在关键未决时 `complete=false`。
- 按实际目的使用目标 checkout 的解析器生成和复核派生分片。核对每个分片的 ID、行数和字节数。
- 把产物写到目标目录同层的暂存文件，确认写入、校验及关联齐全后发布。批量中断时恢复原快照或明确标记未完成。按保留政策清理无关缓存，保留必要的当前证据和身份映射。

### 快照文件示例

一条合成证据记录可写为以下 JSONL 对象。真实数据填已读、可定位的事实，日期使用来源支持的精度。

```json
{"event_id":"event1","source_ids":["SRC-example"],"object_claims":{"description":"合成示例","locator":"示例决定第2段"},"date_claims":{"coverage_start":"2020","coverage_end":""},"limitation":"仅演示格式"}
```

将四张核心 CSV、压缩逐行审核、压缩逐对审查和压缩事实文件列入 `output_sha256`。下列可在暂存区完成，并在验收前按实际结论设置 `complete`。继续追加报告、模板或其他审计文件时也可将它们纳入文件哈希清单。

```python
from hashlib import sha256
from pathlib import Path
import json

stage = Path("stage")
tracked = ("events.csv", "sources.csv", "event-sources.csv", "curation-decisions.csv",
           "research/row-review.csv.gz", "research/duplicate-review.csv.gz",
           "research/evidence.jsonl.gz")
checkpoint = {
    "active": 1, "target": 1, "remaining": 0, "complete": False,
    "final_all_row_review": "research/row-review.csv.gz",
    "current_semantic_review_queue": "research/duplicate-review.csv.gz",
    "current_semantic_review_pending_pairs": 0,
    "output_sha256": {name: sha256((stage / name).read_bytes()).hexdigest() for name in tracked},
}
(stage / "research/checkpoint.json").write_text(
    json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
```

正式目录若采用 `current_snapshot_only`，只保留现行可审查状态。要复算当前统计或继续研究，现行快照与本 skill 足够作为起点。过去已经删除的原始输入、旧批次与审计链需要真实原档才能回放，同一批公开资料也可能更新。记录重建依赖与已读范围，区分流程复现和逐字重放。
