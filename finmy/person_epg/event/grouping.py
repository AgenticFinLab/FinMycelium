"""Bounded duplicate *review* selection; similarity never merges facts."""
from collections import defaultdict
import re

from .schema import COLLECTION_IDS


# Remove narrative glue, not domain vocabulary or behavioral categories.
STOP = set('the a an and or of to in on for from with by as at its his her their was were '
           'is are be been had has have that this these those he she they it reported '
           'stated said described source account publicly'.split())


def terms(text):
    return {w for w in re.findall(r'[^\W_]+', text.casefold()) if len(w) > 2 and w not in STOP}


def ambiguity_groups(facts, max_group=8):
    """Sparse postings select local competitors, then form disjoint review groups.

    An actor or shared organization alone is insufficient. Name/date anchors and
    overlapping matter descriptions merely nominate records for semantic decisions.
    Limit posting neighbors and group size so broad events do not become all-pairs
    prompts. Each record is assigned once; the full index remains available.
    """
    buckets, records, scores = defaultdict(list), {}, {}
    # Entity IDs already provide the actor/object anchor. Do not count repeated
    # company/person names again as evidence of behavioral similarity.
    entity_names = {n for e in facts['entities']
                    for name in [e['name'], *e.get('aliases', [])] for n in terms(name)}
    action_terms = {}
    for collection in ('entities', 'actions', 'contexts', 'relation_candidates'):
        for record in facts[collection]:
            ref = (collection, record[COLLECTION_IDS[collection]])
            records[ref] = record
            name = re.sub(r'\W+', ' ', record.get('name', record.get('description', '')).casefold()).strip()
            if name:
                buckets[(collection, 'name', name)].append(ref)
            if collection != 'actions':
                continue
            actor = record['actor']['entity_id']
            if record['time']['start']:
                buckets[(collection, 'actor_time', actor, record['time']['start'])].append(ref)
            action_terms[ref] = terms(' '.join([record.get('name', ''), record.get('description', ''),
                record.get('object', {}).get('description', '')])) - entity_names
            for oid in record.get('object', {}).get('entity_refs', []):
                if oid != facts['person']['person_id']:
                    buckets[(collection, 'object', actor, oid)].append(ref)
            # Unknown objects still permit a shared, distinctive description lead.
            for word in sorted(action_terms[ref]):
                buckets[(collection, 'word', actor, word)].append(ref)

    for key, refs in sorted(buckets.items()):
        refs = sorted(set(refs))
        for i, left in enumerate(refs):
            for right in refs[i + 1:i + 13]:
                pair = (left, right)
                if key[1] in ('name', 'actor_time'):
                    scores[pair] = max(scores.get(pair, 0), 2 if key[1] == 'name' else 1)
                    continue
                a, b = records[left], records[right]
                ta, tb = a['time'], b['time']
                if (all(t.get('start') and t.get('end') for t in (ta, tb))
                        and (ta['end'] <= tb['start'] or tb['end'] <= ta['start'])):
                    continue  # Different known occurrences are not lexical duplicates.
                shared = action_terms[left] & action_terms[right]
                objects = set(a.get('object', {}).get('entity_refs', [])) & set(b.get('object', {}).get('entity_refs', []))
                objects.discard(facts['person']['person_id'])
                similarity = len(shared) / max(1, min(len(action_terms[left]), len(action_terms[right])))
                if len(shared) >= (3 if objects else 5) and similarity >= .3:
                    scores[pair] = max(scores.get(pair, 0), similarity)
    groups, owners = [], {}
    for (left, right), score in sorted(scores.items(), key=lambda item: (-item[1], item[0])):
        a, b = owners.get(left), owners.get(right)
        if a is not None and a == b:
            continue
        merged = ({left} if a is None else groups[a]) | ({right} if b is None else groups[b])
        if len(merged) > max_group:
            continue
        index = a if a is not None else b if b is not None else len(groups)
        if index == len(groups):
            groups.append(set())
        if b is not None and b != index:
            groups[b] = set()
        groups[index] = merged
        for ref in merged:
            owners[ref] = index
    return [sorted(g) for g in groups if len(g) > 1]
