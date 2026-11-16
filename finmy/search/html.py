"""Decode and extract public HTML without rewriting its text or fetching links."""
import codecs
import re
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup, NavigableString, Comment, UnicodeDammit
from bs4.dammit import EncodingDetector

PARSER_VERSION = 'search-html-v4'


def decode_html(raw, header_encoding=None):
    """Prefer BOM/valid UTF-8, then page declarations and explicit HTTP hints.

    Requests' implicit Latin-1 is not a declaration. GB2312/GBK labels commonly
    cover GB18030 text; retain the label and the actual decoder in the audit.
    """
    declared = EncodingDetector.find_declared_encoding(raw, is_html=True)
    candidates = []
    for marker, encoding in ((codecs.BOM_UTF32_LE, 'utf-32'), (codecs.BOM_UTF32_BE, 'utf-32'),
                             (codecs.BOM_UTF8, 'utf-8-sig'), (codecs.BOM_UTF16_LE, 'utf-16'),
                             (codecs.BOM_UTF16_BE, 'utf-16')):
        if raw.startswith(marker):
            candidates.append((encoding, 'bom'))
            break
    candidates += [('utf-8', 'valid_utf8'), (declared, 'html_declaration'),
                   (header_encoding, 'http_hint')]
    audit = dict(declared_encoding=declared, header_encoding=header_encoding)
    for label, reason in candidates:
        if not label:
            continue
        try:
            encoding = codecs.lookup(label).name
            if encoding in {'gb2312', 'gbk'}:
                encoding = 'gb18030'
            text = raw.decode(encoding)
        except (LookupError, UnicodeError):
            continue
        if '\x00' not in text and '\ufffd' not in text:
            return text, dict(audit, encoding=encoding, encoding_basis=reason)
    detected = UnicodeDammit(raw, is_html=True)
    text = detected.unicode_markup or ''
    return text, dict(audit, encoding=detected.original_encoding,
                      encoding_basis='detected', decoding_replacements=detected.contains_replacement_characters)


def _text(node):
    return ' '.join(node.get_text(' ', strip=True).split())


def _public_link(base, href):
    try:
        parsed = urlsplit(urljoin(base or '', href))
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
            return None
        return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or '/', parsed.query, ''))
    except ValueError:
        return None


def _metadata(soup, base):
    title = _text(soup.title) if soup.title else ''
    authors, publication, links = [], [], []
    for node in soup.find_all('meta'):
        key = str(node.get('property') or node.get('name') or node.get('itemprop') or '').lower()
        value = node.get('content')
        if not isinstance(value, str) or not value.strip():
            continue
        if key in {'og:title', 'twitter:title'} and not title:
            title = value.strip()
        if key in {'author', 'article:author', 'dc.creator', 'byl'} and value not in authors:
            authors.append(value[:300])
        # Only explicit publication fields; never infer a date from a URL,
        # financial period, copyright, retrieval time or dateModified.
        if key in {'article:published_time', 'datepublished', 'pubdate', 'publishdate', 'dc.date.issued'}:
            publication.append(dict(value=value[:100], field=key))
    for node in soup.select('time[itemprop="datePublished"]'):
        value = node.get('datetime') or _text(node)
        if value:
            publication.append(dict(value=value[:100], field='time.datePublished'))
    for node in soup.select('link[rel], a[rel]'):
        relation = 'canonical' if 'canonical' in node.get('rel', []) else 'next' if 'next' in node.get('rel', []) else None
        if relation:
            url = _public_link(base, node.get('href', ''))
            if url:
                links.append(dict(url=url, text=_text(node) or ('Declared ' + relation + ' URL'), relation=relation))
    return dict(title=title[:500], authors=authors, publication=publication, links=links)


