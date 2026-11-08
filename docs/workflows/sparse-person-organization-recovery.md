# PersonOrganization 输出截断与组织阶段恢复

本补丁叠加在 PR #18 的 `6b776f0` 和已应用的
`FinMycelium_episode_scope_recovery.patch` 上。新日志记录的 Sparse 源文件哈希
与该基线一致。不要重复应用上一份时间修复补丁。

## 已确认的失败原因

运行 `build_output_20261108154252218335` 的原始响应明确记录：

| 字段 | 值 |
| --- | --- |
| PersonOrganization finish_reason | length |
| completion_tokens / 配置 max_new_tokens | 8192 / 8192 |
| prompt_tokens | 124203 |
| refusal / tool_calls | null / false |
| 已完成抽取 | 6 Stages / 15 Episodes，以及 Event 描述 |
| 总调用 | 61：前 60 次抽取，最后 1 次组织输出截断 |

响应非空，但 JSON 在第 7 个 occurrence_relevance 中途结束。
旧错误消息 `incomplete or non-text completion` 没有区分这些原因。
原代码在解析之前拒绝 `finish_reason != stop`，因此不会进行 JSON 格式重试。
不能靠补括号接收这个响应：余下场景关联说明及后续字段尚未完整生成。

`FinalEventCascade.json` 已经保存。原始 126 个产物哈希全部一致，七角色结果可
完整重组出该文件，构造检查与证据报告也能重算一致。因此本次可以复用抽取草稿。
这与此前在 E10 抽取中途失败、没有完整 FinalEventCascade 的运行不同。

## 修复范围

公开 schema、最终 EPG JSON 格式、HTML/JS 渲染文件和固定 Buffett JSON 均不改动。
不提高原模型输出上限，不更改人物范围、实际行为人、日期、来源或抽取细节。

1. 大规模人物组织使用四阶段执行，最终仍合成原私有 PLAN_SCHEMA：
   - Layout：规划 Domains / Events / Stages。
   - Assignments：每批最多 20 个 Activity，明确归属或未分配原因。
   - Relevance：每批最多 5 个 Occurrence，给出人物关联及可选背景归属。
   - Relations：按起点每批最多 20 个 Activity，终点可以来自其他批次。
2. 每次调用仍获得完整抽取事实及完整原文；仅划分输出责任。
   批次共用 system 和事实前缀，任务后缀指定本批 ID；缓存收益由服务端决定。
3. 每批检查引用、覆盖及写入范围，合并后再次全量校验。
   不静默删掉活动或无归属事件，也不将未完成计划写成 FinalPersonEPG。
4. 列表批次只有在纯 `finish_reason=length`、无 refusal/tool_calls 时才二分。
   截断响应本身不会被拼接或截取前缀使用。拒绝和工具响应仍明确失败。
5. 小规模（最多 20 Activities 且最多 5 Occurrences）保留单次组织，
   若遇长度截断则转分阶段。提示要求紧凑 JSON，省略无实质意义的可选重复字段。
6. 新错误类型明确显示 finish_reason、实际 completion tokens 及配置输出上限。
   分批与重试均使用同一调用账本、超时和原调用预算。

Layout 本身不做二分，单项批次也无法继续拆小；这些情况仍可能因长度明确失败。
分阶段执行解决输出规模问题，不保证模型一定生成正确的语义组织。

## 应用补丁

在已应用上一份时间修复的分支上：

```bash
git apply --check /path/to/FinMycelium_person_organization_recovery.patch
git apply /path/to/FinMycelium_person_organization_recovery.patch
```

之后通过原 Web/CLI 入口启动的新人物 Sparse 构建会自动使用新组织执行逻辑。

## 复用这次结果，只重跑人物组织

解压 build ZIP，找到**直接包含 RunManifest.json 和 FinalEventCascade.json** 的目录。
以下命令在仓库根目录执行。先离线检查：

```bash
python -m finmy.runner.sparse_person_recovery \
  --source-run /path/to/build_output_20261108154252218335
```

检查通过后执行：

```bash
python -m finmy.runner.sparse_person_recovery \
  --source-run /path/to/build_output_20261108154252218335 \
  --env-file .env \
  --execute
```

已有有效模型环境变量时可省略 `--env-file`。默认读取 `configs/person_sparse.yml`
补充 agents 和输出目录；原 run 的 subject_id、English、模型生成参数、证据政策等
从 manifest 原样恢复，不会被 YAML 示例中的 Chinese/其他人物 ID 覆盖。
可用 `--output-root output/person-recovery` 指定新的输出父目录。

恢复入口会先验证哈希、输入/配置摘要、角色完整性、抽取重放、证据和审核报告。
它保留原目录，并在新目录中生成结果；不会修改原 manifest 的 failed 状态。
原 61 次调用保存在 OriginalCallLedger.json，新 CallLedger.json 只记录新增请求；
manifest 同时记录历史及累计用量，原 300 次预算扣除历史后剩 239 次。
再次恢复也继承累计历史，不会通过重启重置调用额度。

完成后，新目录包含 FinalPersonEPG.json、FinalPersonEPG.html 等正常产物。
HTML 若单独生成失败，仍以现有 PersonRenderStatus.json 记录。
新完成目录可使用原 `sparse_build_runner --replay` 严格重放。

此入口只适用于抽取已完整、失败发生在人物组织或后续步骤的 person run。
它会重新执行整个组织阶段，不续用已成功的组织子批次，也不接收截断的组织结果。

## 验证和内容审核边界

- 新日志实际离线 preflight 通过：16 sources、59,892 字符、61 历史调用。
- 23 个相关测试文件合计 **169 tests / 108 subtests** 通过，包含分批覆盖、
  跨批关系、长度二分、拒绝/工具响应处理、历史预算、恢复链、原目录不变、
  最终严格 replay、时间修复和 HTML/CLI 路由。
- 当前环境缺少完整 lmbase；上述测试使用显式容器替身和模拟模型响应，
  不验证真实 API transport。未调用在线模型，也没有生成本次运行的真实最终人物 EPG。
- 可复用的抽取仍是待审草稿：原报告有 10 条未匹配引用、10 个缺少引用的字段、
  88 个质量复核候选；semantic_approval=false。5 条时间范围冲突记录也保留。
  本补丁不将这些标记清除或伪装成语义审核通过。
- 固定 Buffett JSON 的 SHA-256 保持
  `ce9b0ed055f39fedfd4fda91d93dc55954b0504814199e6e4b6143213032c20c`。
