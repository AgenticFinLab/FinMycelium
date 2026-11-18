# Interactive person event visualization

A saved `person-event-1.0` draft can be exported as a standalone HTML file.
The viewer shows stages, phases, actions, context and source evidence. Cards
show a summary and expand in place to reveal their own text. The connecting
lines follow the expanded card. The workbench uses this scrollable view as the
primary artifact and saves it as `gantt.html` for review and collection.

## Export from the workbench

1. Start the [event workbench](event-workbench.md) in the project environment.
2. Open an existing person event build task with a saved JSON draft.
3. Inspect the graph under **交互式人物事件图** or select **下载交互式事件图 HTML**.
4. Open the downloaded file in a browser and click an action or source card.
   The card expands and its lines follow its border. A source card opens its
   own excerpts. Click again or press Escape to collapse the card.

For an older native run with a valid saved timeline, the workbench displays the
scrollable view from its verified JSON. **从已保存 JSON 重新绘图** writes this
version to that run and refreshes its HTML receipt. A collected graph keeps its
reviewed copy. Draft and partial downloads carry their review status.

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

## Generated layout

The exporter builds one complete canvas per Phase directly from the event JSON.
Stage and Phase names form the top navigation. Shared Phase context appears in a
band above the actions. Actions extend horizontally, with their context nearby
and source evidence below. The canvas grows with the data and supports native
horizontal and vertical scrolling at a normal, readable scale.

Opening or switching a Phase starts at the left edge and top of its canvas.
The selector and arrow buttons switch between Phases and event background;
there is no pagination within a Phase. Stage controls stay in reach during
horizontal scrolling. A cross-Phase link scrolls to its destination card.

People and organizations have circular nodes. Actor links point into actions;
object and context links point to the referenced entities. Related actions are
grouped together, and explicit `precedes` / `enables` relations guide their
placement. Each record appears only once on a given Phase canvas, including
shared contexts, entities and sources. Relationships between actions that used
to be on different views are drawn directly. Other relation types keep their
original meaning; unknown order does not acquire an arrowhead.

The layout follows the reference graph's colors and section structure. Card
positions are calculated at export. Clicking a card expands its own text,
moves lower rows down to make room, and redraws connections against its borders.
Collapsing restores the original geometry. Long text scrolls inside the expanded
card. Entity links attach to the circular icon while it is collapsed.

Collapsed cards prefer an explicit short label or summary, otherwise an
extractive label from the existing text. Repeated actor names and neutral source
wrappers can be omitted from the preview; original text remains in the detail.
Source cards show their name and date, with passages available on expansion.
Evidence lines are faint until their source or target receives hover, keyboard
focus, or expansion.

Relationship colors follow the existing palette: purple for action links,
blue-gray for roles, ochre for context, and green for evidence. Rounded labels
identify the relation without covering cards. Hovering or focusing a node
emphasizes its immediate neighbors and connecting arrows together; unrelated
nodes and links recede. A subtle directional trace runs only while inspecting
a directed relationship. Unknown-order and inferred links remain static, and
the viewer respects the system's reduced-motion preference. These effects do
not change node coordinates, Phase navigation, or the underlying records.

Direct context references take precedence. Remaining context can be grouped by
dates or by evidence it shares with a Phase. Unassigned context stays in event
background canvas. These assignments affect presentation only. Cross-Phase
relations are navigable below each graph. All actions, contexts, sources and
evidence passages remain available across the canvases. Uncited sources and
passages are included in the event background canvas.

`graph_view.py` resolves records and associations. `graph_labels.py` prepares
compact labels. `graph_layout.py` groups records by Phase and assigns coordinates.
`graph.html` renders the cards and
routes connections. Default exports use these same functions for every event.

## Explicit custom layout

The optional `--layout` argument accepts a user-supplied authored layout tied
to the input graph's fingerprint. Automatic exports use the generated layout.
The explicit layout must contain a `digest` and a `pages` array with the existing
`title`, `phase`, `cards`, `paths`, `labels`, `evidence` and `jumps` fields.

## Automated verification

```console
python -m unittest discover -s tests -p 'test_person_event_graph_html.py' -v
```

Expect `Ran 10 tests` and `OK`. The tests cover offline export, preservation of
embedded records, script escaping, layout binding, and protection against
overwriting the input, plus entity roles, explicit action order, compact source
cards, preservation of full text, complete Phase canvases, node deduplication,
and unpaginated background evidence.
