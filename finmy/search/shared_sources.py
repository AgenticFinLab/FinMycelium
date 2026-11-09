"""Phase-local originals: reuse never transfers another event's source review."""
from __future__ import annotations

import copy
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
import re
import shutil
import tempfile
from threading import RLock

from .state import SearchState, digest, write_json


class SharedSourcePool:
    def __init__(self, phase_root, subject_scope):
        self.phase_root = Path(phase_root)
        self.root = self.phase_root / 'shared_sources'
        self.scope = copy.deepcopy(subject_scope)
        self.lock = RLock()
        self.errors = []
        self.root.mkdir(parents=True, exist_ok=True)
        identity = {'version': 'shared-originals-v1', 'subject_scope': self.scope}
        path = self.root / 'scope.json'
        with self._guard():
            if path.exists():
                if json.loads(path.read_text(encoding='utf-8')) != identity:
                    raise ValueError('Shared originals belong to a different subject scope')
            else:
                write_json(path, identity)

    @contextmanager
    def _guard(self):
        # Workers share one instance, while the file lock also protects explicit
        # cache hydration from a separate instance/process. No mutable index is
        # required: every published record is a validated immutable snapshot.
        with self.lock, (self.root / '.pool.lock').open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def _check_scope(self, state):
        if (state.root.parent.resolve() != self.phase_root.resolve()
                or state.data['task'].get('subject_scope') != self.scope):
            raise ValueError('Shared originals cannot cross subject or phase boundaries')

    @staticmethod
    def _usable(document):
        from .sources import document_is_usable
        return document_is_usable(document)

    def publish(self, state):
        self._check_scope(state)
        with self._guard():
            from .handoff import source_selection_status
            for sid, entry in state.data['sources'].items():
                try:
                    self._publish_entry(state, sid, entry, source_selection_status)
                except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
                    self._failure('publish_source', sid, error)

    def _publish_entry(self, state, sid, entry, source_selection_status):
        if not isinstance(entry, dict):
            raise ValueError('Invalid shared source entry')
        version = entry.get('version')
        if not version or not any(r['version'] == version and r['end'] > r['start']
                                  for r in entry.get('read_ranges', [])):
            return
        if source_selection_status(state, sid, version) is not None:
            return
        parsed_hash = entry['parsed_hashes'][version]
        key = digest([state.root.name, sid, version, parsed_hash])
        target = self.root / key
        if target.exists():
            return
        source = state.root / 'sources' / sid / version
        temporary = Path(tempfile.mkdtemp(prefix='.publish-', dir=self.root))
        try:
            shutil.copyfile(source / 'raw', temporary / 'raw')
            shutil.copyfile(source / 'parsed.json', temporary / 'parsed.json')
            metadata = {key: copy.deepcopy(entry[key]) for key in
                        ('source_id', 'url', 'title', 'discoveries', 'published_at') if key in entry}
            record = {
                'source': metadata, 'source_id': sid, 'version': version,
                'parsed_hash': parsed_hash, 'origin_task': state.root.name,
                'origin_event_id': state.data['task'].get('event_id'),
                'subject_scope': self.scope,
            }
            write_json(temporary / 'record.json', {**record, 'record_sha256': digest(record)})
            temporary.rename(target)
        except (OSError, ValueError, KeyError, TypeError) as error:
            self._failure('publish_source', sid, error)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    def _failure(self, stage, identifier, error):
        # A bad immutable snapshot is excluded, never repaired or silently trusted.
        with self.lock:
            row = {'stage': stage, 'identifier': identifier, 'error_type': type(error).__name__}
            if row not in self.errors:
                self.errors.append(row)
                write_json(self.root / 'errors.json', self.errors)

    def hydrate(self, task_ids):
        """Publish inspected originals from prior attempts, including insufficient ones."""
        for task_id in task_ids:
            if (self.phase_root / task_id / 'runs/initial/run.json').exists():
                try:
                    state = SearchState(self.phase_root, task_id)
                except (OSError, ValueError, KeyError, TypeError) as error:
                    self._failure('hydrate_task', task_id, error)
                    continue
                self._check_scope(state)
                self.publish(state)

    def _records(self):
        for path in sorted(self.root.glob('*/record.json')):
            if path.parent.name.startswith('.'):
                continue
            try:
                row = self._record(path)
            except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
                self._failure('shared_snapshot', path.parent.name, error)
                continue
            if row is not None:
                yield row

    def _record(self, path):
        row = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(row, dict) or not isinstance(row.get('source'), dict):
            raise ValueError('Invalid shared original record')
        if digest({key: value for key, value in row.items() if key != 'record_sha256'}) != row.get('record_sha256'):
            raise ValueError('Shared original metadata integrity mismatch')
        sid, version, parsed_hash = row['source_id'], row['version'], row['parsed_hash']
        if (not re.fullmatch(r'[0-9a-f]{24}', sid)
                or not re.fullmatch(r'[0-9a-f]{64}', version)
                or not re.fullmatch(r'[0-9a-f]{64}', parsed_hash)
                or not re.fullmatch(r'[A-Za-z0-9_-]+', row['origin_task'])
                or row.get('subject_scope') != self.scope):
            raise ValueError('Invalid shared original identity')
        # A parser repair invalidates older snapshots; never reintroduce its
        # old mojibake or stale paragraph locations.
        origin_path = self.phase_root / row['origin_task'] / 'runs/initial/run.json'
        origin = json.loads(origin_path.read_text(encoding='utf-8'))
        if (not isinstance(origin, dict) or not isinstance(origin.get('sources'), dict)
                or not isinstance(origin.get('task'), dict)):
            raise ValueError('Invalid shared original source task')
        original_entry = origin['sources'].get(sid, {})
        if not isinstance(original_entry, dict):
            raise ValueError('Invalid shared original source metadata')
        if (origin['task'].get('subject_scope') != self.scope
                or original_entry.get('url') != row['source'].get('url')
                or row['source'].get('source_id') != sid):
            raise ValueError('Shared original provenance differs from its source task')
        if original_entry.get('parsed_hashes', {}).get(version) != parsed_hash:
            return None
        raw = (path.parent / 'raw').read_bytes()
        parsed = (path.parent / 'parsed.json').read_bytes()
        if digest(raw) != version or digest(parsed) != parsed_hash:
            raise ValueError('Shared original integrity mismatch')
        document = json.loads(parsed)
        if (not isinstance(document, dict) or not isinstance(document.get('blocks'), list)
                or any(not isinstance(block, dict) or not isinstance(block.get('text'), str)
                       for block in document['blocks'])):
            raise ValueError('Invalid shared original document')
        if not self._usable(document):
            return None
        return row, raw, parsed, document

    def has_sources(self):
        with self._guard():
            return next(self._records(), None) is not None

    def refresh(self, state):
        """Expose saved bodies as leads, without inheriting review or event membership."""
        self._check_scope(state)
        self.publish(state)
        imported = []
        with self._guard():
            for row, raw, parsed, document in self._records():
                if row['origin_task'] == state.root.name:
                    continue
                sid, version = row['source_id'], row['version']
                previous = state.data['sources'].get(sid)
                if previous and previous.get('version'):
                    continue  # Keep this event's pinned version and review.
                entry = previous if previous is not None else copy.deepcopy(row['source'])
                entry.setdefault('discoveries', [])
                for discovery in row['source'].get('discoveries', []):
                    if discovery not in entry['discoveries']:
                        entry['discoveries'].append(copy.deepcopy(discovery))
                if not entry.get('title'):
                    entry['title'] = row['source'].get('title', '')
                reuse = {'provider': 'shared_original', 'origin_task': row['origin_task'],
                         'origin_event_id': row['origin_event_id'], 'version': version,
                         'parsed_hash': row['parsed_hash'],
                         'title': row['source'].get('title', ''),
                         'summary': '\n\n'.join(b['text'] for b in document['blocks'])[:700]}
                entry['discoveries'].append(reuse)
                entry.setdefault('reused_from', []).append({key: value for key, value in reuse.items()
                                                          if key not in {'summary', 'provider'}})
                if version not in entry.setdefault('versions', []):
                    entry['versions'].append(version)
                entry.setdefault('parsed_hashes', {})[version] = row['parsed_hash']
                entry.update(source_id=sid, version=version, status=document['status'])
                entry.pop('error_type', None)
                folder = state.root / 'sources' / sid / version
                folder.mkdir(parents=True, exist_ok=True)
                (folder / 'raw').write_bytes(raw)
                (folder / 'parsed.json').write_bytes(parsed)
                state.data['sources'][sid] = entry
                imported.append(sid)
            if imported:
                state.save()
                state.trace({'action': 'shared_sources_imported', 'source_ids': imported,
                             'review_inherited': False})
        return imported
