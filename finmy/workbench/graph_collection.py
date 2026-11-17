"""Review-bound person Event collection, registry updates and reversible withdrawal."""
import csv
import io
import json
from pathlib import Path
import re

import yaml

from finmy.dataset import DatasetCatalog, accepted_artifact_paths, catalog_event_directory, within
from finmy.search.state import digest
from finmy.search.summary import atomic_text, directory_lock
from .catalog_actions import folder_files, replace_folder, action_record, save_action

FILES = ('epg.json', 'gantt.html', 'review.md')
FIELDS = ('event_id', 'build_task_id', 'graph_sha256', 'input_sha256', 'gantt_sha256')


def parse_review(raw):
    text = raw.decode('utf-8-sig') if isinstance(raw, bytes) else raw
    match = re.match(r'\A---\s*\n(.*?)\n---\s*\n(.*)\Z', text, re.S)
    if not match:
        raise ValueError('review.md 需要模板中的 YAML 元信息及审核正文')
    try:
        node = yaml.compose(match[1])
        if not isinstance(node, yaml.MappingNode): raise ValueError()
        keys = [k.value for k, _ in node.value]
        if len(keys) != len(set(keys)): raise ValueError()
        meta = yaml.load(match[1], Loader=yaml.BaseLoader)
    except (yaml.YAMLError, ValueError) as exc:
        raise ValueError('审核元信息格式无效或字段重复') from exc
    if not all(isinstance(meta.get(k), str) and meta[k].strip() for k in (*FIELDS, 'reviewer', 'reviewed_at', 'decision')):
        raise ValueError('请填写审核人、时间、结论及完整版本绑定')
    if not all(re.fullmatch(r'[a-f0-9]{64}', meta[k]) for k in ('graph_sha256', 'input_sha256', 'gantt_sha256')):
        raise ValueError('审核哈希无效')
    if not match[2].strip(): raise ValueError('请保留内容与证据审核结论，不能只提供元信息')
    return meta


def registry(catalog):
    root = Path(catalog['root']).resolve()
    path = root/'event-epg/events.csv' if catalog['kind'] == 'event' else root.joinpath(*Path(catalog['event_dir']).parts[:2])/'events.csv'
    if within(root, path.relative_to(root)) != path or path.is_symlink():
        raise ValueError('事件主表不能重定向')
    raw = path.read_bytes()
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    fields = reader.fieldnames or []
    required = {'event_id', 'status', 'epg_path', 'gantt_path', 'review_path'}
    if not required <= set(fields) or len(fields) != len(set(fields)):
        raise ValueError('事件主表缺少成果字段或存在重复列')
    rows = list(reader)
    if any(None in r or any(v is None for v in r.values()) for r in rows):
        raise ValueError('事件主表列数不一致')
    matches = [r for r in rows if r['event_id'] == catalog['event_id']]
    if len(matches) != 1: raise ValueError('事件主表身份缺失或重复')
    row = matches[0]
    if catalog['kind'] == 'person_event' and (row.get('person_id') != catalog['person_id'] or row.get('storyline_id') != catalog['storyline_id']):
        raise ValueError('事件主表人物或 storyline 不一致')
    return path, raw, fields, rows, row


def _registry_text(fields, rows):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
    writer.writeheader(); writer.writerows(rows)
    return stream.getvalue()


def _identity(catalog, graph):
    if (graph.get('schema_version') != 'person-event-1.0'
            or graph.get('event', {}).get('event_id') != catalog['event_id']
            or graph.get('person', {}).get('person_id') != catalog.get('person_id')
            or graph.get('storyline', {}).get('storyline_id') != catalog.get('storyline_id')):
        raise ValueError('图与 event / person / storyline 身份不一致')


def graph_collection(catalog):
    files = folder_files(catalog_event_directory(catalog)/'epg', FILES)
    if not files: return None
    if set(files) != set(FILES): raise ValueError('正式图、Gantt 或审核记录缺失')
    meta = parse_review(files['review.md'])
    if (meta['decision'] != 'accepted' or meta['event_id'] != catalog['event_id']
            or digest(files['epg.json']) != meta['graph_sha256']
            or digest(files['gantt.html']) != meta['gantt_sha256']):
        raise ValueError('正式成果与审核绑定不一致')
    _identity(catalog, json.loads(files['epg.json']))
    # Native rendering embeds the exact JSON file hash, not a newly serialized hash.
    if meta['graph_sha256'].encode() not in files['gantt.html']:
        raise ValueError('Gantt 未绑定当前图')
    _, _, _, _, row = registry(catalog)
    if row['status'] != 'accepted' or any(row[k] != v for k, v in accepted_artifact_paths(catalog).items()):
        raise ValueError('正式成果存在，但主表尚未一致登记')
    return dict(files=files, review=meta, review_sha256=digest(files['review.md']))


def build_collection(row):
    body = row['body']
    if not body.get('catalog') or body.get('kind') != 'person_event': return None
    try:
        current = graph_collection(body['catalog'])
        if not current or current['review']['build_task_id'] != row['id']: return None
        state = json.loads((Path(body['artifact_directory'])/'state.json').read_text())
        if (current['review']['graph_sha256'] != state.get('graph_sha256')
                or current['review']['input_sha256'] != state.get('input_sha256')): return None
        return current
    except (ValueError, OSError, KeyError, TypeError):
        return None


