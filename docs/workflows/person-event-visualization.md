# Interactive person event visualization

A saved `person-event-1.0` draft can be exported as a standalone HTML file.
Each Phase shows actions and context, followed by separate Evidence and Sources
sections. Select a card or action relation to inspect the fields it asserts and
follow their evidence. The workbench saves this view as `gantt.html` for review
and collection.

Each Phase places Actions by evidenced time and order. Actions may share a
column on separate rows when the available information leaves their order open.
The [person Event visualization design](../person-event-visualization/0-overview.md)
covers the full diagram, its [visual legend](../person-event-visualization/4-visual-legend.md)
and the rules for multi-row placement.

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

The embedded preview and the HTML download use the same document. When the
saved viewer is current or newer, the workbench serves the verified file directly.
For an older native run with a valid saved timeline, the workbench displays the
scrollable view from its verified JSON. **从已保存 JSON 重新绘图** writes this
version to the run and refreshes its HTML receipt. A changed export is stored
under the run’s `visualizations/` directory. Earlier attempts and collected
graphs keep their original files. A repeat export with identical bytes can
reuse the same file. If redrawing fails, a previously successful receipt stays
available. Draft and partial downloads carry their review status.

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

The **Context scope** key above the diagram shows which scopes appear on this
page. Its labels stay readable at overview zoom. Read Context cards by their
fill, border and position.

| Scope on this page | How to recognize it | What the graph records |
| --- | --- | --- |
| Phase-wide | Blue card with a solid top rule. On a single-Action page, an inherited condition or constraint sits above the Action and carries the label **Phase-wide**. | The Phase records the reference. Its typed branches show which Actions inherit that condition or constraint. |
| Action-linked | Cream card beside its Action or Actions | An Action explicitly cites this Context, for example as a condition, trigger, constraint or result. Conditions usually sit above the Action and results below. |
| Reference only | Gray card with a dashed outline in **Additional context** | The page includes this background for reference, for example through a matching date or shared passage. It has no recorded Phase or Action link on this page. |

A Context cited by several Actions appears once with its recorded connections.
If the Phase also cites it, its card uses the Phase-wide styling and its details show
**Phase-wide and action-linked**. Scope is local to each page. Background
without a Phase can be read on the event background page.

Select a shared card to highlight all Actions that inherit at least one of its
Phase references. The inspector lists the highlighted Actions, confirmed
exceptions and unresolved cases. A multi-Action Phase has a **Shared phase context**
band. Follow the ochre dashed branches marked **condition · Phase-wide** or
**constraint · Phase-wide** to see the effective scope of each use. Open a branch
or its label to inspect the original qualification, evidence and any matching
explicit Action reference. A shared card lists the people or organizations it mentions
under **Entities mentioned**. Focus one of those entities to see its mention
line. Closing the details or changing Phase clears the scope highlight.

The **Context category (left stripe)** key appears beside **Context scope** on
pages with a categorized Context. Its three labeled stripes stay at a fixed size
as the diagram zooms. **Environment** uses ochre, **Parties & relationships**
uses blue-gray, and **Personal state** uses rose. Each card also names its
category beside its ID. **Retrospective** identifies a
`post_hoc` perspective. Open the card to inspect its scope, category and evidence.

For `condition`, `trigger` and `constraint`, follow the arrow from the Context
to the Action. For `result`, follow it from the Action to the Context.
A `participation` arrow runs from the recorded participant to the Action
and displays the recorded role when available. A Phase-wide participation
uses a Phase card in the shared section. A trigger or result recorded for the
whole Phase also uses the Phase endpoint. A `knowledge-source` arrow runs from
the information to its recorded recipient. Each reference retains its scope,
qualifications and evidence. Open **Recorded uses** on the Context to inspect
individual references, including ones with an unknown endpoint.

People and organizations appear as circular nodes. Read the dated Action cards from
left to right at the precision supported by the graph. A simple chain can occupy one
row. Branches, overlapping intervals and Actions with the same unresolved position
use separate rows. Dotted **Possible window** brackets show where an Action could
have occurred. A solid **Duration** bar spans a documented continuing activity.
The **Action chronology** axis marks the available dates and times. Spacing adapts
to the page and does not measure elapsed time.

Read **By** or **From** as a one-sided limit. A **By** card sits to the left of
the date and a **From** card to its right. The closed end meets the boundary column.
The Action can occur on the boundary date. A separately evidenced sequence takes priority.
An Action with only a remote anchor can show **After A21**. **Phase only** marks an
Action whose membership is known and whose date is open. These cards share the
Phase timeline. Open a card for the original wording, evidence and order paths.
An undated chain with internal order retains its **Relative order** heading.
**Order disputed** identifies conflicting claims.

Action-linked conditions sit above the Action group and results below it. A Context
that is both a result and a later condition may occupy an existing horizontal gap
between its two independently ordered Actions. Each recorded use connects to its
own endpoint. Zooming and resizing preserve the Action rows. [Layout rules](../person-event-visualization/1-action-layout.md)

For older graphs with day precision, the automatic view can display a single named
part of the day when the Action's recorded time expression and a located quotation
supporting that field agree. The inspector retains the original wording and evidence.
A direct export can use the frozen build input to verify quotations against source text.

Each purple Action relation is visible when the Phase opens. Read its label in
the order **from Action · predicate · to Action**, for example
`A04 continues A21`. Within a Phase the wire connects two Action cards.
Its label follows the wire as you zoom. When the space between cards is too
narrow, the label sits beside the Action row with a short line back to the wire.
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
