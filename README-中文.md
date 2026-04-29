<div align="center">

# FinMycelium

### 一个全面的**多智能体金融事件重建**平台，由 AI 驱动

**[中文版](README-中文.md) | [English](README.md)**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Apache%202.0-4CAF50?style=for-the-badge&logo=apache&logoColor=white)](https://opensource.org/licenses/Apache-2.0)
[![Status](https://img.shields.io/badge/Status-Alpha-FF9800?style=for-the-badge)](https://github.com/AgenticFinLab/FinMycelium)
[![LangGraph](https://img.shields.io/badge/LangGraph-Enabled-00A86B?style=for-the-badge&logo=graphql&logoColor=white)](https://github.com/langchain-ai/langgraph)

**金融事件重建 • 多智能体 • 智能化 • 模块化 • AI 驱动**

</div>

---

> 如何从大规模、异构且嘈杂的真实世界数据中，将特定事件（特别是金融事件）的完整时间顺序过程重建为结构化时间线（如甘特图）？

> **FinMycelium**，这个名字借用了"finance"（金融）和"mycelium"（菌丝体），是一个**金融事件重建平台**，它从多源、多样的公共文档中重建完整的金融事件过程，形成结构化时间线。我们的平台基于大模型驱动的多智能体系统构建，智能体协作收集、匹配和总结大规模、异构且嘈杂的真实世界数据，最终构建全面且结构化的事件重建。

> Finance Mycelium (菌丝体)：一个如菌丝体般在异构金融事件碎片中自主延伸、连接并重构真相的动态网络。


---

## 功能特性

### 核心能力
- **多源数据收集**：从多种来源收集相关数据，包括新闻文章、社交媒体、官方报告和其他公共文档。
- **数据匹配与总结**：识别、对齐和压缩异构来源中的有用信息，直接支持金融事件重建。
- **事件重建**：利用基于大模型的多智能体系统，自主整合、连接和重建来自碎片化金融数据的连贯事件叙述。
- **结构化呈现**：使用甘特图和[事件发展序列](docs/reference/the_organizational_and_interorganizational_development_of_disasters.pdf)可视化重建的时间线，提供清晰、结构化的事件概览。
- **Web 界面**：提供直观的、基于 Streamlit 的交互式 UI，用于实时金融事件分析、探索和可视化。

---

## 待办事项

> - [ ] 解决提示词和生成内容中的"超出长度限制"问题。
> - [ ] 将 FinMycelium 重新架构为*完全基于智能体*的平台。
> - [ ] 优化事件重建管道以提高处理*速度*。
> - [ ] 扩展数据收集的*数据源范围*。
> - [ ] 在 Web 界面中实现*多语言支持*。


---

## 项目演示



https://github.com/user-attachments/assets/edd7d0f4-4c0f-4429-96b3-9a8846e2c270


---

## 快速开始

### 前置要求
- Python 3.11+
- LLM 服务的 API 密钥（OpenAI、DeepSeek 等）

### 安装
```bash
git clone https://github.com/AgenticFinLab/FinMycelium.git
cd FinMycelium
pip install -r requirements.txt
cp .env.example .env
```

编辑 `.env` 文件，填入您的 API 密钥和配置设置。
FinMycelium 依赖 [lmbase](https://github.com/AgenticFinLab/lmbase) 仓库提供核心 LLM 推理与基础工具组件。

### 基本使用

#### 使用管道
```python
from finmy.pipeline import FinmyPipeline
import yaml

# 加载配置
with open("configs/pipline.yml", "r") as f:
    config = yaml.safe_load(f)

# 初始化并运行管道
pipeline = FinmyPipeline(config)
pipeline.lm_build_pipeline_main(
    data_sources=[
      "https://edition.cnn.com/2025/11/11/uk/zhimin-qian-cryptocurrency-fraud-scheme-jailed-uk-intl-hnk",
      "https://www.theguardian.com/uk-news/2025/nov/11/fraudster-who-hid-in-london-is-jailed-over-bitcoin-scam",
      "https://www.cps.gov.uk/cps/news/two-people-imprisoned-their-key-roles-largescale-money-laundering-case"
    ],
    query_text="What is the case involving fraud and money laundering by Qian Zhimin?",
    key_words=["fraud", " money laundering"]
)
```

#### Web 界面
```bash
streamlit run examples/utest/test_web_interface.py
```

---


#### 详细指南
- [使用指南](celium/docs/usage_guidance.md) - 关于使用 FinMycelium 的全面指南


---

## 重建的事件

- **📦 重建结果**：`FinalEventCascade.json` 重建的事件详情。

- **🗓️ 甘特图可视化**：（`FinalEventCascade_gantt.html`）`FinalEventCascade.json` 的时间线可视化。
  > 双击 `.html` 文件在浏览器中查看可视化。

- **📊 事件级联数据**：（`Class_Build_Event_Cascade_*.json`）重建的事件发展序列。

---

1. 蓝天格锐诈骗案（天津蓝天格锐特大非法集资案）： 


| 构建器类型      | 结果                                                                                                                                                                                                                          |
|-------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| AgentEventBuilder | 📦 [重建结果](docs/assets/builder_results/lan_tian_ge_rui_fraud_case/FinalEventCascade.json)<br>🗓️ [甘特图可视化](docs/assets/builder_results/lan_tian_ge_rui_fraud_case/FinalEventCascade_gantt.html) |
| ClassEventBuilder | 📊 [事件发展序列](docs/assets/builder_results/lan_tian_ge_rui_fraud_case/Class_Build_Event_Cascade_Ponzi_Scheme.json)                                                                                           |

2. 海南房地产泡沫： 

| 构建器类型      | 结果                                                                                                                                                                                                                    |
|-------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| AgentEventBuilder | 📦 [重建结果](docs/assets/builder_results/hainan_real_estate_foam/FinalEventCascade.json)<br>🗓️ [甘特图可视化](docs/assets/builder_results/hainan_real_estate_foam/FinalEventCascade_gantt.html) |
| ClassEventBuilder | 📊 [事件发展序列](docs/assets/builder_results/hainan_real_estate_foam/Class_Build_Event_Cascade_Other_Financial_Event.json)                                                                               |


3. 郁金香泡沫： 

| 构建器类型      | 结果                                                                                                                           |
|-------------------|----------------------------------------------------------------------------------------------------------------------------------|
| ClassEventBuilder | 📊 [事件发展序列](docs/assets/builder_results/tulip_bubble/Class_Build_Event_Cascade_Other_Financial_Event.json) |


4. FTX 加密货币交易所崩盘（交易所FTX崩盘）： 

| 构建器类型      | 结果                                                                                                                                                                                                                              |
|-------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| AgentEventBuilder | 📦 [重建结果](docs/assets/builder_results/ftx_crypto_exchange_collapse/FinalEventCascade.json)<br>🗓️ [甘特图可视化](docs/assets/builder_results/ftx_crypto_exchange_collapse/FinalEventCascade_gantt.html) |
| ClassEventBuilder | 📊 [事件发展序列](docs/assets/builder_results/ftx_crypto_exchange_collapse/Class_Build_Event_Cascade_Embezzlement___Misappropriation_of_Funds.json)                                                                 |

---

## 许可证

本项目采用 **Apache License 2.0** 许可证 - 详情请参阅 [LICENSE](LICENSE) 文件。

[![License](https://img.shields.io/badge/License-Apache%202.0-4CAF50?style=flat-square&logo=apache&logoColor=white)](LICENSE)

---

## 致谢

我们要感谢以下项目和社区：

- [LangGraph](https://github.com/langchain-ai/langgraph) - 多智能体编排
- [Streamlit](https://streamlit.io/) - Web 界面框架
- [Bettafish](https://github.com/666ghj/BettaFish) - 媒体爬虫框架
- [LlamaIndex](https://github.com/run-llama/llama_index) - 索引和检索
- 各种 LLM 提供商和搜索 API 提供的优质服务

---

## 联系与支持

如果您遇到任何问题或有任何建议，请随时[提交问题](https://github.com/AgenticFinLab/FinMycelium/issues)。

---

<div align="center">

### 由 [AgenticFin Lab](https://github.com/AgenticFinLab) 制作

[⬆ 返回顶部](#-finmycelium)

</div>