def reviewed_artifacts(row):
    body = row['body']
    if body.get('kind') != 'person_event' or row['status'] != 'completed' or body.get('disposition') == 'discarded':
        raise ValueError('请先完成结构草稿；舍弃或 partial 产物不能直接收录')
    root = Path(body['artifact_directory'])
    state = json.loads((root/'state.json').read_text())
    if state.get('execution_status') != 'finished' or state.get('result_status') != 'draft':
        raise ValueError('当前运行还不是完整 draft')
    graph = within(root, state['output']).read_bytes()
    checks = within(root, state['checks']).read_bytes()
    payload = (root/'input.json').read_bytes()
    render = state.get('visualization', {})
    if render.get('status') != 'completed' or render.get('graph_sha256') != digest(graph):
        raise ValueError('Gantt 缺失或属于另一版图，请先重新绘图并审核')
    html = within(root, render['output']).read_bytes()
    report = json.loads(checks)
    if (digest(json.loads(payload)) != body['input_hash']
            or digest(graph) != state['graph_sha256'] or digest(checks) != state['checks_sha256']
            or digest(payload) != state['input_sha256'] or digest(html) != render.get('html_sha256')
            or report.get('graph_sha256') != state['graph_sha256']
            or report.get('input_sha256') != state['input_sha256']
            or report.get('summary', {}).get('errors') != 0):
        raise ValueError('图、输入、检查或 Gantt 的版本不一致或存在结构错误')
    _identity(body['catalog'], json.loads(graph))
    return dict(epg=graph, gantt=html, binding=dict(event_id=row['event_id'], build_task_id=row['id'],
                graph_sha256=digest(graph), input_sha256=digest(payload), gantt_sha256=digest(html)))


def review_template(row):
    item = reviewed_artifacts(row)
    meta = dict(item['binding'], decision='pending', reviewer='', reviewed_at='')
    return '---\n'+yaml.safe_dump(meta, sort_keys=False)+'---\n\n# Content and evidence review\n\n'+\
        'Review subject attribution, actions, time and phases, relationships, and supporting evidence.\n'+\
        'Record findings, remaining uncertainties and the acceptance conclusion here.\n'


def collect_graph(controller, task_id, review_bytes, *, confirmed=False):
    from .build_tasks import worker_lock
    if not confirmed: raise ValueError('请确认审核结论后收录')
    meta = parse_review(review_bytes)
    if meta['decision'] != 'accepted': raise ValueError('审核结论尚未通过')
    with worker_lock(controller.root, task_id, blocking=False):
        row = controller.inspect(task_id)
        body = row['body']; catalog = body['catalog']
        root = Path(body['artifact_directory'])
        with directory_lock(root):
            items = reviewed_artifacts(row)
            if any(meta[k] != v for k, v in items['binding'].items()):
                raise ValueError('审核对应另一构建任务、图、输入或 Gantt，请重新检查')
            files = {'epg.json': items['epg'], 'gantt.html': items['gantt'], 'review.md': review_bytes}
            table = registry(catalog)[0]
            parent = catalog_event_directory(catalog)
            parent.mkdir(parents=True, exist_ok=True)
            with directory_lock(table.parent), directory_lock(parent):
                old = folder_files(parent/'epg', FILES)
                if old:
                    existing = graph_collection(catalog)
                    if existing['files'] == files: return existing['review']
                    raise ValueError('事件已收录其他版本；请明确撤回后再收录')
                path, original, fields, rows, entry = registry(catalog)
                # Re-resolve identity and destination; catalog edits cannot redirect a saved task.
                selected = DatasetCatalog(catalog['root']).select(catalog['event_id'], catalog.get('person_id'))
                if catalog_event_directory(selected) != parent:
                    raise ValueError('目录身份或路径已变化，请先核对')
                if entry['status'] == 'accepted' or any(entry[k] for k in accepted_artifact_paths(catalog)):
                    raise ValueError('主表已有成果登记，请先核对或撤回')
                receipt = action_record(catalog, 'epg', 'collected', files, reviewer=meta['reviewer'])
                receipt['build_task_id'] = task_id
                entry.update(status='accepted', **accepted_artifact_paths(catalog))
                with replace_folder(parent/'epg', files):
                    try:
                        atomic_text(path, _registry_text(fields, rows))
                        save_action(catalog, receipt, files)
                    except Exception:
                        path.write_bytes(original)
                        raise
                return receipt


def withdraw_graph(catalog, *, expected_review, reviewer, reason):
    if not reason.strip(): raise ValueError('请填写撤回原因')
    table = registry(catalog)[0]; parent = catalog_event_directory(catalog)
    with directory_lock(table.parent), directory_lock(parent):
        current = graph_collection(catalog)
        if not current or current['review_sha256'] != expected_review:
            raise ValueError('成果版本已变化，请刷新后检查')
        path, original, fields, rows, entry = registry(catalog)
        receipt = action_record(catalog, 'epg', 'withdrawn', current['files'], reviewer=reviewer, reason=reason)
        receipt['build_task_id'] = current['review']['build_task_id']
        entry.update(status='in_review', epg_path='', gantt_path='', review_path='')
        with replace_folder(parent/'epg', {}):
            try:
                atomic_text(path, _registry_text(fields, rows))
                save_action(catalog, receipt, current['files'])
            except Exception:
                path.write_bytes(original)
                raise
        return receipt
