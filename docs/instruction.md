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

> **Note**: MinerU API tokens expire after 14 days. Please obtain a new token from [MinerU](https://mineru.net/apiManage/token) before expiration and update it in your `.env` file.

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
| `--output_dir`       | `-o`       | `output`      | Directory to save parsed Markdown, images, metadata, and parsing log                                                                             |
| `--batch_size`       | `-b`       | `200`         | Number of PDFs processed per API batch (max: 200)                                                                                                |
| `--language`         | `-l`       | `en`          | Document language (`en`, `zh`, etc.)                                                                                                              |
| `--check_pdf_limits` | `-c`       | `True`        | Enable validation of PDF size (max: 200 MB) and page count (max: 600). If enabled, oversized PDFs are automatically split into compliant chunks. |
| `--retry_failed`     | `-r`       | `True`        | Automatically retry processing any files that failed during the initial pass                                                                     |

---

#### Output Structure

Successfully parsed documents are saved under `{output_dir}/{sanitized_filename}/` with the following contents:

- `full.md` – Cleaned Markdown representation of the document  
- `layout.json` – Structured layout and block-level metadata  
- `images/` – Folder containing all extracted images  
- `{file_id}_content_list.pdf` – Content list (table of contents or extracted headings)  
- `{file_id}_origin.pdf` – A copy of the original PDF  

Additionally, a **centralized parsing log file** is generated at the top level of the output directory:

- `parser_information.csv`: CSV file recording metadata for each successfully parsed PDF

##### Example `parser_information.csv` entry:

```csv
RawDataID,Source,Location,Time,Copyright,Method,Tag,BatchID
1,D:\GitHub\FinMycelium\input\A Novel Approach to Hurdle Rate Calibration.pdf,D:\GitHub\FinMycelium\output\A_Novel_Approach_to_Hurdle_Rate_Calibration\full.md,2025-11-19 16:46:39,NULL,MinerU,"AgenticFin, HKUST(GZ)",5b2e1b0a-b78d-49d4-a0ac-b34d603c7a86
```

**Field Descriptions**:
- `RawDataID`: Unique numeric ID assigned per parsed file  
- `Source`: Full path to the input PDF  
- `Location`: Full path to the generated `full.md` file  
- `Time`: Timestamp of successful parsing (ISO format)  
- `Copyright`: Placeholder for copyright info (currently `NULL`)  
- `Method`: Parsing engine used (`MinerU`)  
- `Tag`: Optional user-defined tags (e.g., for dataset labeling)  
- `BatchID`: UUID identifying the processing batch (useful for tracking retries or parallel jobs)

> **Note**: Only successfully parsed files appear in `parser_information.csv`.

> **Privacy & Scalability Tip**: For large-scale or sensitive document processing, consider [self-hosting MinerU](https://github.com/opendatalab/mineru) to avoid API limits and enhance data privacy.

---

### 2. Filter Parsed PDFs by Keywords

Use regular expressions to filter parsed PDF records based on **keywords or phrases** in multiple markdown files (`full.md`) and save the matching records to a CSV file.

#### Basic Usage

```bash
# Filter for records containing a single phrase
python examples/Collector/filter_pdf.py -i output -k reinforcement-learning

# Filter for records containing multiple keywords or phrases
python examples/Collector/filter_pdf.py -i output -k ESG,financial-risk,market-volatility

# Custom input path with multiple keywords
python examples/Collector/filter_pdf.py \
  --input_path "parsed_results" \
  --keywords "deep-q-network,market-volatility"
```

> **Tip**: 
> 1. The script reads `parser_information.csv` from the specified input folder and processes each record's corresponding `full.md` file using the 'Location' field.  
> 2. Any `-` in a keyword is automatically replaced with a space, enabling natural phrase input via CLI (e.g., `reinforcement-learning` -> `reinforcement learning`). 
>  
**Note**: Because command-line shells treat spaces as argument separators, multi-word phrases must be entered without literal spaces, use hyphens (`-`) to connect words instead (e.g., use `reinforcement-learning` rather than `"reinforcement learning"` to avoid quoting issues or parsing errors).

---

#### Parameters

| Parameter      | Short Form | Default Value | Description                                                                                                                                                                                              |
| -------------- | ---------- | ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--input_path` | `-i`       | **Required**  | Root directory containing `parser_information.csv` and corresponding `full.md` files                                                                                                                     |
| `--keywords`   | `-k`       | **Required**  | A string of keywords or phrases, separated by commas (e.g., `ESG,financial-risk,market-volatility`). Hyphens (`-`) are converted to spaces (e.g., `reinforcement-learning` -> `reinforcement learning`). |

---

#### Output Structure

The script generates `filter_information.csv` in the same input folder, containing only records from `parser_information.csv` where the corresponding `full.md` file **contains at least one of the specified keywords**.

The output CSV maintains the same structure as the input `parser_information.csv` with the following fields:
- **RawDataID**: Unique identifier for the original data record
- **Source**: Path to the original input PDF file
- **Location**: Path to the corresponding output markdown file
- **Time**: Timestamp when the parsing occurred
- **Copyright**: Copyright information (if available)
- **Method**: Parsing method used
- **Tag**: Metadata tags associated with the record
- **BatchID**: Batch identifier for the processing run

**Example output:**
```csv
RawDataID,Source,Location,Time,Copyright,Method,Tag,BatchID
1,D:\GitHub\FinMycelium\input\A Novel Approach to Hurdle Rate Calibration.pdf,D:\GitHub\FinMycelium\output\A_Novel_Approach_to_Hurdle_Rate_Calibration\full.md,2025-11-19 16:46:39,NULL,MinerU,"AgenticFin, HKUST(GZ)",5b2e1b0a-b78d-49d4-a0ac-b34d603c7a86
3,D:\GitHub\FinMycelium\input\Reinforcement Learning in Finance.pdf,D:\GitHub\FinMycelium\output\Reinforcement_Learning_in_Finance\full.md,2025-11-19 17:23:15,NULL,MinerU,"AgenticFin, HKUST(GZ)",a1b2c3d4-e5f6-7890-1234-567890abcdef
```

> **Note**:  
> - Only records whose corresponding `full.md` files contain **at least one match** for **any keyword** are included in the results.  
> - Keywords like `deep-q-network` are internally converted to `deep q network` and matched as literal phrases (not individual words).  
> - The script performs case-insensitive matching using regular expressions.

---

### 3. Keyword Search in Parsed PDFs

Use regular expressions to search for **one or more keywords or phrases** in multiple parsed PDF text files (`full.md`) and save the search results to a JSON file.

#### Basic Usage

```bash
# Search for a single phrase (hyphen automatically converted to space)
python examples/Collector/test_search.py -i pdf_parse_results -k "reinforcement-learning"

# Search for multiple keywords or phrases
python examples/Collector/test_search.py -i pdf_parse_results -k "ESG,reinforcement-learning,financial-risk"

# Custom output path and context window
python examples/Collector/test_search.py \
  --input-path "parsed_results" \
  --keyword "deep-q-network,market-volatility" \
  --output-path "findings.json" \
  --context-chars 1500
```

> **Tip**: 
> 1. The script recursively scans all subdirectories under `--input-path` for files named `full.md`.  
> 2. Any `-` in a keyword is automatically replaced with a space, enabling natural phrase input via CLI (e.g., `deep-q-network` -> `deep q network`). 
>  
**Note**: Because command-line shells treat spaces as argument separators, multi-word phrases must be entered without literal spaces—use hyphens (`-`) to connect words instead (e.g., use `reinforcement-learning` rather than `"reinforcement learning"` to avoid quoting issues or parsing errors).

---

#### Parameters

| Parameter          | Short Form | Default Value                     | Description                                                                                     |
| ------------------ | ---------- | --------------------------------- | ----------------------------------------------------------------------------------------------- |
| `--input-path`     | `-i`       | `pdf_parse_results`               | Root directory containing subfolders with `full.md` files                                       |
| `--keyword`        | `-k`       | **Required**                      | **One or more keywords/phrases**, separated by commas. Hyphens (`-`) are converted to spaces (e.g., `reinforcement-learning` -> `reinforcement learning`). |
| `--output-path`    | `-o`       | `{input-path}/search_information.json` | Path to save the JSON results file                                                             |
| `--context-chars`  | `-c`       | `2000`                            | Number of characters to capture before and after each keyword match (total context ≈ 4000 chars) |

---

#### Output Structure

The script generates a JSON file containing one entry per `full.md` file **where any of the keywords were found**.

Fields **SampleID**, **RawDataID**, **Location**, **Time**, **Category**, **Field**, **Tag**, **Method**, and **Reviews** follow the standard definitions in the [metadata specification](https://github.com/AgenticFinLab/group-resource/blob/main/materials/metadata-specific.md).

Additional fields specific to the keyword search include:  
- **Source**: Path to the original input file.  
- **keyword**: The **list of searched keywords/phrases** (after hyphen-to-space conversion).  
- **match_count**: Total number of matches **across all keywords** in the file.  
- **matches**: List of match details, each containing:  
  - `matched_keyword`: The specific keyword/phrase that was matched.  
  - `line_number`: Approximate line number of the match.  
  - `keyword_position`: Character range `[start, end]` of the matched keyword.  
  - `context`: Full sentence surrounding the match.

> **Note**: Each match records which keyword triggered it, enabling multi-keyword analysis.

**Example output:**
```json
[
  {
    "SampleID": "1",
    "RawDataID": "2",
    "Location": "D:\\GitHub\\FinMycelium\\output\\search_information.json",
    "Time": "2025-11-19 17:31:39",
    "Category": "",
    "Field": "",
    "Tag": "AgenticFin, HKUST(GZ)",
    "Method": "Regular Expression",
    "Reviews": "",
    "Source": "D:\\GitHub\\FinMycelium\\output\\A_novel_data-efficient_double_deep_Q-network_framework_for_intelligent_financial_portfolio_management\\full.md",
    "keyword": ["reinforcement learning", "financial risk"],
    "match_count": 75,
    "matches": [
      {
        "matched_keyword": "reinforcement learning",
        "line_number": 13,
        "keyword_position": [869, 888],
        "context": "To address these challenges, this work introduces Portfolio Double Deep Q-Network (PDQN), a novel architecture inspired by recent advancements in reinforcement learning."
      },
      {
        "matched_keyword": "financial risk",
        "line_number": 42,
        "keyword_position": [3201, 3214],
        "context": "Our model explicitly accounts for financial risk through dynamic volatility weighting."
      }
    ]
  }
]
```

> **Note**:  
> - Context snippets are automatically expanded to include complete sentences while respecting the `--context-chars` limit.  
> - Only files containing **at least one match** for **any keyword** are included in the results.  
> - Keywords like `deep-q-network` are internally converted to `deep q network` and matched as literal phrases (not individual words).

--- 


### 4. Upload data to database

Upload parsing or keyword search results (in CSV or JSON format) into the database as structured records. The format of the data must comply with the [metadata-specific schema](https://github.com/AgenticFinLab/group-resource/blob/main/materials/metadata-specific.md).

#### Prerequisites

Add the database configuration to `.env`:

```python
DB_HOST = "xxx" 
DB_PORT = 3306
DB_NAME= "xxx"
DB_USER= "xxx"
DB_PASSWORD="xxx"
DB_CHARSET="xxx"
```

#### Basic Usage

```bash
# Import default JSON file into default table
python examples/Collector/data_to_db.py

# Import custom CSV file into a specific table
python examples/Collector/data_to_db.py \
  --file "data/custom_parsers.csv" \
  --table-name "CustomRawData_PDF"

# Import JSON file and recreate the table from scratch
python examples/Collector/data_to_db.py \
  --file "data/search_results.json" \
  --table-name "Sample_PDF" \
  --delete-table
```

> **Tip**: Use `--delete-table` to drop and recreate the table (equivalent to clearing and reinitializing). The table is automatically created if it doesn't exist during import.

---

#### Parameters

| Parameter        | Short Form | Default Value                  | Description                                                                 |
|------------------|------------|--------------------------------|-----------------------------------------------------------------------------|
| `--file`         | `-f`       | `output/search_information.json` | Path to the input **CSV or JSON** file containing the data to upload        |
| `--table-name`   | `-t`       | `Sample_PDF`                   | Name of the target database table                                           |
| `--delete-table` | `-d`       | `False`                        | **Drop and recreate** the table before importing (removes all existing data)|
| `--show-stats`   | `-s`       | `True`                         | Display import summary including total records and sample entries           |

> **Note**:  
> - The script **does not require column or type definitions**, it infers structure from the input file.  
> - Supported file extensions: `.csv` and `.json` only.  
> - For JSON files, the top-level must be a **list of objects**, where each object represents one record.

---

#### Expected File Format

For unified format, the expected columns are as follows.

##### For CSV:
Must contain headers, and column order is not critical as long as field names match the database schema expectations (e.g., from `metadata-specific.md`):

```csv
RawDataID,Source,Location,Time,Copyright,Method,Tag,BatchID
1,D:\GitHub\FinMycelium\input\A Novel Approach to Hurdle Rate Calibration.pdf,D:\GitHub\FinMycelium\output\A_Novel_Approach_to_Hurdle_Rate_Calibration\full.md,2025-11-19 16:46:39,NULL,MinerU,"AgenticFin, HKUST(GZ)",5b2e1b0a-b78d-49d4-a0ac-b34d603c7a86
```

##### For JSON:

Refer to the `Example Output` in Section 2 for the expected format.


---

#### Output & Feedback

On successful execution, the script will:

- Validate the input file
- Connect to the database
- Optionally drop and recreate the table (`--delete-table`)
- Import all records
- Print statistics like:

The displayed record includes all user-provided fields:
```
--- Import Statistics ---
Total records in database: 42
Sample records (first 5):
  Record 1: (1, 'D:\\GitHub\\FinMycelium\\input\\A Novel Approach to Hurdle Rate Calibration.pdf', 'D:\\GitHub\\FinMycelium\\output\\A_Novel_Approach_to_Hurdle_Rate_Calibration\\full.md', datetime.datetime(2025, 11, 19, 16, 46, 39), '', 'MinerU', 'AgenticFin, HKUST(GZ)', '5b2e1b0a-b78d-49d4-a0ac-b34d603c7a86', datetime.datetime(2025, 11, 19, 17, 29, 19), datetime.datetime(2025, 11, 19, 17, 29, 19))
  ...
Data import completed successfully!
```

---