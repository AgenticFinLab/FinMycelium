"""Versioned raw sources and stable paragraph/page locations."""
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
import ipaddress
import json
import re
import socket

from .state import digest, now, write_json
from .decoding import decode_source, shell_reason


class SourceIntegrityError(ValueError):
    """One saved source cannot be trusted; unrelated sources remain usable."""

    def __init__(self, source_id, message, *, version=None):
        self.source_id = source_id
        self.version = version
        super().__init__(message)


def quarantine_source(state, sid, exc):
    """Record the excluded version without deleting or reinterpreting evidence."""
    entry = state.data['sources'].get(sid)
    if entry is None:
        return
    record = dict(source_id=sid, version=getattr(exc, 'version', None) or entry.get('version'),
                  error_type=type(exc).__name__, reason=str(exc),
                  excluded_from_handoff=True)
    if entry.get('quarantine') != record:
        entry['quarantine'] = record
        state.trace(dict(action='source_quarantined', **record))
        state.save()


def canonical_url(url):
    p = urlsplit(url)
    if p.scheme not in {'http', 'https'} or not p.hostname or p.username or p.password:
        raise ValueError('Expected public HTTP(S) source URL')
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or '/', p.query, ''))


class ParagraphParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.current, self.hidden = [], [], 0

    def flush(self):
        text = ''.join(self.current).strip()
        if text:
            self.parts.append(text)
        self.current = []

    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style', 'noscript'}:
            self.hidden += 1
        if not self.hidden and tag in {'p', 'div', 'br', 'li', 'tr', 'h1', 'h2', 'h3', 'section'}:
            self.flush()

    def handle_endtag(self, tag):
        if tag in {'script', 'style', 'noscript'}:
            self.hidden = max(0, self.hidden - 1)
        if not self.hidden and tag in {'p', 'div', 'li', 'tr', 'h1', 'h2', 'h3', 'section'}:
            self.flush()

    def handle_data(self, text):
        if not self.hidden:
            self.current.append(text)


def _parse_document(raw, kind, encoding='utf-8'):
    if kind == 'pdf':
        try:
            from pypdf import PdfReader
        except ImportError:
            from PyPDF2 import PdfReader
        reader = PdfReader(BytesIO(raw))
        if reader.is_encrypted:
            raise ValueError('Encrypted PDF')
        return ([{'page': i + 1, 'paragraph': 1, 'text': page.extract_text() or ''}
                 for i, page in enumerate(reader.pages)], None, 'pdf_text_extraction')
    text, resolved, decision = decode_source(raw, kind, encoding)
    if kind == 'html':
        parser = ParagraphParser()
        parser.feed(text)
        parser.flush()
        blocks = parser.parts
    elif kind == 'txt':
        blocks = [x for x in text.split('\n\n') if x.strip()]
    else:
        raise ValueError('Unsupported source format')
    return [{'paragraph': i + 1, 'text': p} for i, p in enumerate(blocks)], resolved, decision


def parse_document(raw, kind, encoding='utf-8'):
    return _parse_document(raw, kind, encoding)[0]


def document_is_usable(document):
    return (document.get('status') in {'success', 'partial'}
            and any(row.get('text', '').strip() for row in document.get('blocks', []))
            and shell_reason(document.get('blocks', []), document.get('kind')) is None)


def _parsed_source(raw, kind, encoding, *, partial=False):
    blocks, resolved, decision = _parse_document(raw, kind, encoding)
    reason = shell_reason(blocks, kind)
    status = ('blocked' if reason else ('partial' if partial else 'success')
              if any(b['text'].strip() for b in blocks) else 'empty')
    result = dict(blocks=blocks, status=status, kind=kind,
                  parser_version='search-v2', encoding=resolved,
                  supplied_encoding=encoding, encoding_decision=decision)
    if reason:
        result['unusable_reason'] = reason
    return result


