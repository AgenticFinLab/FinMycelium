# Event workbench

A local, single-user workspace for event tables, evidence and graph review.

From the repository root, in the FinMycelium Python environment:

```bash
python -m finmy.workbench --port 8537
```

Open `http://localhost:8537`. The server listens on the local loopback interface.
The initial workspace is empty. SQLite records are stored in the Git-ignored
`output/workbench/` directory. Set `FINMY_WORKBENCH_HOME` to use another local
directory. Back up that directory separately from the source repository.

## Pages

- **Data:** event tables, source material, graph versions and exports.
- **Tasks:** save batch configurations and cancel unstarted tasks.
- **Review:** confirm scope, review evidence and graphs, and record revisions.
- **Settings:** choose Sparse or Agent, an Ark model and concurrency; check
  credential presence. Store credentials in `.env`.

This release supports local data management and review. Search, URL fetching,
API checks, model execution and post-run usage/cost reporting are planned for
the execution integration. Until then, tasks remain saved configurations and
execution controls stay disabled. Shared-server deployment requires
authentication and worker integration.

## Workflow

1. Create an event or import a UTF-8 CSV/XLSX table. Check the column mapping and
   preview, then confirm the import.
2. Complete a name, description and included scope, then confirm the scope.
3. Upload TXT/text PDF files or register sources with URLs and text. Select the
   material to include, inspect the construction input and review the evidence.
4. Import an EventCascade JSON and confirm its association with the event and
   current input. Inspect its Gantt, fields and evidence snippets.
5. Save corrections as new graph versions. Record a reviewer name and approve,
   return or flag the current version.
6. Select events in the master table and export CSV, Excel or an event ZIP.
   Approved graphs are included as `FinalEPG.json`.

## Data handling

Event imports are atomic; duplicate IDs must be resolved before import.
Blank IDs receive local `EVT-` IDs. Dates retain year/month/day precision. CSV and
Excel exports use the same field names as the downloadable template. CSV cells
that could execute spreadsheet formulas are escaped.

The [event master](event-master.md) defines bilingual names, aliases, scope,
retrieval fields and related events. Scope confirmation is required before task
creation. Exports include all fields, including hidden columns.

Source originals are retained; included text is used verbatim in input previews.
PDF upload accepts unencrypted text PDFs up to 200 pages and 20 MiB.
URLs are saved as source references. Keep credentials in `.env`; source text
and URLs are included in exported event packages.

Graph import preserves the supplied event ID and requires explicit association
with the workspace event and its current evidence. Import checks cover basic
structure, nested IDs and edge references. Graph edits create immutable revisions;
IDs and structural indices are read-only. Gantt displays partial dates as intervals
and omits entries with unknown dates.

Reviews bind to input and graph versions. Changed construction input invalidates
prior approval. After an input change, reimport or reconstruct the graph against
the current input before review. Reviewer names are entered manually. Original
drafts, revisions and review history are retained.

Export selected records as CSV, Excel or a ZIP with source text/manifests, graph
versions, reviews and task records. Back up the workspace directory to preserve
the uploaded binary originals as well.

Offline tests:

```bash
python -m pytest tests/test_workbench.py tests/test_workbench_ui.py -q
```

Optional desktop/mobile Chromium acceptance uses its own temporary workspace:

```bash
python tests/workbench_browser_check.py --chromium /path/to/chrome --output output/workbench-browser
```
