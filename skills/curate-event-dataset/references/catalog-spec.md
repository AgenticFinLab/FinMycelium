# 主表规范与分类

本说明和 [24 列空模板](../assets/events.template.csv)、[合成示例](../assets/events.example.csv)整理自 EPG-dataset 的 `event-epg/master-table-spec.md`、`events.template.csv`、`examples/events.example.csv`、`research/domain-category-review.md`。引用真实项目规范时，核对目标 checkout 与本模板的差异。示例行仅演示格式。

## 字段契约

| 字段 | 填写规则 |
| --- | --- |
| `event_id` | 必填。1–80 字符，首字符为 ASCII 字母或数字，其余为字母、数字、`_`、`-`、`.`。同一事项续用原 ID，只有明确授权才批量改号。 |
| `event_name_zh`、`event_name_en` | 至少填一种。双语名称指向同一事项与范围，另一语言未知可留空。 |
| `aliases` | JSON 字符串数组，收录真实别名、缩写及历史称呼。 |
| `description` | 必填。写主体、具体事项和已核节点，注明材料所述指控、计划、估计或争议。 |
| `domain`、`category` | 分别指主要研究领域和领域内的主题或动作。优先复用同义已有写法。新增时登记理由与边界。 |
| `country_region`、`participants` | JSON 字符串数组。填与研究相关的地域和主体，发布机构所在国只有与范围有关时才计入。 |
| `coverage_start`、`coverage_end` | 允许 `YYYY`、`YYYY-MM`、`YYYY-MM-DD`。保留证据精度，未知留空。对持续或只核到一个节点的事项写明研究截止及覆盖限制。 |
| `scope_include` | 必填。具体到主体、动作、阶段、结果或所读窗口，能与邻近事件区分。 |
| `scope_exclude` | 说明相邻过程、另案、未核阶段或后续结果。存在重叠风险时要具体。 |
| `keywords` | JSON 字符串数组。用于检索的题名变体、主体、机制或编号，实际查询另记。 |
| `search_language` | 空、`zh`、`en`、`zh-en`。表达检索偏好。 |
| `source_hints` | JSON 字符串数组。可定位的来源线索。正式证据见来源索引和事件–来源表。 |
| `owner`、`notes` | 协作人和短说明。无协作人留空，事实或证据缺口写明并在审计中展开。 |
| `related_events` | JSON 对象数组，每项严格包含 `event_id`、`relation_type`、`note`。 |
| `status` | `planned`、`in_progress`、`in_review`、`needs_revision`、`accepted`。新行默认 `planned`。 |
| `epg_path`、`gantt_path`、`review_path` | 仅在真实验收后填写，全部指向 `event-epg/` 下实际文件，使用相对路径及 `/`。 |
| `duplicate_status` | 最后一列，依据逐对审查派生。允许空、`duplicate`、`overlap`、`possible_duplicate`。 |

CSV 使用 UTF-8，允许 BOM。JSON 数组用 `[]` 或空值。日期、编号保留文本。对同一行的日期区间按原精度的可能日期核对，避免人为补成月初、年初或来源发布日期。多值内容给实际 JSON 解析器处理，保留值内标点。模板的前 19 列是 Workbench 输入，后 5 列供目录管理和审计。

`related_events` 允许 `overlap`（范围重叠）、`contains`（本行包含目标）、`part_of`（本行属于目标）、`possible_duplicate`（疑似重复）、`related`（关联）。禁止自引用、同一行重复目标。外部目标在 `note` 中明确外部目录或待导入。关系一条一向。有方向的包含关系与末列的整行标记各自登记。

`duplicate_status` 记录已登记配对在本行的最高优先级，依次为 `duplicate`、`overlap`、`possible_duplicate`。空值表示当前审计未登记配对。按 [逐对裁决规则](research-and-audit.md)生成标记。状态和标记都不提供事实认证或图验收。

## 分类复核

按原始值分别统计每个 `domain`、每个 `category` 和各 `(domain, category)` 组合。明确基线 ID 集、分段行数、空值和是否计入已标重复。一个类别名跨多个领域时，类别名计数与组合计数不同。基线按 ID 明确选择，避免依赖表行次序。

新增领域看研究对象是否稳定、有独立边界。新增类别看能否与同领域既有类区分，使用至少一个代表事件及其范围作为理由，检查同义写法、跨域同名和单例。可用「保留」「明确边界」「建议复用」「同义归并」「复核归属」输出结论。单例可对应独立历史过程。对高频来源族、相邻类和低相似的双语表达提高抽查比例。

典型判断可用这几类对照。

- `Water and Sanitation Development` 与 `Water & Sanitation Development` 表达同一概念。统一写法前先统计受影响 ID。
- 对 `Merger Control Inquiries`，审查事项的主要对象是竞争监管，金融企业并购这一行业背景不足以单独决定领域。
- `Research & Education Grant Awards` 可跨主题复用。只有来源区分实际批准、授予或签约时才使用不同动作类。研究资助身份和研究成效各自需要证据。
- 地震常规类与大震类并行时写明采用的震级字段及阈值。按项目融资批准提出事件时，主题词可放题名或关键词，优先复用适用的融资类。
- 职业伤害、交通安全调查与产品召回可能横跨领域。按独立研究问题、受影响对象及监管过程划界。

运行 [分类计数命令](runbook.md#分类计数)，把机器计数与研究人员的分类判断分开记录。按类别审核的结论不外推成全表逐条事实认证。
