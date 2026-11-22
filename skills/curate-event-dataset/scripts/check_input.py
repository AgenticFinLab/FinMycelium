"""Check a complete event master or a batch against the skill's CSV template."""
import argparse
import csv
from datetime import date
from pathlib import Path
import re
import sys
import unicodedata
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from finmy.workbench.domain import LIST_FIELDS, event_record, graph_from_bytes
from finmy.dataset import section, table_rows


TEMPLATE = Path(__file__).resolve().parents[1] / "assets/events.input.template.csv"
ID = re.compile(r"event[1-9][0-9]*")
SOURCE_ID = re.compile(r"\bSRC-[0-9]+\b")
EVENT_REF = re.compile(r"\bevent[1-9][0-9]*\b")
REQUIRED_TEXT = ("event_name_zh", "event_name_en", "description", "domain", "category", "scope_include")
RESEARCH_FIELDS = ("aliases", "country_region", "participants", "coverage_start", "coverage_end")
PLACEHOLDERS = {"tbd", "n/a", "unknown", "pending verification", "待核实", "待补充"}
STAGE_ROWS = {"baseline": 3000, "final": 10000}
PROGRESS_FIELDS = ["Phase", "Event IDs or candidate scope", "Research completed",
                   "Duplicate review coverage", "Open issues", "Next action"]


def is_url(value):
    if not re.fullmatch(r"https?://[^\s\\]+", value):
        return False
    try:
        parsed = urlsplit(value)
        return bool(parsed.hostname) and parsed.username is None and parsed.password is None
    except ValueError:
        return False


def check_text(key, value):
    if value.strip().casefold() in PLACEHOLDERS:
        raise ValueError(f"{key} 含占位符")
    if key == "event_name_zh" or (key == "source_hints" and is_url(value)):
        return
    # Detect clearly non-English scripts without rejecting Latin diacritics.
    # Individual Greek symbols and the micro prefix occur in English technical prose.
    prose = re.sub(r"(?<![Α-ω])[Α-Ωα-ωµ](?![Α-ω])", "", value)
    if any(c.isalpha() and "LATIN" not in unicodedata.name(c, "") for c in prose):
        raise ValueError(f"{key} 请使用英文")


def load_sources(path):
    with TEMPLATE.with_name("sources.template.csv").open(encoding="utf-8-sig", newline="") as template:
        fields = next(csv.reader(template))
    sources = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        if reader.fieldnames != fields:
            raise ValueError("sources.csv 表头与来源模板不一致")
        for row in reader:
            if None in row or None in row.values():
                raise ValueError(f"来源索引第 {reader.line_num} 行列数有误")
            sid = row["source_id"]
            if not SOURCE_ID.fullmatch(sid) or sid in sources:
                raise ValueError(f"来源索引第 {reader.line_num} 行 ID 无效或重复：{sid}")
            if not all(row[k].strip() for k in ("title", "reading_note", "support_note")):
                raise ValueError(f"{sid} 缺标题、阅读定位或支持说明")
            if any(row[k].strip().casefold() in PLACEHOLDERS for k in
                   ("title", "publication_info", "reading_note", "support_note")):
                raise ValueError(f"{sid} 的来源信息仍为占位符")
            url = row["url"].strip()
            if (url and not is_url(url)) or (not url and not row["publication_info"].strip()):
                raise ValueError(f"{sid} 请核对 URL 或填写可定位文号")
            # Only explicit attributions establish support. Comparisons can mention other events.
            supported = set()
            for line in row["support_note"].splitlines():
                if not line.strip():
                    continue
                match = re.fullmatch(r"(event[1-9][0-9]*):\s*(.+)", line.strip())
                if not match or match[2].strip().casefold() in PLACEHOLDERS:
                    raise ValueError(f"{sid} 的 support_note 须按 eventN: 具体事实 分行登记")
                supported.add(match[1])
            sources[sid] = (url, supported, row["publication_info"])
    return sources


def check_source_hints(eid, hints, sources):
    citations = set()
    urls = set()
    unlabelled = []
    for hint in hints:
        if re.match(r"https?://", hint, re.I) and not is_url(hint):
            raise ValueError("独立来源链接须为有效 URL，并以小写 http:// 或 https:// 开头")
        if is_url(hint):
            urls.add(hint)
            continue
        ids = SOURCE_ID.findall(hint)
        if not ids:
            unlabelled.append(hint)
        if ids:
            detail = SOURCE_ID.sub("", hint).strip(" \t\r\n:;—–-,.()[]")
            if not re.search(r"[A-Za-z]", detail) or detail.casefold() in PLACEHOLDERS:
                raise ValueError("来源编号旁须有英文定位及支持说明")
        citations.update(ids)
    if not citations:
        raise ValueError("source_hints 须在英文定位及支持说明中引用 SRC-编号")
    if sources is None:
        return
    indexed_urls = set()
    publication_records = []
    for sid in sorted(citations):
        if sid not in sources:
            raise ValueError(f"{eid} 引用了不存在的 {sid}")
        url, supported_events, publication = sources[sid]
        if eid not in supported_events:
            raise ValueError(f"{sid} 的 support_note 缺少 {eid}")
        if url:
            indexed_urls.add(url)
        publication_records.append(publication)
    if urls != indexed_urls:
        raise ValueError(f"{eid} 的来源 URL 与引用的索引条目不一致")
    for item in unlabelled:
        # A separately supplied document number may be transcribed from publication_info.
        if not any(item in publication for publication in publication_records):
            raise ValueError(f"{eid} 有未绑定来源的说明；请标注对应 SRC 编号，或核对独立文号")


