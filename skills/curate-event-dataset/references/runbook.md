# 操作流程

## 环境和基线

需要Python 3.10+、FinMycelium与EPG-dataset两个checkout、可联网阅读的agent。随仓库交付scripts/curate_events.py及export_event_workbench.py；skill不能脱离它们单独运行。预检和一致性校验用标准库，召回另需scikit-learn：`python -m pip install scikit-learn`。记录实际依赖与工具版本。

在FinMycelium根目录执行，替换实际路径：

```powershell
$FinmyRoot = (Get-Location).Path
$DatasetRoot = (Resolve-Path "../EPG-dataset").Path
$SkillRoot = Join-Path $FinmyRoot "skills/curate-event-dataset"
$RunDir = Join-Path $DatasetRoot ("output/curation/run-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
python -X utf8 -B "$SkillRoot/scripts/preflight.py" --finmy-root "$FinmyRoot" --dataset-root "$DatasetRoot" --mode resume --output "$DatasetRoot/output/curation/preflight.json"
python -X utf8 -B "$SkillRoot/scripts/catalog_workflow.py" init --dataset-root "$DatasetRoot" --finmy-root "$FinmyRoot" --run-dir "$RunDir" --basis existing
```

existing冻结当前四张CSV及当前身份基线元数据，分别复制到baseline和stage并登记run.json。独立初建用fresh代替existing，只创建空表头；已有run续跑跳过init，先核对冻结哈希。预检退出0只表示报告生成，须另核对缺失文件、Git冲突、检查点差异和接口结果，不盲目刷新哈希。

大审计CSV可能以.csv.gz保存；使用curate_events.read可读取实际.gz路径或自动解析同名.csv逻辑路径。JSONL事实用gzip.open逐行读取；四张核心CSV保持普通文本。若检查点标记current_snapshot_only，仅使用当前文件，不要求旧批次、历史ZIP或存储映射。

修改只在stage进行。按当前规范和[审计约定](research-and-audit.md)研究、扩充并维护四表；来源、原决策保持不变前缀，变更追加决策及old/new。记录研究截止日、实际查询/工具、已读定位、缓存和覆盖缺口，不执行依赖退役输入的prepare或validate_tables.py。

## 校验、召回和审核

```powershell
python -X utf8 -B "$SkillRoot/scripts/catalog_workflow.py" verify --dataset-root "$DatasetRoot" --finmy-root "$FinmyRoot" --run-dir "$RunDir"
python -X utf8 -B "$SkillRoot/scripts/catalog_workflow.py" recall --dataset-root "$DatasetRoot" --finmy-root "$FinmyRoot" --run-dir "$RunDir"
python -X utf8 -B "$SkillRoot/scripts/catalog_workflow.py" ledger --dataset-root "$DatasetRoot" --finmy-root "$FinmyRoot" --run-dir "$RunDir"
```

verify检查schema、引用、冻结身份覆盖、决策前缀、old/new重放、正式表并发变化和数组冗余，输出revisions.json及validation.json。既有执行信息默认保护，有实际授权变动才用--allow-workflow-state-changes；accepted行需将对应已收录文件一并复制至stage相对路径。

recall生成字符TF-IDF近邻候选，保存方法、版本、阈值、主表哈希和完整候选键。执行者结合原文填写pair-review.csv的verdict、reason、source_locators、reviewed_on、reviewer。verdict为distinct、bounded_overlap或invalid_signal。需合并者先修改stage、决策和关系，再重跑召回；额外语义信号在审计中留证，不能只依赖词法候选。

ledger生成row-review.csv，预填ID、行哈希、来源ID，verdict=pending。逐行填写identity_note、date_note、scope_note、fact_locators、review_method、verdict、reviewed_on、reviewer；事实定位不能为空，日期不明说明其不确定性。只有实际证据足以支撑目录身份/范围才填supported，保留原文阅读限制。工具不自动填通过。

同schema旧审核可用--reuse-ledger <旧CSV>复用哈希一致且supported的记录；其他格式须先映射核对。变更后用以下命令归档旧记录并刷新：

