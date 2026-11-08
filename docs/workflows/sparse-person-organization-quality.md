# 人物组织质量：固定事实下的主题组织与关系上下文

本补丁接在 `FinMycelium_relation_batch_fix.patch` 之后。
该补丁此前依赖的 Episode scope 和 person organization recovery 补丁也需要已应用。

本次只实现三步计划中的第一步：在同一份已抽取事实上改善人物组织。
不改搜索、上下文输入分配、七角色抽取、Sparse RAG 证据卡检索与稀疏路由、
公开 schema、最终 JSON 格式、固定 Buffett JSON 或 HTML/JS。
组织内容及私有诊断文件会变化；输出格式不变不等于输出内容逐字不变。

## 执行变化

### 主题、阶段与细节

- Domain 表达活动领域；Event 表达人物持续参与的事项或主题。
- 一个主题可以跨越多个场景，一个场景也可以服务多个主题。
- Stage 依据有证据支持的参与、判断或行动变化，不按日期、会议场次机械切分。
- 有助解释进展时填写阶段概述；必要时设置主题中的展示标题。
- 同一活动跨主题时，评估 `detail_indices`，避免默认把全部细节重复放入每条主线。
- 保留真实行动主体；已有 occurrence 可以作为必要背景，不能补造角色或行为。
- 不设领域数、阶段数、关系数或连通率目标。

### 一次布局复核

大于 20 个 Activity 或 5 个 Occurrence 的分阶段路径，在 Layout 后增加一次
LayoutReview，复核主题归并、场景与主题的区别及阶段边界，然后固定修订后的布局
供 Assignments 和 Relevance 使用。复核仍返回原有布局结构，不能改写事实数组。

这增加一个逻辑模型调用；无效输出仍受原 `max_json_attempts` 限制，所有提交计入
原 `max_calls`。没有额外的循环、隐式额度提升或审核失败后的自动放行。
布局复核超长不能按活动拆分，明确失败并保存已完成布局。

小规模单次完整计划路径保留一次调用，使用改进后的共同组织提示并保存派生上下文。
只有其长度失败转入分阶段路径时，才增加独立 LayoutReview。

### 关系阶段使用已确定的组织结果

在 Assignments 和 Relevance 全量校验后，从固定事实和组织计划确定性生成
主题上下文，包括最终主题/阶段归属、显示标题、精确选定的细节、实际主体、场景、
时间与证据引用，以及未挂载活动等诊断。

该上下文传给每批 Relations 和 RelationsReview，包括跨主题、跨批候选。
它是组织视图，不是新的事实或引用来源；原始完整证据仍在共享请求中。
维持上一补丁的候选归集、精确去重、冲突版本复核和起点归属机制。

`detail_indices` 缺省或 null 表示全部原细节，空数组表示明确不展示细节。
上下文不改写原细节，不截断或改造引用，不把未选细节从事实包中删除。
有依据的跨场景联系可以保留；不根据同主题、先后顺序或连通性制造关系。

## 私有产物与兼容性

- `PersonOrganization-Layout-Plan-Result.json`：初始布局。
- `PersonOrganization-LayoutReview-Plan-Result.json`：分阶段路径复核后的布局。
- `PersonOrganization-Context-Result.json`：关系生成前实际使用的主题上下文；
  单次路径保存完整计划的派生上下文。
- `PersonOrganization-FinalContext-Result.json`：分阶段路径完成后的组织视图与诊断。
- 原关系候选审计、校验错误、调用账本和最终组织计划继续保存。

诊断只提示检查，不能证明语义正确，也不会强制补齐节点或关系。
事实支持与人工审核标志仍为未完成状态。
执行版本升级到 4；公开组织契约仍为 1。
恢复入口接受旧版 1、2、3 失败检查点，仍执行原有哈希、输入、配置和抽取回放检查。

## 应用

```bash
git apply --check /path/to/FinMycelium_person_organization_quality.patch
git apply /path/to/FinMycelium_person_organization_quality.patch
```

YAML 无需更改，使用原人物模式入口即可。
需要固定已有抽取进行对照时，可复用此前失败但抽取已完成的运行目录：

```bash
python -m finmy.runner.sparse_person_recovery \
  --source-run /path/to/build_output_20261108161341775039

python -m finmy.runner.sparse_person_recovery \
  --source-run /path/to/build_output_20261108161341775039 \
  --env-file .env \
  --execute
```

源目录应直接包含 RunManifest.json 和 FinalEventCascade.json。
恢复入口只接受通过检查的失败运行，不接受 HTML 或已完成运行。
恢复会复用原抽取并重新执行整个人物组织，计入原历史调用预算，结果写入新目录。
若要与旧组织版本做真实 A/B，应两次使用同一个已验证抽取检查点及相同模型配置，
分别保留运行产物，不能把新搜索或新抽取引起的差异算成组织收益。

## 验证边界

30 个相关测试文件共 **222 tests / 156 subtests** 通过。
另外对两份用户提供的 HTML 内嵌事实包进行了离线投影检查：
原包不变，选定细节与现有 renderer 的选择规则一致。

离线测试验证原事实与来源保留、复核后布局贯穿后续步骤、细节选择语义、
关系生成和复核收到相同组织上下文、原调用预算、旧版本恢复、HTML 输出和严格回放。
测试使用显式 lmbase 容器替身和模拟响应，不调用在线模型。
这能验证执行与数据传递正确，不能证明真实模型已经达到旧版的组织质量。
最终仍需用相同事实包检查主题归并、重复展示、背景作用和关系的证据支持。
