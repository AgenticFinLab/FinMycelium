# P0：事件相关性过滤

本补丁接入当前 Web UI 的 `ReconstructionService`，位置为网页资料收集完成后、原有长度限制之前。
保留已应用的 `run_single_inference` 接口修复，不修改 `AgentEventBuilder` 或 lmbase。
非 UI 的 `run_search_pipeline` 暂不自动接入；本模块可单独导入或回放已保存资料。

## 应用与测试

在 FinMycelium 根目录、已激活的 fin 环境中执行：

```bash
git apply --check finmycelium_p0_relevance_filter.patch
git apply finmycelium_p0_relevance_filter.patch
python -m unittest discover -s tests -p 'test_event_relevance*.py' -v
```

停止旧 Streamlit 进程，再启动：

```bash
PYTHONNOUSERSITE=1 python -m streamlit run examples/uTEST/test_web_interface.py
```

过滤默认开启，可继续上传原来的 YAML。模型默认沿用 YAML 的 `lm_name`，因此在当前
DeepSeek 配置下复用 `DEEPSEEK_API_KEY`，无需新增依赖或密钥。会额外产生分类模型调用。
依赖的是已有 `finmy.builder.utils.run_single_inference`，不是直接调用旧的单条推理接口。

## 做了什么

从用户输入生成 Event Profile，再将资料分为 CORE、CONTEXT、IRRELEVANT。
每批最多4段、默认每段8000字符，长文完整分段并保留重叠，不只检查开头。
只有一篇文档的所有段都获得有原文摘录支持且置信度不低于0.9的 IRRELEVANT 判断，才从构图输入排除。
任一段有关联就保留整篇；低置信度、缺失结果、重复结果、无效 JSON、API 失败等记为 REVIEW 并保留。
LLM 置信度未经过校准；0.9是保守筛选阈值，不是事实准确率保证。

不按发表年份硬删：2024年回顾2022年交易可为 CORE，2019年相关融资可为 CONTEXT。
保存 URL、发布日期、source_id（字段名 `document_id`），并将这些元数据传给构图器。
分类器生成的事件时间、理由不会作为事实追加到构图正文；分类摘录只验证是否出现在提供的文本中，
不代表已验证原始新闻真实性。搜索摘要与抓取结果仍需按原有来源记录回查。

这版先落实“Event Profile + LLM 分类”，没有新增关键词黑名单、搜索查询拆解或来源优劣评分。
保留原始输入顺序；不修改 P1 排序与 P2 的 `break` 长度截断。长文中含少量有效内容时仍保留整篇，
提取有效段落、预算分配和近重复去重可另做后续改动。没有自动修复生成图中的错误。

## 输出文件

文件在本次 `pipeline_output_*` 目录中。原有 `formatted_*` 和 `All_Text_Content_*` 保持不变。

| 文件 | 内容 |
|---|---|
| `retrieved_documents.json` | 全部输入资料，含稳定的本次运行编号、URL、发布日期、原始正文 |
| `event_profile.json` | 原始任务、关键词及抽取的任务范围 |
| `relevance_decisions.json` | 所有文档的分类、每段理由与摘录、保留/排除状态、调用统计及错误提示 |
| `filtered_documents.json` | 通过相关性筛选的资料，含 CORE/CONTEXT/REVIEW 标签 |
| `filtered_contents.json` | 筛选后的构图候选文本，尚未做长度截断 |
| `builder_input_contents.json` | Web UI 实际送给构图器的文本，已应用原有长度限制 |

`document_id` 在一次运行中稳定，回放相同顺序也相同；不是跨事件统一实体ID。
`.relevance_cache/` 缓存同一输出目录中的请求结果，键包含模型、提示词版本、任务及原文。
删除该目录可强制重新分类。未记录密钥；模型异常只记录类型，避免错误消息携带凭据。

## 可选配置

不用改配置即可启用。需要自定义时，在所上传 YAML 的顶层增加：

```yaml
relevance_filter:
  enabled: true
  # 不写 lm_name 则沿用顶层 lm_name。
  # lm_name: deepseek/deepseek-chat
  batch_size: 4
  chunk_chars: 8000
  overlap_chars: 200
  drop_confidence: 0.9
  json_mode: true
  cache: true
```

关闭时仅设置 `enabled: false`，原始文本直接走原有流程，不调用分类模型。
需严格指定范围时，可增加 `event_profile`，字段为 `subject`、`organizations`、
`period: [起始时间或null, 截止时间或null]`、`focus`，会跳过自动 Profile 抽取。

## 先回放已有资料，不重新搜索或构图

从项目根目录执行，`--input-dir` 指向解压后的某一次 `pipeline_output_*` 文件夹：

```bash
python -m finmy.runner.relevance_filter \
  --input-dir /path/to/pipeline_output_2026110314372403361912 \
  --config configs/pipline.yml \
  --query "Reconstruct Warren Buffett's and Berkshire Hathaway's Occidental Petroleum investment activities during 2022–2023, including purchases, ownership changes, approvals and public statements." \
  --keywords "Warren Buffett,Berkshire Hathaway,Occidental Petroleum,OXY,2022,2023"
```

输出默认位于该目录的 `relevance_review/`。此命令不调用搜索/抓取/构图，但会调用当前配置的 LLM。
旧数据按明确匹配的标题恢复来源元数据；同名对应多个URL时保留空元数据，不猜测关联。
Web UI 新运行直接记录来源，不依赖标题匹配。

27项离线测试使用模拟模型/检索/解析器，覆盖 API 失败、格式错误、证据校验、长文尾部、
跨年份回顾、旧文件回放和 Web UI 接入。真实筛选效果须用已有29条资料人工核对；
自动化测试通过不等于分类准确率达标。