def check_duplicate_decisions(issue_text, duplicates, sources, event_ids):
    pair_section = section(issue_text, 2, "Pair decisions")
    rows = iter(table_rows(pair_section))
    template = TEMPLATE.with_name("issues.template.md").read_text(encoding="utf-8-sig")
    if next(rows, None) != next(table_rows(template)):
        raise ValueError("ISSUES.md 缺少配对裁决表头")
    resolved = set()
    pairs = set()
    for cells in rows:
        if len(cells) != 6:
            raise ValueError("ISSUES.md 的配对裁决须为六列")
        members = frozenset(EVENT_REF.findall(cells[0]))
        if len(members) != 2 or not members <= event_ids:
            raise ValueError(f"ISSUES.md 配对须引用两个不同且已登记的事件：{cells[0]}")
        if members in pairs:
            raise ValueError(f"ISSUES.md 中同一配对有多条当前裁决：{cells[0]}")
        pairs.add(members)
        decision = cells[1].strip("`")
        pair = re.fullmatch(r"(event[1-9][0-9]*)\s*(?:→|->)\s*(event[1-9][0-9]*)",
                            decision.replace("`", ""))
        if decision == "pending":
            raise ValueError(f"ISSUES.md 中仍有待核配对：{cells[0]}")
        if not pair and decision not in ("distinct", "overlap"):
            raise ValueError(f"ISSUES.md 配对裁决类型无效：{decision}")
        if pair:
            eid, representative = pair.groups()
            if (members != set(pair.groups()) or eid in resolved or representative not in duplicates.get(eid, ())
                    or representative in duplicates):
                raise ValueError(f"ISSUES.md 的代表行裁决与主表不一致或重复：{eid} → {representative}")
            resolved.add(eid)
        if not all(cells[2:]) or any(cell.casefold() in PLACEHOLDERS for cell in cells[2:]):
            raise ValueError(f"ISSUES.md 的配对缺比较、依据或日期：{cells[0]}")
        evidence = set(SOURCE_ID.findall(cells[4]))
        if not evidence or evidence - sources.keys():
            raise ValueError(f"ISSUES.md 的配对裁决须引用新版索引中的来源 ID：{cells[0]}")
        supported = set().union(*(sources[sid][1] for sid in evidence))
        if not members <= supported:
            raise ValueError(f"ISSUES.md 的配对来源合计须在 support_note 中覆盖双方：{cells[0]}")
        if not any(c.isalnum() for c in SOURCE_ID.sub("", cells[4])):
            raise ValueError(f"ISSUES.md 的配对还须写明原文定位及支持事实：{cells[0]}")
        try:
            if date.fromisoformat(cells[5]).isoformat() != cells[5]:
                raise ValueError
        except ValueError:
            raise ValueError(f"ISSUES.md 的核查日期须为有效的 YYYY-MM-DD：{cells[0]}") from None
    missing = duplicates.keys() - resolved
    if missing:
        raise ValueError(f"ISSUES.md 缺少已标重复行的直接裁决：{', '.join(sorted(missing))}")


def check_progress(plan, stage):
    progress = section(plan, 2, "Batch progress and open questions")
    rows = iter(table_rows(progress))
    if next(rows, None) != PROGRESS_FIELDS:
        raise ValueError("research-plan.md 缺少模板中的批次进度表头")
    coverage = {field: set() for field in PROGRESS_FIELDS[2:4]}
    for row in rows:
        if len(row) != len(PROGRESS_FIELDS) or row[0] not in ("baseline", "expansion"):
            raise ValueError("批次进度行须按模板填写，阶段为 baseline 或 expansion")
        lo, hi = ((1, STAGE_ROWS["baseline"]) if row[0] == "baseline"
                  else (STAGE_ROWS["baseline"] + 1, STAGE_ROWS["final"]))
        for field, cell in zip(coverage, row[2:4]):
            if not cell or cell in ("-", "—"):
                continue
            for item in cell.split(","):
                span = re.fullmatch(r"event([1-9][0-9]*)(?:\s*[-–]\s*event([1-9][0-9]*))?", item.strip())
                if not span:
                    raise ValueError(f"{field} 须列出实际完成的 eventN 或 eventA-eventB")
                start, end = int(span[1]), int(span[2] or span[1])
                if not lo <= start <= end <= min(hi, STAGE_ROWS[stage]):
                    raise ValueError(f"{field} 的编号区间与阶段不符：{item}")
                coverage[field].update(range(start, end + 1))
    expected = set(range(1, STAGE_ROWS[stage] + 1))
    for field, covered in coverage.items():
        missing = sorted(expected - covered)
        if missing:
            sample = ", ".join(f"event{i}" for i in missing[:8])
            raise ValueError(f"research-plan.md 的 {field} 缺 {len(missing)} 条，含 {sample}")


