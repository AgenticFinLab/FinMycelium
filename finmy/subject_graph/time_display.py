"""Preserve natural time wording while projecting normalized display bounds."""
import copy


def project_time(field, boundary):
    result = copy.deepcopy(field)
    if isinstance(result, dict) and "time_window" in result:
        result["value"] = result["time_window"][boundary]
    return result


def time_label(field):
    window = field.get("time_window") if isinstance(field, dict) else None
    if not window:
        return None
    return window["original"] + ("（约）" if window["approximate"] else "")


def time_note(*fields):
    notes = []
    for field in fields:
        label = time_label(field)
        if label:
            window = field["time_window"]
            note = f"Time: {label}<br>{window['start']} — {window['end']}"
            if window["approximate"]:
                note += "<br>发生于该范围内，具体日期不详。"
            if note not in notes:
                notes.append(note)
    return "<br>".join(notes)
