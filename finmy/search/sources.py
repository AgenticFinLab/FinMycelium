"""Versioned raw sources and stable paragraph/page locations."""
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import time
from urllib.parse import urlsplit, urlunsplit
import ipaddress
import json
import re
import socket

from .state import digest, now, write_json


def canonical_url(url):
    p = urlsplit(url)
    if p.scheme not in {'http', 'https'} or not p.hostname or p.username or p.password:
        raise ValueError('Expected public HTTP(S) source URL')
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or '/', p.query, ''))


class ParagraphParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.current, self.hidden = [], [], 0
        self.scopes = {'article': 0, 'main': 0}
        self.scoped_parts = {'article': [], 'main': []}

    def flush(self):
        text = ''.join(self.current).strip()
        if text:
            self.parts.append(text)
            for tag, depth in self.scopes.items():
                if depth:
                    self.scoped_parts[tag].append(text)
        self.current = []

    def handle_starttag(self, tag, attrs):
        if tag in self.scopes:
            self.flush()
            self.scopes[tag] += 1
        if tag in {'script', 'style', 'noscript'}:
            self.hidden += 1
        if not self.hidden and tag in {'p', 'div', 'br', 'li', 'tr', 'h1', 'h2', 'h3', 'section'}:
            self.flush()

    def handle_endtag(self, tag):
        if tag in self.scopes:
            self.flush()
            self.scopes[tag] = max(0, self.scopes[tag] - 1)
        if tag in {'script', 'style', 'noscript'}:
            self.hidden = max(0, self.hidden - 1)
        if not self.hidden and tag in {'p', 'div', 'li', 'tr', 'h1', 'h2', 'h3', 'section'}:
            self.flush()

    def handle_data(self, text):
        if not self.hidden:
            self.current.append(text)


def pdf_blocks(text, page, max_chars=1600):
    """Located slices of extracted page text, not claimed PDF layout paragraphs.

    Prefer blank lines and sentence-ending line breaks. For long uninterrupted
    passages use sentence/line boundaries; never split a word or table row merely
    to meet the soft size target. Offsets preserve every extracted character.
    """
    boundaries = {0, len(text)}
    boundaries.update(m.end() for m in re.finditer(r'\n[ \t]*\n|[.!?。！？][\"”’)]?[ \t]*\n', text))
    blocks = []
    points = sorted(boundaries)
    for start, end in zip(points, points[1:]):
        while end - start > max_chars:
            passage = text[start:end]
            # Prefer complete extracted lines, including rows with dotted leaders.
            pattern = r'\n' if '\n' in passage else r'[.!?。！？][\"”’)]?\s+'
            candidates = [start + m.end() for m in re.finditer(pattern, passage)]
            before = [p for p in candidates if p <= start + max_chars]
            cut = max(before) if before else next(iter(candidates), end)
            if cut == end:
                break
            blocks.append(dict(page=page, paragraph=len(blocks)+1,
                               start=start, end=cut, text=text[start:cut]))
            start = cut
        blocks.append(dict(page=page, paragraph=len(blocks)+1,
                           start=start, end=end, text=text[start:end]))
    return blocks or [dict(page=page, paragraph=1, start=0, end=0, text='')]


def parse_document(raw, kind, encoding='utf-8'):
    if kind == 'pdf':
        try:
            from pypdf import PdfReader
        except ImportError:
            from PyPDF2 import PdfReader
        reader = PdfReader(BytesIO(raw))
        if reader.is_encrypted:
            raise ValueError('Encrypted PDF')
        return [block for i, page in enumerate(reader.pages)
                for block in pdf_blocks(page.extract_text() or '', i + 1)]
    text = raw.decode(encoding)
    if kind == 'html':
        parser = ParagraphParser()
        parser.feed(text)
        parser.flush()
        # Keep introductions/questions alongside a nested article inside <main>.
        blocks = parser.scoped_parts['main'] or parser.scoped_parts['article'] or parser.parts
    elif kind == 'txt':
        blocks = [x for x in text.split('\n\n') if x.strip()]
    else:
        raise ValueError('Unsupported source format')
    return [{'paragraph': i + 1, 'text': p} for i, p in enumerate(blocks)]


def fetch_public(url, config, *, timeout=None):
    """Bounded ordinary HTML/PDF download; redirects are validated individually."""
    if not config.allow_network:
        raise PermissionError('Network execution is disabled')
    import requests
    from urllib.parse import urljoin
    deadline = time.monotonic() + timeout if timeout is not None else None
    for _ in range(6):
        url = canonical_url(url)
        p = urlsplit(url)
        addresses = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == 'https' else 80))
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError('Non-public source address')
        remaining = config.timeout if deadline is None else deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Document download deadline exceeded')
        with requests.get(url, timeout=min(config.timeout, remaining), stream=True, allow_redirects=False) as response:
            if response.is_redirect:
                url = urljoin(url, response.headers['Location'])
                continue
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                if deadline is not None and time.monotonic() >= deadline:
                    raise TimeoutError('Document download deadline exceeded')
                size += len(chunk)
                if size > config.max_download_bytes:
                    raise ValueError('Document exceeds download limit')
                chunks.append(chunk)
            raw = b''.join(chunks)
            mime = response.headers.get('Content-Type', '').lower()
            kind = 'pdf' if raw.startswith(b'%PDF') else 'html' if 'html' in mime else 'txt' if 'text/plain' in mime else 'unsupported'
            return raw, kind, response.encoding or 'utf-8'
    raise ValueError('Too many redirects')


