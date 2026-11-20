# 可运行的完整教学案例

本案例使用[合成教学档案](../assets/worked-example.json)演示两项许可。东岸海堤建设许可和西岸潮位监测许可属于同一港口计划，但主管机构、地点与授权动作不同，因此判为 `bounded_overlap`。两条都保留，主表末列均为 `overlap`。工作台解析阶段可用真实目标 checkout 验证字段与分片。

## 运行

在 FinMycelium 根目录执行。使用现有 EPG-dataset 作为输出容器，或创建一个空数据目录并将 `$Dataset` 改为其绝对路径。当前 Python 环境需装有 scikit-learn。

```powershell
$Finmy = (Get-Location).Path
$Dataset = (Resolve-Path "../EPG-dataset").Path
$Skill = Join-Path $Finmy "skills/curate-event-dataset"
$Demo = Join-Path $Dataset ("output/curation/example-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
python -X utf8 -B "$Skill/scripts/worked_example.py" --dataset-root $Dataset --finmy-root $Finmy --run-dir $Demo
python -X utf8 -B "$Skill/scripts/snapshot_review.py" check --catalog "$Demo/snapshot" --finmy-root $Finmy --target 2
```

成功后应看到 `event1`、`event2` 共两行，主表有 24 列，逐对账中有一对 `bounded_overlap`，两行有 `overlap` 标记。导入 manifest 列出两片，每片一行、19 个业务字段。示例的来源、审核和裁决均为合成材料。

## 按文件学习

| 顺序 | 打开的文件 | 看什么 |
| --- | --- | --- |
| 1 | `input-1.csv`、`input-2.csv`、`composition.json` | 两张独立的事件输入，按指定顺序组装，并记录输入哈希。 |
| 2 | `stage/events.csv`、`sources.csv`、`event-sources.csv`、`curation-decisions.csv` | 主表、材料、主张支持和身份决策分别管理，关联键可交叉检查。后三个 CSV 均在 `stage/`。 |
| 3 | `recall-method.json`、`pair-review.csv` | 共有简称会召回候选。比较许可对象和所授权操作后登记为范围重叠。 |
| 4 | `row-review.csv`、`evidence.jsonl` | 逐行审核用当前行哈希绑定原文摘要、日期含义和研究范围。 |
| 5 | `validation.json`、`snapshot/research/checkpoint.json` | 先完成严格验证，再物化当前可核的文件和哈希。 |
| 6 | `workbench/manifest.json` | 原文材料和审计字段仍在快照中，导入分片投影工作台字段。 |

## 手工复练

从[运行手册](runbook.md)的新建模式开始，运行 `init`。参考生成的四表填入两条合成输入，使用 `compose` 绑定两侧哈希。用 `recall` 查看候选，读两份示例材料及其适用范围并填写判定。把表内重叠写入当前逐对账后运行 `sync-marks`，再按最终主表刷新 `ledger` 和 `recall`。复用原裁决时保留依据和阅读时间。

完成事实 JSONL 后，依次执行 [快照物化](catalog-migration.md#物化待发布快照)和 [分片导出](workbench.md#导出)。练习一次失败路径时，可在隔离副本内去掉一条事实记录，检查快照生成会拒绝缺失 ID。正式任务须用真实来源和实际阅读记录替换案例内容。
