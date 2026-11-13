# 6 · 合成案例：从输入到图与检查

导航：[总览](0-overview.md) · [输入与事实](1-input-and-facts.md) · [图协议](2-graph-contract.md) · [检查与输出](5-validation-and-output.md)

本例的人物、机构、事件、正文和 ID 均为文档作者构造的合成数据，未访问外部来源，也不是模型构建实验或真实效果证明。它只演示协议如何衔接。正式运行继承实际目录 ID、来源与原文，不采用本例的占位身份。

## 6.1 已确认输入

用户选择 Mina Lee 的一条 Event，确认 2020 年 2 月 1–7 日的行为范围。输入仍使用公共的 `user_query + samples`；以下三段是本次全部交接正文，也是三个合成来源的完整文本。`content_status=full_text` 描述本例来源的获取范围，不是实际模型阅读的证明。

```json
{
  "user_query": {
    "query_text": "Reconstruct Mina Lee's response under the disclosure restriction during 1–7 February 2020.",
    "key_words": ["Mina Lee", "disclosure restriction"],
    "extras": {
      "person_event": {
        "person_id": "DEMO-PERSON-0001",
        "person_name": "Mina Lee",
        "storyline_id": "DEMO-STORYLINE-01",
        "storyline_name": "Public communication",
        "event_id": "DEMO-EVENT-01",
        "event_name": "Response under a disclosure restriction",
        "scope": {
          "period": "1–7 February 2020",
          "include": "The restriction, Lee's acknowledgement, internal briefing and public response.",
          "exclude": "Other projects and later communication."
        },
        "aliases": []
      },
      "source_registry": {
        "SRC-1": {
          "title": "Synthetic record 1",
          "source_url": null,
          "origin": "Authored example, sample SAMPLE-1; not a real publication.",
          "published_at": null,
          "retrieved_at": null,
          "source_type": "synthetic_record",
          "content_status": "full_text"
        },
        "SRC-2": {
          "title": "Synthetic record 2",
          "source_url": null,
          "origin": "Authored example, sample SAMPLE-2; not a real publication.",
          "published_at": null,
          "retrieved_at": null,
          "source_type": "synthetic_record",
          "content_status": "full_text"
        },
        "SRC-3": {
          "title": "Synthetic record 3",
          "source_url": null,
          "origin": "Authored example, sample SAMPLE-3; not a real publication.",
          "published_at": null,
          "retrieved_at": null,
          "source_type": "synthetic_record",
          "content_status": "full_text"
        }
      }
    }
  },
  "samples": [
    {
      "sample_id": "SAMPLE-1",
      "raw_data_id": "SRC-1",
      "content": "On 1 February 2020, the Harbor Project Office issued a disclosure restriction. The restriction applied to Mina Lee's public statements and remained in effect through 7 February 2020. On 1 February 2020, Mina Lee, acting in her personal capacity, received and acknowledged the restriction."
    },
    {
      "sample_id": "SAMPLE-2",
      "raw_data_id": "SRC-2",
      "content": "On 3 February 2020, Mina Lee, acting in her personal capacity, held an internal briefing about the disclosure restriction. From 1 through 4 February 2020, Lee focused on internal preparation."
    },
    {
      "sample_id": "SAMPLE-3",
      "raw_data_id": "SRC-3",
      "content": "On 5 February 2020, Mina Lee, acting in her personal capacity, published a response. The response addressed questions raised in the internal briefing on 3 February. From 5 through 7 February 2020, Lee focused on public communication."
    }
  ]
}
```

## 6.2 统一事实与定位

抽取首先形成三个候选动作，未组织前的 `phase_id` 为 null。限制的存在进入环境 Context；机构是 Entity，机构发布限制的独立行为作为上下文依据，不额外扩充焦点人物的动作集合。

