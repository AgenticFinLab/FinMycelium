"""Marginal evidence selection over validated original spans, without extra calls."""
import re
from .state import digest

ROLES = {'terms', 'personal', 'condition', 'outcome', 'corroboration', 'contradiction', 'context'}


def annotation(item):
    """Optional model judgments; never substitute these fields for original text."""
    result = {}
    if 'fact_ids' in item:
        value = item['fact_ids']
        if (not isinstance(value, list) or not value or len(value) > 32
                or any(not isinstance(x, str) or not x.strip() or len(x) > 120 for x in value)):
            raise ValueError('fact_ids needs 1..32 short nonempty coverage keys')
        result['fact_ids'] = sorted(set(value))
    for key in ('claim_id', 'independence_key'):
        if key in item:
            if not isinstance(item[key], str) or not item[key].strip() or len(item[key]) > 180:
                raise ValueError(key + ' must be a short nonempty semantic key')
            result[key] = item[key]
    if 'evidence_role' in item:
        if item['evidence_role'] not in ROLES:
            raise ValueError('Unknown evidence_role')
        result['evidence_role'] = item['evidence_role']
    return result


def normalized(text):
    return ' '.join(text.split())


def overlap(text, originals):
    """Copied wording lowers candidate priority; it does not prove equivalence."""
    from difflib import SequenceMatcher
    words = re.findall(r'\w+', text.casefold())
    if not words:
        return 0
    return max((max(m.size for m in SequenceMatcher(None, words,
                re.findall(r'\w+', old.casefold()), autojunk=False).get_matching_blocks()) / len(words)
                for old in originals), default=0)


def features(mark, text):
    facts = set(mark.get('fact_ids', []))
    role = mark.get('evidence_role', 'unclassified')
    # Without semantic annotations preserve unique inspected evidence; do not
    # manufacture semantic coverage/independence from shared words or hostnames.
    claim = mark.get('claim_id') or digest(normalized(text))
    keys = facts or {'unclassified'}
    result = {('claim', f, claim, role) for f in keys}
    if role == 'context':
        # Context earns value only for facts not already covered by selected evidence.
        return {('fact', f) for f in facts}
    result |= {('fact', f) for f in facts}
    result |= {('role', f, role) for f in facts if role != 'unclassified'}
    if mark.get('independence_key') and role == 'corroboration':
        result |= {('independent', f, claim, mark['independence_key']) for f in keys}
    # Differing numbers, dates and negation are protected even if the model
    # accidentally assigns the same semantic claim ID to different statements.
    values = tuple(re.findall(r'\b\d[\d.,%/-]*|\b(?:not|never|no|denied|unless)\b', text.casefold()))
    result |= {('qualification', f, claim, values) for f in keys}
    return result


def choose(entries, render, picked, sizes, budget, *, deduplicate=False, support=()):
    candidates = []
    for sid, (_, items) in entries.items():
        for i, w in enumerate(items):
            mark = w['mark']
            keys = features(mark, w['text'])
            # Fact/claim labels guide coverage, but cannot replace a cited answer
            # with another passage carrying the same labels. Only existing marks
            # are eligible; a citation never reads or selects unmarked originals.
            for ref in support:
                if (not isinstance(ref, dict) or ref.get('source_id') != sid
                        or ref.get('version', mark['version']) != mark['version']
                        or any(type(ref.get(k)) is not int for k in ('block','start','end'))
                        or not 0 <= ref['start'] < ref['end']):
                    continue
                for r in w.get('ranges', [mark]):
                    a,z = max(r['start'], ref['start']),min(r['end'], ref['end'])
                    if r['block'] == ref['block'] and a < z:
                        keys.add(('support', sid, mark['version'], r['block'], a, z))
            candidates.append(dict(sid=sid, index=i, mark=mark, text=normalized(w['text']),
                                   features=keys,ranges=w.get('ranges')))
    seen, texts, decisions = set(), set(), []
    remaining = budget
    weights = {'fact': 4, 'claim': 2, 'role': 2, 'independent': 1, 'qualification': 1, 'support': 1}
    while candidates:
        ranked = []
        for c in candidates:
            new = c['features'] - seen
            independent = any(f[0] == 'independent' for f in new)
            # A changed label cannot make identical original text independent.
            gain = 0 if c['text'] in texts and (deduplicate or not independent) else sum(weights[f[0]] for f in new)
            content, _ = render(c['sid'], picked[c['sid']] | {c['index']})
            cost = len(content) - sizes[c['sid']]
            ranked.append((c, gain, cost, new))
        feasible = [r for r in ranked if r[1] > 0 and r[2] <= remaining]
        if not feasible:
            for c, gain, cost, new in ranked:
                decisions.append(dict(passage=c['mark'], status='redundant' if gain == 0 else 'material_limit',
                                      marginal_gain=gain))
            break
        c, gain, cost, new = min(feasible, key=lambda r: (
            not any(f[0] == 'support' for f in r[3]), -r[1], r[2], r[0]['sid'], r[0]['index']))
        picked[c['sid']].add(c['index']); sizes[c['sid']] += cost; remaining -= cost
        seen.update(c['features']); texts.add(c['text']); candidates.remove(c)
        decisions.append(dict(passage=c['mark'], status='retained', marginal_gain=gain,
                              new_facts=sorted(f[1] for f in new if f[0] == 'fact')))
        if c['ranges']:
            decisions[-1].update(selection='target_table_rows',
                delivered_ranges=[{k:r[k] for k in ('block','start','end')} for r in c['ranges']])
    return remaining, decisions
