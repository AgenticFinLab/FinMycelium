<div align="center">

# FinMycelium

### A comprehensive **Multi-Agent Financial Event Reconstruction** platform powered by AI

**[中文版](README-中文.md) | [English](README.md)**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Apache%202.0-4CAF50?style=for-the-badge&logo=apache&logoColor=white)](https://opensource.org/licenses/Apache-2.0)
[![Status](https://img.shields.io/badge/Status-Alpha-FF9800?style=for-the-badge)](https://github.com/AgenticFinLab/FinMycelium)
[![LangGraph](https://img.shields.io/badge/LangGraph-Enabled-00A86B?style=for-the-badge&logo=graphql&logoColor=white)](https://github.com/langchain-ai/langgraph)

**Financial Event Reconstruction • Multi-Agent • Intelligent • Modular • AI-Powered**

</div>

---

> How can the complete chronological process of a specific event, particularly a financial event, be reconstructed as a structured timeline such as a Gantt chart from large-scale, heterogeneous, and noisy real-world data?

> **FinMycelium**, a name borrowed from "finance" and "mycelium" is a **Financial Event Reconstruction Platform** that reconstructs the complete financial event process as a structured timeline from multi-source, diverse public documents. Our platform is built on a large model–based multi-agent system, in which agents cooperate to collect, match, and summarize large-scale, heterogeneous, and noisy real-world data, ultimately building a comprehensive and structured reconstruction of the event.

> Finance Mycelium (菌丝体)：一个如菌丝体般在异构金融事件碎片中自主延伸、连接并重构真相的动态网络.


---

## Features

### Core Capabilities
- **Multi-Source Data Collection**: Gather relevant data from diverse sources, including news articles, social media, official reports, and other public documents.
- **Data Matching and Summarization**: Identify, align, and condense useful information across heterogeneous sources to directly support financial event reconstruction.
- **Event Reconstruction**: Leverage a large model–based multi-agent system to autonomously integrate, connect, and reconstruct coherent event narratives from fragmented financial data.
- **Structured Presentation**: Visualize the reconstructed timeline using Gantt charts and [Event Developmental Sequence](docs/reference/the_organizational_and_interorganizational_development_of_disasters.pdf) to deliver a clear, structured overview of the event.
- **Web Interface**: Provide an intuitive, Streamlit-based interactive UI for real-time financial event analysis, exploration, and visualization.

---

## To Do List

> - [ ] Address the "exceeding length limits" issue in both prompts and generations.
> - [ ] Re-architect FinMycelium as a *fully agent-based* platform.
> - [ ] Optimize the event reconstruction pipeline to improve processing *speed*.
> - [ ] Expand the *range of data sources* for data collection.
> - [ ] Implement *multi-language support* in the web interface.


---

## Project Demonstration


https://github.com/user-attachments/assets/590a0f93-fe37-4ff1-b7f8-b5cf7c613a52







---

## Quick Start

### Prerequisites
- Python 3.11+
- API Keys for LLM services (OpenAI, DeepSeek, etc.)

### Installation
```bash
git clone https://github.com/AgenticFinLab/FinMycelium.git
cd FinMycelium
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with your API keys and configuration settings.

### Basic Usage

#### Using the Pipeline
```python
from finmy.pipeline import FinmyPipeline
import yaml

# Load configuration
with open("configs/pipline.yml", "r") as f:
    config = yaml.safe_load(f)

# Initialize and run pipeline
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

#### Web Interface
```bash
streamlit run examples/utest/test_web_interface.py
```

---


#### Detailed Guidance
- [Usage Guidance](celium/docs/usage_guidance.md) - Comprehensive guide on using FinMycelium


---


## Reconstructed Events

- **📦 Reconstructed Result**: `FinalEventCascade.json` reconstructed event details.

- **🗓️ Gantt Chart Visualization**: (`FinalEventCascade_gantt.html`) timeline visualization of `FinalEventCascade.json`.
  > Double-click the `.html` file for visualization on your browser.

- **📊 Event Cascade Data**: (`Class_Build_Event_Cascade_*.json`) reconstructed Event Developmental Sequence.

---

1. Lan Tian Ge Rui Fraud Case (天津蓝天格锐特大非法集资案): 


| Builder Type      | Result                                                                                                                                                                                                                          |
|-------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| AgentEventBuilder | 📦 [Reconstructed Result](docs/assets/builder_results/lan_tian_ge_rui_fraud_case/FinalEventCascade.json)<br>🗓️ [Gantt Chart Visualization](docs/assets/builder_results/lan_tian_ge_rui_fraud_case/FinalEventCascade_gantt.html) |
| ClassEventBuilder | 📊 [Event Developmental Sequence](docs/assets/builder_results/lan_tian_ge_rui_fraud_case/Class_Build_Event_Cascade_Ponzi_Scheme.json)                                                                                           |

2. Hainan Real Estate Foam (海南房地产泡沫): 

| Builder Type      | Result                                                                                                                                                                                                                    |
|-------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| AgentEventBuilder | 📦 [Reconstructed Result](docs/assets/builder_results/hainan_real_estate_foam/FinalEventCascade.json)<br>🗓️ [Gantt Chart Visualization](docs/assets/builder_results/hainan_real_estate_foam/FinalEventCascade_gantt.html) |
| ClassEventBuilder | 📊 [Event Developmental Sequence](docs/assets/builder_results/hainan_real_estate_foam/Class_Build_Event_Cascade_Other_Financial_Event.json)                                                                               |


3. Tulip Bubble (郁金香泡沫): 

| Builder Type      | Result                                                                                                                           |
|-------------------|----------------------------------------------------------------------------------------------------------------------------------|
| ClassEventBuilder | 📊 [Event Developmental Sequence](docs/assets/builder_results/tulip_bubble/Class_Build_Event_Cascade_Other_Financial_Event.json) |


4. FTX Crypto Exchange Collapse (交易所FTX崩盘): 

| Builder Type      | Result                                                                                                                                                                                                                              |
|-------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| AgentEventBuilder | 📦 [Reconstructed Result](docs/assets/builder_results/ftx_crypto_exchange_collapse/FinalEventCascade.json)<br>🗓️ [Gantt Chart Visualization](docs/assets/builder_results/ftx_crypto_exchange_collapse/FinalEventCascade_gantt.html) |
| ClassEventBuilder | 📊 [Event Developmental Sequence](docs/assets/builder_results/ftx_crypto_exchange_collapse/Class_Build_Event_Cascade_Embezzlement___Misappropriation_of_Funds.json)                                                                 |

---

## License

This project is licensed under the **Apache License 2.0** - see the [LICENSE](LICENSE) file for details.

[![License](https://img.shields.io/badge/License-Apache%202.0-4CAF50?style=flat-square&logo=apache&logoColor=white)](LICENSE)

---

## Acknowledgments

We would like to thank the following projects and communities:

- [LangGraph](https://github.com/langchain-ai/langgraph) - Multi-agent orchestration
- [Streamlit](https://streamlit.io/) - Web interface framework
- [Bettafish](https://github.com/666ghj/BettaFish) - Media crawler framework
- [LlamaIndex](https://github.com/run-llama/llama_index) - Indexing and retrieval
- Various LLM providers and search APIs for their excellent services

---

## Contact & Support

Please feel free to [open an issue](https://github.com/AgenticFinLab/FinMycelium/issues) if you encounter any problems or have any suggestions.

---

<div align="center">

### Made by [AgenticFin Lab](https://github.com/AgenticFinLab)

[⬆ Back to Top](#-finmycelium)

</div>