| 事实 | 原文 | 组织后的去向 |
| --- | --- | --- |
| 接收并确认限制 | EV-3 | ACTION-1 → PHASE-1 |
| 召开内部说明会 | EV-4 | ACTION-2 → PHASE-1 |
| 发布回应 | EV-6、EV-7 | ACTION-3 → PHASE-2 |
| 披露限制及其适用时期 | EV-1、EV-2 | CTX-1；Stage 局面依据 |
| 确认接收所支持的知情 | EV-3 | CTX-2，以 I 说明推断边界 |
| 回应针对说明会问题 | EV-7，结合动作证据 | CANDIDATE-1 → REL-3 |

资料还明确给出两种行为模式的时期，因此在一个 Stage 内组织两个 Phase；不是因为有三份材料就生成三个阶段。组织只写入动作归属，不重新提取动作。

以下偏移按三个输入 sample 的 Unicode 码点计算；引文必须逐字匹配。所有来源仅为本例的本地合成记录。

| Evidence | sample | 起止偏移 | quote |
| --- | --- | --- | --- |
| `EV-1` | `SAMPLE-1` | `[0, 78)` | On 1 February 2020, the Harbor Project Office issued a disclosure restriction. |
| `EV-2` | `SAMPLE-1` | `[79, 182)` | The restriction applied to Mina Lee's public statements and remained in effect through 7 February 2020. |
| `EV-3` | `SAMPLE-1` | `[183, 288)` | On 1 February 2020, Mina Lee, acting in her personal capacity, received and acknowledged the restriction. |
| `EV-4` | `SAMPLE-2` | `[0, 122)` | On 3 February 2020, Mina Lee, acting in her personal capacity, held an internal briefing about the disclosure restriction. |
| `EV-5` | `SAMPLE-2` | `[123, 191)` | From 1 through 4 February 2020, Lee focused on internal preparation. |
| `EV-6` | `SAMPLE-3` | `[0, 84)` | On 5 February 2020, Mina Lee, acting in her personal capacity, published a response. |
| `EV-7` | `SAMPLE-3` | `[85, 164)` | The response addressed questions raised in the internal briefing on 3 February. |
| `EV-8` | `SAMPLE-3` | `[165, 233)` | From 5 through 7 February 2020, Lee focused on public communication. |

## 6.3 最终图示例

以下完整 JSON 展示各对象的引用；字段规则仍以第 1、2 章为准。两个 Phase 的基准均明确保留缺口，不能因为有一项约束就宣称所有主体状态已知。

