# Preparing PDF source material

Run the examples from the FinMycelium checkout in an activated Python 3.11+
environment. Install the package with `python -m pip install -e .`. Model-backed
components use the sibling `lmbase` checkout. [Environment setup](workflows/sparse-rag-build.md#install-and-configure)

## Parse and filter PDFs

Place PDFs under `input/` and set `MINERU_API_KEY` in the environment or the
checkout’s local `.env`. This step sends the selected files to MinerU.
The same invocation can filter the parsed text for case-insensitive literal keywords.

```bash
python examples/uTEST/Collector/test_pdf.py --help
python examples/uTEST/Collector/test_pdf.py -i input -o output -l en --keywords "capital allocation" acquisition
```

For a single file, use `-p path/to/report.pdf`. Each successfully parsed file
has a `full.md` under the output directory. The parser records its location in
`parser_information.json`. Filtering writes matching records to
`filter_information.json` when keywords are supplied. The example uses
`finance` when keywords are omitted. Repeated parses can append records.
[PDF collector](../finmy/pdf_collector/pdf_collector.py)

## Search existing Markdown locally

```bash
python examples/uTEST/Collector/regex_search.py -i output -k "capital allocation,acquisition" -c 250
```

The command reads existing `full.md` files recursively. It writes
`output/search_information.json`, with the relative source path, keyword, line,
character offsets and surrounding text for every match. Offsets use an exclusive
end. The context window extends to paragraph boundaries. Use `-o` to choose
another output file. [Search example](../examples/uTEST/Collector/regex_search.py)

## Import parser records into a local database

The parser index is a JSON object with a `records` list. Run this Python
example from the checkout after parsing. It creates a new `pdf_sources` table
in `output/sources.sqlite`. If that table already exists, the write stops and
its rows are preserved.

```python
import json
from pathlib import Path
import pandas as pd
from finmy.db_manager import PDDataBaseManager

records = json.loads(Path("output/parser_information.json").read_text(encoding="utf-8"))["records"]
if records:
    db = PDDataBaseManager({"url": "sqlite:///output/sources.sqlite"})
    db.write_sql(pd.DataFrame(records), "pdf_sources", if_exists="fail")
```

For tabular CSV input, `db.read_csv(path)` returns a DataFrame accepted by the
same writer. [Database helpers](../finmy/db_manager.py)
