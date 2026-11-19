# 高盛事件的构建模型对照

2026-11-15 至 11-17。任务是重建巴菲特在高盛危机投资中的有据行动。比较模型时按交接正文的 SHA-256 分组。同一事件在不同轮检索中取得的访谈、公告与年报段落不同，跨输入的结果单独解释。

## 三种模型读取同一份 82,244 字符的交接

检索 `54abbce4814b` 选入 19 份材料，构建输入 SHA-256 为 `ef910ea7c1905fa0e2d9f2774e5b6dd66832ea54273597fee04b80138ba5771f`。三次运行均使用 Ark，普通输出，单次上下文上限 240,000 字符，分段 12,000 字符、重叠 400，局部读取最多 40 次、96,000 字符。Kimi 在恢复时提高了单次输出上限，三份最终配置均为 65,536 tokens。Seed Evolving 的累计调用额度在恢复后升到 80，其余为 60。[固定检索记录](https://github.com/AgenticFinLab/EPG-dataset/blob/3b297b65e51f094956118fe4ba7fd31ccc6cb3dd/workbench/search/20261116-004046_goldman-sachs-crisis-investment_54abbce4814b/summary.json)

| 模型与运行 | Action / Context | Stage / Phase | 关系 / 引文 | 调用 | 已回报 token | 累计模型时间 | 最后状态 |
|---|---:|---:|---:|---:|---:|---:|---|
| Kimi K3.1 Pro · `PBUILD-dee74d7e4a1d` | 26 / 71 | 3 / 6 | 10 / 116 | 32 | 1,315,107（30 次有用量） | 238.3 分 | 离线收尾 draft |
| Doubao Seed Evolving · `PBUILD-2459ce9ac5cb` | 26 / 53 | 4 / 5 | 21 / 119 | 62 | 2,706,866（62 次） | 192.5 分 | 离线收尾 draft |
| Doubao Seed 2.1 Pro · `PBUILD-e5b5eed21086` | 19 / 39 | 5 / 6 | 25 / 116 | 54 | 2,485,751（54 次） | 229.9 分 | 自动 partial |

三张图的引文均覆盖 19 个来源。Kimi 在收尾时利用保存的修正响应把 28 个行动归并为 26 个，保留全部 116 条可定位引文。它的 10 条边中有 7 条 `precedes`，适合逐条核对行动顺序，对促成、回应和延续的表达较少。Seed Evolving 给出 6 条 `overlaps`，Seed 2.1 Pro 给出 7 条。遇到多家媒体同日报告同一次修约，应先查是否为同一行动；同日披露本身不足以证明两段行为在时间上重叠。Seed 2.1 Pro 还有未处置的构建事项，保留其自动产物便于复查。[Kimi 运行](https://github.com/AgenticFinLab/EPG-dataset/blob/3b297b65e51f094956118fe4ba7fd31ccc6cb3dd/workbench/build/20261116-005532_goldman-sachs-crisis-investment_PBUILD-dee74d7e4a1d/summary.json) · [Seed Evolving 运行](https://github.com/AgenticFinLab/EPG-dataset/blob/3b297b65e51f094956118fe4ba7fd31ccc6cb3dd/workbench/build/20261116-184058_goldman-sachs-crisis-investment_PBUILD-2459ce9ac5cb/summary.json)

## 较早的 Kimi 与 DeepSeek 对照

检索 `ff7f0a2fc996` 同样选入 19 个来源，正文为 89,945 字符，输入 SHA-256 为 `b3c907c1abd473d7bc8329ecb1be7cb87498681c0d8d5202e9845eb3b4101261`。两次完整运行均以 32,768 tokens 为单次输出上限。此组同时改变了供应商和模型。

| 接入与运行 | Action / Context | Stage / Phase | 关系 / 引文 | 调用 / 已回报 token | 累计模型时间 | 状态 |
|---|---:|---:|---:|---:|---:|---|
| TokenHub Kimi K3.1 Pro · `PBUILD-b74798fdefa6` | 19 / 59 | 4 / 6 | 10 / 94 | 38 / 1,557,075 | 227.6 分 | draft |
| Ark DeepSeek V4 Pro · `PBUILD-7804d454d068` | 19 / 57 | 5 / 6 | 7 / 81 | 37 / 1,462,451 | 94.3 分 | partial |

两次都得到 19 个行动，耗时和引用证据差异明显。另有两次任务因上下文误设为 24,000 字符在首次调用前停止，一次因模型接入点不可用而失败。这些任务只提供接入诊断。[早期输入记录](https://github.com/AgenticFinLab/EPG-dataset/blob/3b297b65e51f094956118fe4ba7fd31ccc6cb3dd/workbench/search/20261115-161657_goldman-sachs-crisis-investment_ff7f0a2fc996/summary.json)

## 采用决定

采用 Kimi 普通模式作为后续同材料实验的基线。阶段和关系中哪些事实得到支持，由可定位的原文和抽取、归并、关系审查的记录一起判断。上述结果支持先改进这些通用环节。每个模型在每个输入上只有一次完整运行，且恢复额度、接入和离线收尾不同，尚不足以决定按阶段切换供应商。

后续检索 `573dc02cc3f4` 交付 25 个来源。首轮 Kimi 得到 26 个行动、80 个 Context、140 条引文和 3 条关系。增加来源确实扩大了取证范围，新增材料能否连成有据的行动链仍取决于构建过程。[同一输入的六轮完整构建对照](person-build-reasoning.md)
