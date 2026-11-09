"""Decode saved source bytes without trusting HTTP's historical Latin-1 default."""
import codecs
import re


_CHARSET = re.compile(br"charset\s*=\s*['\"]?\s*([A-Za-z0-9._:-]+)", re.I)
_XML_ENCODING = re.compile(br"^\s*<\?xml\b[^>]*\bencoding\s*=\s*['\"]([^'\"]+)", re.I)
_META_ATTRIBUTE = re.compile(br'''([^\s=/>]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))''')


def _codec(name):
    if not isinstance(name, str) or not name.strip():
        return None
    try:
        info = codecs.lookup(name.strip())
    except LookupError:
        return None
    if not getattr(info, '_is_text_encoding', True):
        return None
    resolved = info.name
    # GB18030 is backward compatible with the usual GBK/GB2312 declarations.
    return 'gb18030' if resolved in {'gb2312', 'gbk'} else resolved


def declared_encoding(raw, kind):
    """Read real document declarations, not charset strings in scripts/footer."""
    prefix = raw[:65536]
    xml = _XML_ENCODING.search(prefix)
    if xml:
        value = _codec(xml.group(1).decode('ascii', errors='replace'))
        if value:
            return value, 'xml_declaration'
    if kind == 'html':
        head = re.split(br'</head\s*>', prefix, maxsplit=1, flags=re.I)[0]
        head = re.sub(br'<!--.*?-->|<script\b[^>]*>.*?</script\s*>|<style\b[^>]*>.*?</style\s*>',
                      b'', head, flags=re.I | re.S)
        for tag in re.finditer(br'<meta\b[^>]*>', head, re.I):
            attrs = {m.group(1).lower(): next(value for value in m.groups()[1:] if value is not None)
                     for m in _META_ATTRIBUTE.finditer(tag.group())}
            charset = attrs.get(b'charset')
            if charset is None and attrs.get(b'http-equiv', b'').lower() == b'content-type':
                match = _CHARSET.search(attrs.get(b'content', b''))
                charset = match.group(1) if match else None
            if charset:
                value = _codec(charset.decode('ascii', errors='replace'))
                if value:
                    return value, 'html_meta'
    return None, None


def decode_source(raw, kind, encoding=None):
    """Return text, actual codec and decision; every decoding attempt is strict.

    A BOM is definitive. Document declarations override HTTP hints, since common
    HTTP clients synthesize ISO-8859-1 for text without an explicit charset.
    Valid UTF-8 takes precedence over that weak Latin-1 hint; genuine Latin-1
    still decodes as Latin-1 when UTF-8 is invalid. No replacement/ignore pass
    can manufacture a successful original body.
    """
    for marker, codec in ((codecs.BOM_UTF32_LE, 'utf-32'),
                          (codecs.BOM_UTF32_BE, 'utf-32'),
                          (codecs.BOM_UTF8, 'utf-8-sig'),
                          (codecs.BOM_UTF16_LE, 'utf-16'),
                          (codecs.BOM_UTF16_BE, 'utf-16')):
        if raw.startswith(marker):
            return raw.decode(codec), codec, 'byte_order_mark'
    declared, why = declared_encoding(raw, kind)
    hinted = _codec(encoding)
    candidates = []
    if declared:
        candidates.append((declared, why))
    if hinted and hinted not in {'iso8859-1', 'ascii'}:
        candidates.append((hinted, 'supplied_charset'))
    candidates.append(('utf-8', 'utf8_validation'))
    if hinted:
        candidates.append((hinted, 'supplied_charset'))
    candidates.append(('gb18030', 'gb18030_fallback'))
    tried, last = set(), None
    for codec, reason in candidates:
        if codec in tried:
            continue
        tried.add(codec)
        try:
            return raw.decode(codec), codec, reason
        except (UnicodeError, LookupError) as exc:
            last = exc
    raise last or ValueError('No supported source encoding')


def shell_reason(blocks, kind):
    """Recognize explicit access challenges and empty catalog templates only.

    This is a body-availability check, not a relevance or minimum-length filter.
    An ordinary article mentioning login/CAPTCHA is not rejected.
    """
    if kind != 'html':
        return None
    text = '\n'.join(row.get('text', '') for row in blocks).strip()
    first = text.split('\n', 1)[0].strip().casefold()
    if first == 'client challenge' and 'required part of this site' in text.casefold():
        return 'client_challenge'
    if first in {'just a moment...', 'just a moment', 'checking your browser',
                 'verify you are human', 'robot check'}:
        return 'access_challenge'
    if first == '环境异常' and '完成验证后即可继续访问' in text:
        return 'access_challenge'
    # Exact login forms only: an article with a login banner and real body does
    # not match this small vocabulary and remains available to the agent.
    lines = [line.strip().casefold() for line in text.splitlines() if line.strip()]
    login_labels = {'sign in', 'log in', 'login', 'sign in to continue',
                    'log in to continue', 'email', 'email address', 'username',
                    'password', 'remember me', 'forgot password?',
                    'forgot your password?', 'create account', 'create an account',
                    '登录', '请先登录', '登录后继续', '邮箱', '用户名', '密码',
                    '记住我', '忘记密码', '注册'}
    if (first in {'sign in', 'log in', 'login', 'sign in to continue',
                  'log in to continue', '登录', '请先登录', '登录后继续'}
            and set(lines) <= login_labels):
        return 'login_form'
    compact = re.sub(r'\s+', '', text)
    if ('您现在的位置：首页文献详细' in compact
            and '添加成功！前往申请单查看' in compact
            and '二级参考文献（0）参考文献（0）' in compact
            and not any(label in text for label in ('摘要：', '摘要:', '作者：', '作者:', 'Abstract:', 'Author:'))):
        return 'empty_catalog_template'
    return None
