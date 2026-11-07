# 人物 EPG：Schema 与 JSON 接口

本模块保存人物经历的事实、证据和组织关系，主层级为 **Person → Domain → Event → Stage → Activity**。本次接入数据接口、旧格式转换和校验；自动归类、阶段生成与新层级渲染后续接入。

## 1. 文件与版本

| 文件 | 用途 |
|---|---|
| [`finmy/person_epg/schema_model.json`](../finmy/person_epg/schema_model.json) | 表、字段、键、约束及视图的定义源 |
| [`finmy/person_epg/schema.json`](../finmy/person_epg/schema.json) | `person-epg-3.0` JSON Schema，Draft 2020-12 |
| [`finmy/person_epg/mysql.sql`](../finmy/person_epg/mysql.sql) | MySQL 8.0.17+、InnoDB 的建表与视图定义 |
| [`person_epg_data_dictionary.md`](person_epg_data_dictionary.md) | 全部 25 张表、157 个字段、59 条外键和行内约束 |
| [`buffett_oxy.json`](../examples/data/person_epg/buffett_oxy.json) | 带 Event、Stage 与活动成员的固定样例 |

重新生成 SQL 和 JSON Schema：

```sh
python -m finmy.person_epg.generate
```

`schema_model.json` 是结构定义的源文件；字段变更后重新生成两个接口文件并运行相关测试。SQL 使用 `utf8mb4_0900_bin`，ID 区分大小写及尾部空格。该排序规则自 [MySQL 8.0.17](https://dev.mysql.com/doc/relnotes/mysql/8.0/en/news-8-0-17.html) 提供。

JSON 根字段 `schema_version` 标识交换格式，值为 `person-epg-3.0`。`graph.schema_version` 记录原始 SubjectGraph 版本，旧数据转换时保留 `subject-graph-1.0`，用于恢复旧格式。

## 2. 概念与记录粒度

| 概念 | 对应表 | 一条记录表示什么 |
|---|---|---|
| Person | `subject_graph`、`entity`、`entity_alias` | 一次建模任务及其焦点人物；人物身份由实体注册表统一引用 |
| Domain | `domain` | 本任务中的一个领域，如投资与收购；名称由任务和资料决定 |
| Event | `event` | 围绕人物持续展开的一项经历，如对西方石油的投资 |
| Stage | `stage` | 某个 Event 内人物行动、公开判断或参与方式的一个阶段 |
| Activity | `activity` | 一个原始行为、交易或背景事项的统一引用 |
| Occurrence | `occurrence` | 一次具体发生事项或场景，如一次大会、采访或购股事项 |

命名对应如下：此前设计中的 `storyline` 现为 `event`；旧 SubjectGraph 中的 `Event` 对应新格式的 `occurrence`。原有单事件重构模式及其 `EventCascade` 类型继续保持原义。

同一次大会可包含针对不同投资的发言。这些活动共享一个 Occurrence，分别加入相关 Event。Stage 由人物参与的演进组织，不能仅由大会日期或来源文件边界确定。

## 3. 键、关系与范式

### 3.1 标识和基数

- `subject_graph` 主键是 `graph_id`。其余表的主键均包含 `graph_id`，ID 只在所属图内唯一。
- `(graph_id, event_id)` 确定一个 Event；它必须归属于一个 Domain。一个 Domain 可含零到多个 Event。
- Stage 主键为 `(graph_id, event_id, stage_id)`，同名 `stage_id` 可在不同 Event 内使用。
- Event 与 Activity 为多对多，通过 `event_activity` 连接。同一 Activity 在一个 Event 内最多出现一次，跨 Event 复用不复制事实。
- `event_activity.stage_id` 可空；非空时，复合外键保证它属于该行 Event。每个成员至多属于一个 Stage；未分段成员直接挂在 Event 下。
- `occurrence_participant` 表示实体参与某个 Occurrence；`participation` 保存具体角色及角色时间。一名参与者可以有多条角色记录。
- `entity_relation` 保存人物/机构之间的关系，`relation_occurrence` 记录相关场景。关系不要求两个端点都出现在每个关联 Occurrence 的参与者集合中。

`sort_order`、`ordinal`、`detail_index` 均为从零开始的非负顺序值；`sort_order` 不保证唯一，应用读取时可追加主键作为稳定排序条件。

### 3.2 Activity 的事实引用

`activity` 的 `action_id`、`transaction_id`、`context_occurrence_id` **恰有一个非空**。三者分别引用 `action`、`financial_transaction` 和 `occurrence`，各分支都有真实外键。每个非空事实引用还有图内唯一约束，避免同一事实重复注册。

`activity` 不保存标题、执行者或时间副本，这些属性通过 `v_activity_facts` 从原始事实表读取。交易的两端实体仍为交易双方，不自动认定为人物决策者。旧格式转换生成 `A:`、`T:` 前缀的活动 ID，原始行为、交易和场景 ID 保持原值。

`event_activity.display_title` 是该展示位置的可选标题；为空时使用原始事实标题。`detail_mode=all` 显示全部 `activity_detail`；`selected` 通过 `event_activity_detail` 选择已有细节，可为空选集。同一份细节正文和证据只存一份。

### 3.3 3NF 的适用范围

关系核心按第三范式设计。每表的完整主键决定其非键属性；组织成员只保存归属与显示选择，不重复保存活动事实。

| 主要函数依赖 | 设计结果 |
|---|---|
| `(graph_id, entity_id) → name, entity_type, attributes` | 姓名与实体属性不复制到参与、行为和关系表 |
| `(graph_id, event_id) → domain_id, label, summary` | Stage 和活动成员不重复保存领域归属 |
| `(graph_id, event_id, stage_id) → label, summary, boundary_reason` | 阶段在所属 Event 内定义 |
| `(graph_id, activity_id) → 唯一事实引用` | 标题、执行者、事实时间通过引用取得 |
| `(graph_id, event_id, activity_id) → stage_id, display_title, detail_mode, sort_order` | 同一活动可以拥有不同组织位置而保持同一事实身份 |

开放属性、描述列表和证据元数据使用 JSON 文档列，内部结构由对应接口定义；这些文档内部不作完全关系化的范式声明。整个交换 JSON 是表的序列化表示，不以“JSON 满足 3NF”描述其性质。

## 4. 时间与证据

### 4.1 时间表示

事实通过 `time_value` 引用时间。`value` 保留规范值或 `unknown`；`window_start`、`window_end`、`original_text`、`is_approximate` 成组保存已有时间窗口，四项同时有值或同时为空。窗口起点必须不晚于终点。

`window_semantics` 的值为：

- `uncertainty`：活动发生于窗口中的某个未知时点。
- `duration`：窗口表示实际持续区间。
- `NULL`：已有数据尚未区分上述含义。

`is_approximate` 记录精度，与持续时间含义分开。转换保留已有原表达和窗口，不推断新的日期。图形定位使用的包络范围不写入 Stage 或 Event 的事实时间；未来渲染器根据成员查询得到。

### 4.2 证据定位

证据链为 `source_document → evidence_span ← evidence_link → evidence_set`：

- `source_document` 保存准确正文、可用的 URL 与发布时间。发布时间是文档属性，活动时间另行保存。
- `evidence_span` 保存原文引文。可定位时同时填写 `document_id`、`char_start`、`char_end`，偏移采用 Unicode 码点的左闭右开区间 `[start,end)`；须满足正文切片与 `quote` 完全一致。
- 旧数据若只有引文而无可确认正文，保留 `quote`，三个定位字段均为空；转换不会生成来源地址或猜测偏移。
- `evidence_set.field_metadata` 保存各局部字段的理由、置信度及可选状态等元数据；`evidence_link` 通过局部 `field_path` 和 `quote_order` 将字段与引文关联。

局部路径以该证据集所属的原始记录为根，遵循 JSON Pointer 转义；旧格式字段路径保留以支持往返转换。来源身份、引文存在性、原文是否支持结论是不同检查，其中语义支持由构建/复查步骤处理。

### 4.3 活动关系

`activity_relation` 连接两个 Activity，`entity_relation` 连接两个实体。

| 类型 | 从 A 到 B 的含义 |
|---|---|
| `precedes` | A 在 B 之前，不隐含因果 |
| `overlaps` | A 与 B 的时间重叠 |
| `executed_by` | A 为决策或指令，B 为落实它的活动 |
| `explains` | A 解释或回顾 B |
| `responds_to` | A 回应 B |
| `context_for` | A 是 B 的相关背景，不自动表示人物已知该背景 |

`basis` 取 `source`（原文明确）、`inferred`（依据原文整理）、`temporal`（仅由时间推出）。`temporal` 仅用于 `precedes`、`overlaps`。非时间联系要求引用实际包含引文的证据集。相同方向、端点和类型的连线图内唯一，不允许自环。

## 5. JSON 与数据库的对应

JSON 根对象含 `schema_version`、`graph` 和其余 24 个表名数组；即使为空也保留数组。`graph` 对应 `subject_graph` 单行，其余行隐含 `graph.graph_id`，SQL 落表时补齐同一 `graph_id`。数组字段、主外键名称与数据字典保持一致。

可空字段可写 `null` 或按 JSON Schema 省略；省略的可空字段映射为 SQL NULL。非空字段按 JSON Schema 必须提供，SQL 默认值不等于 JSON 可省略该字段。日期窗口使用 `YYYY-MM-DD`。

`source_document.published_at` 在 JSON 中采用带时区的 ISO 日期时间：`YYYY-MM-DDTHH:MM:SS[.ffffff]Z` 或末尾使用 `±HH:MM` 偏移，小数秒最多 6 位；日期时间未知时为 `null` 或省略。程序校验实际日历日期与 UTC 转换后的 MySQL 存储范围。入库器先转换为 UTC，再移除时区写入 `DATETIME(6)`；例如 `2023-05-06T09:30:00.123456+08:00` 存为 `2023-05-06 01:30:00.123456`。数据库读回的该列按 UTC 解释，导出时附加 `Z`。本补丁提供格式校验，实际数据库写入器由后续持久化实现负责。

| 约束位置 | 负责内容 |
|---|---|
| JSON Schema | 字段名与类型、必填项、枚举、互斥事实引用、成组可空字段 |
| `validate_person_epg` | 跨表引用、主键/唯一键、主体身份及可确定的证据/成员约束 |
| MySQL | 主外键、唯一键、NOT NULL、CHECK 等存储完整性 |
| 构建/组织步骤 | 事实抽取、阶段划分、证据语义支持及活动联系判定 |

程序校验返回 `valid` 和带 `path`、`message` 的 `errors`。数据库约束不能替代内容判定；阶段划分不会由 JSON/SQL 校验器补造。

## 6. 查询视图与后续渲染

| 视图 | 返回内容 |
|---|---|
| `v_activity_facts` | Activity 对应的原始事实、真实执行者/交易双方及事实时间 |
| `v_person_timeline` | 人物、Domain、Event、可选 Stage、活动及场景、两端时间；通过各层排序字段组织 |
| `v_activity_hover_details` | 每个 Event 展示位置应显示的活动细节 |
| `v_event_links` | 两端均属于同一 Event 的活动关系 |
| `v_event_entity_relations` | Event 成员涉及的 Occurrence 中关联的实体关系 |
| `v_evidence` | 局部字段、引文及可用的来源正文信息 |

SQL 视图不声明返回顺序，调用方应显式 `ORDER BY`。`v_person_timeline` 的 `event_id` 指组织事件，`occurrence_id` 指具体发生场景。尚未分组的事实不出现在该组织视图中，仍保存在事实表和 `v_activity_facts`。

这次补丁提供数据接口；现有 HTML 继续读取原来的 `FinalSubjectGraph.json`，新层级渲染后续消费 `FinalPersonEPG.json` 或上述视图。

## 7. 转换、校验与兼容

在仓库根目录执行，路径可按当前文件名替换：

```sh
python -m pip install 'jsonschema>=4.18,<5'
python -m finmy.person_epg convert FinalSubjectGraph.json --output FinalPersonEPG.json
python -m finmy.person_epg validate FinalPersonEPG.json
python -m finmy.person_epg export-legacy FinalPersonEPG.json --output RestoredSubjectGraph.json
```

也可先验证仓库固定样例：

```sh
python -m finmy.person_epg validate examples/data/person_epg/buffett_oxy.json
python -m unittest discover -s tests -p 'test_person_epg*.py' -v
```

有效 JSON 的校验结果为 `{"valid": true, "errors": []}`，退出码为 0；无效结果列出字段路径和原因，退出码为 1。转换与还原命令成功时打印输出文件路径。测试覆盖旧事实往返、引用完整性与组织成员约束，运行不调用搜索或模型 API。

转换保留原始事实、引用、角色、交易信息与时间表达。旧图中的 `events` 进入 `occurrence`；行为与交易注册为 Activity。`domain`、`event`、`stage`、`event_activity`、`event_activity_detail`、`activity_relation` 初始为空，组织结果由后续步骤显式填入。

导出旧格式还原旧事实结构；新增 Domain/Event/Stage 与活动联系没有旧格式槽位，仍以 `FinalPersonEPG.json` 为保存依据。不要用一次旧格式导出再导入代替新格式文件的保存。

人物构建流程保留现有 `FinalSubjectGraph.json`、HTML 和旧投影，同时新增 `FinalPersonEPG.json`，并在构建结果的 `extras["person_epg"]` 中提供它。旧 Event 模式、公司模式与搜索入口不因这套人物数据接口改变。

## 8. MySQL 部署与生命周期

`mysql.sql` 用于 **空 schema**，不会创建数据库，也不会修改现有 `db_manager` 表。文件先建表，再添加外键，最后创建视图；无 `DROP` 和自动数据迁移。新结构包含跨表引用，不应向已有同名表直接重复执行。

部署时选择独立的空数据库，在 MySQL 客户端执行：

```sql
SOURCE finmy/person_epg/mysql.sql;
```

MySQL DDL 会隐式提交。建表完成后才开始数据事务；它不能按 SQLite 的延迟外键方式一次任意顺序导入。主体注册表与实体/证据表存在引用环，建议装载顺序为：

1. 插入 `subject_graph`，暂置 `subject_entity_id`、`evidence_set_id` 为 NULL。
2. 插入证据集、时间记录和源文档；随后插入实体、别名、证据片段及证据引用。
3. 插入 Occurrence、参与者集合、角色、行为、交易、交易标的、实体关系及关系场景。
4. 插入 Activity、活动细节、Domain、Event、Stage、活动成员、细节选择和活动关系。
5. 回填主体实体与主体证据集，完成最终图校验，再提交事务。

最终图要求 `subject_entity_id` 指向现有的 `individual`；SQL 的可空设计仅为分步加载服务。FK 默认限制更新/删除，不启用级联；业务删除一张图时应先清除主体回指，再按依赖反序删除图内记录，最后删除 `subject_graph`。索引由主键、唯一键和外键需要提供，当前不加入未经查询负载验证的额外性能索引。

本补丁没有执行远端数据库迁移。数据字典列出的存储约束与自动测试共同用于核对 SQL/JSON 的对应关系。
