# 研究与审计约定

CSV使用UTF-8，数组/对象使用JSON，字段以当前规范及脚本为准。正式目录只保留可审查记录，原文和临时文件放output。

## 来源及决策

| 文件 | 字段 |
| --- | --- |
| sources.csv | source_id,title,url,publisher,publication_info,accessed_on,locator,reading_note |
| event-sources.csv | event_id,source_id,supported_fields,support_note,verification_result,verified_on,reviewer |
| curation-decisions.csv | record_id,event_id,legacy_uid,decision,canonical_event_id,reason,source_ids,changed_fields,reviewed_on,reviewer |

source_id稳定；URL和locator定位实际已读正文，reading_note说明阅读范围和限制。publication_info未知可空，访问日不是发布日期；阅读日期和执行者如实填写。来源容器可支持多个成员，须有成员级定位，不能机械删除重复event-source组合。

supported_fields为主表字段名数组，support_note记录支持身份、日期或边界的具体事实。verification_result为supported/conflicting/insufficient；最终有效记录不能有未解决关键冲突。无充分证据者暂缓，不能把访问失败直接判为虚构。批准、拟议协议、法院录入、责任认定、付款和实施成效分别表述；计划日期不写成已发生，公告日不自动作为过程起止。

decision为retain/revise/merge/exclude/defer。历史来源与决策保持不变前缀，纠错来源追加新ID；最新决策以CSV追加顺序为准。source_ids为数组；changed_fields为字段到old/new的对象，未修改为{}。修订可按顺序重放，合并/撤回保留去向，ID不回收。已有owner、状态或成果路径变化须有实际依据。

## 重复裁决与逐行结论

召回覆盖全表双语名/别名和主体，并结合具体项目/交易/案号、期间、地域、范围及来源上下文补查。保留算法、版本、参数和对应主表哈希；相似度只产生候选，零词法候选不等于无重复。

裁决比较是否同一具体事项、持续过程、报道/阶段/译名，说明为何需两个研究任务。共享机构、法条、热线或集合页不证明同一事项；不同编号和匿名字母也不证明独立。确需保留的包含或重叠事项写明各自边界及related_events，不能把possible_duplicate当终检已完成。

使用流程工具生成pair-review.csv和row-review.csv，所有新判断初始pending，字段填写见[操作流程](runbook.md)。复用旧审核需行哈希一致、来源和边界仍适用，并保留原日期及阅读限制；其他格式须显式映射，不能仅凭历史PASS自动认证。原响应、正文和成员字段哈希分别记录，无本地文件不伪造哈希；缓存相符不证明事实或全文已读。

## 发布与报告

正式event-epg保留唯一events.csv、来源/支撑/决策三表、research-plan.md、quality-report.md及research审计。每批保存输入/输出哈希、目标与有效数、变更及未决项、覆盖缺口和下一步。当前逐行结论、候选队列和报告指针必须对应当前主表；历史文件不覆盖。

检查点沿用已有格式；新建至少记录target、active、remaining、execution_date、batches、current_semantic_review_queue、current_semantic_review_pending_pairs、final_all_row_review、final_review_scope、complete和output_sha256。先核实未知变更，再刷新哈希；清单不含检查点自身。发布中断或有关键未决时不标complete。

质量报告汇总可复算数量、历史去向、来源/审核覆盖及限制、重复裁决、领域/地域/年代/语言偏差、实际命令结果和接口状态。机器检查、agent来源复核、独立人工审核分别表述，不宣称绝对无误或穷尽去重。