```json
{
  "schema_version": "person-event-1.0",
  "person": {"person_id": "DEMO-PERSON-0001", "name": "Mina Lee", "aliases": [], "event_ids": ["DEMO-EVENT-01"]},
  "storyline": {"storyline_id": "DEMO-STORYLINE-01", "person_id": "DEMO-PERSON-0001", "name": "Public communication"},
  "event": {
    "event_id": "DEMO-EVENT-01",
    "person_id": "DEMO-PERSON-0001",
    "storyline_id": "DEMO-STORYLINE-01",
    "name": "Response under a disclosure restriction",
    "scope": {
      "period": "1–7 February 2020",
      "include": "The restriction, Lee's acknowledgement, internal briefing and public response.",
      "exclude": "Other projects and later communication."
    },
    "time": {
      "text": "1–7 February 2020",
      "kind": "duration",
      "start": "2020-02-01",
      "end": "2020-02-08",
      "start_precision": "day",
      "end_precision": "day"
    },
    "summary": "During the disclosure restriction, Lee acknowledged receipt, held an internal briefing and published a response. The response addressed questions raised in the briefing; the documented behavior shifted from internal preparation to public communication.",
    "support": [
      {
        "target": "/summary",
        "mode": "I",
        "evidence_ids": [],
        "premise_refs": [
          {"collection": "actions", "object_id": "ACTION-1", "field": "/description"},
          {"collection": "actions", "object_id": "ACTION-2", "field": "/description"},
          {"collection": "actions", "object_id": "ACTION-3", "field": "/description"},
          {"collection": "phases", "object_id": "PHASE-1", "field": "/description"},
          {"collection": "phases", "object_id": "PHASE-2", "field": "/description"}
        ],
        "reason": "Synthesize the documented actions and the two stated behavior periods."
      },
      {"target": "/time", "mode": "A", "evidence_ids": ["EV-1", "EV-2", "EV-5", "EV-8"]}
    ]
  },
  "entities": [
    {"entity_id": "DEMO-PERSON-0001", "name": "Mina Lee", "type": "person", "aliases": []},
    {"entity_id": "ENTITY-OFFICE", "name": "Harbor Project Office", "type": "organization", "aliases": []}
  ],
  "stages": [
    {
      "stage_id": "STAGE-1",
      "event_id": "DEMO-EVENT-01",
      "name": "Restricted disclosure",
      "description": "Lee's public statements were subject to the disclosure restriction.",
      "time": {
        "text": "1–7 February 2020",
        "kind": "duration",
        "start": "2020-02-01",
        "end": "2020-02-08",
        "start_precision": "day",
        "end_precision": "day"
      },
      "boundary_reason": "The record bounds the restriction from its issue on 1 February through 7 February.",
      "support": [
        {"target": "/description", "mode": "A", "evidence_ids": ["EV-1", "EV-2"]},
        {"target": "/time", "mode": "A", "evidence_ids": ["EV-1", "EV-2"]},
        {
          "target": "/boundary_reason",
          "mode": "I",
          "evidence_ids": ["EV-1", "EV-2"],
          "reason": "Use the documented period of the restriction as the observed situation boundary, without inventing an earlier stage."
        }
      ]
    }
  ],
  "phases": [
    {
      "phase_id": "PHASE-1",
      "stage_id": "STAGE-1",
      "name": "Internal preparation",
      "description": "Lee focused on internal preparation.",
      "time": {
        "text": "1–4 February 2020",
        "kind": "duration",
        "start": "2020-02-01",
        "end": "2020-02-05",
        "start_precision": "day",
        "end_precision": "day"
      },
      "boundary_reason": "The source states the period of this behavior pattern.",
      "support": [
        {"target": "/description", "mode": "A", "evidence_ids": ["EV-5"]},
        {"target": "/time", "mode": "A", "evidence_ids": ["EV-5"]},
        {"target": "/boundary_reason", "mode": "O", "evidence_ids": ["EV-5"]}
      ],
      "baseline_context_refs": [
        {
          "context_id": "CTX-1",
          "relation_type": "constraint",
          "support": [{"target": "/relation_type", "mode": "A", "evidence_ids": ["EV-2"]}]
        }
      ],
      "gaps": [
        {
          "target": "/baseline_context_refs",
          "reason": "No phase-wide relationship or person-state baseline is established. The action-specific awareness of receipt is retained separately."
        }
      ]
    },
    {
      "phase_id": "PHASE-2",
      "stage_id": "STAGE-1",
      "name": "Public communication",
      "description": "Lee focused on public communication. Only one distinct action is documented within this phase.",
      "time": {
        "text": "5–7 February 2020",
        "kind": "duration",
        "start": "2020-02-05",
        "end": "2020-02-08",
        "start_precision": "day",
        "end_precision": "day"
      },
      "boundary_reason": "The source states the period of this behavior pattern.",
      "support": [
        {
          "target": "/description",
          "mode": "I",
          "evidence_ids": ["EV-6", "EV-8"],
          "reason": "The source states the behavior period. Only one distinct public action is present in the supplied records; this is not a claim of complete real-world coverage."
        },
        {"target": "/time", "mode": "A", "evidence_ids": ["EV-8"]},
        {"target": "/boundary_reason", "mode": "O", "evidence_ids": ["EV-8"]}
      ],
      "baseline_context_refs": [
        {
          "context_id": "CTX-1",
          "relation_type": "constraint",
          "support": [{"target": "/relation_type", "mode": "A", "evidence_ids": ["EV-2"]}]
        }
      ],
      "gaps": [
        {
          "target": "/baseline_context_refs",
          "reason": "No phase-wide relationship or person-state baseline is established. The action-specific awareness of receipt is retained separately."
        }
      ]
    }
  ],
  "actions": [
    {
      "action_id": "ACTION-1",
      "name": "Acknowledge restriction",
      "description": "Lee received and acknowledged the disclosure restriction.",
      "actor": {"entity_id": "DEMO-PERSON-0001", "capacity": "personal"},
      "object": {"description": "The disclosure restriction.", "entity_refs": []},
      "time": {
        "text": "On 1 February 2020",
        "kind": "occurrence_window",
        "start": "2020-02-01",
        "end": "2020-02-02",
        "start_precision": "day",
        "end_precision": "day"
      },
      "phase_id": "PHASE-1",
      "support": [
        {"target": "/description", "mode": "A", "evidence_ids": ["EV-3"]},
        {"target": "/actor", "mode": "A", "evidence_ids": ["EV-3"]},
        {"target": "/object", "mode": "A", "evidence_ids": ["EV-3"]},
        {"target": "/time", "mode": "A", "evidence_ids": ["EV-3"]},
        {
          "target": "/phase_id",
          "mode": "I",
          "evidence_ids": ["EV-3", "EV-5"],
          "reason": "The documented action date and behavior fit this phase's stated pattern."
        }
      ],
      "delta_context_refs": [
        {
          "context_id": "CTX-2",
          "relation_type": "knowledge-source",
          "entity_id": "DEMO-PERSON-0001",
          "support": [
            {
              "target": "/relation_type",
              "mode": "I",
              "evidence_ids": ["EV-3"],
              "reason": "Receipt and acknowledgement support the information reaching Lee at this action."
            }
          ]
        }
      ]
    },
    {
      "action_id": "ACTION-2",
      "name": "Hold internal briefing",
      "description": "Lee held an internal briefing about the disclosure restriction.",
      "actor": {"entity_id": "DEMO-PERSON-0001", "capacity": "personal"},
      "object": {"description": "The disclosure restriction discussed in the internal briefing.", "entity_refs": []},
      "time": {
        "text": "On 3 February 2020",
        "kind": "occurrence_window",
        "start": "2020-02-03",
        "end": "2020-02-04",
        "start_precision": "day",
        "end_precision": "day"
      },
      "phase_id": "PHASE-1",
      "support": [
        {"target": "/description", "mode": "A", "evidence_ids": ["EV-4"]},
        {"target": "/actor", "mode": "A", "evidence_ids": ["EV-4"]},
        {"target": "/object", "mode": "A", "evidence_ids": ["EV-4"]},
        {"target": "/time", "mode": "A", "evidence_ids": ["EV-4"]},
        {
          "target": "/phase_id",
          "mode": "I",
          "evidence_ids": ["EV-4", "EV-5"],
          "reason": "The documented action date and behavior fit this phase's stated pattern."
        }
      ]
    },
    {
      "action_id": "ACTION-3",
      "name": "Publish response",
      "description": "Lee published a response addressing questions from the internal briefing.",
      "actor": {"entity_id": "DEMO-PERSON-0001", "capacity": "personal"},
      "object": {"description": "Questions raised in the internal briefing on 3 February.", "entity_refs": []},
      "time": {
        "text": "On 5 February 2020",
        "kind": "occurrence_window",
        "start": "2020-02-05",
        "end": "2020-02-06",
        "start_precision": "day",
        "end_precision": "day"
      },
      "phase_id": "PHASE-2",
      "support": [
        {"target": "/description", "mode": "A", "evidence_ids": ["EV-6", "EV-7"]},
        {"target": "/actor", "mode": "A", "evidence_ids": ["EV-6"]},
        {"target": "/object", "mode": "A", "evidence_ids": ["EV-7"]},
        {"target": "/time", "mode": "A", "evidence_ids": ["EV-6"]},
        {
          "target": "/phase_id",
          "mode": "I",
          "evidence_ids": ["EV-6", "EV-7", "EV-8"],
          "reason": "The documented action date and behavior fit this phase's stated pattern."
        }
      ]
    }
  ],
  "relations": [
    {
      "relation_id": "REL-1",
      "from_action_id": "ACTION-1",
      "to_action_id": "ACTION-2",
      "type": "precedes",
      "basis": "derived",
      "support": [
        {
          "target": "",
          "mode": "I",
          "evidence_ids": [],
          "premise_refs": [
            {"collection": "actions", "object_id": "ACTION-1", "field": "/time"},
            {"collection": "actions", "object_id": "ACTION-2", "field": "/time"}
          ],
          "reason": "The latest possible occurrence in the first window precedes the earliest in the second; compare the exclusive end with the next start."
        }
      ]
    },
    {
      "relation_id": "REL-2",
      "from_action_id": "ACTION-2",
      "to_action_id": "ACTION-3",
      "type": "precedes",
      "basis": "derived",
      "support": [
        {
          "target": "",
          "mode": "I",
          "evidence_ids": [],
          "premise_refs": [
            {"collection": "actions", "object_id": "ACTION-2", "field": "/time"},
            {"collection": "actions", "object_id": "ACTION-3", "field": "/time"}
          ],
          "reason": "The latest possible occurrence in the first window precedes the earliest in the second; compare the exclusive end with the next start."
        }
      ]
    },
    {
      "relation_id": "REL-3",
      "from_action_id": "ACTION-3",
      "to_action_id": "ACTION-2",
      "type": "responds_to",
      "basis": "asserted",
      "support": [{"target": "", "mode": "A", "evidence_ids": ["EV-4", "EV-6", "EV-7"]}]
    }
  ],
  "contexts": [
    {
      "context_id": "CTX-1",
      "category": "environment",
      "description": "A disclosure restriction applied to Mina Lee's public statements.",
      "entity_refs": ["DEMO-PERSON-0001", "ENTITY-OFFICE"],
      "time": {
        "text": "Issued on 1 February; in effect through 7 February 2020.",
        "kind": "duration",
        "start": "2020-02-01",
        "end": "2020-02-08",
        "start_precision": "day",
        "end_precision": "day"
      },
      "perspective": "world",
      "support": [
        {"target": "/description", "mode": "A", "evidence_ids": ["EV-1", "EV-2"]},
        {"target": "/time", "mode": "A", "evidence_ids": ["EV-1", "EV-2"]},
        {"target": "/perspective", "mode": "A", "evidence_ids": ["EV-1", "EV-2"]}
      ]
    },
    {
      "context_id": "CTX-2",
      "category": "person_state",
      "description": "Lee was aware of receiving the disclosure restriction when she acknowledged it.",
      "entity_refs": ["DEMO-PERSON-0001"],
      "time": {
        "text": "On 1 February 2020",
        "kind": "occurrence_window",
        "start": "2020-02-01",
        "end": "2020-02-02",
        "start_precision": "day",
        "end_precision": "day"
      },
      "perspective": "belief",
      "support": [
        {
          "target": "",
          "mode": "I",
          "evidence_ids": ["EV-3"],
          "reason": "Acknowledging receipt supports awareness of receipt at that time; it does not establish a broader motive or knowledge."
        }
      ]
    }
  ],
  "sources": [
    {
      "source_id": "SRC-1",
      "title": "Synthetic record 1",
      "url": null,
      "origin": "Authored example, sample SAMPLE-1; not a real publication.",
      "published_at": null,
      "retrieved_at": null,
      "source_type": "synthetic_record",
      "content_status": "full_text"
    },
    {
      "source_id": "SRC-2",
      "title": "Synthetic record 2",
      "url": null,
      "origin": "Authored example, sample SAMPLE-2; not a real publication.",
      "published_at": null,
      "retrieved_at": null,
      "source_type": "synthetic_record",
      "content_status": "full_text"
    },
    {
      "source_id": "SRC-3",
      "title": "Synthetic record 3",
      "url": null,
      "origin": "Authored example, sample SAMPLE-3; not a real publication.",
      "published_at": null,
      "retrieved_at": null,
      "source_type": "synthetic_record",
      "content_status": "full_text"
    }
  ],
  "evidence": [
    {
      "evidence_id": "EV-1",
      "sample_id": "SAMPLE-1",
      "source_id": "SRC-1",
      "quote": "On 1 February 2020, the Harbor Project Office issued a disclosure restriction.",
      "start": 0,
      "end": 78,
      "location_status": "matched",
      "sample_sha256": "94a22a0ec711ff250f98d5875eb211b89d4ad16ed632276359f882e5f513b236"
    },
    {
      "evidence_id": "EV-2",
      "sample_id": "SAMPLE-1",
      "source_id": "SRC-1",
      "quote": "The restriction applied to Mina Lee's public statements and remained in effect through 7 February 2020.",
      "start": 79,
      "end": 182,
      "location_status": "matched",
      "sample_sha256": "94a22a0ec711ff250f98d5875eb211b89d4ad16ed632276359f882e5f513b236"
    },
    {
      "evidence_id": "EV-3",
      "sample_id": "SAMPLE-1",
      "source_id": "SRC-1",
      "quote": "On 1 February 2020, Mina Lee, acting in her personal capacity, received and acknowledged the restriction.",
      "start": 183,
      "end": 288,
      "location_status": "matched",
      "sample_sha256": "94a22a0ec711ff250f98d5875eb211b89d4ad16ed632276359f882e5f513b236"
    },
    {
      "evidence_id": "EV-4",
      "sample_id": "SAMPLE-2",
      "source_id": "SRC-2",
      "quote": "On 3 February 2020, Mina Lee, acting in her personal capacity, held an internal briefing about the disclosure restriction.",
      "start": 0,
      "end": 122,
      "location_status": "matched",
      "sample_sha256": "f60fbf786a311e1835ab40326ba3aee89bca00981b922dffb6868625e45b00ee"
    },
    {
      "evidence_id": "EV-5",
      "sample_id": "SAMPLE-2",
      "source_id": "SRC-2",
      "quote": "From 1 through 4 February 2020, Lee focused on internal preparation.",
      "start": 123,
      "end": 191,
      "location_status": "matched",
      "sample_sha256": "f60fbf786a311e1835ab40326ba3aee89bca00981b922dffb6868625e45b00ee"
    },
    {
      "evidence_id": "EV-6",
      "sample_id": "SAMPLE-3",
      "source_id": "SRC-3",
      "quote": "On 5 February 2020, Mina Lee, acting in her personal capacity, published a response.",
      "start": 0,
      "end": 84,
      "location_status": "matched",
      "sample_sha256": "fff4bf89dd92083e2f227b0da2ec2b0302d887ebf6a4b87aadca35d1bb7da42c"
    },
    {
      "evidence_id": "EV-7",
      "sample_id": "SAMPLE-3",
      "source_id": "SRC-3",
      "quote": "The response addressed questions raised in the internal briefing on 3 February.",
      "start": 85,
      "end": 164,
      "location_status": "matched",
      "sample_sha256": "fff4bf89dd92083e2f227b0da2ec2b0302d887ebf6a4b87aadca35d1bb7da42c"
    },
    {
      "evidence_id": "EV-8",
      "sample_id": "SAMPLE-3",
      "source_id": "SRC-3",
      "quote": "From 5 through 7 February 2020, Lee focused on public communication.",
      "start": 165,
      "end": 233,
      "location_status": "matched",
      "sample_sha256": "fff4bf89dd92083e2f227b0da2ec2b0302d887ebf6a4b87aadca35d1bb7da42c"
    }
  ]
}
```

