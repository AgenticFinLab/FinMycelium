# 运行手册

## 环境与三种起点

Python 3.10+ 运行随附工具。词法召回需要 scikit-learn，安装到个人虚拟环境，记录版本。来源阅读由具有搜索和正文读取能力的执行者完成。FinMycelium 的工作台解析以目标 checkout 为准，数据目录可为有现行快照的 EPG-dataset 或新建的独立工作区。不需要从数据目录复制旧脚本才能运行本 skill。

首次使用可先执行[完整教学案例](worked-example.md)。调用各命令时使用同一个 Python 环境，必要时把示例中的 `python` 替换为虚拟环境中的解释器路径。`python -m pip show scikit-learn` 可记录实际召回版本。

在 FinMycelium 根目录运行下列 PowerShell。替换数据目录和目标数量。`$Run` 的目录应尚未存在。

```powershell
$Finmy = (Get-Location).Path
$Dataset = (Resolve-Path "../EPG-dataset").Path
$Skill = Join-Path $Finmy "skills/curate-event-dataset"
$Run = Join-Path $Dataset ("output/curation/curation-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
$ArgsForRun = @("--dataset-root", $Dataset, "--finmy-root", $Finmy, "--run-dir", $Run)
python -X utf8 -B "$Skill/scripts/preflight.py" --dataset-root $Dataset --finmy-root $Finmy --mode resume
python -X utf8 -B "$Skill/scripts/catalog_workflow.py" init @ArgsForRun --basis existing
```

- **续跑。** `existing` 把现行四张 CSV、当前身份基线、逐对标记底账以及可用的 H2EPR 审计输入冻结在 `baseline/`，同时拷入 `stage/`。读 `run.json` 的哈希及脚本版本。已有运行目录直接复用，先核快照。
- **从零构建。** `--mode rebuild` 预检并以 `--basis fresh` 建四张空表。从公开来源建立新身份，在暂存区研究。数据目录为空时创建可写目录后再运行。模板与示例见 [字段契约](catalog-spec.md#字段契约)。
- **复查现行快照。** `--mode review` 预检后可直接用 `snapshot_review.py check` 检查主表、检查点和当前审计的一致性。正式文件的哈希异常要定位原因，记录认可的变更后才更新哈希。复查不自动续写工作台状态。

预检返回 0 表示成功生成报告。逐项检查 checkpoint、源代码库存、业务行解析、整表上传和数据集直读。整表上传的字节限制可通过分片处理。旧 `data/events/` 的工作表、注册表和图清单不作为本流程依赖。

已有 `accepted` 行时，按主表相对路径把实际收录的 EPG、Gantt 和审核文件复制进 `stage/` 的对应位置，以便结构检查及快照物化解析路径。保留原文件和审核结论。研究流程中的待审核图或临时图不能充当这些收录文件。

## 扩充与留证

按用户目标记「现有有效数、目标数、还差的净增数」。每批按缺口调节候选规模和已确认净增，记录新增、修订、合并、暂缓与失败的原因。优先覆盖未充分代表的领域、地区、年代、来源语种和事件类型；减少按单一数据库批量填充带来的偏置。

数量较大时，可先按主管机构或来源类型分组获取候选，再按正式编号批量定位成员原文。索引、列表和相似度可批量处理。每项入选仍需核对身份、时间和范围的实际依据。对同一批文书中的不同学校或项目，分别确认审批对象。对同一事项的多份通告，合到同一过程。按候选数、已读数、可录入数和实际净增分别报告进度。

| 阶段 | 当前行为 | 留下的记录 |
| --- | --- | --- |
| 定位 | 用案例号、项目号、任务号或当地语言题名查找原文。 | 实际查询、工具、访问时间、来源状态 |
| 阅读 | 阅读正文、官方数据库成员或有关页段。逐项支持身份、日期、范围。 | 来源 URL、成员或页段定位、事实摘要、阅读限制 |
| 入账 | 先更新来源及关联，再更新事件和决策。证据不足的候选进入暂缓队列。 | 四张暂存 CSV、候选去向、剩余问题 |
| 去重 | 对全表及本批召回，与额外目录并行比对，确认独立范围。 | 候选集、分数、依据、逐对判定 |
| 收尾 | 刷新变化行的哈希和审核，验收真实导入格式。 | 当前逐行审核、事实档案、检查点、质量报告 |

文件和判定约定见 [来源、去重与终检](research-and-audit.md)。正式发布采用当前快照的目录把旧批次和缓存留在运行区，仅保留必要的当前状态。真实证据记录保持原阅读日期。

## 生成候选与逐行检查

```powershell
python -X utf8 -B "$Skill/scripts/catalog_workflow.py" recall @ArgsForRun
python -X utf8 -B "$Skill/scripts/catalog_workflow.py" ledger @ArgsForRun
python -X utf8 -B "$Skill/scripts/catalog_workflow.py" verify @ArgsForRun
```

- `recall` 写 `pair-review.csv`、`recall-method.json`，初始全为 pending。需跨表时添加 `--compare-csv <独立输入表>`，两表 ID 不重叠。已并入主表的副表使用主表内召回。表内与跨表各自取近邻，并加入双语名称/别名、成员链接和常用正式编号信号。方法文件绑定两侧哈希，保留完整候选键。
- `ledger` 写 `row-review.csv`，预填 ID、主表行哈希和已关联来源。支持 `--reuse-ledger` 复用 schema 一致、行哈希一致的 supported 结论。复核仍需确认来源和边界适用。修改后用 `--refresh-ledger --reuse-ledger <旧审核>` 和 `--archive-previous-recall` 刷新审查。
- `verify` 检查结构、引用、决策与来源前缀、变化重放、快照并发变化、工作流状态和新行质量。暂存检查保持未改动的旧数据例外。需要保留已登记 H2EPR 证据缺口时，使用 `--allow-h2epr-audit-exceptions`，该选项绑定随存副表和行审计。
- **严格验收**用 `verify @ArgsForRun --target <目标> --final`。它同时要求逐行审核、最新候选裁决以及不存在待处理的重复标记。不能与 H2EPR 例外模式组合。可重新运行生成的 `validation.json` 给出实际经过的检查。

验收通过再按 [快照物化步骤](catalog-migration.md#物化待发布快照)生成 `snapshot/`。该目录生成后仍处于运行区。正式发布根据用户授权处理。实际导入与 EPG 构建遵循 [接口与验收](workbench.md)。

## 分类计数

```powershell
python -X utf8 -B "$Skill/scripts/snapshot_review.py" classification --master "$Dataset/event-epg/events.csv" --baseline "$Dataset/event-epg/events_H2EPR.csv"
```

输出包含主表哈希、两组计数、域和类别总数、领域–类别组合和代表 ID。`--baseline` 接受含唯一 ID 的 CSV，适用于基线子集。评估政策和例子见 [分类复核](catalog-spec.md#分类复核)。

## 工具回归

```powershell
python -X utf8 -B "$Skill/scripts/smoke_test.py" --dataset-root $Dataset --finmy-root $Finmy
```

隔离的合成测试覆盖全新 24 列目录、续跑重放、未核审核和候选拒绝、行变更后刷新、压缩记录、跨表召回、分类统计和 Workbench 字段投影。测试不研究真实事件。
