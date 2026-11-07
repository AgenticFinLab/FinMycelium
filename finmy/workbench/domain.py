"""Offline interchange and validation without builder or provider imports."""

import calendar
import csv
import hashlib
import io
import json
import re
import zipfile
from datetime import date
from urllib.parse import urlsplit


FIELDS = {
    "event_id": "事件 ID", "event_name_zh": "中文名称", "event_name_en": "英文名称",
    "aliases": "别名", "description": "事件简介", "domain": "领域", "category": "类别",
    "country_region": "国家／地区", "participants": "主要主体",
    "coverage_start": "覆盖开始时间", "coverage_end": "覆盖结束时间",
    "scope_include": "纳入范围", "scope_exclude": "排除范围",
    "keywords": "检索关键词", "search_language": "检索语言", "source_hints": "来源线索",
    "owner": "负责人", "notes": "备注", "related_events": "相关事件",
}
LIST_FIELDS = {"aliases", "country_region", "participants", "keywords", "source_hints"}
RELATIONS = {"overlap": "范围重叠", "contains": "包含", "part_of": "被包含", "possible_duplicate": "疑似重复", "related": "相关"}
LANGUAGES = {"": "未设置", "zh": "中文", "en": "英文", "zh-en": "中英"}
DERIVED_FIELDS = {"scope_review": "范围确认", "evidence_review": "资料审核", "graph_review": "图审核",
                  "status": "流程状态", "graph_version": "当前图版本", "relation_count": "关联数量", "updated": "更新时间"}
DEFAULT_COLUMNS = ["event_id", "event_name_zh", "event_name_en", "classification", "coverage", "scope_review", "status", "owner", "relation_count"]
TABLE_LABELS = {**FIELDS, **DERIVED_FIELDS, "classification": "领域／类别", "coverage": "覆盖时间"}
SCOPE_FIELDS = ("event_name_zh", "event_name_en", "aliases", "description", "domain", "category",
                "country_region", "participants", "coverage_start", "coverage_end", "scope_include", "scope_exclude")
MODELS = {
    "Doubao Seed 2.0 Pro": "doubao-seed-2-0-pro-260215",
    "GLM-5.2": "glm-5-2-260617",
    "DeepSeek V4 Pro": "deepseek-v4-pro-ga-260813",
    "DeepSeek V4.1 Flash": "deepseek-v4-1-flash-261017",
    "Doubao Seed 2.1 Lite": "doubao-seed-2-1-lite-260915",
}
DEFAULT_MODEL = next(iter(MODELS.values()))
MAX_UPLOAD = 20 * 1024 * 1024
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def date_bounds(value):
    """Bounds for display/validation only; stored partial dates are unchanged."""
    if not value or value.lower() == "unknown":
        return None
    if not re.fullmatch(r"\d{4}(-\d{2}){0,2}", value):
        raise ValueError("时间请填写 YYYY、YYYY-MM、YYYY-MM-DD，或留空")
    parts = [int(p) for p in value.split("-")]
    y, m = parts[0], parts[1] if len(parts) > 1 else 1
    lo = date(y, m, parts[2] if len(parts) == 3 else 1)
    hi = lo if len(parts) == 3 else date(y, m, calendar.monthrange(y, m)[1]) if len(parts) == 2 else date(y, 12, 31)
    return lo, hi


def event_record(data):
    if set(data) - set(FIELDS):
        raise ValueError("存在未识别的字段")
    result = {k: string_list(data.get(k, [])) if k in LIST_FIELDS else str(data.get(k) or "").strip()
              for k in FIELDS if k != "related_events"}
    relations = data.get("related_events", [])
    if relations is None or relations == "":
        relations = []
    if isinstance(relations, str):
        relations = json.loads(relations)
    if not isinstance(relations, list):
        raise ValueError("相关事件须为列表")
    seen = set()
    for item in relations:
        if not isinstance(item, dict) or set(item) != {"event_id", "relation_type", "note"}:
            raise ValueError("相关事件需要 event_id、relation_type、note")
        target = item["event_id"]
        if not isinstance(target, str) or not ID_RE.fullmatch(target) or target == result["event_id"] or target in seen:
            raise ValueError("关联 ID 无效、自引用或重复")
        if not isinstance(item["relation_type"], str) or item["relation_type"] not in RELATIONS or not isinstance(item["note"], str):
            raise ValueError("关联类型或说明无效")
        seen.add(target)
    result["related_events"] = relations
    if not result["event_name_zh"] and not result["event_name_en"]:
        raise ValueError("中文名称、英文名称至少填写一项")
    if any(len(encoded(v)) > 100000 for v in result.values()):
        raise ValueError("单个字段内容过长")
    if result["search_language"] not in LANGUAGES:
        raise ValueError("检索语言须为 zh、en 或 zh-en")
    if result["event_id"] and not ID_RE.fullmatch(result["event_id"]):
        raise ValueError("事件 ID 仅支持字母、数字、下划线、短横线和点")
    start, end = date_bounds(result["coverage_start"]), date_bounds(result["coverage_end"])
    if start and end and start[0] > end[1]:
        raise ValueError("开始时间不能晚于结束时间")
    return result