图内 `ACTION-2 precedes ACTION-3` 与 `ACTION-3 responds_to ACTION-2` 同时存在。这是合法的类型化语义环；本例没有先后冲突，可用先后视图仍无环。由 REL-1、REL-2 的传递路径也能确定 ACTION-1 先于 ACTION-3，无需另存直接边或标为顺序未知。动作的图组合由归属派生，不再复制一份 Stage 图数据。

- `G(PHASE-1)` 含 ACTION-1、ACTION-2 和 REL-1。
- `G(PHASE-2)` 含 ACTION-3，没有内部关系；单动作原因写在 Phase 描述中。
- `G(STAGE-1)` 合并上述两图，再加入跨 Phase 的 REL-2、REL-3。
- 本例只有一个 Stage，所以 Event 动作图与该 Stage 的动作图相同。

支持记录区分来源断言 A、分析推导 I 与记录内容 O。两个 Phase 的边界理由写的是“来源明确给出该行为模式的时期”，所以该理由用 O；行为模式和时期本身仍按命题使用 A 或 I。已知行为对象保留在 Action.object 中，非实体对象不强造实体。未知基准保留 Gap，不制造主体动机。

## 6.4 检查与状态示例

下列为根据本例数据列出的示意检查报告，**不是新构建器运行产生的报告**。文件哈希按对应 JSON 对象以 UTF-8、两空格缩进、原字段顺序及末尾换行序列化后计算；与上面为便于阅读而混用紧凑排版的代码块字节不同。图中的 sample 哈希则针对确切的 `content`。

