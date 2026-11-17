"""Short, extractive card labels; full record text stays in the expanded card."""
import re


def shorten(text, limit):
    text = re.sub(r'\s+', ' ', text or '').strip()
    if len(text) <= limit:
        return text
    head = text[:limit - 1]
    # Prefer a word boundary for spaced languages, without dropping CJK text.
    if ' ' in head and len(head.rsplit(' ', 1)[-1]) < 20:
        head = head.rsplit(' ', 1)[0]
    return head.rstrip(' ,;:') + '…'


def card_label(record, kind, fallback, actor=None):
    """Use explicit short labels first, then compact existing text, without inference."""
    for field in ('short_label', 'label', 'summary'):
        if isinstance(record.get(field), str) and record[field].strip():
            return shorten(record[field], 96)
    text = re.sub(r'\s+', ' ', fallback or '').strip()
    if kind == 'action' and actor:
        names = [actor.get('name', ''), *actor.get('aliases', [])]
        for name in sorted(filter(None, names), key=len, reverse=True):
            if text.casefold().startswith(name.casefold() + ' '):
                remainder = text[len(name):].strip()
                # Do not turn a joint action into a single-actor statement.
                if not re.match(r'(?:and|with|&|及|和)\b', remainder, re.I):
                    text = remainder[:1].upper() + remainder[1:]
                break
        return shorten(text, 90)
    if kind == 'context':
        # Remove only neutral source wrappers; keep qualifiers, negation and modality.
        text = re.sub(
            r'^(?:The (?:same )?(?:source|article|release|letter|report) '
            r'(?:states?|says?|reports?|notes?) (?:that )?)', '', text, flags=re.I)
        # One complete sentence when available. Decimal points are not boundaries.
        text = re.split(r'(?<=[.!?。！？])\s+(?=[A-Z“"\u4e00-\u9fff])', text, maxsplit=1)[0]
        return shorten(text[:1].upper() + text[1:], 104)
    return shorten(text, 82 if kind == 'source' else 100)