def extends_saved_body(previous, candidate):
    """Require recognizable original text and additional body, not a longer error page.

    This is an acquisition guard, not a semantic completeness verdict.
    """
    def normalized(text):
        return ' '.join(re.findall(r'\w+', text.casefold()))
    old = normalized(' '.join(b['text'] for b in previous))
    new = normalized(' '.join(b['text'] for b in candidate))
    if len(new) < len(old) + max(100, len(old) // 10):
        return False
    # Skip short headings: a shared title alone does not establish body continuity.
    anchors = [normalized(b['text'])[:160] for b in previous
               if len(normalized(b['text'])) >= 160]
    if not anchors:
        return len(old) >= 40 and old in new
    return sum(anchor in new for anchor in anchors) >= (len(anchors) + 1) // 2


def fetch_failure(exc):
    """Safe acquisition diagnostics, without exception strings or response bodies."""
    response = getattr(exc, 'response', None)
    code = getattr(response, 'status_code', None)
    code = code if isinstance(code, int) else None
    if code in {401, 403, 451} or isinstance(exc, PermissionError):
        category, retryable = 'access_denied', False
    elif code in {404, 410}:
        category, retryable = 'not_found', False
    elif code == 429:
        category, retryable = 'rate_limited', True
    elif code == 408 or (code is not None and code >= 500):
        category, retryable = 'server_error', True
    elif code is None and (isinstance(exc, OSError) or type(exc).__name__ in {'Timeout', 'ReadTimeout', 'ConnectTimeout', 'ConnectionError'}):
        category, retryable = 'network_error', True
    else:
        category, retryable = 'request_error', False
    retry_after = 30 if code == 429 else 0
    value = (getattr(response, 'headers', {}) or {}).get('Retry-After', '')
    if value:
        try:
            retry_after = max(0, int(value))
        except (ValueError, TypeError):
            try:
                deadline = parsedate_to_datetime(value)
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=timezone.utc)
                retry_after = max(0, int((deadline-datetime.now(timezone.utc)).total_seconds()))
            except (ValueError, TypeError, OverflowError):
                pass
    return dict(error_type=type(exc).__name__, http_status=code, category=category,
                retryable=retryable, retry_after_seconds=retry_after,
                hint='Trace an accessible original by its title, author, quote or an observed link. '
                     'A failed fetch does not establish irrelevance; snippets are not source bodies.')


