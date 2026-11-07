# 人物 EPG 数据字典

本字典对应 `person-epg-3.0`。结构定义源为 [`schema_model.json`](../finmy/person_epg/schema_model.json)，执行 DDL 为 [`mysql.sql`](../finmy/person_epg/mysql.sql)。概念与使用流程见 [Schema 说明](person_epg_schema.md)。

共 **25 张表、157 个字段、59 条外键**。所有字段均列出；`PK`、`FK` 表示该字段属于相应复合键，不表示单列独立唯一。`NULL=是` 表示可空；默认值列中的 `—` 表示 SQL 未声明显式默认值。

所有表使用 InnoDB、utf8mb4；主外键采用图内复合标识。JSON 中仅 `graph` 显式保存 `graph_id`，其余表行从根图继承该值。

## 表目录

1. [`subject_graph`](#1-subject_graph)：人物图主表：一行对应一次人物建模任务。
2. [`entity`](#2-entity)：实体注册表：一行对应图内一个人物、公司或其他实体。
3. [`entity_alias`](#3-entity_alias)：实体别名：一行对应同一实体的一个别名。
4. [`occurrence`](#4-occurrence)：具体发生事项：一行对应一次大会、采访、交易场景等。
5. [`occurrence_participant`](#5-occurrence_participant)：场景参与者集合：一行表达实体参与某个 Occurrence。
6. [`participation`](#6-participation)：参与角色记录：保存实体在场景中的角色和角色时间。
7. [`action`](#7-action)：原始行为记录：保存实施者、发生场景、行为内容和时间。
8. [`financial_transaction`](#8-financial_transaction)：原始交易记录：保存所属场景、交易双方、时间和内容。
9. [`transaction_instrument`](#9-transaction_instrument)：交易标的描述：一行对应一项有序的原始标的描述。
10. [`entity_relation`](#10-entity_relation)：实体关系：保存人物/机构间关系及有效时间。
11. [`relation_occurrence`](#11-relation_occurrence)：实体关系与场景的多对多关联。
12. [`source_document`](#12-source_document)：来源正文：保存引文定位所用的原文。
13. [`evidence_span`](#13-evidence_span)：原文引文：保存正文片段或尚未定位的旧引文。
14. [`evidence_set`](#14-evidence_set)：局部证据容器：保存字段元数据。
15. [`evidence_link`](#15-evidence_link)：字段与引文的多对多连接，包含字段路径及引用顺序。
16. [`time_value`](#16-time_value)：可复用时间记录：原值与可选时间窗口。
17. [`occurrence_label`](#17-occurrence_label)：场景短标题：一条场景最多一个全图显示名称。
18. [`activity`](#18-activity)：活动注册表：一行恰好引用一个行为、交易或背景事项。
19. [`activity_detail`](#19-activity_detail)：活动原始细节：同一正文可被不同 Event 选择显示。
20. [`domain`](#20-domain)：领域：同一人物图中的一个组织类别。
21. [`event`](#21-event)：人物持续经历：归属于一个主要领域。
22. [`stage`](#22-stage)：人物参与阶段：在所属 Event 内唯一。
23. [`event_activity`](#23-event_activity)：Event 的活动成员及可选阶段归属。
24. [`event_activity_detail`](#24-event_activity_detail)：某个 Event 中某个活动选中的原始细节。
25. [`activity_relation`](#25-activity_relation)：活动之间的有向联系，独立保存连线证据。

## 1. subject_graph

人物图主表：一行对应一次人物建模任务。

**主键**：`(graph_id)`。

| 字段 | SQL 类型 | 键 | NULL | 默认值 | 含义 |
|---|---|---|---|---|---|
| `graph_id` | `VARCHAR(128)` | PK/FK | 否 | — | 所属人物图的标识；复合键和外键均以此限定引用范围。 |
| `schema_version` | `VARCHAR(32)` | — | 否 | — | 原始 SubjectGraph 版本；旧图转换保留 subject-graph-1.0。 |
| `subject_entity_id` | `VARCHAR(128)` | FK | 是 | — | 焦点人物实体；加载期间可空，完成态必须引用 individual。 |
| `subject_type` | `VARCHAR(32)` | — | 否 | — | 焦点类型，固定 individual。 |
| `title` | `TEXT` | — | 否 | — | 人物建模任务标题。 |
| `coverage_start` | `VARCHAR(32)` | — | 是 | — | 任务覆盖起点的原始字符串；可空。 |
| `coverage_end` | `VARCHAR(32)` | — | 是 | — | 任务覆盖终点的原始字符串；可空。 |
| `descriptions` | `JSON` | — | 是 | — | 有序任务描述的 JSON 值；字段证据另存。 |
| `evidence_set_id` | `VARCHAR(128)` | FK | 是 | — | 本记录的局部字段证据集；未知或未单独提供时为空。 |

**外键**：

- `(graph_id, subject_entity_id)` → `entity(graph_id, entity_id)`。
- `(graph_id, evidence_set_id)` → `evidence_set(graph_id, evidence_set_id)`。

**唯一性与检查约束**：

```sql
CONSTRAINT ck_person_subject CHECK (subject_type = 'individual');
```

## 2. entity

实体注册表：一行对应图内一个人物、公司或其他实体。

**主键**：`(graph_id, entity_id)`。

| 字段 | SQL 类型 | 键 | NULL | 默认值 | 含义 |
|---|---|---|---|---|---|
| `graph_id` | `VARCHAR(128)` | PK/FK | 否 | — | 所属人物图的标识；复合键和外键均以此限定引用范围。 |
| `entity_id` | `VARCHAR(128)` | PK | 否 | — | 图内实体标识。 |
| `name` | `TEXT` | — | 否 | — | 该实体的名称。 |
| `entity_type` | `VARCHAR(64)` | — | 否 | — | 实体类别，如 individual、organization；焦点必须为 individual。 |
| `attributes` | `JSON` | — | 是 | — | 开放属性的 JSON 值；字段证据经局部路径关联。 |
| `evidence_set_id` | `VARCHAR(128)` | FK | 是 | — | 本记录的局部字段证据集；未知或未单独提供时为空。 |
| `sort_order` | `INT UNSIGNED` | — | 否 | `0` | 从零开始的显示/还原顺序；不表示事实时间或优先级。 |

**外键**：

- `(graph_id)` → `subject_graph(graph_id)`。
- `(graph_id, evidence_set_id)` → `evidence_set(graph_id, evidence_set_id)`。

## 3. entity_alias

实体别名：一行对应同一实体的一个别名。

**主键**：`(graph_id, entity_id, alias)`。

| 字段 | SQL 类型 | 键 | NULL | 默认值 | 含义 |
|---|---|---|---|---|---|
| `graph_id` | `VARCHAR(128)` | PK/FK | 否 | — | 所属人物图的标识；复合键和外键均以此限定引用范围。 |
| `entity_id` | `VARCHAR(128)` | PK/FK | 否 | — | 图内实体标识。 |
| `alias` | `VARCHAR(255)` | PK | 否 | — | 实体的一个别名；同一实体内按精确字符串去重。 |
| `sort_order` | `INT UNSIGNED` | — | 否 | `0` | 从零开始的显示/还原顺序；不表示事实时间或优先级。 |

**外键**：

- `(graph_id, entity_id)` → `entity(graph_id, entity_id)`。

## 4. occurrence

具体发生事项：一行对应一次大会、采访、交易场景等。

**主键**：`(graph_id, occurrence_id)`。

| 字段 | SQL 类型 | 键 | NULL | 默认值 | 含义 |
|---|---|---|---|---|---|
| `graph_id` | `VARCHAR(128)` | PK/FK | 否 | — | 所属人物图的标识；复合键和外键均以此限定引用范围。 |
| `occurrence_id` | `VARCHAR(128)` | PK | 否 | — | 具体发生场景的图内标识。 |
| `title` | `TEXT` | — | 否 | — | 大会、采访、购股等具体发生事项的标题。 |
| `subject_relevance` | `TEXT` | — | 否 | — | 该事项与焦点人物的关联说明。 |
| `start_time_id` | `VARCHAR(128)` | FK | 是 | — | 起点时间记录；未知引用时为空。 |
| `end_time_id` | `VARCHAR(128)` | FK | 是 | — | 终点时间记录；未知引用时为空。 |
| `descriptions` | `JSON` | — | 是 | — | 有序背景/事实描述的 JSON 值。 |
| `evidence_set_id` | `VARCHAR(128)` | FK | 是 | — | 本记录的局部字段证据集；未知或未单独提供时为空。 |
| `sort_order` | `INT UNSIGNED` | — | 否 | `0` | 从零开始的显示/还原顺序；不表示事实时间或优先级。 |

**外键**：

- `(graph_id)` → `subject_graph(graph_id)`。
- `(graph_id, evidence_set_id)` → `evidence_set(graph_id, evidence_set_id)`。
- `(graph_id, start_time_id)` → `time_value(graph_id, time_id)`。
- `(graph_id, end_time_id)` → `time_value(graph_id, time_id)`。

## 5. occurrence_participant

场景参与者集合：一行表达实体参与某个 Occurrence。

**主键**：`(graph_id, occurrence_id, entity_id)`。

| 字段 | SQL 类型 | 键 | NULL | 默认值 | 含义 |
|---|---|---|---|---|---|
| `graph_id` | `VARCHAR(128)` | PK/FK | 否 | — | 所属人物图的标识；复合键和外键均以此限定引用范围。 |
| `occurrence_id` | `VARCHAR(128)` | PK/FK | 否 | — | 具体发生场景的图内标识。 |
| `entity_id` | `VARCHAR(128)` | PK/FK | 否 | — | 图内实体标识。 |

**外键**：

- `(graph_id, occurrence_id)` → `occurrence(graph_id, occurrence_id)`。
- `(graph_id, entity_id)` → `entity(graph_id, entity_id)`。

## 6. participation

参与角色记录：保存实体在场景中的角色和角色时间。

**主键**：`(graph_id, participation_id)`。

| 字段 | SQL 类型 | 键 | NULL | 默认值 | 含义 |
|---|---|---|---|---|---|
| `graph_id` | `VARCHAR(128)` | PK/FK | 否 | — | 所属人物图的标识；复合键和外键均以此限定引用范围。 |
| `participation_id` | `VARCHAR(128)` | PK | 否 | — | 本图中的角色参与记录标识；同一实体可有多条。 |
| `occurrence_id` | `VARCHAR(128)` | FK | 否 | — | 具体发生场景的图内标识。 |
| `entity_id` | `VARCHAR(128)` | FK | 否 | — | 图内实体标识。 |
| `role` | `TEXT` | — | 否 | — | 实体在该 Occurrence 中的角色。 |
| `start_time_id` | `VARCHAR(128)` | FK | 是 | — | 起点时间记录；未知引用时为空。 |
| `end_time_id` | `VARCHAR(128)` | FK | 是 | — | 终点时间记录；未知引用时为空。 |
| `evidence_set_id` | `VARCHAR(128)` | FK | 是 | — | 本记录的局部字段证据集；未知或未单独提供时为空。 |
| `sort_order` | `INT UNSIGNED` | — | 否 | `0` | 从零开始的显示/还原顺序；不表示事实时间或优先级。 |

**外键**：

- `(graph_id, occurrence_id, entity_id)` → `occurrence_participant(graph_id, occurrence_id, entity_id)`。
- `(graph_id, evidence_set_id)` → `evidence_set(graph_id, evidence_set_id)`。
- `(graph_id, start_time_id)` → `time_value(graph_id, time_id)`。
- `(graph_id, end_time_id)` → `time_value(graph_id, time_id)`。

## 7. action

原始行为记录：保存实施者、发生场景、行为内容和时间。

**主键**：`(graph_id, action_id)`。

| 字段 | SQL 类型 | 键 | NULL | 默认值 | 含义 |
|---|---|---|---|---|---|
| `graph_id` | `VARCHAR(128)` | PK/FK | 否 | — | 所属人物图的标识；复合键和外键均以此限定引用范围。 |
| `action_id` | `VARCHAR(128)` | PK | 否 | — | 行为的图内标识。 |
| `occurrence_id` | `VARCHAR(128)` | FK | 否 | — | 具体发生场景的图内标识。 |
| `actor_id` | `VARCHAR(128)` | FK | 否 | — | 实际实施者；必须属于同一 Occurrence 的参与者集合。 |
| `action_type` | `TEXT` | — | 否 | — | 行为、判断或发言的文字描述。 |
| `timestamp_time_id` | `VARCHAR(128)` | FK | 是 | — | 该行为/交易发生时间的记录。 |
| `evidence_set_id` | `VARCHAR(128)` | FK | 是 | — | 本记录的局部字段证据集；未知或未单独提供时为空。 |
| `sort_order` | `INT UNSIGNED` | — | 否 | `0` | 从零开始的显示/还原顺序；不表示事实时间或优先级。 |

**外键**：

- `(graph_id, occurrence_id, actor_id)` → `occurrence_participant(graph_id, occurrence_id, entity_id)`。
- `(graph_id, evidence_set_id)` → `evidence_set(graph_id, evidence_set_id)`。
- `(graph_id, timestamp_time_id)` → `time_value(graph_id, time_id)`。

## 8. financial_transaction

原始交易记录：保存所属场景、交易双方、时间和内容。

**主键**：`(graph_id, transaction_id)`。

| 字段 | SQL 类型 | 键 | NULL | 默认值 | 含义 |
|---|---|---|---|---|---|
| `graph_id` | `VARCHAR(128)` | PK/FK | 否 | — | 所属人物图的标识；复合键和外键均以此限定引用范围。 |
| `transaction_id` | `VARCHAR(128)` | PK | 否 | — | 交易的图内标识。 |
| `occurrence_id` | `VARCHAR(128)` | FK | 否 | — | 具体发生场景的图内标识。 |
| `name` | `TEXT` | — | 否 | — | 交易名称。 |
| `from_entity_id` | `VARCHAR(128)` | FK | 是 | — | 已知交易发起方，引用同一 Occurrence 的参与者；未知为 NULL。 |
| `to_entity_id` | `VARCHAR(128)` | FK | 是 | — | 已知交易接收方，引用同一 Occurrence 的参与者；未知为 NULL。 |
| `timestamp_time_id` | `VARCHAR(128)` | FK | 是 | — | 该行为/交易发生时间的记录。 |
| `details` | `JSON` | — | 是 | — | 有序交易细节的 JSON 值，保留原始内容。 |
| `evidence_set_id` | `VARCHAR(128)` | FK | 是 | — | 本记录的局部字段证据集；未知或未单独提供时为空。 |
| `sort_order` | `INT UNSIGNED` | — | 否 | `0` | 从零开始的显示/还原顺序；不表示事实时间或优先级。 |

**外键**：

- `(graph_id, occurrence_id)` → `occurrence(graph_id, occurrence_id)`。
- `(graph_id, occurrence_id, from_entity_id)` → `occurrence_participant(graph_id, occurrence_id, entity_id)`。
- `(graph_id, occurrence_id, to_entity_id)` → `occurrence_participant(graph_id, occurrence_id, entity_id)`。
- `(graph_id, evidence_set_id)` → `evidence_set(graph_id, evidence_set_id)`。
- `(graph_id, timestamp_time_id)` → `time_value(graph_id, time_id)`。

## 9. transaction_instrument

交易标的描述：一行对应一项有序的原始标的描述。

**主键**：`(graph_id, transaction_id, ordinal)`。

| 字段 | SQL 类型 | 键 | NULL | 默认值 | 含义 |
|---|---|---|---|---|---|
| `graph_id` | `VARCHAR(128)` | PK/FK | 否 | — | 所属人物图的标识；复合键和外键均以此限定引用范围。 |
| `transaction_id` | `VARCHAR(128)` | PK/FK | 否 | — | 交易的图内标识。 |
| `ordinal` | `INT UNSIGNED` | PK | 否 | — | 交易内从零开始的标的描述序号。 |
| `description` | `TEXT` | — | 否 | — | 交易标的原始描述；不生成独立金融工具身份。 |
| `evidence_set_id` | `VARCHAR(128)` | FK | 是 | — | 本记录的局部字段证据集；未知或未单独提供时为空。 |

**外键**：

- `(graph_id, transaction_id)` → `financial_transaction(graph_id, transaction_id)`。
- `(graph_id, evidence_set_id)` → `evidence_set(graph_id, evidence_set_id)`。

## 10. entity_relation

实体关系：保存人物/机构间关系及有效时间。

**主键**：`(graph_id, relation_id)`。

| 字段 | SQL 类型 | 键 | NULL | 默认值 | 含义 |
|---|---|---|---|---|---|
| `graph_id` | `VARCHAR(128)` | PK/FK | 否 | — | 所属人物图的标识；复合键和外键均以此限定引用范围。 |
| `relation_id` | `VARCHAR(128)` | PK | 否 | — | 实体关系的图内标识。 |
| `from_entity_id` | `VARCHAR(128)` | FK | 否 | — | 关系或交易的起始实体标识。 |
| `to_entity_id` | `VARCHAR(128)` | FK | 否 | — | 关系或交易的目标实体标识。 |
| `relation_type` | `TEXT` | — | 否 | — | 实体关系名称，如 chairman of。 |
| `valid_from_time_id` | `VARCHAR(128)` | FK | 是 | — | 关系有效期起点的时间记录。 |
| `valid_to_time_id` | `VARCHAR(128)` | FK | 是 | — | 关系有效期终点的时间记录。 |
| `evidence_set_id` | `VARCHAR(128)` | FK | 是 | — | 本记录的局部字段证据集；未知或未单独提供时为空。 |
| `sort_order` | `INT UNSIGNED` | — | 否 | `0` | 从零开始的显示/还原顺序；不表示事实时间或优先级。 |

**外键**：

- `(graph_id, from_entity_id)` → `entity(graph_id, entity_id)`。
- `(graph_id, to_entity_id)` → `entity(graph_id, entity_id)`。
- `(graph_id, evidence_set_id)` → `evidence_set(graph_id, evidence_set_id)`。
- `(graph_id, valid_from_time_id)` → `time_value(graph_id, time_id)`。
- `(graph_id, valid_to_time_id)` → `time_value(graph_id, time_id)`。

## 11. relation_occurrence

实体关系与场景的多对多关联。

**主键**：`(graph_id, relation_id, occurrence_id)`。

| 字段 | SQL 类型 | 键 | NULL | 默认值 | 含义 |
|---|---|---|---|---|---|
| `graph_id` | `VARCHAR(128)` | PK/FK | 否 | — | 所属人物图的标识；复合键和外键均以此限定引用范围。 |
| `relation_id` | `VARCHAR(128)` | PK/FK | 否 | — | 实体关系的图内标识。 |
| `occurrence_id` | `VARCHAR(128)` | PK/FK | 否 | — | 具体发生场景的图内标识。 |
| `sort_order` | `INT UNSIGNED` | — | 否 | `0` | 从零开始的显示/还原顺序；不表示事实时间或优先级。 |

**外键**：

- `(graph_id, relation_id)` → `entity_relation(graph_id, relation_id)`。
- `(graph_id, occurrence_id)` → `occurrence(graph_id, occurrence_id)`。

## 12. source_document

来源正文：保存引文定位所用的原文。

**主键**：`(graph_id, document_id)`。

| 字段 | SQL 类型 | 键 | NULL | 默认值 | 含义 |
|---|---|---|---|---|---|
| `graph_id` | `VARCHAR(128)` | PK/FK | 否 | — | 所属人物图的标识；复合键和外键均以此限定引用范围。 |
| `document_id` | `VARCHAR(128)` | PK | 否 | — | 来源文档的图内标识。 |
| `title` | `TEXT` | — | 是 | — | 原始文档标题；未提供时为空。 |
| `source_url` | `TEXT` | — | 是 | — | 可核实的来源 URL；未提供时为空。 |
| `published_at` | `DATETIME(6)` | — | 是 | — | 文档发布时间；JSON 使用带时区的 ISO 日期时间（`Z` 或 `±HH:MM`），小数秒最多 6 位；入库先转为 UTC，再移除时区，读回按 UTC 解释。 |
| `content` | `LONGTEXT` | — | 否 | — | 准确的来源正文，作为引文字符偏移的基准。 |

**外键**：

- `(graph_id)` → `subject_graph(graph_id)`。

## 13. evidence_span

原文引文：保存正文片段或尚未定位的旧引文。

**主键**：`(graph_id, span_id)`。

| 字段 | SQL 类型 | 键 | NULL | 默认值 | 含义 |
|---|---|---|---|---|---|
| `graph_id` | `VARCHAR(128)` | PK/FK | 否 | — | 所属人物图的标识；复合键和外键均以此限定引用范围。 |
| `span_id` | `VARCHAR(128)` | PK | 否 | — | 引文片段的图内标识。 |
| `document_id` | `VARCHAR(128)` | FK | 是 | — | 可定位的源文档；与两个偏移同时有值或同时为空。 |
| `char_start` | `BIGINT UNSIGNED` | — | 是 | — | Unicode 码点起点，包含该字符。 |
| `char_end` | `BIGINT UNSIGNED` | — | 是 | — | Unicode 码点终点，不包含该字符；必须大于起点。 |
| `quote` | `LONGTEXT` | — | 否 | — | 原文连续引文；定位已知时须等于正文切片。 |

**外键**：

- `(graph_id)` → `subject_graph(graph_id)`。
- `(graph_id, document_id)` → `source_document(graph_id, document_id)`。

**唯一性与检查约束**：

```sql
CONSTRAINT `ck_span_location` CHECK ((`document_id` IS NULL AND `char_start` IS NULL AND `char_end` IS NULL) OR (`document_id` IS NOT NULL AND `char_start` IS NOT NULL AND `char_end` IS NOT NULL AND `char_end` > `char_start`));
CONSTRAINT `uq_resolved_span` UNIQUE (`graph_id`, `document_id`, `char_start`, `char_end`);
```

## 14. evidence_set

局部证据容器：保存字段元数据。

**主键**：`(graph_id, evidence_set_id)`。

| 字段 | SQL 类型 | 键 | NULL | 默认值 | 含义 |
|---|---|---|---|---|---|
| `graph_id` | `VARCHAR(128)` | PK/FK | 否 | — | 所属人物图的标识；复合键和外键均以此限定引用范围。 |
| `evidence_set_id` | `VARCHAR(128)` | PK | 否 | — | 本记录的局部字段证据集；未知或未单独提供时为空。 |
| `field_metadata` | `JSON` | — | 是 | — | 按局部 JSON Pointer 保存理由、置信度、状态及还原元数据。 |

**外键**：

- `(graph_id)` → `subject_graph(graph_id)`。

## 15. evidence_link

字段与引文的多对多连接，包含字段路径及引用顺序。

**主键**：`(graph_id, evidence_set_id, field_path, quote_order)`。

| 字段 | SQL 类型 | 键 | NULL | 默认值 | 含义 |
|---|---|---|---|---|---|
| `graph_id` | `VARCHAR(128)` | PK/FK | 否 | — | 所属人物图的标识；复合键和外键均以此限定引用范围。 |
| `evidence_set_id` | `VARCHAR(128)` | PK/FK | 否 | — | 本记录的局部字段证据集；未知或未单独提供时为空。 |
| `field_path` | `VARCHAR(255)` | PK | 否 | — | 证据集所属记录内的字段路径，按 JSON Pointer 转义。 |
| `quote_order` | `INT UNSIGNED` | PK | 否 | — | 同一字段的从零开始引文序号；保留引用顺序。 |
| `span_id` | `VARCHAR(128)` | FK | 否 | — | 引文片段的图内标识。 |

**外键**：

- `(graph_id, evidence_set_id)` → `evidence_set(graph_id, evidence_set_id)`。
- `(graph_id, span_id)` → `evidence_span(graph_id, span_id)`。

## 16. time_value

可复用时间记录：原值与可选时间窗口。

**主键**：`(graph_id, time_id)`。

| 字段 | SQL 类型 | 键 | NULL | 默认值 | 含义 |
|---|---|---|---|---|---|
| `graph_id` | `VARCHAR(128)` | PK/FK | 否 | — | 所属人物图的标识；复合键和外键均以此限定引用范围。 |
| `time_id` | `VARCHAR(128)` | PK | 否 | — | 时间记录的图内标识。 |
| `value` | `VARCHAR(128)` | — | 否 | — | 原格式规范时间值，可包含 unknown；不强制伪造具体日期。 |
| `window_start` | `DATE` | — | 是 | — | 已有时间窗口起点，YYYY-MM-DD。 |
| `window_end` | `DATE` | — | 是 | — | 已有时间窗口终点，YYYY-MM-DD，包含该日。 |
| `original_text` | `TEXT` | — | 是 | — | 产生该窗口的原时间表达，如 2022 年 7 月下旬。 |
| `is_approximate` | `BOOLEAN` | — | 是 | — | 该窗口的日期是否为近似表示。 |
| `window_semantics` | `VARCHAR(16)` | — | 是 | — | uncertainty / duration；旧材料未说明时为 NULL。 |

**外键**：

- `(graph_id)` → `subject_graph(graph_id)`。

**唯一性与检查约束**：

```sql
CONSTRAINT `ck_time_window` CHECK ((`window_start` IS NULL AND `window_end` IS NULL AND `original_text` IS NULL AND `is_approximate` IS NULL) OR (`window_start` IS NOT NULL AND `window_end` IS NOT NULL AND `original_text` IS NOT NULL AND `is_approximate` IS NOT NULL AND `window_start` <= `window_end` AND `is_approximate` IN (0,1)));
CONSTRAINT ck_window_semantics CHECK (window_semantics IS NULL OR (window_start IS NOT NULL AND window_semantics IN ('uncertainty','duration')));
```

## 17. occurrence_label

场景短标题：一条场景最多一个全图显示名称。

**主键**：`(graph_id, occurrence_id)`。

| 字段 | SQL 类型 | 键 | NULL | 默认值 | 含义 |
|---|---|---|---|---|---|
| `graph_id` | `VARCHAR(128)` | PK/FK | 否 | — | 所属人物图的标识；复合键和外键均以此限定引用范围。 |
| `occurrence_id` | `VARCHAR(128)` | PK/FK | 否 | — | 具体发生场景的图内标识。 |
| `label` | `TEXT` | — | 否 | — | Occurrence 的可选全图短标题；原始 title 保留。 |

**外键**：

- `(graph_id, occurrence_id)` → `occurrence(graph_id, occurrence_id)`。

## 18. activity

活动注册表：一行恰好引用一个行为、交易或背景事项。

**主键**：`(graph_id, activity_id)`。

| 字段 | SQL 类型 | 键 | NULL | 默认值 | 含义 |
|---|---|---|---|---|---|
| `graph_id` | `VARCHAR(128)` | PK/FK | 否 | — | 所属人物图的标识；复合键和外键均以此限定引用范围。 |
| `activity_id` | `VARCHAR(128)` | PK | 否 | — | 统一活动标识，引用一个既有事实。 |
| `action_id` | `VARCHAR(128)` | FK | 是 | — | 引用原始 action；与另外两类事实引用互斥。 |
| `transaction_id` | `VARCHAR(128)` | FK | 是 | — | 引用原始 financial_transaction；与另外两类事实引用互斥。 |
| `context_occurrence_id` | `VARCHAR(128)` | FK | 是 | — | 引用单独展示的背景 Occurrence；与另外两类事实引用互斥。 |

**外键**：

- `(graph_id)` → `subject_graph(graph_id)`。
- `(graph_id, action_id)` → `action(graph_id, action_id)`。
- `(graph_id, transaction_id)` → `financial_transaction(graph_id, transaction_id)`。
- `(graph_id, context_occurrence_id)` → `occurrence(graph_id, occurrence_id)`。

**唯一性与检查约束**：

```sql
CONSTRAINT ck_activity_one_fact CHECK ((CASE WHEN action_id IS NULL THEN 0 ELSE 1 END + CASE WHEN transaction_id IS NULL THEN 0 ELSE 1 END + CASE WHEN context_occurrence_id IS NULL THEN 0 ELSE 1 END) = 1);
CONSTRAINT uq_activity_action UNIQUE (graph_id, action_id);
CONSTRAINT uq_activity_transaction UNIQUE (graph_id, transaction_id);
CONSTRAINT uq_activity_context UNIQUE (graph_id, context_occurrence_id);
```

## 19. activity_detail

活动原始细节：同一正文可被不同 Event 选择显示。

**主键**：`(graph_id, activity_id, detail_index)`。

| 字段 | SQL 类型 | 键 | NULL | 默认值 | 含义 |
|---|---|---|---|---|---|
| `graph_id` | `VARCHAR(128)` | PK/FK | 否 | — | 所属人物图的标识；复合键和外键均以此限定引用范围。 |
| `activity_id` | `VARCHAR(128)` | PK/FK | 否 | — | 统一活动标识，引用一个既有事实。 |
| `detail_index` | `INT UNSIGNED` | PK | 否 | — | 从零开始的细节序号；在对应 Activity 内唯一。 |
| `value` | `TEXT` | — | 否 | — | 该活动的一条原始细节正文。 |
| `evidence_set_id` | `VARCHAR(128)` | FK | 是 | — | 本记录的局部字段证据集；未知或未单独提供时为空。 |

**外键**：

- `(graph_id, activity_id)` → `activity(graph_id, activity_id)`。
- `(graph_id, evidence_set_id)` → `evidence_set(graph_id, evidence_set_id)`。

## 20. domain

领域：同一人物图中的一个组织类别。

**主键**：`(graph_id, domain_id)`。

| 字段 | SQL 类型 | 键 | NULL | 默认值 | 含义 |
|---|---|---|---|---|---|
| `graph_id` | `VARCHAR(128)` | PK/FK | 否 | — | 所属人物图的标识；复合键和外键均以此限定引用范围。 |
| `domain_id` | `VARCHAR(128)` | PK | 否 | — | 领域的图内标识。 |
| `label` | `TEXT` | — | 否 | — | 任务生成的领域名称，如投资与收购。 |
| `summary` | `TEXT` | — | 是 | — | 领域的可选概述。 |
| `sort_order` | `INT UNSIGNED` | — | 否 | `0` | 从零开始的显示/还原顺序；不表示事实时间或优先级。 |

**外键**：

- `(graph_id)` → `subject_graph(graph_id)`。

## 21. event

人物持续经历：归属于一个主要领域。

**主键**：`(graph_id, event_id)`。

| 字段 | SQL 类型 | 键 | NULL | 默认值 | 含义 |
|---|---|---|---|---|---|
| `graph_id` | `VARCHAR(128)` | PK/FK | 否 | — | 所属人物图的标识；复合键和外键均以此限定引用范围。 |
| `event_id` | `VARCHAR(128)` | PK | 否 | — | 组织层 Event 的图内标识。 |
| `domain_id` | `VARCHAR(128)` | FK | 否 | — | 领域的图内标识。 |
| `label` | `TEXT` | — | 否 | — | 持续经历名称，如西方石油投资。 |
| `summary` | `TEXT` | — | 是 | — | 该 Event 的可选人物经历摘要。 |
| `evidence_set_id` | `VARCHAR(128)` | FK | 是 | — | 本记录的局部字段证据集；未知或未单独提供时为空。 |
| `sort_order` | `INT UNSIGNED` | — | 否 | `0` | 从零开始的显示/还原顺序；不表示事实时间或优先级。 |

**外键**：

- `(graph_id, domain_id)` → `domain(graph_id, domain_id)`。
- `(graph_id, evidence_set_id)` → `evidence_set(graph_id, evidence_set_id)`。

## 22. stage

人物参与阶段：在所属 Event 内唯一。

**主键**：`(graph_id, event_id, stage_id)`。

| 字段 | SQL 类型 | 键 | NULL | 默认值 | 含义 |
|---|---|---|---|---|---|
| `graph_id` | `VARCHAR(128)` | PK/FK | 否 | — | 所属人物图的标识；复合键和外键均以此限定引用范围。 |
| `event_id` | `VARCHAR(128)` | PK/FK | 否 | — | 组织层 Event 的图内标识。 |
| `stage_id` | `VARCHAR(128)` | PK | 否 | — | 所属 Event 内的阶段标识。 |
| `label` | `TEXT` | — | 否 | — | 阶段名称，描述人物行动、判断或参与方式的变化。 |
| `summary` | `TEXT` | — | 是 | — | 该阶段的可选摘要。 |
| `boundary_reason` | `TEXT` | — | 是 | — | 阶段划分依据；支持片段引用 evidence_set_id。 |
| `evidence_set_id` | `VARCHAR(128)` | FK | 是 | — | 本记录的局部字段证据集；未知或未单独提供时为空。 |
| `sort_order` | `INT UNSIGNED` | — | 否 | `0` | 从零开始的显示/还原顺序；不表示事实时间或优先级。 |

**外键**：

- `(graph_id, event_id)` → `event(graph_id, event_id)`。
- `(graph_id, evidence_set_id)` → `evidence_set(graph_id, evidence_set_id)`。

## 23. event_activity

Event 的活动成员及可选阶段归属。

**主键**：`(graph_id, event_id, activity_id)`。

| 字段 | SQL 类型 | 键 | NULL | 默认值 | 含义 |
|---|---|---|---|---|---|
| `graph_id` | `VARCHAR(128)` | PK/FK | 否 | — | 所属人物图的标识；复合键和外键均以此限定引用范围。 |
| `event_id` | `VARCHAR(128)` | PK/FK | 否 | — | 组织层 Event 的图内标识。 |
| `activity_id` | `VARCHAR(128)` | PK/FK | 否 | — | 统一活动标识，引用一个既有事实。 |
| `stage_id` | `VARCHAR(128)` | FK | 是 | — | 可空阶段归属；为空时活动直接挂在 Event 下。 |
| `display_title` | `TEXT` | — | 是 | — | 当前 Event 中的可选展示标题；为空时读取事实标题。 |
| `detail_mode` | `VARCHAR(16)` | — | 否 | `'all'` | all：全部细节；selected：按 event_activity_detail 选取。 |
| `sort_order` | `INT UNSIGNED` | — | 否 | `0` | 从零开始的显示/还原顺序；不表示事实时间或优先级。 |

**外键**：

- `(graph_id, event_id)` → `event(graph_id, event_id)`。
- `(graph_id, activity_id)` → `activity(graph_id, activity_id)`。
- `(graph_id, event_id, stage_id)` → `stage(graph_id, event_id, stage_id)`。

**唯一性与检查约束**：

```sql
CONSTRAINT ck_detail_mode CHECK (detail_mode IN ('all','selected'));
```

## 24. event_activity_detail

某个 Event 中某个活动选中的原始细节。

**主键**：`(graph_id, event_id, activity_id, detail_index)`。

| 字段 | SQL 类型 | 键 | NULL | 默认值 | 含义 |
|---|---|---|---|---|---|
| `graph_id` | `VARCHAR(128)` | PK/FK | 否 | — | 所属人物图的标识；复合键和外键均以此限定引用范围。 |
| `event_id` | `VARCHAR(128)` | PK/FK | 否 | — | 组织层 Event 的图内标识。 |
| `activity_id` | `VARCHAR(128)` | PK/FK | 否 | — | 统一活动标识，引用一个既有事实。 |
| `detail_index` | `INT UNSIGNED` | PK/FK | 否 | — | 从零开始的细节序号；在对应 Activity 内唯一。 |

**外键**：

- `(graph_id, event_id, activity_id)` → `event_activity(graph_id, event_id, activity_id)`。
- `(graph_id, activity_id, detail_index)` → `activity_detail(graph_id, activity_id, detail_index)`。

## 25. activity_relation

活动之间的有向联系，独立保存连线证据。

**主键**：`(graph_id, link_id)`。

| 字段 | SQL 类型 | 键 | NULL | 默认值 | 含义 |
|---|---|---|---|---|---|
| `graph_id` | `VARCHAR(128)` | PK/FK | 否 | — | 所属人物图的标识；复合键和外键均以此限定引用范围。 |
| `link_id` | `VARCHAR(128)` | PK | 否 | — | 活动关系的图内标识。 |
| `from_activity_id` | `VARCHAR(128)` | FK | 否 | — | 关系起点 Activity。 |
| `to_activity_id` | `VARCHAR(128)` | FK | 否 | — | 关系终点 Activity；与起点不同。 |
| `relation_type` | `VARCHAR(32)` | — | 否 | — | precedes / overlaps / executed_by / explains / responds_to / context_for。 |
| `description` | `TEXT` | — | 是 | — | 该连线的可选文字说明。 |
| `basis` | `VARCHAR(16)` | — | 否 | — | source / inferred / temporal；temporal 只配时间关系。 |
| `evidence_set_id` | `VARCHAR(128)` | FK | 是 | — | 连线本身的证据集；非时间关系必须有实际引文支持。 |

**外键**：

- `(graph_id, from_activity_id)` → `activity(graph_id, activity_id)`。
- `(graph_id, to_activity_id)` → `activity(graph_id, activity_id)`。
- `(graph_id, evidence_set_id)` → `evidence_set(graph_id, evidence_set_id)`。

**唯一性与检查约束**：

```sql
CONSTRAINT ck_link_not_self CHECK (from_activity_id <> to_activity_id);
CONSTRAINT ck_activity_relation_type CHECK (relation_type IN ('precedes','overlaps','executed_by','explains','responds_to','context_for'));
CONSTRAINT ck_relation_basis CHECK (basis IN ('source','inferred','temporal'));
CONSTRAINT ck_semantic_link_evidence CHECK (relation_type IN ('precedes','overlaps') OR evidence_set_id IS NOT NULL);
CONSTRAINT uq_activity_link UNIQUE (graph_id, from_activity_id, to_activity_id, relation_type);
CONSTRAINT ck_temporal_basis CHECK (basis <> 'temporal' OR relation_type IN ('precedes','overlaps'));
```

## 完整性约定

- 所有 FK 默认限制更新/删除，无级联操作。复合 FK 中可空引用为 NULL 时按 MySQL 的外键规则处理；其余组成字段仍受本行约束。
- SQL 的可空状态也包括分步加载用途；完成态焦点人物必须存在，且类型为 `individual`。
- 非时间活动关系还须引用至少一个实际引文，已定位引文须等于正文切片；这些跨表内容检查由 `validate_person_epg` 完成。
- `overlaps` 的两个端点语义对称；SQL 仅对已保存的有向端点组合去重。组织器若需消除反向重复，应采用一致的端点顺序。
- 行内 CHECK/UNIQUE 在上表逐项列出；阶段依据、个人决策归属和证据是否充分由构建/复查流程处理。
