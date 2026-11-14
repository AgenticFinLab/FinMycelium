"""Read dataset catalogs and freeze single-event search inputs, without services."""
from copy import deepcopy
import csv
import io
import json
from pathlib import Path
import re

from finmy.search.state import digest, now, write_json


def within(root, relative):
    root = Path(root).expanduser().resolve()
    value = Path(relative)
    if value.is_absolute() or '..' in value.parts or not value.parts:
        raise ValueError('数据集路径必须是目录内的相对路径')
    path = (root / value).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError('数据集路径越出所选目录')
    return path


def component(value):
    if not value or value in {'.', '..'} or any(c in value for c in '/\\\n\r\x00'):
        raise ValueError('目录名称无效，请检查主表中的名称或 ID')
    return value


def dataset_root(workspace):
    path = Path(workspace) / 'dataset.json'
    return json.loads(path.read_text(encoding='utf-8')).get('root', '') if path.exists() else ''


def save_dataset_root(workspace, root):
    catalog = DatasetCatalog(root)
    write_json(Path(workspace) / 'dataset.json', {'root': str(catalog.root)})
    return catalog


def output_directory(root, *parts):
    """Resolve ignored run output without writing to the accepted catalogs."""
    if not str(root).strip():
        raise ValueError('请先在设置中填写 EPG-dataset 本地路径，以保存构建输出')
    base = Path(root).expanduser().resolve()
    if not base.is_dir():
        raise ValueError('数据集根目录已不存在')
    output = within(base, 'output')
    if output != base / 'output':
        raise ValueError('output 不能重定向到其他目录')
    if output.exists() and not output.is_dir():
        raise ValueError('output 必须是目录')
    return within(output, Path(*(component(value) for value in parts))) if parts else output


def catalog_event_directory(catalog):
    """The formal catalog destination, separate from ignored execution output."""
    root = Path(catalog['root']).expanduser().resolve()
    relative = Path(catalog['event_dir'])
    kind = catalog.get('kind')
    valid = ((kind == 'event' and len(relative.parts) == 3
              and relative.parts[:2] == ('event-epg', 'events')
              and relative.name == component(catalog['event_id']))
             or (kind == 'person_event' and len(relative.parts) == 4
                 and relative.parts[0] == 'person-epg'))
    if not valid or any(component(p) != p for p in relative.parts):
        raise ValueError('事件收录路径不符合数据集目录约定')
    path = within(root, relative)
    if path != root/relative:
        raise ValueError('事件收录目录不能经过符号链接')
    return path


def accepted_artifact_paths(catalog):
    """Registry-relative paths; callers fill them only after graph acceptance."""
    root = Path(catalog['root']).expanduser().resolve()
    folder = catalog_event_directory(catalog)/'epg'
    base = root/'event-epg' if catalog['kind'] == 'event' else root.joinpath(*Path(catalog['event_dir']).parts[:2])
    return {key: str((folder/name).relative_to(base)) for key, name in
            (('epg_path', 'epg.json'), ('gantt_path', 'gantt.html'), ('review_path', 'review.md'))}


def summary_directory(catalog):
    relative = Path(catalog['event_dir'])
    allowed = Path('event-epg/events') if catalog['kind'] == 'event' else Path('person-epg')
    if not relative.is_relative_to(allowed) or relative == allowed:
        raise ValueError('event 汇总目录不在对应的数据集分类下')
    return output_directory(catalog['root'], 'search', *relative.parts)


def string_list(value):
    value = value or ''
    items = json.loads(value) if value.lstrip().startswith('[') else value.splitlines()
    if not isinstance(items, list) or any(not isinstance(v, str) for v in items):
        raise ValueError('多值字段需要 JSON 字符串数组或每行一项')
    return list(dict.fromkeys(v.strip() for v in items if v.strip()))


def table_rows(markdown):
    for line in markdown.splitlines():
        if not line.lstrip().startswith('|'):
            continue
        cells = [v.strip().replace('\\|', '|') for v in re.split(r'(?<!\\)\|', line.strip().strip('|'))]
        if cells and not re.fullmatch(r'[:\- ]+', cells[0]):
            yield cells