```powershell
python -X utf8 -B "$SkillRoot/scripts/catalog_workflow.py" ledger --dataset-root "$DatasetRoot" --finmy-root "$FinmyRoot" --run-dir "$RunDir" --refresh-ledger --reuse-ledger "$RunDir/row-review.csv"
python -X utf8 -B "$SkillRoot/scripts/catalog_workflow.py" recall --dataset-root "$DatasetRoot" --finmy-root "$FinmyRoot" --run-dir "$RunDir" --archive-previous-recall
```

归档在run/history；变更行和重新召回的候选回到pending。旧裁决需确认当前边界仍适用才能复用，不能删候选避开审核。

## 最终验收和统计

达到目标并完成实际来源研究、逐行审核、候选裁决和覆盖检查后运行，替换实际目标：

```powershell
python -X utf8 -B "$SkillRoot/scripts/catalog_workflow.py" verify --dataset-root "$DatasetRoot" --finmy-root "$FinmyRoot" --run-dir "$RunDir" --target 10000 --final
python -X utf8 -B "$DatasetRoot/scripts/curate_events.py" summary --catalog "$RunDir/stage" --baseline-catalog "$RunDir/baseline" --finmy-root "$FinmyRoot" --target 10000
```

fresh省略summary的--baseline-catalog。新目录无旧候选文件时，historical_lexical_pairs为null，表示没有历史统计，本轮结果看pair-review。最终校验要求逐行全覆盖、哈希匹配、充分填写、来源可关联，召回与当前表一致且原候选全部裁决。RECORDED_FINAL_CHECKS_PASS只证明记录一致性，实际来源判断仍由执行者负责。

## Web导出与发布

```powershell
python -X utf8 -B "$DatasetRoot/scripts/export_event_workbench.py" --source "$RunDir/stage/events.csv" --output "$RunDir/workbench-import" --baseline "$RunDir/baseline/events.csv" --chunk-size 2500 --finmy-root "$FinmyRoot"
```

fresh省略--baseline；有撤回时先完成映射裁决，再用--allow-withdrawals生成审阅表。导出前19个业务字段并真实解析回环；目录status及三成果路径不作为上传字段。核对manifest、文件哈希、总数和跨文件ID。每片须满足当前行数/字节限制，必要时降低chunk-size或另拆delta再验证。

分别验证三个入口：上传用domain.py的read_table；Web数据集直读用dataset.py的DatasetCatalog；Builder还需正文samples及范围/材料审核。预检检查前两个入口；上传成功不能证明目录直读兼容。sources及链接不会自动导入为正文。已有ID不能靠批量导入覆盖，changed/withdrawn审阅表不作为新增导入。本skill只交付文件和限制说明。

发布前确认正式四表仍匹配冻结快照；有用户修改先协调。工具不自动发布，fresh不能擅自替换现行目录。将四张stage表、研究报告及run.json、revisions.json、validation.json、row-review.csv、pair-review.csv、recall-method.json和实际阅读记录放入正式event-epg；正式目录按检查点保留策略维护；current_snapshot_only时仅发布当前结论、必要事实和检查点，不重新引入旧批次或变更链。更新统计、报告/队列/逐行结论指针，最后登记输出哈希。多文件发布中断不得标完成。

交付代码版本、未提交修改、当前基线及哈希、依赖/命令和必要缓存获取方式。运行两仓库git diff --check，单独报告无关Git冲突，不为通过而修改其他文件；不提交、推送或写数据库。

## 启动与维护

调用示例：`使用 $curate-event-dataset，FinMycelium为<路径>，EPG-dataset为<路径>。从现行基线继续，扩充至总计10000条，逐条来源核查、全局去重及全表终检后交付主表与审计。` 独立建设注明fresh，复查注明只检查修复；已达到目标则直接终检。

工具修改后运行隔离合成数据回归，不会研究或修改正式事件：

```powershell
python -X utf8 -B "$SkillRoot/scripts/smoke_test.py" --dataset-root "$DatasetRoot" --finmy-root "$FinmyRoot"
```