def _clean(soup):
    # Keep headings/bylines and substantive sidebars; remove only clear chrome.
    for node in list(soup.find_all(['script', 'style', 'noscript', 'template', 'svg', 'iframe',
                                    'nav', 'button', 'input', 'select'])):
        node.decompose()
    for node in list(soup.find_all(True)):
        if node.attrs is None:
            continue
        labels = set(node.get('class', [])) | {node.get('id', ''), node.get('role', '')}
        hidden = node.has_attr('hidden') or str(node.get('aria-hidden', '')).lower() == 'true'
        hidden |= bool(re.search(r'(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*hidden)\b',
                                 node.get('style', ''), re.I))
        chrome = bool(labels & {'navigation', 'banner', 'contentinfo', 'advertisement', 'advert',
                                'ads', 'social-share', 'share-buttons', 'cookie-banner'})
        site_footer = node.name == 'footer' and not node.find_parent(['main', 'article'])
        if hidden or chrome or site_footer:
            node.decompose()
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()


def _blocks(root):
    """Keep visible order, inline wording and table cell boundaries.

    Locations name paragraphs/rows in this version's saved parse, not PDF-style
    coordinates or offsets in raw HTML. Raw bytes are stored separately.
    """
    blocks, current = [], []
    boundaries = {'p', 'div', 'section', 'article', 'main', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                  'li', 'blockquote', 'br', 'dl', 'dt', 'dd', 'pre', 'header', 'footer'}

    def append(text, **locator):
        text = re.sub(r'\s+', ' ', text).strip()
        if text:
            blocks.append(dict(paragraph=len(blocks)+1, text=text, **locator))

    def flush():
        append(''.join(current))
        current.clear()

    def visit(node):
        if isinstance(node, NavigableString):
            current.append(str(node))
            return
        if not getattr(node, 'name', None) or node.name in {'head', 'script', 'style'}:
            return
        if node.name == 'table':
            flush()
            table = len([b for b in blocks if b.get('table_start')]) + 1
            caption = node.find('caption')
            if caption:
                append(_text(caption), table=table, table_caption=True)
            rows = [r for r in node.find_all('tr') if r.find_parent('table') is node]
            for i, row in enumerate(rows):
                cells = row.find_all(['th', 'td'], recursive=False)
                if cells:
                    append(' | '.join(_text(c) for c in cells), table=table, row=i+1,
                           table_start=i == 0,
                           cells=[dict(column=j+1, header=c.name == 'th',
                                       rowspan=c.get('rowspan', '1'), colspan=c.get('colspan', '1'))
                                  for j, c in enumerate(cells)])
            return
        if node.name in boundaries:
            flush()
        for child in node.children:
            visit(child)
        if node.name in boundaries:
            flush()
    visit(root)
    flush()
    return blocks


def _plain(blocks):
    # Cell delimiters are presentation, not quoted text.
    return [b['text'].replace(' | ', '') if b.get('cells') else b['text'] for b in blocks]


def _ordered_originals(blocks, original):
    """Reject extractor inventions/reordering; a conservative DOM fallback remains."""
    original = ''.join(original.split())
    position = 0
    for text in _plain(blocks):
        needle = ''.join(text.split())
        found = original.find(needle, position)
        if found < 0:
            return False
        position = found + len(needle)
    return True