def section(text, level, title):
    matches = list(re.finditer(rf'^{"#" * level}\s+(.+?)\s*#*\s*$', text, re.M))
    found = [m for m in matches if re.fullmatch(title, m[1], re.I)]
    if len(found) != 1:
        raise ValueError(f'研究计划章节缺失或重复：{title}')
    match = found[0]
    end = re.search(rf'^#{{1,{level}}}\s+', text[match.end():], re.M)
    return text[match.end():match.end() + end.start() if end else len(text)].strip()


def labelled(text, label):
    pattern = rf'^\s*[-*]\s+\*\*{re.escape(label)}:?\*\*:?\s*(.*?)(?=^\s*[-*]\s+\*\*|^#|\Z)'
    match = re.search(pattern, text, re.M | re.S | re.I)
    return match[1].strip() if match else ''


class DatasetCatalog:
    def __init__(self, root):
        if not str(root).strip():
            raise ValueError('请先在设置中填写 EPG-dataset 本地路径')
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise ValueError('EPG-dataset 本地目录不存在')
        if not any(within(self.root, p).is_file() for p in ('event-epg/events.csv', 'person-epg/people.csv')):
            raise ValueError('目录中未找到 event-epg/events.csv 或 person-epg/people.csv')

    def _csv(self, relative, required, identity):
        path = within(self.root, relative)
        if not path.is_file():
            raise ValueError(f'目录中缺少 {relative}')
        raw = path.read_bytes()
        if len(raw) > 20 * 1024 * 1024:
            raise ValueError('目录表格过大')
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames) or not set(required) <= set(reader.fieldnames):
            raise ValueError(f'{relative} 表头缺失或重复：需要 {", ".join(required)}')
        rows = []
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError(f'{relative} 有列数不一致的记录')
            row = {k: v.strip() for k, v in row.items()}
            if not any(row.values()):
                continue
            if not row[identity]:
                raise ValueError(f'{relative} 存在空 {identity}')
            rows.append(row)
        if len({r[identity] for r in rows}) != len(rows):
            raise ValueError(f'{relative} 存在重复 {identity}')
        return rows, {'path': str(path.relative_to(self.root)), 'sha256': digest(raw)}

    def people(self):
        return self._csv('person-epg/people.csv', ['person_id', 'name', 'research_plan'], 'person_id')[0]

    def _person(self, person_id):
        rows, source = self._csv('person-epg/people.csv', ['person_id', 'name', 'research_plan'], 'person_id')
        person = next((r for r in rows if r['person_id'] == person_id), None)
        if person is None:
            raise ValueError('主表中不存在该人物')
        plan = within(self.root / 'person-epg', person['research_plan'])
        if plan.parent == self.root / 'person-epg' or plan.name != 'research-plan.md':
            raise ValueError('人物研究计划应位于独立人物目录的 research-plan.md')
        return person, plan, source

    def events(self, person_id=None):
        path = 'event-epg/events.csv' if person_id is None else str(self._person(person_id)[1].with_name('events.csv').relative_to(self.root))
        required = ['event_id', 'event_name', 'period']
        required += ['description', 'scope_include', 'scope_exclude'] if person_id is None else ['person_id', 'storyline_id', 'storyline_name']
        rows, _ = self._csv(path, required, 'event_id')
        if person_id:
            if any(r['person_id'] != person_id for r in rows):
                raise ValueError('人物 events.csv 中存在不同 person_id')
            paths = [(r['storyline_name'], r['event_name']) for r in rows]
            if len(set(paths)) != len(paths):
                raise ValueError('不同 event 的收录目录重名，请先在主表和研究计划中明确区分')
        return rows

    def select(self, event_id, person_id=None):
        # Re-read actual files when preparing a snapshot; nothing is written to the dataset.
        rows = self.events(person_id)
        event = next((r for r in rows if r['event_id'] == event_id), None)
        if event is None:
            raise ValueError('主表中不存在该 event')
        record = {'kind': 'person_event' if person_id else 'event', 'root': str(self.root),
                  'event_id': event_id, 'event_name': event['event_name'], 'event_row': event,
                  'period': event['period'], 'selected_at': now()}
        if not event['event_name']:
            raise ValueError('事件名称为空')
        if person_id:
            person, plan_path, person_source = self._person(person_id)
            raw = plan_path.read_bytes()
            text = raw.decode('utf-8-sig')
            identity = next((r[1] for r in table_rows(section(text, 2, r'1\.\s*person and research scope')) if r[0] == 'person_id'), None)
            if identity != person_id:
                raise ValueError('研究计划与人物主表的 person_id 不一致')
            description = section(text, 3, re.escape(event_id) + r'\s*[·—:]\s*.+')
            primary = re.search(r'\*\*Primary storyline:\*\*\s*(\S+)', description)
            if not primary or primary[1] != event['storyline_id']:
                raise ValueError('研究说明与 events.csv 的 storyline_id 不一致')
            overview = section(description, 4, 'Event overview')
            connection = section(description, 4, 'Connection to the person')
            scope = section(description, 4, 'Research scope')
            questions = section(description, 4, 'Further research')
            sources = []
            for row in table_rows(section(text, 2, r'6\.\s*Source index')):
                if len(row) > 1 and re.search(r'(?<![\w-])' + re.escape(row[0]) + r'(?![\w-])', description):
                    sources.append({'id': row[0], 'record': ' | '.join(row)})
            sources_text = '\n'.join(s['record'] for s in sources)
            leads = list(dict.fromkeys(re.findall(r'https?://[^\s<>\[\]()]+', sources_text + '\n' + questions)))
            _, event_source = self._csv(str(plan_path.with_name('events.csv').relative_to(self.root)), ['event_id'], 'event_id')
            # Display this deterministic path before confirmation; names with path separators need catalog correction.
            directory = plan_path.parent / component(event['storyline_name']) / component(event['event_name'])
            record.update(person_id=person_id, person_name=person['name'], person_row=person,
                          storyline_id=event['storyline_id'], storyline_name=event['storyline_name'],
                          description=overview, connection=connection, further_research=questions,
                          period=labelled(scope, 'Activity period') or event['period'],
                          scope_include=labelled(scope, 'Included'), scope_exclude=labelled(scope, 'Excluded and related events'),
                          research_description=description, source_leads=sources, seed_urls=leads,
                          aliases=string_list(person.get('aliases', '')), key_words=[],
                          files=[person_source, event_source, {'path': str(plan_path.relative_to(self.root)), 'sha256': digest(raw)}])
        else:
            _, source = self._csv('event-epg/events.csv', ['event_id'], 'event_id')
            directory = self.root / 'event-epg/events' / component(event_id)
            record.update(description=event['description'], scope_include=event['scope_include'], scope_exclude=event['scope_exclude'],
                          key_words=string_list(event.get('keywords', '')), source_leads=string_list(event.get('source_hints', '')),
                          seed_urls=[u for u in string_list(event.get('source_hints', '')) if u.startswith(('https://', 'http://'))],
                          files=[source])
        record['event_dir'] = str(within(self.root, directory.relative_to(self.root)).relative_to(self.root))
        record['snapshot_sha256'] = digest({k: v for k, v in record.items() if k != 'selected_at'})
        return record


