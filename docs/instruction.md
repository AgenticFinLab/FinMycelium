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

> **Tip**: The script automatically retries failed files once if `--retry_failed True` (default).

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

> **Note**: For large-scale or sensitive document processing, consider [self-hosting MinerU](https://github.com/opendatalab/mineru) to avoid API limits and enhance privacy.

---

### 2. Keyword Search in Parsed PDFs

Use regular expressions to search for keywords in multiple parsed PDF text content and save the search results to a JSON file.

#### Basic Usage

```bash
# Basic keyword search (output saved as search_information.json in input directory)
python examples/Collector/test_search.py -i pdf_parse_results -k "financial risk"

# Custom output path and context window
python examples/Collector/test_search.py \
  --input-path "parsed_results" \
  --keyword "ESG" \
  --output-path "esg_findings.json" \
  --context-chars 1500
```

> **Tip**: The script recursively scans all subdirectories under `--input-path` for files named `full.md`.

---

#### Parameters

| Parameter          | Short Form | Default Value                     | Description                                                                                     |
| ------------------ | ---------- | --------------------------------- | ----------------------------------------------------------------------------------------------- |
| `--input-path`     | `-i`       | `pdf_parse_results`               | Root directory containing subfolders with `full.md` files                                       |
| `--keyword`        | `-k`       | **Required**                      | Keyword or phrase to search for in the markdown content                                          |
| `--output-path`    | `-o`       | `{input-path}/search_information.json` | Path to save the JSON results file                                                             |
| `--context-chars`  | `-c`       | `2000`                            | Number of characters to capture before and after each keyword match (total context ≈ 4000 chars) |

---

#### Output Structure

The script generates a JSON file containing a list of result entries, one per `full.md` file where the keyword was found. Each entry includes:

- Absolute file path  
- Searched keyword  
- Timestamp of the search  
- Total number of matches in the file  
- Detailed match information, including:
  - Approximate line number
  - Character position range of the keyword (`(start, end)`)
  - Surrounding context (expanded to full sentence boundaries)

**Example output:**
```json
[
  {
    "file_path": "D:\\GitHub\\FinMycelium\\output\\A novel data-efficient double deep Q-network framework for intelligent financpdf\\full.md",
    "keyword": "Reinforcement",
    "timestamp": "2025-11-19T11:08:06.873718",
    "match_count": 73,
    "matches": [
      {
        "line_number": 13,
        "keyword_position": [
          869,
          882
        ],
        "context": "To address these challenges, this work introduces Portfolio Double Deep Q-Network (PDQN), a novel architecture inspired by recent advancements in reinforcement learning."
      },
      {
        "line_number": 17,
        "keyword_position": [
          2127,
          2140
        ],
        "context": "Introduction\n\nThe persistent challenge of achieving optimal decision-making in dynamic and high-dimensional environments remains central to artificial intelligence and reinforcement learning research."
      },
    ]
  },
]
```

> **Note**: Context snippets are automatically expanded to include complete sentences while respecting the `--context-chars` limit. Only files containing at least one match are included in the results.

---

### 3. Import the PDF parsing results

Import the PDF parsing results as `RawData` into the database. The data format followed by `RawData` can be found at [metadata-specific](https://github.com/AgenticFinLab/group-resource/blob/main/materials/metadata-specific.md).

#### Basic Usage

```bash
# Import parser info with default settings
python examples/Collector/csv_to_db.py

# Custom configuration example
python examples/Collector/csv_to_db.py \
  --csv-file "data/custom_parsers.csv" \
  --table-name "CustomRawData_PDF" \
  --clear-table \
  --show-stats
```

> **Tip**: Use `--clear-table` if you want to replace all existing records. Use `--create-table` (enabled by default) to ensure the target table exists.

---

#### Parameters

| Parameter            | Short Form | Default Value                                                                 | Description                                                                                   |
| -------------------- | ---------- | ----------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| `--csv-file`         | `-f`       | `output/parser_information.csv`                                               | Path to the CSV file containing parser metadata                                               |
| `--table-name`       | `-t`       | `RawData_PDF`                                                                 | Name of the target database table                                                             |
| `--required-columns` | `-c`       | `['Source', 'Location', 'Time', 'Copyright', 'Method', 'Tag']`                 | List of expected column names in the CSV (order-sensitive)                                    |
| `--column-types`     | `-y`       | `['VARCHAR(255)', 'VARCHAR(255)', 'DATETIME', 'VARCHAR(255)', 'VARCHAR(255)', 'VARCHAR(255)']` | SQL data types corresponding to each required column                                          |
| `--create-table`     | `-n`       | `True`                                                                        | Automatically create the database table if it doesn’t exist                                   |
| `--clear-table`      | `-x`       | `False`                                                                       | Delete all existing rows in the table before importing new data                               |
| `--show-stats`       | `-s`       | `True`                                                                        | Display import summary including total records and sample entries after completion            |

> **Important**: The `--required-columns` and `--column-types` must be provided as **matching lists**, each column must have a corresponding SQL type.

---

#### Expected CSV Format

Your CSV file must include the following columns (unless overridden via `--required-columns`):

```csv
Source,Location,Time,Copyright,Method,Tag
D:\GitHub\FinMycelium\input\A Novel Approach to Hurdle Rate Calibration.pdf,D:\GitHub\FinMycelium\output\A Novel Approach to Hurdle Rate Calibration\full.md,2025-11-19 12:14:07,N/A,MinerU,"AgenticFin, HKUST(GZ)",
...
```

- **Time** must be in a parseable datetime format (e.g., `YYYY-MM-DD HH:MM:SS`)
- Missing or malformed rows may cause import failures

---

#### Output & Feedback

On successful execution, the script will:

- Confirm database connection
- Create or clear the target table (if requested)
- Import all valid rows from the CSV
- Print statistics like:

```
--- Import Statistics ---
Total records in database: 42
Sample records (first 5):
  Record 1: ('D:\\GitHub\\FinMycelium\\input\\A Novel Approach to Hurdle Rate Calibration.pdf', 'D:\\GitHub\\FinMycelium\\output\\A Novel Approach to Hurdle Rate Calibration\\full.md', datetime.datetime(2025, 11, 19, 12, 14, 7), None, 'MinerU', 'AgenticFin, HKUST(GZ)', datetime.datetime(2025, 11, 19, 13, 39, 36), datetime.datetime(2025, 11, 19, 13, 39, 36))
  ...
Data import completed successfully!
```

---