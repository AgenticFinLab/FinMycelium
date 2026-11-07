# 上下文预算分配补丁

在已应用 `finmycelium_inference_compat.patch` 和 `finmycelium_p0_relevance_filter.patch`
的版本上继续应用，不撤销前两个补丁。仅接入 Web UI 的资料预算分配；不改搜索、P0 分类规则、
模型、数据库或 AgentEventBuilder。非 UI 的 `run_search_pipeline` 没有自动接入本模块。

## 应用

```bash
cd /bigdata2/hyt/projects/FinMycelium
git apply --check finmycelium_context_budget.patch
git apply finmycelium_context_budget.patch
python -m unittest discover -s tests -p 'test_context_budget*.py' -v
```

停止旧 Streamlit 进程后重新启动，继续上传原 YAML 即可：

```bash
PYTHONNOUSERSITE=1 python -m streamlit run examples/uTEST/test_web_interface.py
```

## 分配规则

1. 沿用 P0 标签，CORE 优先于 CONTEXT，REVIEW 在后；同类保持原顺序。
2. 先为 CORE 和 CONTEXT 各文档分配最多2000字符的起始预算，再扩展各篇。
   当预算足够容纳起始份额时，后面的背景文献不会被前面的长文挤掉。
3. 单篇默认最多12000字符；之后才用剩余预算处理 REVIEW。预算不足时会明确记录未纳入的文档。
4. 长文优先截取 P0 验证过的原文摘录、附近上下文及相关段落，保留字符偏移。
   不生成摘要，不把分类模型的理由/推断时间当作事实。完整原文与过滤记录不被修改。
5. 不再遇到一篇过长文档就停止扫描全部后续文档。元数据、摘录标签也计入预算。

这些是基于现有标签的确定性分配规则，不会纠正 P0 本身的误分类，也未实现跨文档去重。
所有输出片段都来自原文；标明缺省段落及原文字偏移，避免误认为是连续全文。
若文档缺少可用的 P0 段落判断，截取回退到原文开头。很小的预算仍可能无法覆盖所有重要资料；
CORE/CONTEXT 被遗漏时，页面和报告会给出警告。

## 配置与输出

不用改 YAML。需要调整时，在原来的 `all_content_config` 中增加下面两个可选项，
不要再创建第二个同名配置段：

```yaml
all_content_config:
  max_content_length: 60000
  max_document_chars: 12000
  min_document_chars: 2000
```

单位都是 Python 字符数，不是 token。总上限只计算输入资料，不包含构图提示词、Schema、
Agent 历史和模型输出；它不是完整的模型上下文上限。

原有 `builder_input_contents.json` 仍保存实际构图输入。本次输出目录新增
`context_budget_report.json`，含纳入/遗漏文档、标签、截取范围、字符数和警告。
分类器返回值增加 `documents` 与 `decisions`，原有返回键及分类行为不变。
关闭 P0 时无需相关性记录即可分配预算；未截取的短文仍保持原始文本。

## 离线回放，不再搜索或调用模型

将 `--input-dir` 换为已解压、含 `filtered_documents.json` 的 P0 输出目录：

```bash
python -m finmy.runner.context_budget \
  --input-dir /path/to/pipeline_output_2026110315335203334263 \
  --max-chars 60000
```

输出在其 `budget_review/` 子目录，保留原运行产物。CLI 的总预算和单篇上限分别由
`--max-chars` 与 `--max-document-chars` 指定，默认60000与12000；不读取 YAML。
此命令只重新选择资料，不运行 EventBuilder。

## 验证范围

新增25项离线测试：长文不阻断尾部、CORE/CONTEXT 优先、长文尾部摘录、来源偏移、
中文字符预算、重复段落、无分类结果、极小预算、关闭P0、UI接入、CLI回放等，另含100组
随机输入/预算的不变量检查。原 P0 的22项分类单元测试也通过。

对用户提供的本次12篇保留资料，以60000字符预算离线回放：原来进入构图10篇，
新分配纳入12篇，其中8篇CORE、1篇CONTEXT、3篇REVIEW，2篇以摘录形式保留，
总量52290字符。股东信中涉及 Occidental 的相关原文进入输入。
这验证的是资料分配，不代表已重新构图或验证了图的准确率。

撤销本次补丁（未在相关位置继续修改代码时）：

```bash
git apply -R finmycelium_context_budget.patch
```