def string_list(value):
    if isinstance(value, str):
        value = json.loads(value) if value.strip().startswith("[") else value.splitlines()
    if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
        raise ValueError("多值字段须为字符串列表或每行一项")
    return list(dict.fromkeys(v.strip() for v in value if v.strip()))


def stored_record(body):
    """Expose V1 rows without mutating history or guessing a title language."""
    if "title" not in body:
        return body
    result = {k: [] if k in LIST_FIELDS or k == "related_events" else "" for k in FIELDS}
    for k in ("event_id", "description", "domain", "category", "owner", "notes"):
        result[k] = body.get(k, "")
    for k in ("participants", "keywords"):
        result[k] = [body[k]] if body.get(k) else []
    result["legacy_fields"] = {k: body.get(k, "") for k in ("title", "scope_note", "start_time", "end_time")}
    return result


def display_name(event):
    return event.get("event_name_zh") or event.get("event_name_en") or event.get("legacy_fields", {}).get("title") or event.get("title") or event["event_id"]


def read_matrix(raw, filename):
    if len(raw) > MAX_UPLOAD:
        raise ValueError("文件不能超过 20 MiB")
    if filename.lower().endswith(".csv"):
        matrix = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    elif filename.lower().endswith(".xlsx"):
        from openpyxl import load_workbook
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if sum(info.file_size for info in archive.infolist()) > 100 * 1024 * 1024:
                raise ValueError("Excel 解压体积超过 100 MiB")
        book = load_workbook(io.BytesIO(raw), read_only=True, data_only=False)
        try:
            sheet = book.active
            if sheet.max_column > 100 or sheet.max_row > 5001:
                raise ValueError("Excel 超出列数或 5,000 行记录限制")
            matrix = []
            for row in sheet.iter_rows():
                if any(c.data_type == "f" for c in row):
                    raise ValueError("Excel 中不能包含公式，请先转为文本")
                matrix.append(["" if c.value is None else str(c.value) for c in row])
                if len(matrix) > 5001:
                    raise ValueError("单次最多导入 5,000 个事件")
        finally:
            book.close()
    else:
        raise ValueError("仅支持 CSV 和 XLSX")
    if not matrix or len(matrix) < 2 or len(matrix) > 5001:
        raise ValueError("请提供 1–5,000 行事件记录")
    return matrix


def read_table(raw, filename, mapping=None):
    matrix = read_matrix(raw, filename)
    aliases = {label: key for key, label in FIELDS.items()}
    original = [str(h).strip() for h in matrix[0]]
    if len(set(original)) != len(original):
        raise ValueError("表头重复")
    headers = [mapping.get(h) if mapping is not None else aliases.get(h, h) for h in original]
    # Exported summaries are informative, never authorization to approve a row.
    headers = [None if h in DERIVED_FIELDS else h for h in headers]
    chosen = [h for h in headers if h is not None]
    if len(set(chosen)) != len(chosen) or set(chosen) - set(FIELDS) or not {"event_name_zh", "event_name_en"}.intersection(chosen):
        raise ValueError("请完成字段映射，至少包含一种事件名称，且目标字段不能重复")
    rows = []
    for number, values in enumerate(matrix[1:], 2):
        if not any(str(v).strip() for v in values):
            continue
        if len(values) != len(headers):
            raise ValueError(f"第 {number} 行列数与表头不一致")
        try:
            rows.append(event_record({key: value for key, value in zip(headers, values) if key is not None}))
        except ValueError as exc:
            raise ValueError(f"第 {number} 行：{exc}") from exc
    if not rows:
        raise ValueError("没有事件记录")
    return rows