def search_task(selection, *, period, include, exclude):
    if not include.strip() or not selection['description'].strip():
        raise ValueError('请补齐事件说明及本次纳入范围')
    record = deepcopy(selection)
    scope = dict(period=period.strip(), include=include.strip(), exclude=exclude.strip())
    lines = ['Research this single event within the confirmed scope. Do not expand to other events.',
             f"Event: {record['event_name']} ({record['event_id']})"]
    if record['kind'] == 'person_event':
        lines += [f"Person: {record['person_name']} ({record['person_id']})",
                  f"Storyline: {record['storyline_name']} ({record['storyline_id']})"]
    lines += [f"Activity period: {scope['period'] or 'Not specified; preserve uncertainty'}",
              f"Included: {scope['include']}", f"Excluded: {scope['exclude'] or 'Not specified'}",
              'Activity dates do not limit publication dates; retrospective sources are allowed.',
              'Planning context below guides research and is not source evidence:', record['description']]
    for key in ('connection', 'further_research'):
        if record.get(key): lines.append(record[key])
    if record.get('source_leads'):
        lines += ['Source leads (to verify):', json.dumps(record['source_leads'], ensure_ascii=False)]
    return dict(target_type='event', target_name=record['event_name'] + (f" — {record['person_name']}" if record['kind'] == 'person_event' else ''),
                query_text='\n\n'.join(lines), key_words=record['key_words'], seed_urls=record['seed_urls'],
                catalog=record, research_scope=scope)
