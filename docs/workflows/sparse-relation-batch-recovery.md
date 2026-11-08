# 关系越批：候选归集、归属复核与语义重试

增量基线为 PR #18 的 `6b776f0`，加上此前已经应用的两份补丁：
`FinMycelium_episode_scope_recovery.patch` 和
`FinMycelium_person_organization_recovery.patch`。
本次不改配置额度、公开 schema、最终 EPG JSON 格式、固定 Buffett JSON 或 HTML。

## 原失败与修复边界

运行 `build_output_20261108161341775039` 已完成 7 个 Stage、11 个 Episode，
以及 Layout、Assignments、Relevance；在 Relations 第一批失败。
本批负责 20 个关系起点，全局有 39 个 Activity。

| 响应 | 关系数 | 起点来自其他批 | 未知 ID / 自环 |
| --- | ---: | ---: | --- |
| 首次 | 34 | 16 | 0 / 0 |
| Retry1 | 36 | 18 | 0 / 0 |
| Retry2 | 23 | 11 | 0 / 0 |

三次响应都是完整 JSON、finish_reason=stop。原程序将起点越批作为整份响应失败，
却仍以“修复 JSON 格式”提示重试，模型持续输出全局关系。

另外，前两次各有 5 条时间关系未通过现有检查：涉及 unknown、月份时间、
自然语言时间。未能机械确立先后关系，不等于发现事实时间逆序。
第三次虽没有这些时间检查问题，仍有把“会议包含发言”误用为 executed_by 的风险。
因此，越批候选可保留，但不能未经复核就全部当成最终正确关系。

## 新执行流程

分阶段人物组织的关系部分使用执行版本 3：

1. **先完成所有 Relations 生成批。** 继续提示本批起点职责，目标可以跨批。
   对端点全局已知、非自环且通过引用及时间规则的完整响应，接收为候选。
   已知起点越批本身不再导致整份响应反复失败，也不会因此跳过后续生成批。
2. **程序确定候选归属。** 按 from_activity_id 归入对应起点批；完全相同的
   候选精确去重，保留所有来源批次。同一 `(from, to, relation_type)` 的不同
   描述、依据或证据版本全部保留，不无声覆盖。
3. **统一按归属批复核。** 在生成批全部结束后进行 RelationsReview，避免后执行
   的批次发现前批候选时遗漏。模型只返回 candidate_id、accept/reject、理由，
   不允许改写端点或事实。每个候选恰好一个决定，同键版本最多接受一个。
4. **装配并全量校验。** 只有明确接受的候选进入原组织计划；拒绝理由留存审计。
   合并后继续使用原 validate_organization / apply_organization。
   候选复核不等于金标准审核，semantic_approval 仍为 false。

小规模单次人物组织继续使用原完整计划验证路径；上述归属复核针对分阶段路径。
复核会增加模型调用，全部计入原 max_calls 预算，未增加次数或重试额度。

## 仍然严格检查的内容

- 未知起点、未知目标、自环、结构错误、非有限数值。
- 非时间关系必须有支持关系本身的引用；引用非空不等于已证明语义成立。
- 原时间检查继续生效，不改日期、unknown、精度或时间窗口来通过校验。
- executed_by 必须表示决策/指令与执行，不能用于“出席会议→在会上发言”。
- 复核缺项、重复决定、引用其他复核组候选、同时接受冲突版本，均触发具体错误。
- 长度拆分不拆散同键版本组；单组仍超长时明确失败。其他失败不伪装成长度问题。

组织校验错误现在进入专用语义重试：带具体路径、错误类型、端点、时间原值、
完整候选及完整原始上下文。真正的 JSON 格式错误仍走语法重试。
NaN、Infinity 和溢出浮点数在解析入口拒绝，原响应字符串保留在 trace 中，
不会因为诊断文件严格序列化而中断下一次重试。

包含真正无效关系的整份响应仍被拒绝，其原始内容保留诊断；不会从中截取
“看起来有效”的部分当成成功结果。归属复核处理的是通过候选校验的完整响应。

## 审计与失败处理

- `PersonOrganization-RelationCandidates-Result.json`：全部已收集候选、归属批、
  来源、跨批标记、各版本、复核决定，以及失败状态。
- `PersonOrganizationValidationErrors.json`：每次组织校验失败的完整候选和问题报告。
- 原始响应、每批结果和 CallLedger 继续保存。中途失败保留已有候选和已完成决定，
  不生成最终人物结果。普通服务异常只记录类型，不把原始 URL/header 写入候选审计。

恢复入口兼容先前执行版本 1、2 的失败目录；公开组织计划契约仍为版本 1。
恢复仍重新执行人物组织阶段，不是从已完成的组织子批次继续。

## 应用与恢复这次运行

在已应用前两份补丁的分支上执行：

```bash
git apply --check /path/to/FinMycelium_relation_batch_fix.patch
git apply /path/to/FinMycelium_relation_batch_fix.patch
```

原 YAML 参数保持不变。解压日志后，找到直接包含 RunManifest.json 和
FinalEventCascade.json 的目录，先离线检查：

```bash
python -m finmy.runner.sparse_person_recovery \
  --source-run /path/to/build_output_20261108161341775039
```

然后仅重跑人物组织：

```bash
python -m finmy.runner.sparse_person_recovery \
  --source-run /path/to/build_output_20261108161341775039 \
  --env-file .env \
  --execute
```

原目录不覆盖，新结果写入新目录；原 61 次调用计入历史，300 次总预算剩 239 次。
前面的抽取可复用，但原有引用与内容审核标记仍保留。

## 验证范围

新增真实回归 fixture 保留三次原始关系响应和必要时间映射，明确标注为失败输入，
不是事实金标准。第三次 23 条候选（含 11 条越批）无损保留；前两次各 5 项时间问题
仍被准确拒绝。固定 Buffett JSON 字节不变。

28 个相关测试文件共 **209 tests / 149 subtests** 通过。
离线测试还覆盖精确去重、冲突版本、跨归属发现、复核漏项、长度拆分、预算耗尽、
候选审计、旧版本恢复、完整 builder 生命周期、HTML 输出和严格 replay。
测试环境使用显式 lmbase 容器替身与模拟/已捕获响应；未调用在线模型，
没有生成本次运行的真实最终人物 EPG，也不保证模型的每项语义判断都正确。