def export_table(rows, kind="csv"):
    columns = list(FIELDS) + list(DERIVED_FIELDS)
    if any("legacy_fields" in row for row in rows):
        columns.append("legacy_fields")
    matrix = [columns] + [[encoded(r[k]) if isinstance(r.get(k), (list, dict)) else r.get(k, "") for k in columns] for r in rows]
    if kind == "csv":
        out = io.StringIO(newline="")
        writer = csv.writer(out)
        for row in matrix:
            writer.writerow(["'" + str(v) if str(v).lstrip().startswith(("=", "+", "-", "@")) else v for v in row])
        return out.getvalue().encode("utf-8-sig")
    from openpyxl import Workbook
    book = Workbook()
    for row in matrix:
        book.active.append(row)
    for row in book.active:
        for cell in row:
            cell.data_type = "s"
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def validate_url(url):
    parsed = urlsplit(url)
    if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("请填写不含凭据的 http/https URL")
    return url


def extract_text(raw, filename):
    if not raw or len(raw) > MAX_UPLOAD:
        raise ValueError("文件为空或超过 20 MiB")
    if filename.lower().endswith(".txt"):
        text = raw.decode("utf-8-sig")
    elif filename.lower().endswith(".pdf"):
        from PyPDF2 import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted or len(reader.pages) > 200:
            raise ValueError("不支持加密 PDF 或超过 200 页的文件")
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
    else:
        raise ValueError("仅支持 TXT 和文本 PDF")
    if not text.strip():
        raise ValueError("未提取到文字；扫描 PDF 暂不支持")
    return text


def unwrap(value):
    return value.get("value", "") if isinstance(value, dict) else value or ""


def validate_graph(graph):
    """Basic structure/reference checks, not a semantic quality certificate."""
    if not isinstance(graph, dict) or not isinstance(graph.get("event_id"), str) or not graph["event_id"].strip():
        raise ValueError("图缺少 event_id")
    if not unwrap(graph.get("title")) or not isinstance(graph.get("stages"), list) or not graph["stages"]:
        raise ValueError("图需要 title 和非空 stages")
    stage_ids = set()
    for stage in graph["stages"]:
        sid = stage.get("stage_id") if isinstance(stage, dict) else None
        if not isinstance(sid, str) or not sid or sid in stage_ids or not isinstance(stage.get("episodes"), list):
            raise ValueError("stage_id 重复或阶段结构不完整")
        stage_ids.add(sid)
        episode_ids = set()
        for episode in stage["episodes"]:
            eid = episode.get("episode_id") if isinstance(episode, dict) else None
            if not isinstance(eid, str) or not eid or eid in episode_ids:
                raise ValueError("episode_id 缺失或在同一阶段内重复")
            episode_ids.add(eid)
            participants = episode.get("participants", [])
            if not isinstance(participants, list):
                raise ValueError("participants 必须是列表")
            ids = set()
            for p in participants:
                pid = p.get("participant_id") if isinstance(p, dict) else None
                if not isinstance(pid, str) or not pid or pid in ids:
                    raise ValueError("情节内 participant_id 缺失或重复")
                ids.add(pid)
                if not isinstance(p.get("actions", []), list):
                    raise ValueError("actions 必须是列表")
            for collection in ("participant_relations", "transactions"):
                edges = episode.get(collection) or []
                if not isinstance(edges, list):
                    raise ValueError(f"{collection} 必须是列表")
                for edge in edges:
                    if not isinstance(edge, dict):
                        raise ValueError("关系必须是对象")
                    for key in ("from_participant_id", "to_participant_id"):
                        target = unwrap(edge.get(key))
                        if target and target != "unknown" and target not in ids:
                            raise ValueError(f"{eid} 关系引用不存在的主体：{target}")
    encoded(graph)
    return graph


def graph_from_bytes(raw):
    if len(raw) > MAX_UPLOAD:
        raise ValueError("图文件超过 20 MiB")
    graph = json.loads(raw.decode("utf-8-sig"))
    if isinstance(graph, list) and len(graph) == 1:
        graph = graph[0]
    return validate_graph(graph)


def editable_fields(value, path=()):
    if isinstance(value, dict):
        for key, child in value.items():
            if key.endswith("_id") or key in {"index_in_stage", "index_in_event", "confidence"}:
                continue
            yield from editable_fields(child, path + (key,))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from editable_fields(child, path + (i,))
    elif isinstance(value, str):
        yield path, value
