## Instructions Guidelines for FinMyCelium

---

### Table of Contents

---

### Configuration

Set up the FinMyCelium environment and install the package in development mode:

```bash
# Create a dedicated conda environment (Python 3.11 recommended)
conda create -n finmycelium python=3.11
# Activate the environment
conda activate finmycelium

# You can use either venv (Python's built-in virtual environment)
# python -m venv .venv
# source .venv/bin/activate  
# On Windows: .venv/Scripts/activate

cd finmycelium

# Install the package in editable mode (for development)
pip install -e .
```

> **Note**: Using `pip install -e .` with conda is common when you're actively developing a package, as it installs your project in "editable" mode—changes to your code take effect immediately without reinstalling.

---

### 1. PDF Parsing

Use the open-source PDF parser [MinerU](https://mineru.net/apiManage/docs) to process collections of PDFs.

#### Prerequisites

For security and convenience, create a `.env` file in your project root and store your [API tokens](https://mineru.net/apiManage/token) there. The parser will automatically load them from the environment.

```env
# .env
# API Key Configuration

# MinerU API base URL
MINERU_API_BASE="https://mineru.net"

# MinerU API key for parsing PDFs
MINERU_API_KEY="xxx.xxx.xxx"
```

Ensure you have installed the required packages:
```bash
pip install python-dotenv
```

> **Note**: Mineru API tokens expire after 14 days. Please obtain a new token from [MinerU](https://mineru.net/apiManage/token) before expiration and update it in your .env file.

#### Basic Usage

```bash
# Parse PDFs with default settings
# The PDF files should be placed in the `input` directory.
# The parsed results will be saved in the `output` directory.
python examples/Collector/test_pdf.py

# Custom configuration example
python examples/Collector/test_pdf.py \
  --input_dir "reports" \
  --output_dir "parsed_results" \
  --batch_size 100 \
  --language "zh" \
  --check_pdf_limits True \
  --retry_failed True
```

> 💡 **Tip**: The script automatically retries failed files once if `--retry_failed True` (default).

---

#### Parameters

| Parameter            | Short Form | Default Value | Description                                                                                                                                      |
| -------------------- | ---------- | ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `--input_dir`        | `-i`       | `input`       | Directory containing source PDF files                                                                                                            |
| `--output_dir`       | `-o`       | `output`      | Directory to save parsed Markdown, images, and metadata                                                                                          |
| `--batch_size`       | `-b`       | `200`         | Number of PDFs processed per API batch (max: 200)                                                                                                |
| `--language`         | `-l`       | `en`          | Document language (`en`, `zh`, etc.)                                                                                                              |
| `--check_pdf_limits` | `-c`       | `True`        | Enable validation of PDF size (max: 200 MB) and page count (max: 600). If enabled, oversized PDFs are automatically split into compliant chunks. |
| `--retry_failed`     | `-r`       | `True`        | Automatically retry processing any files that failed during the initial pass                                                                     |

---

#### Output Structure: 

Successfully parsed documents are saved as:

  - `output/full.md` (Markdown content)
  - `output/layout.json` (layout information)
  - `output/images/` (extracted images)
  - `output/{file_id}_content_list.pdf` (Content Lisf of PDF)
  - `output/{file_id}_origin.pdf` (Original PDF)

> For large-scale or sensitive document processing, consider [self-hosting MinerU](https://github.com/opendatalab/mineru) to avoid API limits and enhance privacy.

---