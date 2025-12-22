# FinMycelium

<div align="center">
<h3>A comprehensive financial data collection and analysis platform powered by AI</h3>

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](https://opensource.org/licenses/Apache-2.0)
[![Status](https://img.shields.io/badge/Status-Alpha-orange.svg)](https://github.com/AgenticFinLab/FinMycelium)

</div>

---

## 📖 Overview

**FinMycelium** is an intelligent financial data collection and analysis platform designed to extract, process, and reconstruct financial events from diverse public sources. Built with a modular architecture and powered by Large Language Models (LLMs), it enables automated collection, matching, summarization, and structured reconstruction of financial information.

### Key Capabilities

- 🔍 **Multi-Source Data Collection**: Web URLs, PDF documents, and social media platforms
- 🤖 **AI-Powered Processing**: LLM-based matching, summarization, and event reconstruction
- 🔄 **Flexible Pipeline**: Configurable components using registry factory pattern
- 📊 **Structured Output**: Reconstruct financial events into structured cascades with stages, episodes, participants, and transactions
- 🌐 **Web Interface**: Streamlit-based interactive UI for analysis and visualization

## ✨ Features

### Data Collection
- **URL Collector**: Extract content from web pages with support for multiple parsing strategies
- **PDF Collector**: Process PDF documents with layout analysis and text extraction
- **Media Platform Support**: Collect data from Xiaohongshu, Douyin, Kuaishou, Bilibili, Weibo, and more
- **Search Integration**: Baidu Search and Bocha Search API support

### Data Processing
- **Intelligent Matching**: Multiple matching strategies (LLM-based, regex, vector-based)
- **Query Summarization**: Keyword extraction and query summarization using LLMs
- **Event Reconstruction**: Multi-agent pipeline for reconstructing financial events with:
  - Skeleton extraction (stages and episodes)
  - Participant identification
  - Transaction reconstruction
  - Timeline and relationship mapping

### Architecture
- **Registry Pattern**: Dynamic component selection without code changes
- **LangGraph Integration**: Multi-agent orchestration with state management
- **Database Support**: MySQL/PostgreSQL integration for data persistence
- **Configuration-Driven**: YAML-based configuration for easy customization

## 🚀 Quick Start

### Prerequisites

- Python 3.11 or higher
- MySQL or PostgreSQL database (optional)
- API keys for LLM services (OpenAI, DeepSeek, etc.)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/AgenticFinLab/FinMycelium.git
   cd FinMycelium
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

   Or install as a package:
   ```bash
   pip install -e .
   ```

3. **Configure environment variables**
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` with your configuration:
   - Database credentials (MySQL/PostgreSQL)
   - API keys for LLM services
   - Search API keys (Baidu, Bocha)
   - Redis configuration (optional)
   - Proxy settings (optional)

### Basic Usage

#### Using the Pipeline

```python
from finmy.pipeline import FinmyPipeline
import yaml

# Load configuration
with open("configs/pipline.yml", "r") as f:
    config = yaml.safe_load(f)

# Initialize pipeline
pipeline = FinmyPipeline(config)

# Run pipeline with data sources
data_sources = [
    "https://example.com/financial-news",
    "/path/to/document.pdf"
]

pipeline.lm_build_pipeline_main(
    data_sources=data_sources,
    query_text="金融风控",
    key_words=["金融风控", "合规", "人工智能"]
)
```

#### Using Individual Components

```python
from finmy.url_collector.url_parser import URLParser
from finmy.pdf_collector.pdf_collector import PDFCollector
from finmy.matcher.registry import get as get_matcher
from finmy.summarizer.registry import get as get_summarizer

# URL collection
url_collector = URLParser(config={"delay": 1.0})
result = url_collector.collect(["https://example.com"])

# PDF collection
pdf_collector = PDFCollector(config={"output_dir": "./output"})
result = pdf_collector.collect(["/path/to/document.pdf"])

# Summarization
summarizer = get_summarizer("KWLMSummarizer", config={"llm_name": "deepseek/deepseek-chat"})
summary = summarizer.summarize(query_text, key_words)

# Matching
matcher = get_matcher("LXMatcher", config={"lm_name": "deepseek/deepseek-chat"})
matches = matcher.match(match_input)
```

### Web Interface

Launch the Streamlit web interface:

```bash
streamlit run finmy/web_interface.py
```

## 📁 Project Structure

```
FinMycelium/
├── README.md                 # Project overview
├── requirements.txt          # Python dependencies
├── setup.py                  # Package setup configuration
├── configs/                  # Configuration files
│   ├── pipline.yml          # Main pipeline configuration
│   └── uTEST/               # Test configurations
├── finmy/                   # Main package
│   ├── __init__.py
│   ├── pipeline.py          # Main pipeline orchestration
│   ├── converter.py         # Data format converters
│   ├── db_manager.py        # Database management
│   ├── generic.py           # Core data structures
│   ├── web_interface.py     # Streamlit web UI
│   ├── builder/             # Event reconstruction builders
│   │   ├── agent_build/     # Multi-agent builder
│   │   ├── class_build/     # Class-based builder
│   │   └── lm_build.py      # LLM-based builder
│   ├── matcher/             # Data matching modules
│   │   ├── lm_match.py      # LLM-based matcher
│   │   ├── re_match.py      # Regex matcher
│   │   └── lx_match.py      # LlamaIndex matcher
│   ├── summarizer/          # Query summarization
│   ├── url_collector/       # URL collection modules
│   │   ├── MediaCollector/  # Social media collectors
│   │   └── SearchCollector/ # Search API collectors
│   └── pdf_collector/       # PDF processing modules
├── examples/                 # Example scripts and demos
│   └── uTEST/               # Test examples
├── docs/                    # Documentation
│   ├── Progress-record.md   # Development progress
│   └── reference.md         # References
└── EXPERIMENT/              # Experimental results (git-ignored)
```

## ⚙️ Configuration

FinMycelium uses YAML configuration files to define pipeline components and parameters. The main configuration file (`configs/pipline.yml`) includes:

- **Language Model Settings**: Model type, name, and generation parameters
- **Database Configuration**: Connection strings and settings
- **Collector Settings**: URL and PDF collector parameters
- **Component Selection**: Summarizer, matcher, and builder types
- **Agent Configuration**: Multi-agent pipeline agent settings

### Example Configuration

```yaml
lm_type: "api"
lm_name: "deepseek/deepseek-chat"

generation_config:
  max_new_tokens: 8192
  temperature: 0.2
  top_p: 0.95

summarizer_config:
  summarizer_type: "KWLMSummarizer"
  llm_name: "deepseek/deepseek-chat"

matcher_config:
  use_matcher: True
  matcher_type: "LXMatcher"
  lm_name: "deepseek/deepseek-chat"

builder_config:
  builder_type: "AgentEventBuilder"
  lm_type: "api"
  lm_name: "deepseek/deepseek-chat"
```

## 🔧 Environment Variables

The project uses environment variables for sensitive configuration. Key variables include:

- **Database**: `DB_URL`, `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`
- **LLM APIs**: `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, etc.
- **Search APIs**: `BAIDU_SEARCH_API_KEY`, `BOCHA_SEARCH_API_KEY`
- **Redis**: `REDIS_HOST`, `REDIS_PORT` (optional)
- **Proxy**: `PROXY_URL` (optional)

See `.env.example` for a complete list of required variables.

## 📚 Documentation

- [Progress Record](docs/Progress-record.md) - Development progress and findings
- [Reference](docs/reference.md) - Related references and resources
- [Examples](examples/) - Example scripts and usage patterns

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## ⚠️ Important Notes

- The `EXPERIMENT/` folder is ignored by git by default. Place experimental results there.
- Never commit your `.env` file to version control.
- Ensure you have proper API keys and database access before running the pipeline.

## 📄 License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with [LangGraph](https://github.com/langchain-ai/langgraph) for multi-agent orchestration
- Uses [Streamlit](https://streamlit.io/) for web interface
- Integrates with various LLM providers and search APIs

## 📮 Contact & Support

- **Repository**: [https://github.com/AgenticFinLab/FinMycelium](https://github.com/AgenticFinLab/FinMycelium)
- **Issues**: [GitHub Issues](https://github.com/AgenticFinLab/FinMycelium/issues)

---

<div align="center">

**Made with ❤️ by AgenticFin Lab**

</div>