def fetch_public(url, config):
    """Bounded ordinary HTML/PDF download; redirects are validated individually."""
    if not config.allow_network:
        raise PermissionError('Network execution is disabled')
    import requests
    from urllib.parse import urljoin
    for _ in range(6):
        url = canonical_url(url)
        p = urlsplit(url)
        addresses = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == 'https' else 80))
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError('Non-public source address')
        with requests.get(url, timeout=config.timeout, stream=True, allow_redirects=False) as response:
            if response.is_redirect:
                url = urljoin(url, response.headers['Location'])
                continue
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > config.max_download_bytes:
                    raise ValueError('Document exceeds download limit')
                chunks.append(chunk)
            raw = b''.join(chunks)
            mime = response.headers.get('Content-Type', '').lower()
            kind = 'pdf' if raw.startswith(b'%PDF') else 'html' if 'html' in mime else 'txt' if 'text/plain' in mime else 'unsupported'
            # requests supplies Latin-1 for text/* with no explicit charset.
            # Preserve only an actual header declaration as an encoding hint.
            declared = re.search(r"charset\s*=\s*['\"]?([A-Za-z0-9._:-]+)", mime, re.I)
            return raw, kind, declared.group(1) if declared else None
    raise ValueError('Too many redirects')


class SourceStore:
    def __init__(self, state, fetcher=None):
        self.state = state
        self.fetcher = fetcher or (lambda url: fetch_public(url, state.config))

    def register(self, url, *, title='', discovery=None):
        url = canonical_url(url)
        sid = digest(url)[:24]
        entry = self.state.data['sources'].setdefault(sid, dict(
            source_id=sid, url=url, title=title, status='unread', discoveries=[], versions=[]))
        if discovery is not None:
            entry['discoveries'].append(discovery)
        self.state.save()
        return sid

    def import_file(self, path):
        path = Path(path).resolve()
        raw = path.read_bytes()
        if len(raw) > self.state.config.max_download_bytes:
            raise ValueError('File exceeds size limit')
        sid = digest(str(path))[:24]
        self.state.data['sources'].setdefault(sid, dict(source_id=sid, url=path.as_uri(),
            title=path.name, status='unread', discoveries=[], versions=[]))
        self.save_raw(sid, raw, {'.pdf': 'pdf', '.html': 'html', '.htm': 'html', '.txt': 'txt'}.get(path.suffix.lower(), 'unsupported'))
        return sid

    def save_raw(self, sid, raw, kind, encoding='utf-8', partial=False):
        entry = self.state.data['sources'][sid]
        version = digest(raw)
        folder = self.state.root / 'sources' / sid / version
        folder.mkdir(parents=True, exist_ok=True)
        raw_path, parsed_path = folder / 'raw', folder / 'parsed.json'
        if raw_path.exists() and raw_path.read_bytes() != raw:
            raise ValueError('Original source integrity mismatch')
        raw_path.write_bytes(raw)
        if parsed_path.exists():
            parsed = parsed_path.read_bytes()
            expected = entry.get('parsed_hashes', {}).get(version)
            if expected is not None and digest(parsed) != expected:
                raise ValueError('Parsed source integrity mismatch')
            document = json.loads(parsed)
        else:
            document = dict(version=version, retrieved_at=now())
            try:
                document.update(_parsed_source(raw, kind, encoding, partial=partial))
                entry.pop('error_type', None)
            except Exception as exc:
                document.update(blocks=[], status='parser_failed', kind=kind,
                                parser_version='search-v2', encoding=None,
                                supplied_encoding=encoding, encoding_decision='parse_failed')
                entry['error_type'] = type(exc).__name__
            write_json(parsed_path, document)
        if version not in entry['versions']:
            entry['versions'].append(version)
        entry.setdefault('parsed_hashes', {})[version] = digest((folder / 'parsed.json').read_bytes())
        entry.update(version=version, status=document['status'])
        self.state.save()
        return document

    def document(self, sid, version=None):
        try:
            entry = self.state.data['sources'][sid]
            version = version or entry.get('version')
            if version not in entry['versions']:
                raise ValueError('Unknown source version')
            folder = self.state.root / 'sources' / sid / version
            if digest((folder / 'raw').read_bytes()) != version:
                raise ValueError('Original source integrity mismatch')
            parsed = (folder / 'parsed.json').read_bytes()
            if digest(parsed) != entry['parsed_hashes'][version]:
                raise ValueError('Parsed source integrity mismatch')
            document = json.loads(parsed)
            if (not isinstance(document, dict) or document.get('version') != version
                    or not isinstance(document.get('blocks'), list)
                    or not isinstance(document.get('status'), str)
                    or not isinstance(document.get('kind'), str)
                    or any(not isinstance(block, dict) or not isinstance(block.get('text'), str)
                           for block in document['blocks'])):
                raise ValueError('Invalid saved source document')
            return document
        except (OSError, ValueError, KeyError, TypeError) as exc:
            # Keep direct access strict. The agent may quarantine this source and
            # continue; callers must never turn damaged bytes into valid text.
            message = (str(exc) if isinstance(exc, ValueError)
                       else 'Saved source could not be verified (' + type(exc).__name__ + ')')
            raise SourceIntegrityError(sid, message, version=version) from exc

    def read(self, sid, block=0, offset=0):
        if type(block) is not int or type(offset) is not int or block < 0 or offset < 0:
            raise ValueError('Invalid source location')
        entry = self.state.data['sources'][sid]
        self.state.reading(sid)
        if not entry.get('version'):
            try:
                raw, kind, encoding = self.fetcher(entry['url'])
                self.save_raw(sid, raw, kind, encoding)
            except Exception as exc:
                entry.update(status='fetch_failed', error_type=type(exc).__name__)
                self.state.save()
                return dict(source_id=sid, status='fetch_failed', error_type=type(exc).__name__)
        doc = self.document(sid)
        from .language_policy import assess
        language = assess(doc, self.state.config.source_languages)
        entry['language_assessment'] = language
        if not language['allowed']:
            entry['status'] = 'language_excluded'
            self.state.save()
            return dict(source_id=sid, status='language_excluded', language_assessment=language,
                        spans=[], next_location=None)
        blocks = doc['blocks']
        if block > len(blocks) or (block == len(blocks) and offset):
            raise ValueError('Unknown block')
        if blocks and (block == len(blocks) or
                       (block == len(blocks)-1 and offset == len(blocks[-1]['text']))):
            raise ValueError('End of saved text: choose an earlier location to reread, another source, or finish')
        requested_location = dict(block=block, offset=offset)
        remaining, spans = self.state.config.max_read_chars, []
        while block < len(blocks) and remaining:
            text = blocks[block]['text']
            if offset > len(text):
                raise ValueError('Offset exceeds block')
            end = min(len(text), offset + remaining)
            spans.append(dict(block=block, start=offset, end=end,
                              text=text[offset:end], locator={k:v for k,v in blocks[block].items() if k != 'text'}))
            remaining -= end - offset
            if end == len(text):
                block, offset = block + 1, 0
            else:
                offset = end
        result = dict(source_id=sid, version=doc['version'], status=doc['status'], spans=spans,
                      next_location=dict(block=block, offset=offset) if block < len(blocks) else None)
        ranges = entry.setdefault('read_ranges', [])
        for span in spans:
            record = dict(version=doc['version'], block=span['block'], start=span['start'], end=span['end'])
            if span['end'] > span['start'] and record not in ranges:
                ranges.append(record)
        entry['read_progress'] = dict(version=doc['version'], last_location=requested_location,
                                     next_location=result['next_location'],
                                     at_end_of_saved_text=result['next_location'] is None)
        result['at_end_of_saved_text'] = result['next_location'] is None
        self.state.save()
        return result