```json
{
  "run_id": "DEMO-RUN-01",
  "input_sha256": "cdc9903c1f5ac503909a83b46e27b27d5decb6613e04c536ad1b026312ad0f26",
  "graph_sha256": "e008604cf9e27b107b3f08008c3ec3d10adfb712d05e36913387438f4d16189f",
  "artifact_hashes": {},
  "summary": {
    "checked": [
      "identity",
      "references",
      "hierarchy",
      "known_time_constraints",
      "quote_locations",
      "consistent_precedence"
    ],
    "not_checked": [
      "semantic_support",
      "real_world_completeness"
    ],
    "errors": 0,
    "warnings": 2
  },
  "issues": [
    {
      "code": "CONTEXT_BASELINE_GAP",
      "severity": "warning",
      "artifact": "graph",
      "object_type": "phase",
      "object_id": "PHASE-1",
      "field": "/baseline_context_refs",
      "message": "No phase-wide relationship or person-state baseline is established. The action-specific awareness of receipt is retained separately."
    },
    {
      "code": "CONTEXT_BASELINE_GAP",
      "severity": "warning",
      "artifact": "graph",
      "object_type": "phase",
      "object_id": "PHASE-2",
      "field": "/baseline_context_refs",
      "message": "No phase-wide relationship or person-state baseline is established. The action-specific awareness of receipt is retained separately."
    }
  ],
  "review_required": true
}
```

