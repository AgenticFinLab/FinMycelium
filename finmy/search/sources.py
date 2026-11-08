"""Versioned raw sources and stable paragraph/page locations."""
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
import ipaddress
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


def parse_document(raw, kind, encoding='utf-8'):
    if kind == 'pdf':
        try:
            from pypdf import PdfReader
        except ImportError:
            from PyPDF2 import PdfReader
        reader = PdfReader(BytesIO(raw))
        if reader.is_encrypted:
            raise ValueError('Encrypted PDF')
        return [{'page': i + 1, 'paragraph': 1, 'text': page.extract_text() or ''}
                for i, page in enumerate(reader.pages)]
    text = raw.decode(encoding)
    if kind == 'html':
        parser = ParagraphParser()
        parser.feed(text)
        parser.flush()
        blocks = parser.parts
    elif kind == 'txt':
        blocks = [x for x in text.split('\n\n') if x.strip()]
    else:
        raise ValueError('Unsupported source format')
    return [{'paragraph': i + 1, 'text': p} for i, p in enumerate(blocks)]


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
            return raw, kind, response.encoding or 'utf-8'
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
        (folder / 'raw').write_bytes(raw)
        try:
            blocks = parse_document(raw, kind, encoding)
            status = ('partial' if partial else 'success') if any(b['text'].strip() for b in blocks) else 'empty'
        except Exception as exc:
            blocks, status = [], 'parser_failed'
            entry['error_type'] = type(exc).__name__
        document = dict(version=version, blocks=blocks, status=status, kind=kind,
                        retrieved_at=now(), parser_version='search-v1', encoding=encoding)
        if not (folder / 'parsed.json').exists():
            write_json(folder / 'parsed.json', document)
        if version not in entry['versions']:
            entry['versions'].append(version)
        entry.setdefault('parsed_hashes', {})[version] = digest((folder / 'parsed.json').read_bytes())
        entry.update(version=version, status=status)
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
