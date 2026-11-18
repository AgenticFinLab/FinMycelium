# FinMycelium：联合执行与职责拆分实验对比

日期：2026-11-18

## 结论与处理

本次配置下，Patch 4 将 Context 关联与 Action 关系发现拆为两个阶段，未改善实际运行表现。Patch 3 的联合执行完成了任务；Patch 4 经一次续跑后仍在 Context 阶段超时，累计模型调用耗时增加 19.6%，没有产生图更新。撤回 Patch 4，恢复 Patch 3 的联合执行方案，保留全部实验记录。

这组结果说明当前职责拆分方案没有带来收益。它包含一组 joint 运行和一组 split 运行（含续跑），不用于推断所有模型、任务规模和拆分配置下的表现。Split 尚未产出完整结果，提取质量无法与 joint 比较。

## 实验设置

任务为 Warren Buffett 的 Goldman Sachs crisis investment 事件重建，仅重放组织完成后的关联阶段，不重新搜索、抽取或组织上游事实。

| 条件 | Patch 3：joint | Patch 4：split |
|---|---|---|
| 输入 | 同一组织快照 | 同一组织快照 |
| 模型 | `ark/kimi-k3-1-pro-261024` | 相同 |
| 总调用上限 | 60 | 60 |
| 单次输出上限 | 65,536 tokens | 65,536 tokens |
| 上下文字符上限 | 240,000 | 240,000 |
| 读取超时 | 900 秒 | 900 秒 |
| 补读上限 | 40 次 / 96,000 字符 | 相同 |
| 执行方式 | Context 关联和关系发现联合处理 | 先 Context 关联，再关系发现 |
| 阶段预算 | 使用总预算 | Context 限 30 次调用、20 次补读、48,000 字符 |

快照指纹：`1ebb05223e2598a6d722248de05adce14de6a820622286e8bfa40b37b082e42e`。

两组保存的 config 完全一致；拆分特有的阶段预算另存于 relation-mode / summary 中，本次未触及。执行代码、阶段提示词和任务交接方式随方案变化。服务端负载、网络状态与模型生成随机性未受控，因此这是固定输入与主要配置的运行对比，不能把超时唯一归因于职责拆分。

## 量化对比

| 指标 | Patch 3：joint | Patch 4：split |
|---|---:|---:|
| 启动次数（含续跑） | 1 | 2 |
| 执行 / 结果状态 | finished / draft | failed / partial |
| 模型调用次数 | 3 | 3 |
| 正常结束的模型调用 | 3 | 1 |
| 被接受的结果调用 | 2 | 0 |
| ReadTimeout 次数 | 0 | 2 |
| 累计模型调用耗时 | 2,228.179 秒（37.14 分钟） | 2,664.855 秒（44.41 分钟） |
| 相对 joint 的累计调用耗时 | 基准 | +436.676 秒（+19.6%） |
| 首轮请求输入 token¹ | 50,163 | 50,212 |
| 补读次数 / 字符 | 16 / 21,112 | 2 / 6,180 |
| 已完成关系审查的 Action | 26 / 26 | 0 / 26 |
| 最终 Action-to-Action 关系数² | 10 | 0 |
| 图是否相对快照发生更新 | 是 | 否，最终图与快照完全一致 |
| token 用量缺失的调用 | 0 / 3 | 2 / 3 |
| 已报告输入 token 合计 | 139,192 | 50,212（仅 1 次调用） |
| 已报告输出 token 合计³ | 62,293 | 5,979（仅 1 次调用） |
| 总 token 合计 | 201,485 | 未知；已报告部分为 56,191 |
| 关系正确率 / 召回率 | 未进行人工标注评测 | 无完整输出，无法比较 |

¹ Split 首次调用没有返回 usage；续跑的第二次调用与首次请求指纹相同，使用其报告的输入 token 数。两组首轮输入规模几乎相同，职责拆分没有明显缩短这次初始上下文。

² 原组织快照的关系数为 0。Split 的 0 表示阶段未完成，没有提交新关系，不能解释为模型判断不存在关系；joint 的 10 条也不等于已核验的 10 条正确关系。

³ completion_tokens 已包含 reasoning_tokens，不应再次相加。Split 两次失败调用用量未知，不能据已报告部分判断 split 更省钱。

耗时统一采用 state.json 中所有调用的 duration_seconds 之和，split 包含失败和续跑调用，不包含两次启动之间的人工等待。Joint 的单次运行墙钟耗时为 2,261.814 秒；split summary 中的 1,566.284 秒仅对应第二次启动，不能当作完整 split 耗时与之比较。

## Split 的失败过程

| 调用 | 任务 | 耗时 | 推理字符 | 正式内容字符 | 结果 |
|---|---|---:|---:|---:|---|
| CALL-000001 | context.0 | 1,109.304 秒 | 19,707 | 0 | ReadTimeout |
| CALL-000002 | context.0 | 274.919 秒 | 24,326 | 892 | 正常结束，请求补读记录 |
| CALL-000003 | context.0 | 1,280.632 秒 | 45,051 | 0 | ReadTimeout |

第二次调用成功读取了两批记录，共 6,180 字符；补读结果已保存。第三次调用在补读后再次超时，Context 完成快照未生成，discovery 调用次数为 0。两次失败均在 HTTP 200、已收到推理内容的情况下发生，没有正常结束标记。

Context 首个任务仍分配了 26 个 Action、4 个 Phase。Patch 4 实现了职责分离，但本次没有进一步将处理规模压缩成小批次。长请求增加了失败后的重做范围；当前日志未记录最后收包时间，无法确定流停止的精确时刻或服务端停顿原因。

## 复现联合执行

恢复后从原快照启动 joint，使用新目录，不添加 `--mode`，也不续跑旧 split 目录：

```bash
python - <<'PY'
from dotenv import load_dotenv
load_dotenv('.env')
from finmy.person_epg.event.relation_experiment import main
raise SystemExit(main([
    'run', 'PBUILD-dee74d7e4a1d_organization-snapshot.json',
    '--output', 'output/relations-test-05-joint',
    '--allow-model',
]))
PY
```

上述命令在撤回 Patch 4 后使用。小批次和重试策略如需评估，应作为后续独立方案。

## 数据来源

- `relations-test-03.zip`：`relation-summary.json`、`state.json`、`attempts/0001/epg.json`、`relation-discovery.json`。
- `relations-test-04-split.zip`：`relation-summary.json`、`state.json`、`organization-snapshot.json`、两次 attempts 的结果和 request.json。

两组运行的代码指纹分别为 `90c034e40e1b77758cf69a3c60d65299ed583f32f6ec0e2847b835c035a6354b`（joint）和 `299e45bfc0c0ecbca8685b1e7c79b05ada8f74ede9529e7eee929be27e003457`（split）。
