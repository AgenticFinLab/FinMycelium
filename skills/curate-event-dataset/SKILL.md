---
name: curate-event-dataset
description: 从历史候选或指定主题重新构建独立事件数据集。依据公开原文辨认事项、确定研究边界、处理重复候选，输出 FinMycelium 可读取的事件输入 CSV。
---

# 构建独立事件数据集

用户已确认 `EPG-dataset/data/events/events.csv` 的 3,000 条全部入选。重建时保留这些事件的编号，逐条补全资料。新增事件按自身的研究价值和 FinMycelium 的事件过程重建目标判断。原表供把握整体选题方向和粒度；新领域、新类型同样可按[事件入选标准](references/event-selection.md)评估。先说明重建这件事能回答什么问题，再核对公开材料能否支持其关键变化及研究边界。运行时将新版统一构建在 `EPG-dataset/event-epg/`，交付 `README.md`、`events.csv`、`research-plan.md`、`sources.csv` 和 `ISSUES.md`；单事件材料和图按 `events/<event_id>/` 收录。首次建库从历史输入与本轮阅读的原文开始，续做只使用本轮新版记录。

执行前阅读[18 列字段规范](references/input-format.md)，按其中的必填、条件必填与选填规则逐列检查。每条交付记录必须有稳定 ID、中英文事件名、英文简介、主领域、具体类别、纳入范围、检索词和可定位的已读来源。仅 event_name_zh 可以使用中文；其他字段及嵌套说明使用英文。遇到无法核实的必填事实，保留历史编号并在工作稿补研；对别名、地点、参与方及活动起止日期做针对性查找，已证实的逐项填入，仍无可靠依据的留空。

实际建库遵循[建库顺序与阶段验收](references/build-workflow.md)。先在新主表登记并逐条检索 event1 至 event3000，完成跨全表查重，把重复双方、相同之处和原文依据写入新版 `event-epg/ISSUES.md`。历史部分通过验收后，再按计划构建 event3001 至 event10000。分配新增 ID 前，按[入选判定](references/event-selection.md)核实已发生的实质变化、材料能否支持过程重建以及范围能否独立，并完成查重。材料暂缺时按具体追查线索决定暂存或跳过。

使用[本轮问题记录模板](assets/issues.template.md)维护每对 ID 的当前裁决。不同批次发现同一配对时合并核查；身份仍待核时保留待核记录。

1. **登记与选批。** 为历史 3,000 项按原 ID 的数字部分预留 event1 至 event3000，新事件从 event3001 起顺延。本轮总目标 10,000 条。规划新增批次时，对照[领域和类别的数量目标](references/domain-category-plan.md)核算尚缺数量，按实际研究范围归类。按用户要求选批，核实后填写，完整交付时覆盖所有预留编号。
2. **阅读并界定。** 用公开原文确认主体、对象和可定位的行动。简介记录有依据的事实，纳入和排除范围说明本次研究的边界。已读来源的 URL 和定位说明写入 source_hints。待核的历史行保留其编号。
3. **查重。** 对照当事方、具体对象、案号及过程边界。仅经核实的重复行在 `is_duplicate` 填小写 `true`；其余行留空。保留原编号并在 related_events 记录确认重复的对应关系。涉及同一公司或同期发生本身不足以判重。
4. **交付。** 使用[主表模板](assets/events.input.template.csv)和[18 列字段规范](references/input-format.md)。对照剩余空项检查原文和已有研究记录：若简介或原文已明确给出对应事实，就填入结构化列；仍有疑问时按字段补查。对已补查仍无法确认或确实不适用的项保留空值。无需为已核过的同一缺口重复检索。[FTX 示例](assets/events.example.csv)演示 event2 如何保留历史身份并界定研究窗口。最终事件图生成并确定采用后再填写 epg_path。

在 FinMycelium 根目录运行格式检查。默认检查完整主表的编号连续性及历史编号覆盖；检查节选或示例时使用 `--batch`。

```shell
python -X utf8 skills/curate-event-dataset/scripts/check_input.py --review-prose path/to/events.csv
python -X utf8 skills/curate-event-dataset/scripts/check_input.py --batch --show-gaps --review-prose --sources skills/curate-event-dataset/assets/sources.example.csv skills/curate-event-dataset/assets/events.example.csv
```

校验器汇总别名、地区、参与方、起止日期的空项数量；加 `--show-gaps` 可按字段查看事件 ID，供交付前复查。所有交付行统一检查纳入范围和检索词，包括单批节选。执行者仍须阅读原文，确认英文表述自然、译名同指一事、活动日期和每项事实有据，并核实图文件确属该事件。

完整主表检查同目录的 sources.csv；分批交付时也应传入本批来源索引。只给独立节选且缺少索引时，仅能检查引用格式。写简介和研究范围时，按[主表的逐行回读规则](references/input-format.md)从各案原文选取可辨认的事实。批内表述重复时先核对内容，保留确实共用的事实与术语。

节选文件放在新版目录以外时，用 `--batch --catalog-root <本轮新版event-epg目录>` 按正式目录核对来源及图路径。批外关系的目标和代表行身份在完整主表中核对。阶段交付前，主表内的疑似重复关系须全部复核。

阶段一交付用 `--stage baseline`，最终交付用 `--stage final`。校验器核对主表、配套文件、重复裁决与双方来源，并从研究计划的批次表分别检查事实核验和查重已覆盖的 ID。图路径有值时，使用 Workbench 的普通事件图读取器检查文件。原文更正、研究范围改变或批次中断时，按[建库流程](references/build-workflow.md)复查受影响的 ID 后再登记完成。
