# Interactive person event visualization

A saved `person-event-1.0` draft can be exported as a standalone HTML file.
Each Phase shows actions and context, followed by separate Evidence and Sources
sections. Select a card or action relation to inspect the fields it asserts and
follow their evidence. The workbench saves this view as `gantt.html` for review
and collection.

## Export from the workbench

1. Start the [event workbench](event-workbench.md) in the project environment.
2. Open an existing person event build task with a saved JSON draft.
3. Inspect the graph under **交互式人物事件图** or select **下载交互式事件图 HTML**.
4. Select an Action or Context and open a field under **Evidence by field**.
   Select a passage to read the full quotation and its location. Follow **Source**
   to see its source record, original link when available, and other
   passages from that source across the event. **Back** returns to the field.
5. Select a person or organization to inspect a recorded role or mention. A
   participation entry keeps the qualifications and evidence of its parent
   context reference. Each field lists its own support. A company named in a
   filing and a person named by a news report can have different attributions.
6. Select a purple action link, its label, or the relation listed on an Action.
   Inspect the two endpoints and the relation type separately. An inference
   includes its recorded reason and links to any premise fields. **Escape**
   closes the details panel.

For an older native run with a valid saved timeline, the workbench displays the
scrollable view from its verified JSON. **从已保存 JSON 重新绘图** writes this
version to that run and refreshes its HTML receipt. A collected graph keeps its
reviewed copy. Draft and partial downloads carry their review status.

## Export from a saved JSON file

From the repository root with Python 3.11 or newer, point the exporter at an
existing `epg.json`. The exporter runs without Streamlit, model credentials or
network access. The output directory must already exist.

```console
python -m finmy.person_epg.event.graph_html /path/to/epg.json --input /path/to/input.json -o epg.html
```

Open the resulting HTML in a browser. The optional `--input` supplies the
frozen build material for checking quotation text, source, offsets and sample
hash. References to a generated handoff header or an unresolved location are
flagged separately in the details panel. When only the graph is available,
the viewer reports the saved location status. Historical `person-epg-3.0`
graphs use their existing renderer.

## Reading the graph

Each Phase opens at **100%**, the largest scale that fits its action rows,
context, participants, Evidence and Sources in the available width and height.
Switching Phase starts a new 100% overview. Resizing the window or opening
details recalculates the fit. **+** and **−** zoom relative to that overview,
and **Fit phase** returns to it. On a dense Phase, use **Reading size** to
see the cards at their original text size. Each Action
keeps the row and order assigned by the layout. Columns spread into the
available width. When the rows need more room, scroll horizontally inside the
diagram. The toolbar and Stage navigation stay in place. **Stages and phases**
toggles the outline.

Shared context appears above its actions. Actions extend horizontally,
with their specific context nearby. People and organizations appear as circular
nodes. Recorded `precedes` and `enables` links help place
actions. Context without an explicit
Phase can be grouped using its date or shared evidence. These placements are
display choices.

Each purple Action relation is visible when the Phase opens. Read its label in
the order **from Action · predicate · to Action**, for example
`A04 continues A21`. Within a Phase the wire connects two Action cards.
Across Phases the local portion connects the Action to the existing tab of the
other Action’s Phase. The label gives both Action IDs on either page.
Select the wire or its label to inspect the relation and its evidence. **Go to**
or the highlighted Phase tab focuses the other Action. **Back to** returns to
the originating Action. Phases with cross-Phase relations open with their
outline expanded. At reading size, scroll the diagram or the outline to see
endpoints outside the viewport.

For Action relations, a dashed stroke marks an inferred relation or
`order_unknown`. Other observed, asserted and rule-derived relations use a
solid stroke. Symmetric relations (`overlaps`, `order_unknown`, `joint_action`)
have no arrowhead. These conventions apply on both sides of a Phase boundary.
Context uses ochre dashes, roles use blue-gray lines, and evidence uses green dots.

A Context can appear in several Phases under the same identifier. Each
appearance shows its links to the Actions on that page and opens the same
evidence record. Cross-Phase navigation is reserved for Action-to-Action
relations whose endpoints belong to different Phases.

Evidence and Sources appear below the diagram and take part in the same
zoom. Their cards wrap to the available width.
Evidence cards contain excerpts. Each points to one Source. One Source may
contain several excerpts, and one field may cite several excerpts from the same
or different sources. Select a record or a field to highlight its evidence
links in green. The graph places excerpts and sources unused by a Phase on the
event background canvas. The **Evidence** and **Sources** shortcuts move to
their sections. The underlying graph retains its original identifiers.

## Explicit custom layout

The optional `--layout` argument accepts a user-supplied authored layout tied
to the input graph's fingerprint. Automatic exports use the generated layout.
The explicit layout must contain a `digest` and a `pages` array with the existing
`title`, `phase`, `cards`, `paths`, `labels`, `evidence` and `jumps` fields.

## Automated verification

```console
python -m unittest discover -s tests -p 'test_person_event_graph_html.py' -v
```

The tests cover offline export, field ownership, source and passage navigation,
cross-Phase relations, quotation checks, layout binding and preservation of
saved records.

With Playwright installed, set `FINMY_TEST_CHROMIUM` to a local Chromium
executable and run `pytest -q tests/test_person_event_rendering.py` to check
the overview, zoom and evidence navigation at desktop and phone sizes.
