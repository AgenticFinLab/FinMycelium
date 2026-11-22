"""Deterministic search metrics over fixed, independently judged originals."""
import math
from collections import Counter


def fraction(numerator, denominator):
    return numerator / denominator if denominator else None


def ranking_metrics(ranking, qrels, k):
    """Grade 2 is direct evidence; nDCG uses graded gains 2**grade - 1.

    The denominator is the judged saved-source pool. Unknown bodies remain
    unknown at their original rank. Short result lists are padded with misses.
    """
    ranking = list(dict.fromkeys(ranking))
    head = ranking[:k]
    unknown = [sid for sid in head if sid not in qrels]
    result = dict(k=k, returned=len(head), unjudged=unknown,
                  judged_fraction=fraction(len(head)-len(unknown), len(head)),
                  precision=None, recall=None, ndcg=None, ap=None,
                  reciprocal_rank=None, hit_rate=None)
    if unknown:
        return result
    grades = [qrels[sid] for sid in head]
    relevant = sum(g == 2 for g in qrels.values())
    hits = sum(g == 2 for g in grades)
    dcg = sum((2**g-1)/math.log2(i+2) for i, g in enumerate(grades))
    ideal = sum((2**g-1)/math.log2(i+2)
                for i, g in enumerate(sorted(qrels.values(), reverse=True)[:k]))
    running = 0
    ap = 0.0
    for i, grade in enumerate(grades, 1):
        if grade == 2:
            running += 1
            ap += running/i
    result.update(precision=hits/k, recall=fraction(hits, relevant),
                  ndcg=fraction(dcg, ideal), ap=fraction(ap, min(relevant, k)),
                  reciprocal_rank=next((1/i for i, g in enumerate(grades, 1) if g == 2), 0.0),
                  hit_rate=float(bool(hits)))
    return result


def merge_ranges(ranges):
    merged = []
    for start, end in sorted(ranges):
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def covered(ranges, start, end):
    return any(a <= start and b >= end for a, b in merge_ranges(ranges))


def overlap(ranges, start, end):
    return sum(max(0, min(b, end)-max(a, start)) for a, b in merge_ranges(ranges))


def material_metrics(units, labels, selected_ranges, questions):
    """Evaluate actual delivered body ranges, independent of file/source order."""
    direct_pool, direct_selected = set(), set()
    pool_questions, selected_questions = set(), set()
    selected_units = selected_chars = useful_chars = direct_chars = mismatch_units = 0
    mismatches = Counter()
    texts = []
    for unit in units:
        label = labels[unit['unit_id']]
        key = (unit['source_id'], unit['version'], unit['block'])
        ranges = selected_ranges.get(key, [])
        chars = overlap(ranges, unit['start'], unit['end'])
        if chars:
            selected_units += 1
            selected_chars += chars
            useful_chars += chars if label['grade'] >= 1 else 0
            direct_chars += chars if label['grade'] == 2 else 0
            mismatch_units += bool(label['mismatch'])
            mismatches.update(label['mismatch'])
            for start, end in merge_ranges(ranges):
                a, b = max(start, unit['start']), min(end, unit['end'])
                if b > a:
                    texts.append(unit['text'][a-unit['start']:b-unit['start']])
        for support in label['supports']:
            # Identical quotations for a question count once across reposts.
            identity = (support['question_id'], ' '.join(support['quote'].split()))
            direct_pool.add(identity)
            pool_questions.add(support['question_id'])
            offset = unit['text'].find(support['quote'])
            while offset >= 0:
                start = unit['start'] + offset
                if covered(ranges, start, start+len(support['quote'])):
                    direct_selected.add(identity)
                    selected_questions.add(support['question_id'])
                    break
                offset = unit['text'].find(support['quote'], offset+1)
    normalized = [' '.join(t.split()) for t in texts if t.strip()]
    total = sum(map(len, normalized))
    unique = sum(map(len, set(normalized)))
    return dict(
        selected_body_chars=selected_chars, selected_annotation_units=selected_units,
        useful_char_fraction=fraction(useful_chars, selected_chars),
        direct_evidence_char_fraction=fraction(direct_chars, selected_chars),
        topic_mismatch_rate=fraction(mismatch_units, selected_units),
        mismatch_counts=dict(mismatches),
        evidence_quote_recall_in_saved_pool=fraction(len(direct_selected), len(direct_pool)),
        retained_evidence_quotes=len(direct_selected), reference_evidence_quotes=len(direct_pool),
        question_coverage=fraction(len(selected_questions), len(questions)),
        question_coverage_in_saved_pool=fraction(len(selected_questions), len(pool_questions)),
        supported_question_ids=sorted(selected_questions),
        missed_supported_question_ids=sorted(pool_questions-selected_questions),
        questions_without_pool_support=sorted({q['id'] for q in questions}-pool_questions),
        exact_duplicate_text_fraction=fraction(total-unique, total),
    )


def evaluate_metrics(units, labels, selected_ranges, questions, rankings, current_versions):
    material = material_metrics(units, labels, selected_ranges, questions)
    # Provider ranks refer to the current acquired version of each URL.
    qrels = {}
    for unit in units:
        sid = unit['source_id']
        if current_versions.get(sid) == unit['version']:
            qrels[sid] = max(qrels.get(sid, 0), labels[unit['unit_id']]['grade'])
    rows = [dict(row, at={str(k):ranking_metrics(row['source_ids'], qrels, k)
                         for k in (1, 3, 5, 10)}) for row in rankings]
    means = {}
    for k in (1, 3, 5, 10):
        measurements = [r['at'][str(k)] for r in rows]
        values = {}
        for metric in ('precision', 'recall', 'ndcg', 'ap', 'reciprocal_rank', 'hit_rate'):
            valid = [r[metric] for r in measurements if r[metric] is not None]
            values[metric] = dict(mean=fraction(sum(valid), len(valid)),
                                 evaluated_lists=len(valid), excluded_lists=len(rows)-len(valid))
        means[str(k)] = values
    return dict(material=material, provider_rankings=rows, provider_macro_at=means,
                source_qrels=qrels, definitions={
                    'relevance': {'0':'irrelevant or mismatched', '1':'useful context',
                                  '2':'direct original support for a requested question'},
                    'ranking_scope':'Actual provider result order, judged against the overall research task; no invented global ranking.',
                    'reference_pool':'All usable saved source bodies, including acquired but unread/unselected text; not the whole web.',
                    'missing_labels':'Unacquired/failed bodies are unknown. Lists with unknown top-k items have null ranking scores.',
                    'recall':'Direct source hits / all grade-2 sources in the judged pool.',
                    'ndcg':'Gain 2**grade-1, discount log2(rank+1), ideal order from the same judged source pool.',
                    'ap':'Sum of precisions at direct hits / min(k, relevant sources); macro mean is MAP@k.',
                    'material':'Character precision uses evaluated body windows and actual selected ranges; question/quote coverage uses exact retained quotes.',
                    'null':'Undefined denominator, missing reference support, or unjudged ranking items; never substituted with zero.',
                })