def repair_saved_sources(state):
    """Explicitly repair cached parsing from unchanged original bytes, offline.

    Call while owning this task's writer lock, normally on a copied resume run.
    Any changed interpretation invalidates the affected read ranges and active
    handoff. Old parses, range ledgers and handoffs remain archived for audit;
    the corrected body must be inspected before a new handoff can use it.
    Merely reading ``document()`` never rewrites historical evidence.
    """
    import copy
    import shutil
    import uuid

    store = SourceStore(state)
    changes = []
    for sid, entry in state.data['sources'].items():
        for version in entry.get('versions', []):
            try:
                old = store.document(sid, version)  # Verify raw and parsed hashes first.
            except SourceIntegrityError as exc:
                quarantine_source(state, sid, exc)
                continue
            if old.get('kind') not in {'html', 'txt'}:
                continue
            folder = state.root / 'sources' / sid / version
            try:
                parsed = _parsed_source((folder / 'raw').read_bytes(), old['kind'],
                                        old.get('supplied_encoding', old.get('encoding')),
                                        partial=old.get('status') == 'partial')
            except (ValueError, LookupError, UnicodeError):
                continue  # Do not replace a historical parse with a failed guess.
            if old.get('blocks') == parsed['blocks'] and old.get('status') == parsed['status']:
                continue
            new = {**old, **parsed, 'reparsed_at': now()}
            if 'unusable_reason' not in parsed:
                new.pop('unusable_reason', None)
            changes.append((sid, version, folder, old, new))
    if not changes:
        return []

    revision = state.run_dir / 'parse_repairs' / uuid.uuid4().hex
    revision.mkdir(parents=True)
    # Preserve the last valid interpretation before changing its references.
    write_json(revision / 'run.json', copy.deepcopy(state.data))
    handoff_files = ('complete_material.json', 'selection.json', 'builder_input.json',
                     'checkpoint.json', 'handoff_repair.json')
    for name in handoff_files:
        original = state.run_dir / name
        if original.exists():
            shutil.copy2(original, revision / name)
    changed_ids = []
    for sid, version, folder, old, new in changes:
        entry = state.data['sources'][sid]
        previous_hash = entry['parsed_hashes'][version]
        archive = folder / 'parsed_revisions' / (previous_hash + '.json')
        archive.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(folder / 'parsed.json', archive)
        old_ranges = [row for row in entry.get('read_ranges', []) if row['version'] == version]
        entry.setdefault('parse_history', []).append({
            'time': now(), 'version': version, 'previous_parsed_sha256': previous_hash,
            'previous_encoding': old.get('encoding'), 'encoding': new.get('encoding'),
            'previous_status': old.get('status'), 'status': new['status'],
            'read_ranges': old_ranges, 'handoff_archive': str(revision.relative_to(state.run_dir)),
            'reason': 'explicit_saved_source_reparse'})
        write_json(folder / 'parsed.json', new)
        entry['parsed_hashes'][version] = digest((folder / 'parsed.json').read_bytes())
        entry['read_ranges'] = [row for row in entry.get('read_ranges', []) if row['version'] != version]
        if entry.get('read_progress', {}).get('version') == version:
            entry.pop('read_progress', None)
        if entry.get('version') == version:
            entry['status'] = new['status']
            entry.pop('error_type', None)
        if sid not in changed_ids:
            changed_ids.append(sid)
    # No active complete manifest may silently refer to a changed interpretation.
    # Retain all historic handoffs; the archive above identifies their old parse.
    for name in handoff_files:
        (state.run_dir / name).unlink(missing_ok=True)
    state.data.pop('pending_finish_repair', None)
    state.data.pop('partial_finalization', None)
    state.data.pop('repeated_query_repair', None)
    state.data['invalid_actions'] = 0
    state.data.setdefault('parse_repairs', []).append({
        'time': now(), 'source_ids': changed_ids,
        'archive': str(revision.relative_to(state.run_dir))})
    state.data.update(status='ready', stop_reason='source_parsing_repaired',
                      feedback={'source_ids': changed_ids,
                                'hint': 'Saved original bytes were decoded again. Inspect these corrected bodies before selecting them.'})
    state.save()
    return changed_ids
