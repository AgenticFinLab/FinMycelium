# Interactive person event visualization

A saved `person-event-1.0` draft can be exported as a standalone HTML file.
The viewer shows stages, phases, actions, context and source evidence. Cards
display summaries and open full record details in an overlay, so inspecting a
card leaves the graph in place. The Gantt view remains the timeline.

## Export from the workbench

1. Start the [event workbench](event-workbench.md) in the project environment.
2. Open an existing person event build task with a saved JSON draft.
3. Under the event's Gantt, select **下载交互式 EPG HTML**.
4. Open the downloaded file in a browser. Switch views, click an action or a
   source card, and close the details. View changes load another graph or page.
   Opening and closing details keeps the current cards in place.

## Export from a saved JSON file

From the repository root with Python 3.11 or newer, point the exporter at an
existing `epg.json`. The exporter runs without Streamlit, model credentials or
network access. The output directory must already exist.

```console
python -m finmy.person_epg.event.graph_html /path/to/epg.json -o epg.html
```

**Expected output.** The command prints `Wrote epg.html`. Open that file
directly in a browser; it needs no local server or external script. The input
JSON stays unchanged. Historical `person-epg-3.0` drafts continue to use their
existing renderer.

For the Goldman Sachs reference, use
`revisions/consolidation-closure-v1/epg.json` from the original run archive.
It opens with 15 slide views. View 2 shows the investment decision and its
evidence. Selecting the link for A06 near the bottom of View 2 opens View 3
and selects that action. Other drafts use the standard fixed-width graph.

## Maintain an authored layout

The built-in `finmy/person_epg/event/graph_layout_goldman.json` is presentation
data for the exact reference graph. `graph.html` owns the browser behavior.
Use the canonical `fingerprint` in `finmy.person_epg.event.records` for layout
binding. JSON indentation or key order does not alter the fingerprint.

An authored layout contains a `digest` and an ordered `pages` array. Each page
has `title`, `phase` (zero for the overview, otherwise the one-based phase
index), `cards`, `paths`, `labels`, `evidence` and `jumps`. Use the bundled
layout as the working example. Card boxes are `[left, top, width, height]` in
pixels on a 1134 × 992 canvas. Card IDs, source IDs and evidence IDs reference
the saved graph. Jump destinations use one-based view numbers. For a revised
graph, review the page content and update the layout and its digest together.

Preview a separate layout for its matching draft with:

```console
python -m finmy.person_epg.event.graph_html /path/to/epg.json --layout /path/to/layout.json -o epg.html
```

A mismatched explicit layout reports an error before output is written. A
graph that does not match the bundled reference uses the standard viewer.

## Automated verification

```console
python -m unittest discover -s tests -p 'test_person_event_graph_html.py' -v
```

Expect `Ran 3 tests` and `OK`. The tests cover offline export, preservation of
embedded records, script escaping, layout binding, and protection against
overwriting the input.