def check(path, *, batch=False, for_search=False, research_gaps=None, sources_path=None, prose_groups=None,
          stage=None, catalog_root=None):
    if stage and (batch or stage not in STAGE_ROWS):
        raise ValueError("阶段检查仅适用于完整主表的 baseline 或 final 阶段")
    if stage and path.name != "events.csv":
        raise ValueError("阶段交付主表必须命名为 events.csv")
    if catalog_root is not None and not batch:
        raise ValueError("--catalog-root 仅用于独立批次节选")
    root = (catalog_root or path.parent).resolve()
    if stage and path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("阶段交付主表超过 DatasetCatalog 的 64 MiB 读取上限")
    with TEMPLATE.open(encoding="utf-8-sig", newline="") as template:
        fields = next(csv.reader(template))
    seen = set()
    references = set()
    duplicates = {}
    sibling = root / "sources.csv"
    if stage and sources_path is not None and sources_path.resolve() != sibling.resolve():
        raise ValueError("阶段检查须使用交付目录自身的 sources.csv")
    if sources_path is None and (not batch or catalog_root is not None or sibling.exists()):
        sources_path = sibling
    sources = load_sources(sources_path) if sources_path is not None else None
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source, strict=True)
        if reader.fieldnames != fields:
            raise ValueError("表头须与 18 列主表模板一致")
        for row in reader:
            try:
                if None in row or None in row.values():
                    raise ValueError("列数有误")
                eid = row["event_id"]
                if not ID.fullmatch(eid) or eid in seen:
                    raise ValueError("事件编号格式错误或重复")
                if int(eid[5:]) > 10000:
                    raise ValueError("本轮事件编号超过 event10000")
                if not batch and eid != f"event{len(seen) + 1}":
                    raise ValueError("完整主表须从 event1 连续排列")
                for key in REQUIRED_TEXT:
                    if not row[key].strip() or not any(c.isalpha() for c in row[key]):
                        raise ValueError(f"{key} 为必填文本")
                for key in ("domain", "category"):
                    label = row[key].strip()
                    if label.startswith(("[", "{")) or re.search(r"[;|\r\n]", label):
                        raise ValueError(f"{key} 须填写一个英文标签")
                duplicate = row.pop("is_duplicate")
                if duplicate not in ("", "true"):
                    raise ValueError("is_duplicate 只接受空单元格或小写 true")
                graph = row.pop("epg_path")
                if graph:
                    if graph != f"events/{eid}/epg/epg.json":
                        raise ValueError(f"epg_path 须指向当前事件的 events/{eid}/epg/epg.json")
                    artifact = root / graph
                    if artifact.resolve() != artifact or not artifact.is_file():
                        raise ValueError("epg_path 对应文件缺失或路径被重定向")
                    try:
                        graph_from_bytes(artifact.read_bytes())
                    except (ValueError, TypeError) as exc:
                        raise ValueError(f"epg_path 对应文件无法作为普通事件图读取：{exc}") from exc
                for key in LIST_FIELDS | {"related_events"}:
                    if row[key].strip() and not row[key].lstrip().startswith("["):
                        raise ValueError(f"{key} 须为 JSON 数组")
                for key in ("coverage_start", "coverage_end"):
                    if row[key].strip().lower() == "unknown":
                        raise ValueError(f"{key} 未知时留空")
                record = event_record(row)
                main_names = {record[key].casefold() for key in ("event_name_en", "event_name_zh")}
                if any(alias.casefold() in main_names for alias in record["aliases"]):
                    raise ValueError("aliases 中重复填入了事件主名")
                if not record["keywords"]:
                    raise ValueError("keywords 至少需要一个来自事件名称或材料的检索词")
                for key, value in record.items():
                    if isinstance(value, str):
                        check_text(key, value)
                    elif key in LIST_FIELDS:
                        for item in value:
                            check_text(key, item)
                check_source_hints(eid, record["source_hints"], sources)
                if prose_groups is not None:
                    title = " ".join(record["event_name_en"].casefold().split())
                    for field in ("description", "scope_include"):
                        content = " ".join(record[field].casefold().split())
                        key = (field, content.replace(title, "{event}"))
                        prose_groups.setdefault(key, []).append(eid)
                relations = record["related_events"]
                for relation in relations:
                    if not ID.fullmatch(relation["event_id"]) or not any(c.isalpha() for c in relation["note"]):
                        raise ValueError("related_events 须填写有效事件编号和英文关系说明")
                    if int(relation["event_id"][5:]) > STAGE_ROWS["final"]:
                        raise ValueError("关系目标超过本轮 event10000 上限")
                    if stage and relation["relation_type"] == "possible_duplicate":
                        raise ValueError("阶段验收前须查清 possible_duplicate 并更新关系与裁决")
                    check_text("related_events.note", relation["note"])
                    references.add(relation["event_id"])
                if duplicate == "true":
                    targets = {r["event_id"] for r in relations if r["relation_type"] == "related"}
                    if not targets:
                        raise ValueError("重复行须通过 related_events 指向保留记录")
                    duplicates[eid] = targets
                    if stage == "final" and int(eid[5:]) > 3000:
                        raise ValueError(f"新增区仍有已确认重复行 {eid}，须先处理并复核数量")
                if research_gaps is not None:
                    for field in RESEARCH_FIELDS:
                        if not record[field]:
                            research_gaps.setdefault(field, []).append(eid)
                seen.add(eid)
            except ValueError as exc:
                raise ValueError(f"第 {reader.line_num} 行：{exc}") from exc
    if not seen or (not batch and len(seen) < 3000):
        raise ValueError("完整主表须覆盖 event1 至 event3000；节选须含数据并使用 --batch")
    if not batch and references - seen:
        raise ValueError(f"完整主表缺少关系目标：{', '.join(sorted(references - seen))}")
    for eid, targets in duplicates.items():
        if not targets.difference(duplicates):
            raise ValueError(f"{eid} 的 related 目标全部是重复行，缺少直接指向的代表行")
    if not batch:
        for sid, (_, supported, _) in sources.items():
            missing = supported - seen
            if missing:
                raise ValueError(f"{sid} 的 support_note 引用了不存在的事件：{', '.join(sorted(missing))}")
    if stage:
        if len(seen) != STAGE_ROWS[stage]:
            raise ValueError(f"{stage} 阶段须恰有 {STAGE_ROWS[stage]} 条，当前 {len(seen)} 条")
        for name in ("README.md", "research-plan.md", "ISSUES.md"):
            document = path.with_name(name)
            if not document.is_file() or not document.read_text(encoding="utf-8-sig").strip():
                raise ValueError(f"阶段交付目录缺少或尚未填写 {name}")
        check_duplicate_decisions(path.with_name("ISSUES.md").read_text(encoding="utf-8-sig"),
                                  duplicates, sources, seen)
        check_progress(path.with_name("research-plan.md").read_text(encoding="utf-8-sig"), stage)
    return len(seen)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--batch", action="store_true", help="校验单批节选，允许不连续编号")
    mode.add_argument("--stage", choices=STAGE_ROWS, help="检查阶段交付的准确行数及配套文件")
    parser.add_argument("--show-gaps", action="store_true", help="按空缺字段列出应复查的事件 ID")
    parser.add_argument("--sources", type=Path, help="指定本批来源索引；完整主表默认读取同目录 sources.csv")
    parser.add_argument("--catalog-root", type=Path, help="批次节选所对应的新版 event-epg 目录，用于定位图和默认来源索引")
    parser.add_argument("--review-prose", action="store_true", help="列出归一化空白、大小写和英文事件名后相同的简介或范围")
    parser.add_argument("--for-search", action="store_true", help="兼容已有命令；默认已检查检索范围和关键词")
    args = parser.parse_args()
    try:
        gaps = {}
        prose = {} if args.review_prose else None
        count = check(args.csv, batch=args.batch, for_search=args.for_search, research_gaps=gaps,
                      sources_path=args.sources, prose_groups=prose, stage=args.stage, catalog_root=args.catalog_root)
    except (OSError, ValueError, csv.Error) as exc:
        parser.exit(1, f"{args.csv}: {exc}\n")
    print(f"通过主表格式检查：{count} 条事件。")
    if args.batch and not args.sources and not args.catalog_root and not args.csv.with_name("sources.csv").is_file():
        print("本批仅检查引用格式；交付复核请提供本轮 sources.csv。")
    if prose:
        for (field, _), events in prose.items():
            if len(events) > 1:
                print(f"复查相同表述 {field}：{', '.join(events)}")
    for field, events in gaps.items():
        detail = "：" + ", ".join(events) if args.show_gaps else ""
        print(f"检索字段留空：{field}（{len(events)} 条）{detail}")
