# 人物 EPG 模式

新增 `builder_config.reconstruction.mode: person`。默认仍为 `event`，使用原来的提示词、检索格式及图输出。当前只支持 `AgentEventBuilder`；尚未提供公司模式和人物专用前端布局。

## 本次修改

| 环节 | 人物模式 |
| --- | --- |
| 输入范围 | 稳定 `subject_id`、姓名/别名、时间范围、专题范围；请求可以进一步收窄 |
| 检索与过滤 | 搜索带上人物范围；直接从配置建立筛选档案；使用独立人物筛选提示；缓存按范围隔离 |
| 七个构图 Agent | 使用独立人物提示，覆盖骨架、检查、参与者、交易、Episode 和两级描述 |
| 经历组织 | 允许平行经历、时间空档、任职/表态等非交易活动；不要求单一事件的因果链或市场冲击 |
| 身份与关系 | 保留图内 `P_` ID；明确人物与公司归属；关系时间受证据限制 |
| 输出 | 兼容 `FinalEventCascade.json`、`IntegratedEventCascade.json` 和原可视化，新增 `person_index.json` |

配置是任务范围，不是事实证据。人物模式不会凭配置生成生平、动机、参与者或交易，也不会将巴菲特自动加入每个伯克希尔交易 Episode。

## 配置

将 `configs/person_buffett_oxy.scope.yml` 的 `reconstruction` 块加入现有完整配置的 `builder_config` 中，保留原有模型、输出目录和 Agent 配置。此示例沿用现有巴菲特案例的 2022–2023 年 OXY 专题。

`subject_id`、`name`、`scope` 必填；`aliases` 是字符串列表。日期支持带引号的 `YYYY`、`YYYY-MM`、`YYYY-MM-DD`，未知边界为 `null`。跨图继续使用同一个 `subject_id`；换图时不要把它改成 `P_4` 等图内 ID。修改研究范围不需要更改人物 ID。

Web 服务会把范围传给检索和筛选，正常 Pipeline 会将同一 `builder_config` 传给构图器。直接调用 builder 时，它同样读取该配置。原 `FinmyPipeline` 的可选 matcher 并未改成人物匹配器；若启用它，需要另行验证不会误删非金融经历。当前默认配置关闭 matcher。

## 用已有巴菲特资料重跑构图

下面的代码在已安装 FinMycelium 及其依赖、配置好模型 API 的环境中执行。它复用已保存的 `builder_input_contents.json` 和 `event_profile.json`，直接调用 builder，不触发搜索、网页解析、数据库或额外的查询总结。**构图仍调用配置的模型 API，不是全离线推理。** 如需改变为完整生平，不能继续把这个局部专题的旧输入当成完整资料。

在仓库根目录执行；把 `saved_run` 改为你现有巴菲特资料目录：

```python
import json
from pathlib import Path
import yaml
from dotenv import load_dotenv
from finmy.generic import UserQueryInput, DataSample
from finmy.builder.base import BuildInput
from finmy.builder.agent_build.main_build import AgentEventBuilder
from finmy.reconstruction_scope import read_reconstruction

load_dotenv()
saved_run = Path("/path/to/your/saved_buffett_run")
config = yaml.safe_load(Path("configs/pipline.yml").read_text(encoding="utf-8"))
overlay = yaml.safe_load(Path("configs/person_buffett_oxy.scope.yml").read_text(encoding="utf-8"))
config["builder_config"]["reconstruction"] = overlay["builder_config"]["reconstruction"]
read_reconstruction(config)
texts = json.loads((saved_run / "builder_input_contents.json").read_text(encoding="utf-8"))
profile = json.loads((saved_run / "event_profile.json").read_text(encoding="utf-8"))
assert isinstance(texts, list) and texts and all(isinstance(t, str) and t.strip() for t in texts)
query = UserQueryInput(query_text=profile["original_request"], key_words=profile["keywords"])
samples = [DataSample(sample_id=f"saved_{i}", raw_data_id=f"saved_{i}", content=text)
           for i, text in enumerate(texts)]
builder = AgentEventBuilder(build_config=config["builder_config"])
result = builder.run(BuildInput(user_query=query, samples=samples))
print("新结果目录：", builder.save_dir)
```

这条路径用于对比同一份输入在两种模式下的构图结果，跳过重新筛选。原始来源清单仍在 `saved_run` 中；不要删除旧目录。需要重新筛选时，用已有的 `finmy.runner.relevance_filter` CLI，对原始 `retrieved_documents.json` 所在目录运行，并传入合并后的人物配置及新输出目录；不要覆盖旧轮次。

原 Gantt 可以直接显示新图：

```python
from finmy.builder.agent_build.visualizer_gantt import EventCascadeGanttVisualizer
EventCascadeGanttVisualizer().plot_cascade(
    result.event_cascades,
    output_path=str(Path(builder.save_dir) / "FinalEventCascade_gantt.html"),
)
```

## 人物身份索引的含义

`person_index.json` 保存人物范围、所有 Episode 的图内路径、可明确匹配的人物节点，以及这些节点的关系路径。关系的事实、证据和起止时间仍保留在主图中。当前匹配要求姓名/已配置别名及 `individual` 类型，发生歧义、重复 ID 或异常数据时记录警告，不强行合并。它不是独立的人物身份核验，也不改写图内 ID。

`subject_presence` 为 `matched`、`not_identified`、`ambiguous` 或 `unresolved`。只有公司节点的 Episode 可以保留在专题中，不能据此声称人物亲自参与。`coverage_start/end` 仅表示请求范围，不证明每段时间都有材料，更不证明完整生平已重构。

## 验证边界

自动化测试使用本地样例和模拟模型返回，验证模式配置、缓存隔离、七个 Agent 的实际提示组装、图整合与落盘、身份索引和事件模式兼容。测试通过不等于真实模型已生成合格人物图。没有材料时，人物骨架检查会明确终止并保留检查结果。

在完整依赖环境中运行：

```bash
python -m unittest discover -s tests -v
```

真实模型重跑后，仍要检查材料覆盖、漏掉的活动、个人/公司归属及证据质量；原 Gantt 目前显示兼容事件层级，尚无跨图人物导航。
