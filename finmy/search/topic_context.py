"""Source-local attribution cues; no case names or inferred factual claims."""
import re
from .topic import contains, linked, excluded


def enrich(document, items, plan):
    # Role aliases are local reading aids, never document-wide entity aliases.
    # Only the defining block and its immediate successor in the same section
    # may use them. Generic pronouns do not establish event relevance.
    definitions = {}
    for i, block in enumerate(document['blocks']):
        aliases = set()
        for entity in plan['entities']:
            pattern = re.escape(entity) + r'[^.;\n]{0,130}\(\s*(?:the\s+)?[“"\']([^”"\']{2,40})[”"\']\s*\)'
            aliases.update(re.findall(pattern, block['text'], re.I))
        if aliases:
            definitions[i] = aliases
    for i, w in enumerate(items):
        w['entity_context'] = False
        if excluded(w, plan):
            continue
        for block in (w['block'], w['block'] - 1):
            if block != w['block'] and document['blocks'][w['block']].get('heading_level') is not None:
                continue
            same_section = any(x['block'] == block and x['section'] == w['section'] for x in items)
            if same_section and any(contains(w['text'], alias) for alias in definitions.get(block, ())):
                w['entity_context'] = True
        # Explicit focal-person speech may remain a reading candidate next to
        # an entity anchor. Pronouns or generic completion words are insufficient.
        named = any(contains(w['text'], p) or re.search(
            r'^\s*' + re.escape(p.split()[-1]) + r'\s*:', w['text'], re.I)
            for p in plan.get('focal_people', []) if p.strip())
        adjacent = any(x['section'] == w['section'] and abs(x['block']-w['block']) <= 1
                       and any(contains(x['text'], e) for e in plan['entities'])
                       for x in items[max(0, i-1):i+2])
        w['entity_context'] |= named and adjacent


def protected(w, plan):
    if not linked(w, plan) or excluded(w, plan) or w['heading']:
        return False
    text = w['text']
    speaker = any(contains(text, p) for p in plan.get('focal_people', []))
    # A supplied full name can also appear as an unambiguous surname speech label.
    speaker |= any(re.search(r'^\s*'+re.escape(p.split()[-1])+r'\s*:', text, re.I)
                   for p in plan.get('focal_people', []) if len(p.split()) > 1)
    speaker |= any(re.search(r'\b(?:said|stated|explained|told)\s+[^.;:]{0,45}\b'
                             +re.escape(p.split()[-1])+r'\b', text, re.I)
                   for p in plan.get('focal_people', []) if len(p.split()) > 1)
    speech = bool(re.search(r'[“"].+[”"]|\b(?:said|stated|explained|told|decided|approved|declined)\b|表示|决定|批准|拒绝', text, re.I))
    return speaker and speech
