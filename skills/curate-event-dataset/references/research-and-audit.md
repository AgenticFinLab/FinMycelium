# 来源、去重与终检

## 证据阅读

用公开原始资料定位单一事件或明确过程。法院、监管机构、招股书与备案、项目登记、机构公告、调查报告和官方数据目录优先。多来源时互补核对事件本体、日期与边界，记录互相冲突的说法及各自角色。对搜索摘要、转述与机器翻译保留阅读限制，读到正文才登记对应字段得到支持。

- **日期含义。** 区分事发、立案、公告、发布、交割、生效、处置与工作队审核日期。公司宣布预计交割可支撑计划，正式备案、交割公告或审计年报才可支撑已完成。
- **措辞归属。** 区分指控、拟议命令、终局裁判、同意和解、实际纠正及结果。写出是哪份材料、哪个主体的判断。
- **定位。** 按标题和页码、条款、段落、表格行或数据库成员 ID 标识实际读到的文字。一个集合页可容纳许多不同成员，每条仍需有成员级定位。已读段落能支撑的边界决定入账范围。
- **真实性缺口。** 若无法定位具体日期、主体或原始主张，记录已查材料、疑似混淆和下一步。暂缓等待新证据。找不到来源时保留待核，也可在用户授权下排除或用另一个真正独立事件替换。

## 四表及逐行审核

四张 CSV 以事件 ID、来源 ID 和显式审计关系连接。JSON 字段以合法 JSON 序列化。

| 表 | 字段 |
| --- | --- |
| `events.csv` | [24 列模板](../assets/events.template.csv) |
| `sources.csv` | `source_id,title,url,publisher,publication_info,accessed_on,locator,reading_note` |
| `event-sources.csv` | `event_id,source_id,supported_fields,support_note,verification_result,verified_on,reviewer` |
| `curation-decisions.csv` | `record_id,event_id,legacy_uid,decision,canonical_event_id,reason,source_ids,changed_fields,reviewed_on,reviewer` |

`supported_fields` 用主表字段名数组。支撑链接指出一条来源支持哪一项主张，`support_note` 写事实短述。弱或冲突材料在研究区记录 `insufficient`、`conflicting`；严格发布的有效链接仅收录已确认的 `supported`。发布日未知可空，访问日须是真实的读取日期。标准审核要求 description 和 scope_include 各有支撑。给已保留的边界例外留明细。

决策值为 `retain`、`revise`、`merge`、`exclude`、`defer`。决策有唯一 `record_id`，`canonical_event_id` 指有效身份。合并者需保留去向和证据；排除或暂缓者移出有效行。暂存续跑维护来源和决定的已冻结前缀。用 `{"coverage_end":{"old":"2020","new":"2020-04"}}` 记录可重放的修订，结构字段从无到有时旧值填 JSON `null`。经过验收后再按目标目录的当前快照政策物化。

逐行审核包含 `event_id,current_row_sha256,source_ids,identity_note,date_note,scope_note,fact_locators,review_method,verdict,reviewed_on,reviewer`。可用 `supported`、`partially_supported`、`pending` 区分实际证据状况。行哈希基于 UTF-8 JSON，键排序且保留 Unicode。哈希一致只说明主表内容相同。已读来源未变且仍支持相同边界时可复用原审核；变更行需重核。事实档案 `research/evidence.jsonl.gz` 按行记录相同事件 ID、source_ids、事实及日期支撑和限制。

## 去重与派生字段

先召回全表题名、别名、主体、正式编号和来源，额外核对跨语言题名、时间轴、国家或管辖地、原文比较位置。常用词、集合链接及共享机构会产生候选噪声。日期或编号不同亦可能属于同一处理过程。把算法输出作待判队列，查清事件对象后才裁决。

| 裁决 | 处理 |
| --- | --- |
| 事例相同 `duplicate` | 选证据和范围更稳妥的身份，按用户要求合并、替换或带标记保留。新闻、译名和同一事件更新作为线索或阶段。 |
| 独立边界但有交集 `bounded_overlap` | 两条可以保留。记录各自独立的目标、适用主体或处置范围。例：类似商品由不同零售商承担独立退换召回；初始地震及另有监管文书的交易所停市。 |
| 共同词语或链接 `distinct` / `invalid_signal` | 保留独立事项及裁决依据。例：NASA Genesis 任务与同缩写的研究项目。 |
| 尚无法判断 `pending` / `possible_duplicate` | 记缺口及所需证据。 |

每对记录左右 ID、检索信号、裁决、重复点或边界、来源和定位，以及实际裁决者和日期。暂存召回用 `pair-review.csv`；现行快照用 `research/duplicate-review.csv.gz`，兼容 `source_ids` 与 `source_locators`。同一无向配对只登记一次。正式配对两侧均应是表内有效 ID。跨表研究的证据可保留在本次审计或报告，完成合并后将其映射到当前 ID 集。

末列映射为 `duplicate` → `duplicate`，`bounded_overlap` → `overlap`，`pending` 或 `possible_duplicate` → `possible_duplicate`。同一行取最高优先级。实现见 `catalog_core.duplicate_marks`。先完成配对、再写入标记并刷新行哈希，避免把候选错误直接写成确认结论。

## 终检口径

| 结论 | 所需证据 |
| --- | --- |
| 台账一致 | 各表主键、字段类型、引用、记录数量、快照哈希与逐行哈希通过。 |
| 逐条来源支持 | 逐行读取已定位的来源与事实范围，覆盖身份、日期和纳入范围。核对原文中的反证及关键裁决。 |
| 候选已裁决 | 对当前表、比较表和新增事件执行召回，候选均有已读依据和结论。检查仍可能漏掉表述差异很大的同一事件。 |
| 交付完成 | 达到数量和来源要求，解决关键未决事项或按用户指定保留例外并明确列出，另行验证目标入口。 |

按领域、地域、年代、语言和来源覆盖报告偏差。新数量、真正通过事实审核的数量、仍待核的数量、重复对数和涉及行数分开。文件存在、导入成功或机器校验通过都不能推导事实真实、图已验收或穷尽所有重复。