这份示例图可以表达为 `execution_status=finished`、`result_status=draft`。两项缺口保留待审核，`review_required` 为 true；不能据此认定描述内容已经正确。Gantt 状态只有实际绘制后才能标为 completed，本例不声称已经生成图表。

若 ACTION-3 无法归属 Phase，应保留它及原因，产生 `ACTION_PHASE_MISSING`，结果为 partial；不能把它从图和事实记录中删除以得到零错误。若只是 Gantt 绘制失败，则图与检查保留，设置 `render_status=failed`，不重跑模型。

以下是独立的协议边界检查，不改变上面的示例图或示意报告：

| 情形 | 应有结果 |
| --- | --- |
| 同一 Context 的 participation 分别关联两个人或两种角色 | 保留两条 ContextRef；不能按 Context ID 与关系类型合并 |
| 两份来源分别说 A1 先于 A2、A2 先于 A1 | 两条主张及证据均保留；Event 的 Conflict 用 related_refs 指向两条关系，alternatives 保留两种说法与支持；两条都排除出可用顺序视图，报告 warning |
| 三条有据先后主张构成环 | Conflict 指明三条涉事关系；环边全部从可用视图排除，原始主张不删；不能任意挑一条当作错误来源 |
| A1 的结束时间已知、开始时间未知 | 即使结束时间早于 A2 起点，也不按区间生成 derived 关系；可保留来源明确陈述的先后并标时间未知 |
| Event 没有 Stage，或 Stage 没有 Phase | 结构未完成，报告 error；保留部分结果，不编造层级凑数 |
| 已获取来源全文，但只交接其中两段 | 来源获取可记 full_text；provenance 标明两段交接范围，步骤记录实际处理范围，不能显示为全文已读 |
