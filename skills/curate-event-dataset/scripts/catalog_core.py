"""Bundled catalog CSV and validation routines adapted from EPG-dataset/scripts/curate_events.py."""
import collections
import csv
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re

FIELDS = 'event_id,event_name_zh,event_name_en,aliases,description,domain,category,country_region,participants,coverage_start,coverage_end,scope_include,scope_exclude,keywords,search_language,source_hints,owner,notes,related_events,status,epg_path,gantt_path,review_path'.split(',')
CATALOG_FIELDS = FIELDS + ['duplicate_status']
SOURCE_FIELDS = 'source_id,title,url,publisher,publication_info,accessed_on,locator,reading_note'.split(',')
LINK_FIELDS = 'event_id,source_id,supported_fields,support_note,verification_result,verified_on,reviewer'.split(',')
DECISION_FIELDS = 'record_id,event_id,legacy_uid,decision,canonical_event_id,reason,source_ids,changed_fields,reviewed_on,reviewer'.split(',')


def read(path):
    path = Path(path)
    if not path.is_file() and path.with_name(path.name + '.gz').is_file():
        path = path.with_name(path.name + '.gz')
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        if any(None in r or any(v is None for v in r.values()) for r in rows):
            raise ValueError(f'malformed CSV: {path}')
        return rows


