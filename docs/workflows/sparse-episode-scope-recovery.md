# Sparse RAG：Episode 时间越界的重试修复

增量补丁基线：PR #18 的 `6b776f0fbed8bac36db460282c2f7b88c2958ca3`。
本次仅改 Sparse builder 的场景提示、异常诊断和重试路径；公开 schema、
最终 EPG JSON 结构、HTML 渲染器/资产及现有 Buffett 回归 JSON 均不变。

## 这次失败的原因

依据用户提供的 `build_output_20261108151414478497` 原始运行记录：

| 内容 | 原记录时间 | 所属场景 |
| --- | --- | --- |
| Berkshire 在 2022 年回购自身股份 | 2022 | E10：Berkshire 2022 share repurchases |
| Buffett 在股东信中解释此前的回购 | 2023-02-25 | E9 股东信发布场景或相应独立陈述场景 |

E10 的起止时间均为 `2022`。模型把后一条陈述行动放入 E10，因此严格时间校验
正确地拒绝了它。不能把该陈述改成 2022，也不能把公司的回购改成人物个人行动。

原代码将此类语义错误送入 JSON 格式恢复提示，仅重复说明
`invalid or truncated JSON`。实际三次响应都仍包含 2023-02-25 的越界行动；
离线重新校验分别检出 5、1、1 项冲突。原代码中的首次越界即停止检查，
因此错误消息只显示第一项。

E9 已有相关描述，不代表所有后续陈述均已作为独立 action 完整收录。
本补丁不会据此自动删除事实、重写 E9，或宣称事实已完成重分配。

该 run 完成 9/21 个 Episode、2/7 个 Stage 描述后失败，共 38 次模型调用，
尚未进入最终人物组织步骤，也未生成最终 EPG。失败不是 HTML 渲染错误。

## 修复行为

1. Participant / Transaction 提示明确约束当前 Episode，区分行动发生时间和
   资料发布时间、后续陈述时间。公司仍是公司行为的 actor；人物不必在每个场景中行动。
2. `TemporalScopeError` 聚合全部越界 action / transaction，保留原始时间、
   完整条目、参与者 ID、目标 Episode 及边界。原时间区间判定与成功返回结构不变。
3. 越界重试附上上一轮完整候选和诊断，要求纠正场景归属；不再将其误称为
   JSON 格式错误。真正的 JSON 语法错误仍使用原有恢复路径。
4. 保存 `EpisodeScopeConflicts.json` 供复核，标记 `needs_scope_review` 和
   `automatic_reassignment: false`。即使当前 Episode 重试成功，记录仍保留。
   计数表示被拒的响应次数，不是去重后的事实数量，也不表示这些事实已丢失或已补齐。
5. 原最大尝试次数、全局调用预算、失败状态及最终产物门槛不变。
   三次仍不合格就继续明确失败，不静默过滤后放行。

诊断进入私有运行产物和 `BuildOutput.extras`；`PersonAcceptance` 增加冲突次数。
这些字段不加入 `FinalPersonEPG.json` 或 `FinalEventCascade.json`。
诊断文件使用现有产物哈希机制。所有源文本原样保留。

本补丁不实现自动跨 Episode 重挂或断点续跑。语义归属和事实覆盖仍需要内容审核；
时间校验仅能检查可解析时间与已知边界，不能证明每个动词、actor、日期都忠于来源。
原先 unknown / 无法解析日期的处理规则保持不变，提示明确禁止用 unknown 绕过校验。

## 应用与重跑

在基线 commit 或包含该基线的兼容分支上，先检查再应用：

```bash
git apply --check /path/to/FinMycelium_episode_scope_recovery.patch
git apply /path/to/FinMycelium_episode_scope_recovery.patch
```

可以沿用现有 Web 入口和人物 Sparse 配置重跑。要复用原始搜索资料、跳过搜索，
也可在仓库根目录直接执行：

```bash
python -m finmy.runner.sparse_build_runner \
  --config configs/person_sparse.yml \
  --input /path/to/build_output_20261108151414478497/BuildInput.json \
  --env-file .env \
  --execute \
  --gantt
```

原 `BuildInput.json` 可直接读取，包含 16 份资料、59,946 字符，无需转换 JSON。
去掉 `--execute --gantt` 可先做离线入口检查。已有相应环境变量时可省 `--env-file`。
实际执行需要项目正常依赖、真实 `lmbase` 及所选模型的有效 API 配置。
`--gantt` 额外输出 `gantt.html`；person 模式完成后本来就会尝试输出 `FinalPersonEPG.html`。

注意仓库示例 `person_sparse.yml` 与失败 run 的部分配置不同：

| 字段 | 失败 run | 仓库示例 |
| --- | --- | --- |
| output_language | English | Chinese |
| subject_id | person_6be9b8ceef454546 | person_warren_buffett |
| aliases | 空列表 | 三个英文/中文别名 |
| scope | 从资料发现人物跨事件、组织的活动 | 明确区分个人决定/陈述与 Berkshire 行为 |

如果需要保持本次实验口径，请将这些项设为原 run 的配置，或使用你实际运行时的
人物 Sparse 配置。姓名、2022–2023 覆盖范围、模型和调用限制在两者中一致。
不要直接将缺少人物配置的搜索 YAML 当作人物 builder 配置。

此次重跑会创建新目录并重新执行 builder；不会复用前 9 个 Episode 的模型结果。
`integrate_from_files(strict=True)` 明确拒绝此失败目录，不能将其当作完整 run replay。

## 验证与限制

- 三份真实失败响应重新校验，仍全部被拒；输入未被改写。
- 20 个相关测试文件共 **142 tests / 80 subtests** 通过，覆盖时间诊断、专用重试、
  语法恢复后仍受时间校验、预算耗尽、三次失败无最终产物、person 全流程、
  adapter / organization / projection、replay，以及 HTML/CLI 路由。
- 新增 fixture 中的模型输出仅用作失败回归输入，不是真实事实的金标准。
  测试中的修正响应是人工编写的 mock，不是实际重新运行所得的结果。
- 当前测试环境缺少完整 `lmbase`，仅用显式数据容器替身与顺序响应测试控制流。
  真实适配器的 transport / accounting 扩展测试无法在该环境跑通，未调用在线模型。
  这些离线结果不保证下一次模型响应一定成功，也不证明事实覆盖完整。
- 原 Buffett 固定 JSON 的 SHA-256 保持
  `ce9b0ed055f39fedfd4fda91d93dc55954b0504814199e6e4b6143213032c20c`。

新增回归可在正常项目测试环境执行：

```bash
PYTHONPATH=tests:. python -m pytest -q \
  tests/test_sparse_temporal_scope.py \
  tests/test_sparse_temporal_recovery_flow.py \
  tests/test_sparse_temporal_recovery_flow.py \
  tests/test_sparse_person_full_flow.py
```