def extract_html(raw, encoding=None, *, url=''):
    text, decode = decode_html(raw, encoding)
    soup = BeautifulSoup(text, 'html.parser')
    metadata = _metadata(soup, url)
    scripted = bool(soup.find('script'))
    _clean(soup)
    visible = soup.body or soup
    heading = soup.find(['h1', 'h2'])
    labels = [metadata['title'], _text(heading) if heading else '']
    body_text = _text(visible)
    invalid = text.count('\ufffd') > max(2, len(text) // 100) or '\x00' in text
    status, reason = 'success', None
    denial = r'(?:403\s*)?(?:access denied|forbidden|request blocked|just a moment[.!…]*|robot check|security verification|访问受限|拒绝访问|安全验证|人机验证)'
    error = r'(?:404\s*)?(?:not found|page not found|404(?: error)?|页面不存在|页面未找到)|(?:50[0-9]\s*)?(?:internal server error|service unavailable|bad gateway)'
    if invalid:
        status, reason = 'garbled', 'Decoded text contains invalid/replacement characters'
    elif len(body_text) < 2000 and any(re.fullmatch(denial, s.strip(), re.I) for s in labels):
        status, reason = 'blocked', 'Page identifies an access challenge, not a source body'
    elif len(body_text) < 2000 and any(re.fullmatch(error, s.strip(), re.I) for s in labels):
        status, reason = 'error_page', 'Page identifies a missing resource or server error'
    elif len(body_text) < 400 and re.search(r'(enable|requires?|turn on).{0,25}javascript|javascript.{0,30}(disabled|required)|请.{0,15}开启.{0,10}javascript', body_text, re.I):
        status, reason = 'shell', 'Page requires client-side rendering; body not acquired'
    elif not body_text:
        status, reason = ('shell', 'Page has scripts but no visible source text') if scripted else ('empty', 'No visible source text')

    blocks, extractor, warnings = [], 'dom', []
    # <main> can contain the interview questions outside a nested <article>.
    scopes = [n for n in soup.find_all('main') if _text(n)]
    if not scopes:
        scopes = [n for n in soup.find_all('article') if _text(n)]
    roots = [n for n in scopes if not any(p is other for other in scopes for p in n.parents)]
    if status == 'success' and roots:
        extractor = 'semantic_dom'
        for root in roots:
            blocks.extend(_blocks(root))
    elif status == 'success':
        import trafilatura
        from lxml import etree
        # Pass Unicode, disable language filtering/comments and do not ask the
        # extractor to infer dates or fetch anything.
        result = trafilatura.bare_extraction('<html>' + str(visible) + '</html>', favor_recall=True,
                    include_tables=True, include_comments=False, include_links=True,
                    with_metadata=False)
        if result is not None:
            extracted = BeautifulSoup(etree.tostring(result.body, encoding='unicode'), 'html.parser')
            for tag in extracted.find_all(True):
                tag.name = {'head': 'h2', 'row': 'tr', 'cell': 'th' if tag.get('role') == 'head' else 'td',
                            'item': 'li', 'list': 'ul', 'quote': 'blockquote'}.get(tag.name, tag.name)
            blocks = _blocks(extracted.body or extracted)
            extractor = 'trafilatura-' + trafilatura.__version__
        if not blocks or not _ordered_originals(blocks, visible.get_text()):
            blocks, extractor = _blocks(visible), 'dom_fallback'
            warnings.append('Extractor did not yield ordered original text; retained visible DOM text')

    # Links are navigation leads, not proof of original authorship or independence.
    link_roots = roots or [visible]
    seen = {l['url'] for l in metadata['links']}
    for root in link_roots:
        for node in root.find_all('a', href=True):
            target = _public_link(url, node['href'])
            if target and target not in seen:
                seen.add(target)
                metadata['links'].append(dict(url=target, text=_text(node)[:200], relation='linked'))
    for i, block in enumerate(blocks):
        block['paragraph'] = i+1
    if status == 'success' and not blocks:
        status, reason = 'empty', 'No source body extracted'
    if not reason and decode['encoding_basis'] == 'detected':
        warnings.append('Encoding inferred from bytes; check quotations if ambiguous')
    return dict(blocks=blocks, status=status, metadata=metadata, **decode,
                parser_version=PARSER_VERSION, extractor=extractor,
                quality=dict(reason=reason, warnings=warnings))


def navigation_hints(metadata, *, limit=6):
    """Bounded observed leads; no crawling or presumed equivalent-source relation."""
    def priority(link):
        text = link.get('text', '').lower()
        return (link.get('relation') != 'canonical',
                not bool(re.search(r'\b(source|original|full|transcript|next|part)\b|原文|来源|全文|下一|续篇', text)),
                not urlsplit(link['url']).path.lower().endswith('.pdf'))
    links = sorted(metadata.get('links', []), key=priority)
    hints = dict(title=metadata.get('title', '')[:300], authors=metadata.get('authors', [])[:3],
                 observed_links=[])
    size = len(str(hints))
    for link in links:
        if len(hints['observed_links']) >= limit:
            break
        compact = dict(link, text=link.get('text', '')[:100])
        if size + len(str(compact)) > 1200:
            continue  # Keep the exact URL in saved metadata; never truncate it.
        hints['observed_links'].append(compact)
        size += len(str(compact))
    return {k:v for k,v in hints.items() if v}