class SourceStore:
    def __init__(self, state, fetcher=None):
        self.state = state
        self.fetcher = fetcher or (lambda url: fetch_public(url, state.config))
        self.partial_fetcher = fetcher or (lambda url: fetch_public(url, state.config, timeout=min(20, state.config.timeout)))
        self.can_complete_partial = fetcher is not None or state.config.allow_network

    def register(self, url, *, title='', discovery=None):
        url = canonical_url(url)
        sid = digest(url)[:24]
        entry = self.state.data['sources'].setdefault(sid, dict(
            source_id=sid, url=url, title=title, status='unread', discoveries=[], versions=[]))
        if not entry.get('title') and title:
            entry['title'] = title
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
        if version in entry['versions']:
            # Reusing raw bytes must also reuse their saved parser and locations.
            document = self.document(sid, version)
            entry.update(version=version, status=document['status'])
            self.state.save()
            return document
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'raw').write_bytes(raw)
        try:
            blocks = parse_document(raw, kind, encoding)
            status = ('partial' if partial else 'success') if any(b['text'].strip() for b in blocks) else 'empty'
        except Exception as exc:
            blocks, status = [], 'parser_failed'
            entry['error_type'] = type(exc).__name__
        document = dict(version=version, blocks=blocks, status=status, kind=kind,
                        retrieved_at=now(), parser_version='search-v3', encoding=encoding)
        if not (folder / 'parsed.json').exists():
            write_json(folder / 'parsed.json', document)
        else:
            document = json.loads((folder / 'parsed.json').read_text())
        if version not in entry['versions']:
            entry['versions'].append(version)
        entry.setdefault('parsed_hashes', {})[version] = digest((folder / 'parsed.json').read_bytes())
        entry.update(version=version, status=document['status'])
        self.state.save()
        return document

    def document(self, sid, version=None):
        import json
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
        return json.loads(parsed)

    def complete_partial(self, sid):
        """Try the original URL once before its partial body is first inspected.

        Keep cached originals on failure; never rebase already-read locations or
        priority annotations onto a different document version.
        """
        entry = self.state.data['sources'][sid]
        version = entry.get('version')
        if (not self.can_complete_partial or entry.get('status') != 'partial'
                or not version or urlsplit(entry['url']).scheme not in {'http', 'https'}
                or any(r['version'] == version and r['end'] > r['start'] for r in entry.get('read_ranges', []))
                or version in entry.get('acquisition_attempts', {})):
            return
        old = self.document(sid, version)
        attempt = dict(status='started', previous_version=version, started_at=now())
        entry.setdefault('acquisition_attempts', {})[version] = attempt
        self.state.save()
        self.state.trace(dict(action='source_acquisition_started', source=sid, **attempt))
        started = time.monotonic()
        try:
            raw, kind, encoding = self.partial_fetcher(entry['url'])
            if len(raw) > self.state.config.max_download_bytes:
                raise ValueError('Document exceeds download limit')
            blocks = parse_document(raw, kind, encoding)
            if extends_saved_body(old['blocks'], blocks):
                document = self.save_raw(sid, raw, kind, encoding)
                attempt.update(status='expanded', version=document['version'],
                               saved_chars=sum(len(b['text']) for b in document['blocks']))
            else:
                attempt.update(status='kept_cached', reason='No recognizable body expansion')
        except Exception as exc:
            attempt.update(status='kept_cached', **fetch_failure(exc))
        attempt['duration_seconds'] = round(time.monotonic() - started, 3)
        self.state.save()
        self.state.trace(dict(action='source_acquisition_result', source=sid, **attempt))

    def read(self, sid, block=0, offset=0, *, query=None):
        if type(block) is not int or type(offset) is not int or block < 0 or offset < 0:
            raise ValueError('Invalid source location')
        if query is not None and (not isinstance(query, str) or not query.strip()):
            raise ValueError('Reading query must be nonempty text')
        if query is not None and (block or offset):
            raise ValueError('Choose a reading query or an explicit location, not both')
        entry = self.state.data['sources'][sid]
        self.state.reading(sid)
        if not entry.get('version'):
            attempts = entry.setdefault('fetch_attempts', [])
            if attempts:
                last = attempts[-1]
                error = last.get('error', dict(retryable=True, category='interrupted'))
                elapsed = (datetime.now(timezone.utc)-datetime.fromisoformat(last['time'])).total_seconds()
                wait = max(0, error.get('retry_after_seconds', 0)-elapsed)
                if not error.get('retryable', False) or len(attempts) >= 2 or wait > 0:
                    return dict(source_id=sid, status='fetch_failed', error_type=entry.get('error_type'),
                                fetch_error=error, retry_skipped=True, retry_in_seconds=round(wait, 1),
                                attempts=len(attempts))
            attempt = dict(time=now(), status='started')
            attempts.append(attempt)
            self.state.save()
            try:
                raw, kind, encoding = self.fetcher(entry['url'])
                self.save_raw(sid, raw, kind, encoding)
                attempt['status'] = entry['status']
                entry.pop('fetch_error', None)
                self.state.save()
            except Exception as exc:
                error = fetch_failure(exc)
                attempt.update(status='fetch_failed', error=error)
                entry.update(status='fetch_failed', error_type=type(exc).__name__, fetch_error=error)
                self.state.save()
                return dict(source_id=sid, status='fetch_failed', error_type=type(exc).__name__,
                            fetch_error=error, attempts=len(attempts))
        # An explicit nonzero cursor belongs to the existing saved version.
        if not block and not offset:
            self.complete_partial(sid)
        doc = self.document(sid)
        blocks = doc['blocks']
        if query is not None:
            from .reading import targeted_spans, read_coverage
            spans, reading = targeted_spans(doc, query, self.state.config.max_read_chars,
                                            entry.get('read_ranges', []))
            ranges = entry.setdefault('read_ranges', [])
            for span in spans:
                record = dict(version=doc['version'], **{k:span[k] for k in ('block','start','end')})
                if record not in ranges:
                    ranges.append(record)
            saved_chars, read_chars = read_coverage(doc, ranges)
            at_end = bool(saved_chars) and read_chars == saved_chars
            previous = entry.get('read_progress', {})
            if ('preview_location' not in reading and previous.get('version') == doc['version']
                    and previous.get('preview_location')):
                reading['preview_location'] = previous['preview_location']
            # Query windows can be disjoint; they do not have a sequential next cursor.
            entry['read_progress'] = dict(version=doc['version'], next_location=None,
                                          at_end_of_saved_text=at_end, **reading)
            self.state.save()
            for span in spans:
                span['read_location'] = dict(block=span['block'],offset=span['start'])
            return dict(source_id=sid, version=doc['version'], status=doc['status'], spans=spans,
                        next_location=None, at_end_of_saved_text=at_end, reading=reading)
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
        for span in spans:
            span['read_location'] = dict(block=span['block'],offset=span['start'])
        self.state.save()
        return result
