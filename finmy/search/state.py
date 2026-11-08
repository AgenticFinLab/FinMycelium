"""Small, persisted search tasks. One writer per task directory."""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else json.dumps(
        value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


@dataclass
class SearchConfig:
    providers: list = field(default_factory=lambda: ['bocha'])
    max_results: int = 5
    max_search_requests: int = 12
    max_read_sources: int = 12
    max_model_calls: int = 30
    max_read_chars: int = 12000
    max_builder_material_chars: int = 60000
    include_domains: list = field(default_factory=list)
    exclude_domains: list = field(default_factory=list)
    publication_start: str | None = None
    publication_end: str | None = None
    baidu_rewrite: bool = False
    allow_network: bool = False
    timeout: int = 120
    max_download_bytes: int = 20000000
    max_model_context_chars: int = 100000
    lm_name: str | None = 'ark/doubao-seed-2-1-lite-260915'
    generation_config: dict = field(default_factory=lambda: {'max_tokens':4096})

    def __post_init__(self):
        if not self.providers or len(set(self.providers)) != len(self.providers):
            raise ValueError('Select unique providers')
        if set(self.providers) - {'baidu', 'bocha', 'exa'}:
            raise ValueError('Unknown search provider')
        for name in ('max_results', 'max_search_requests', 'max_read_sources',
                     'max_model_calls', 'max_read_chars', 'max_builder_material_chars',
                     'timeout', 'max_download_bytes', 'max_model_context_chars'):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(name + ' must be a positive integer')
        if type(self.allow_network) is not bool or type(self.baidu_rewrite) is not bool:
            raise ValueError('Network/rewrite flags must be booleans')
        if not isinstance(self.generation_config, dict):
            raise ValueError('generation_config must be an object')
        if self.max_results > 50:
            raise ValueError('First-version max_results supports 1..50')
        for name in ('include_domains', 'exclude_domains'):
            if not isinstance(getattr(self, name), list) or any(
                not isinstance(d, str) or not d or '/' in d for d in getattr(self, name)
            ):
                raise ValueError(name + ' must contain bare domains')
        for name in ('publication_start', 'publication_end'):
            if getattr(self, name):
                datetime.strptime(getattr(self, name), '%Y-%m-%d')
        if self.publication_start and self.publication_end and self.publication_start > self.publication_end:
            raise ValueError('Publication interval is reversed')


class LimitReached(Exception):
    pass


class SearchState:
    def __init__(self, root, task_id, run_id='initial', *, task=None, config=None):
        for value in (task_id, run_id):
            if not re.fullmatch(r'[A-Za-z0-9_-]+', value):
                raise ValueError('Unsafe task/run identifier')
        self.root = Path(root) / task_id
        self.run_dir = self.root / 'runs' / run_id
        path = self.run_dir / 'run.json'
        if path.exists():
            self.data = json.loads(path.read_text(encoding='utf-8'))
            if task is not None and task != self.data['task']:
                raise ValueError('Task differs from saved scope; create a new task')
            if config is not None and asdict(config) != self.data['config']:
                raise ValueError('Resume must retain saved configuration')
            self.config = SearchConfig(**self.data['config'])
        else:
            if (self.root / 'runs').exists() and any((self.root / 'runs').iterdir()):
                raise ValueError('Resume existing run; a new run ID cannot reset task usage')
            if not isinstance(task, dict) or task.get('target_type') not in {'event', 'person', 'company'}:
                raise ValueError('Task needs target_type: event/person/company')
            if any(not isinstance(task.get(k), str) or not task[k].strip() for k in ('target_name', 'query_text')):
                raise ValueError('Task needs target_name and original query_text')
            if not isinstance(task.get('key_words', []), list) or any(not isinstance(k,str) for k in task.get('key_words', [])):
                raise ValueError('key_words must be a list of strings')
            self.config = config or SearchConfig()
            self.data = dict(task=task, config=asdict(self.config), created_at=now(),
                             input_sha256=digest(task), code_sha256=digest({p.name:digest(p.read_bytes()) for p in Path(__file__).parent.glob('*.py')}),
                             status='ready', usage={'search': 0, 'model': 0},
                             read_sources=[], sources={}, cache={}, feedback=None)
            self.save()

    def save(self):
        self.data['updated_at'] = now()
        write_json(self.run_dir / 'run.json', self.data)

    def trace(self, event):
        with (self.run_dir / 'trace.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'time': now(), **event}, ensure_ascii=False) + '\n')

    def consume(self, kind):
        limit = {'search': self.config.max_search_requests, 'model': self.config.max_model_calls}[kind]
        if self.data['usage'][kind] >= limit:
            raise LimitReached(kind)
        self.data['usage'][kind] += 1
        self.save()  # Count attempted requests, including failures, before execution.

    def reading(self, source_id):
        if source_id not in self.data['read_sources']:
            if len(self.data['read_sources']) >= self.config.max_read_sources:
                raise LimitReached('read_sources')
            self.data['read_sources'].append(source_id)
            self.save()
