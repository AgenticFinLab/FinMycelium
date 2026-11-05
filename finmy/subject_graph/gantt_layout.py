"""Display-only lane allocation and text layout for the existing Gantt renderer."""

from html import escape, unescape
from textwrap import wrap


LABEL_FONT_SIZE = 12
LABEL_LINE_HEIGHT = 18
PIXELS_PER_UNIT = 30


def arrange_subject_events(rows, subject_id, coordinates, *, events):
    """Place each event above its activities, reserving space for full labels.

    Each block can then be translated or collapsed without changing any x
    coordinate. Index zero is event participation, not an additional activity.
    """
    for row in rows:
        context = row["IndexInStage"] == 0
        focused = not context and any(p["id"] == subject_id for p in row["Participants"])
        row["SubjectActivity"] = focused
        row["ContextActivity"] = context

    def set_label(row, title, extra=None):
        # Wrap plain text first so HTML entities are never split across lines.
        lines = wrap(unescape(str(title)), width=34) or [""]
        if extra:
            lines.extend(wrap(unescape(extra), width=34))
        row["LabelText"] = "<br>".join(escape(line) for line in lines)
        half_bar = 0.7 if row["Type"] == "Stage" else 0.46
        return half_bar * 2 + (len(lines) * LABEL_LINE_HEIGHT + 38) / PIXELS_PER_UNIT

    def raw_time(value):
        return str(value.get("value", "unknown") if isinstance(value, dict) else value)

    positions, blocks = {}, {}
    base = 1.2
    for event in reversed(sorted(events, key=lambda r: coordinates(r)[0])):
        sid = event["Group"]
        children = [row for row in rows if row["Group"] == sid]
        children.sort(key=lambda r: (r["ContextActivity"], not r["SubjectActivity"],
                                     coordinates(r)[0], r["IndexInStage"]))
        start = base
        # Y increases upwards; the subject's activities sit nearest the header.
        for row in reversed(children):
            positions[(sid, row["ID"])] = base
            title = "Event context" if row["ContextActivity"] else row["Title"]
            base += set_label(row, title)
        body_height = base - start
        positions[(sid, event["ID"])] = base
        count = sum(not row["ContextActivity"] for row in children)
        first, last = raw_time(event["StartRaw"]), raw_time(event["FinishRaw"])
        date = first if first == last else f"{first} → {last}"
        summary = f"{date} · {count} {'activity' if count == 1 else 'activities'}"
        base += set_label(event, f"{sid} · {event['StageName']}", summary) + 0.6
        event["Expandable"] = bool(children)
        blocks[sid] = {"id": sid, "start": start, "body_height": body_height,
                       "height": base - start, "activity_count": count,
                       "header": {}, "body": {}}
    return positions, blocks, base


def add_subject_label(fig, row, x, y, *, event=False):
    """Use the same readable horizontal labels for events and activities."""
    focused = row.get("SubjectActivity", False)
    text = row["LabelText"]
    if event and row.get("Expandable"):
        text = "▸ " + text
    fig.add_annotation(
        x=x, y=y + (0.7 if event else 0.46), yshift=5,
        text=f"<b>{text}</b>" if focused else text,
        showarrow=False, align="center", xanchor="center", yanchor="bottom",
        captureevents=bool(event and row.get("Expandable")),
        font=dict(size=LABEL_FONT_SIZE, color="#222222" if focused or event else "#666666"),
    )
    if not event and not row.get("ContextActivity"):
        fig.add_annotation(
            x=x, y=y - 0.46, yshift=-4, text=f"Event: {row['Group']}",
            showarrow=False, xanchor="center", yanchor="top",
            font=dict(size=11, color="#666666"),
        )