def write(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    def write_rows(stream):
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    if path.suffix == '.gz':
        with tmp.open('wb') as raw:
            with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as compressed:
                with io.TextIOWrapper(compressed, encoding='utf-8', newline='') as stream:
                    write_rows(stream)
    else:
        with tmp.open('w', encoding='utf-8', newline='') as stream:
            write_rows(stream)
    tmp.replace(path)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def keyed(rows, key):
    result = {r[key]: r for r in rows}
    if len(result) != len(rows) or '' in result:
        raise ValueError(f'non-unique or empty join key: {key}')
    return result


def duplicate_marks(pairs):
    """Project reviewed pair verdicts to a single flag per event."""
    verdict_to_mark = {'duplicate': 'duplicate', 'bounded_overlap': 'overlap',
                       'pending': 'possible_duplicate', 'possible_duplicate': 'possible_duplicate'}
    priority = {'': 0, 'possible_duplicate': 1, 'overlap': 2, 'duplicate': 3}
    marks = {}
    for pair in pairs:
        mark = verdict_to_mark.get(pair['verdict'])
        if not mark:
            continue
        for field in ('left_event_id', 'right_event_id'):
            eid = pair[field]
            if priority[mark] > priority[marks.get(eid, '')]:
                marks[eid] = mark
    return marks


def check(catalog, target=None, *, finmy_root, baseline_catalog=None, allow_h2epr_audit_exceptions=False,
          quiet=False):
    catalog = Path(catalog)
    finmy_root = Path(finmy_root)
    spec = importlib.util.spec_from_file_location('workbench_domain', finmy_root / 'finmy/workbench/domain.py')
    domain = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(domain)
    with (catalog / 'events.csv').open(encoding='utf-8-sig', newline='') as stream:
        header = next(csv.reader(stream))
        if header not in (FIELDS, CATALOG_FIELDS):
            raise ValueError('master header mismatch')
    rows = read(catalog / 'events.csv')
    ids = keyed(rows, 'event_id')
    if header == CATALOG_FIELDS:
        pairs_path = catalog / 'research/duplicate-review.csv.gz'
        marks = duplicate_marks(read(pairs_path)) if pairs_path.is_file() else {}
        if not marks.keys() <= ids.keys() or any(r['duplicate_status'] != marks.get(r['event_id'], '') for r in rows):
            raise ValueError('duplicate_status does not match the current pair audit')
    h2_audit = {}
    duplicate_pairs = set()
    if allow_h2epr_audit_exceptions:
        imported = keyed(read(catalog / 'events_H2EPR.csv'), 'event_id')
        audit = keyed(read(catalog / 'research/h2epr/review.csv'), 'event_id')
        if imported.keys() != audit.keys():
            raise ValueError('H2EPR audit identities do not match the retained input')
        for eid, original in imported.items():
            current = ids.get(eid)
            if current is None or any(current[k] != original[k] for k in header):
                continue
            if hashlib.sha256(encoded(original).encode('utf-8')).hexdigest() != audit[eid]['current_row_sha256']:
                raise ValueError(f'{eid}: stale H2EPR audit')
            h2_audit[eid] = audit[eid]
        duplicate_pairs = {
            frozenset((pair['left_event_id'], pair['right_event_id']))
            for pair in read(catalog / 'research/h2epr/duplicate-review.csv')
            if pair['status'] == 'duplicate'
            and pair['left_event_id'] in h2_audit and pair['right_event_id'] in h2_audit
        }
    for filename, expected in [('sources.csv', SOURCE_FIELDS), ('event-sources.csv', LINK_FIELDS), ('curation-decisions.csv', DECISION_FIELDS)]:
        with (catalog / filename).open(encoding='utf-8-sig', newline='') as stream:
            if next(csv.reader(stream)) != expected:
                raise ValueError(f'{filename}: header mismatch')
    sources = keyed(read(catalog / 'sources.csv'), 'source_id')
    for source in sources.values():
        domain.validate_url(source['url'])
        if any(not source[k].strip() for k in ['title', 'publisher', 'accessed_on', 'locator', 'reading_note']):
            raise ValueError('incomplete read-source record')
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', source['accessed_on']):
            raise ValueError('invalid source access date')
        domain.date_bounds(source['accessed_on'])
    decisions = read(catalog / 'curation-decisions.csv')
    keyed(decisions, 'record_id')
    latest = {r['event_id']: r for r in decisions}  # append-only order is authoritative
    # Retired migration inputs are no longer required. The retained baseline
    # records the original public-ID namespace and count for disposition checks.
    baseline_path = catalog / 'research/baseline.json'
    if baseline_catalog is not None:
        baseline_catalog = Path(baseline_catalog)
        old_ids = {r['event_id'] for r in read(baseline_catalog / 'curation-decisions.csv')}
        old_ids.update(r['event_id'] for r in read(baseline_catalog / 'events.csv'))
    elif baseline_path.is_file():
        baseline = json.loads(baseline_path.read_text(encoding='utf-8-sig'))
        if baseline.get('identity_scope') == 'current_catalog':
            actual = hashlib.sha256(encoded(sorted(ids)).encode('utf-8')).hexdigest()
            if baseline.get('event_ids_sha256') != actual:
                raise ValueError('current identity baseline changed; validate against --baseline-catalog before refreshing it')
            old_ids = set(ids)
        else:
            count = baseline.get('identity_join_count')
            if type(count) is not int or count < 0:
                raise ValueError('invalid historical identity metadata; provide --baseline-catalog')
            old_ids = {f'H2EPR-{i:04d}' for i in range(1, count + 1)}
    elif any(r['event_id'].startswith('H2EPR-') for r in decisions):
        raise ValueError('historical identities present: provide --baseline-catalog or research/baseline.json')
    else:
        old_ids = set()  # A genuinely new catalog has no retired migration identities.
    if not old_ids <= latest.keys():
        raise ValueError('missing historical dispositions')
    for decision in latest.values():
        if decision['decision'] not in {'retain', 'revise', 'merge', 'exclude', 'defer'}:
            raise ValueError('invalid curation decision')
        if not decision['reason'].strip() or not isinstance(json.loads(decision['changed_fields']), dict):
            raise ValueError('incomplete decision')
        source_ids = json.loads(decision['source_ids'])
        if not isinstance(source_ids, list) or not set(source_ids) <= sources.keys():
            raise ValueError('orphan decision source')
        if decision['decision'] in {'retain', 'revise', 'merge'}:
            eid = decision['event_id']
            pending_import = (
                eid in h2_audit and h2_audit[eid]['review_status'] == 'pending'
                and h2_audit[eid]['source_ids'] == '[]' and decision['canonical_event_id'] == eid
            )
            if decision['canonical_event_id'] not in ids or (not source_ids and not pending_import) or not decision['reviewed_on']:
                raise ValueError('unresolved canonical decision')
        if decision['decision'] in {'merge', 'exclude', 'defer'} and decision['event_id'] in ids:
            raise ValueError('inactive event remains in master')
    if not set(ids) <= latest.keys():
        raise ValueError('active event without curation decision')
    links = read(catalog / 'event-sources.csv')
    supported = collections.defaultdict(set)
    for link in links:
        if link['event_id'] not in ids or link['source_id'] not in sources:
            raise ValueError('orphan evidence link')
        if link['verification_result'] != 'supported':
            raise ValueError('unresolved evidence issue in active catalog')
        if not link['support_note'] or not link['verified_on'] or not link['reviewer']:
            raise ValueError('incomplete verification record')
        domain.date_bounds(link['verified_on'])
        fields = json.loads(link['supported_fields'])
        if not isinstance(fields, list) or not set(fields) <= set(FIELDS):
            raise ValueError('invalid supported fields')
        supported[link['event_id']].update(fields)
    titles = collections.defaultdict(list)
    for row in rows:
        domain.event_record({k: row[k] for k in domain.FIELDS})
        for k in ['event_id', 'description', 'scope_include', 'status']:
            if not row[k].strip():
                raise ValueError(f'{row["event_id"]}: missing {k}')
        if row['status'] not in {'planned', 'in_progress', 'in_review', 'needs_revision', 'accepted'}:
            raise ValueError('invalid status')
        for k in domain.LIST_FIELDS | {'related_events'}:
            if row[k] and not isinstance(json.loads(row[k]), list):
                raise ValueError('non-JSON list')
        for k in ('coverage_start', 'coverage_end'):
            if row[k].lower() in {'unknown', 'null', 'n/a'}:
                raise ValueError('nonstandard missing date')
        if not {'description', 'scope_include'} <= supported[row['event_id']]:
            audit = h2_audit.get(row['event_id'], {})
            evidence_fields = supported[row['event_id']]
            pending_input = audit.get('review_status') == 'pending' and not evidence_fields
            bounded_scope = audit.get('review_status') in {'source_supported', 'partially_supported'} and 'description' in evidence_fields
            if not (pending_input or bounded_scope):
                raise ValueError(f'{row["event_id"]}: missing evidence coverage')
        for rel in json.loads(row['related_events'] or '[]'):
            if rel['event_id'] not in ids and not re.search('external|外部|待导入', rel['note'], re.IGNORECASE):
                raise ValueError('unresolved internal relationship')
        for k in ('epg_path', 'gantt_path', 'review_path'):
            value = row[k]
            if value:
                p = Path(value)
                if p.is_absolute() or '\\' in value or '..' in p.parts or not (catalog / p).resolve().is_relative_to(catalog.resolve()):
                    raise ValueError('unsafe artifact path')
                if row['status'] != 'accepted' or not (catalog / p).is_file():
                    raise ValueError('uncollected artifact path')
            elif row['status'] == 'accepted':
                raise ValueError('accepted without artifacts')
        title = re.sub(r'\W+', '', row['event_name_en'].casefold()) or row['event_name_zh']
        if any(frozenset((other, row['event_id'])) not in duplicate_pairs for other in titles[title]):
            raise ValueError('identical normalized title; requires adjudication')
        titles[title].append(row['event_id'])
    if target is not None and len(rows) != target:
        raise ValueError(f'target not achieved: {len(rows)}/{target}')
    if not quiet:
        print(f'PASS: {len(rows)} rows; schema and evidence links only, not semantic truth or global deduplication')


def summarize(catalog, target=None, *, finmy_root, baseline_catalog=None, allow_h2epr_audit_exceptions=False):
    """Recompute progress and coverage from the checked catalog, never from prose."""
    catalog = Path(catalog)
    check(catalog, target, baseline_catalog=baseline_catalog, finmy_root=finmy_root,
          allow_h2epr_audit_exceptions=allow_h2epr_audit_exceptions)
    rows = read(catalog / 'events.csv')
    sources = read(catalog / 'sources.csv')
    links = read(catalog / 'event-sources.csv')
    latest = {r['event_id']: r for r in read(catalog / 'curation-decisions.csv')}
    supported = {r['event_id'] for r in links if r['verification_result'] == 'supported'}
    counts = lambda values: dict(sorted(collections.Counter(values).items()))
    result = {
        'active': len(rows),
        'legacy_active': sum(r['event_id'].startswith('H2EPR-') for r in rows),
        'new_active': sum(not r['event_id'].startswith('H2EPR-') for r in rows),
        'legacy_dispositions': counts(r['decision'] for eid, r in latest.items() if eid.startswith('H2EPR-')),
        'new_candidate_dispositions': counts(r['decision'] for eid, r in latest.items() if not eid.startswith('H2EPR-')),
        'source_records': len(sources),
        'event_source_links': len(links),
        'source_supported_rows': len(supported),
        'domains': counts(r['domain'] for r in rows),
        'categories': counts(r['category'] for r in rows),
        'region_labels': counts(v for r in rows for v in json.loads(r['country_region'] or '[]')),
        'start_decades': counts(r['coverage_start'][:3] + '0s' if r['coverage_start'] else 'unspecified' for r in rows),
        'statuses': counts(r['status'] for r in rows),
        'historical_lexical_pairs': counts(r['decision'] for r in read(catalog / 'research/duplicate-candidates.csv'))
            if (catalog / 'research/duplicate-candidates.csv').is_file() else None,
        'inputs_sha256': {n: hashlib.sha256((catalog / n).read_bytes()).hexdigest() for n in
                         ('events.csv', 'sources.csv', 'event-sources.csv', 'curation-decisions.csv')},
        'limitations': 'Derived statistics only. Region labels are multivalued and may be venues or offshore areas. '
                        'Unspecified start years are not imputed. Source support is not independent human review '
                        'or certification of global semantic deduplication.'
    }
    if allow_h2epr_audit_exceptions:
        review = keyed(read(catalog / 'research/row-review.csv.gz'), 'event_id')
        if review.keys() != latest.keys():
            raise ValueError('current review identities do not match the decision ledger')
        result['rows_with_supported_links'] = len(supported)
        result['fact_review_statuses'] = counts(r['verdict'] for r in review.values())
        result['source_supported_rows'] = result['fact_review_statuses'].get('supported', 0)
    path = catalog / 'research/coverage-summary.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded(result) + '\n', encoding='utf-8')
    print(f'SUMMARY: {len(rows)} active; {len(supported)} with supported links; {len(sources)} sources; {path}')
