"""Derive material confirmation from saved builds, without changing search runs."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from finmy.search.state import digest


def confirmations(builds):
    records = []
    for row in builds:
        body = row['body']
        body = json.loads(body) if isinstance(body, str) else body
        if not (body.get('input_confirmation') or body.get('evidence_review', {}).get('decision') == 'approved'):
            continue
        collection = body.get('search_collection', {})
        manifest = json.loads(collection['files']['manifest.json']) if collection.get('files') else {}
        handoffs = manifest.get('search_handoffs') or [body.get('provenance', {})]
        for handoff in handoffs:
            if all(handoff.get(k) for k in ('search_task_id', 'handoff_revision', 'search_input_sha256')):
                records.append({k: handoff[k] for k in ('search_task_id', 'handoff_revision', 'search_input_sha256')}
                               | {'build_task_id': row['id']})
    return records


def saved_confirmations(workspace):
    database = Path(workspace)/'workbench.sqlite3'
    if not database.is_file():
        return []
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='build_tasks' AND type='table'").fetchone():
            return []
        return confirmations(db.execute('SELECT id,body FROM build_tasks'))


def matching_builds(task_id, revision, input_hash, records):
    if not revision or not input_hash:
        return []
    return sorted({r['build_task_id'] for r in records if r['search_task_id'] == task_id
                   and r['handoff_revision'] == revision and r['search_input_sha256'] == input_hash})


def confirmed_builds(task_id, data, records):
    payload = data.get('builder_input')
    return matching_builds(task_id, data.get('handoff_revision'), digest(payload) if payload else None, records)


def disposition(data, builds):
    if data.get('build_disposition') == 'excluded':
        return 'excluded'
    return 'confirmed' if builds else 'pending'
