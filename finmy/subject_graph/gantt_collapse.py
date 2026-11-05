"""Event folding for the existing Plotly Person Gantt, without changing dates."""

from finmy.subject_graph.gantt_layout import PIXELS_PER_UNIT


def figure_items(fig):
    return {"traces": fig.data, "annotations": fig.layout.annotations or (),
            "shapes": fig.layout.shapes or ()}


def item_counts(fig):
    return {kind: len(items) for kind, items in figure_items(fig).items()}


def item_indices(fig, start):
    return {kind: list(range(start[kind], count)) for kind, count in item_counts(fig).items()}


def make_collapsible(fig, blocks):
    """Store original vertical coordinates once, then show the collapsed view."""
    items = figure_items(fig)
    originals = {kind: {} for kind in items}
    for block in blocks.values():
        for section in ("header", "body"):
            for kind, indices in block[section].items():
                for index in indices:
                    item = items[kind][index]
                    original = {"visible": True if item.visible is None else item.visible}
                    if kind == "traces":
                        original["y"] = list(item.y)
                    elif kind == "annotations":
                        original.update(y=item.y, text=item.text)
                    else:
                        original.update(y0=item.y0, y1=item.y1)
                    originals[kind][str(index)] = original
    fig.layout.meta = {**(fig.layout.meta or {}), "subject_collapse": {
        "blocks": list(blocks.values()), "originals": originals, "expanded": [],
        "pixels_per_unit": PIXELS_PER_UNIT,
    }}
    set_expanded_events(fig, [])


def set_expanded_events(fig, event_ids):
    """Apply the same block translation used by the exported HTML controls."""
    model = fig.layout.meta["subject_collapse"]
    items = figure_items(fig)
    expanded = set(event_ids)
    cursor = 1.2
    for block in model["blocks"]:
        opened = block["id"] in expanded
        hidden_height = 0 if opened else block["body_height"]
        shift = cursor - block["start"] - hidden_height
        for section in ("header", "body"):
            for kind, indices in block[section].items():
                for index in indices:
                    original = model["originals"][kind][str(index)]
                    item = items[kind][index]
                    item.visible = original["visible"] if opened or section == "header" else False
                    if kind == "traces":
                        item.y = [None if y is None else y + shift for y in original["y"]]
                    elif kind == "annotations":
                        item.y = original["y"] + shift
                        item.text = original["text"].replace("▸ ", "▾ ", 1) if opened and section == "header" else original["text"]
                    else:
                        item.y0, item.y1 = original["y0"] + shift, original["y1"] + shift
        cursor += block["height"] - hidden_height
    model["expanded"] = sorted(expanded)
    fig.update_layout(height=max(700, round(170 + cursor * PIXELS_PER_UNIT)),
                      yaxis=dict(range=[0, cursor], tickvals=[], ticktext=[]))


COLLAPSE_SCRIPT = r"""
(function () {
  const chart = document.getElementById('{plot_id}');
  const model = chart.layout.meta.subject_collapse;
  const expanded = new Set(model.expanded);
  const headerTraces = new Map();
  const headerLabels = new Map();
  for (const block of model.blocks) {
    if (!block.body_height) continue;
    for (const index of block.header.traces) headerTraces.set(index, block.id);
    for (const index of block.header.annotations) headerLabels.set(index, block.id);
  }

  function render() {
    const annotations = chart.layout.annotations.map(item => ({...item}));
    const shapes = (chart.layout.shapes || []).map(item => ({...item}));
    const traceIndices = [], ys = [], visible = [];
    let cursor = 1.2;
    for (const block of model.blocks) {
      const opened = expanded.has(block.id);
      const hiddenHeight = opened ? 0 : block.body_height;
      const shift = cursor - block.start - hiddenHeight;
      for (const section of ['header', 'body']) {
        for (const [kind, indices] of Object.entries(block[section])) {
          for (const index of indices) {
            const original = model.originals[kind][index];
            const shown = (opened || section === 'header') ? original.visible : false;
            if (kind === 'traces') {
              traceIndices.push(index);
              ys.push(original.y.map(y => y === null ? null : y + shift));
              visible.push(shown);
            } else if (kind === 'annotations') {
              annotations[index].y = original.y + shift;
              annotations[index].visible = shown;
              annotations[index].text = opened && section === 'header'
                ? original.text.replace('▸ ', '▾ ') : original.text;
            } else {
              shapes[index].y0 = original.y0 + shift;
              shapes[index].y1 = original.y1 + shift;
              shapes[index].visible = shown;
            }
          }
        }
      }
      cursor += block.height - hiddenHeight;
    }
    // Only vertical geometry changes: retain the user's current x-axis window.
    return Plotly.update(chart, {y: ys, visible: visible}, {
      annotations: annotations, shapes: shapes,
      'yaxis.range': [0, cursor],
      height: Math.max(700, Math.round(170 + cursor * model.pixels_per_unit))
    }, traceIndices);
  }

  let pending = Promise.resolve();
  function toggle(id) {
    if (!id) return;
    if (expanded.has(id)) expanded.delete(id); else expanded.add(id);
    pending = pending.then(render);
  }
  chart.on('plotly_click', event => {
    if (event.points.length) toggle(headerTraces.get(event.points[0].curveNumber));
  });
  chart.on('plotly_clickannotation', event => toggle(headerLabels.get(event.index)));
})();
"""
