"""Fact-level evidence and source-bound citations, with explicit v1 adapters."""
from copy import deepcopy
import re

from .schema import FACTS_VERSION, GRAPH_VERSION, LEGACY_FACTS_VERSION, LEGACY_GRAPH_VERSION


def iter_citations(evidence):
    """Return nested associations; historical quote records remain readable."""
    if not isinstance(evidence, dict):
        return []
    if 'citations' in evidence:
        citations = evidence['citations']
        return citations if isinstance(citations, list) else []
    return [evidence] if 'quote' in evidence else []


def citation_is_located(citation):
    """Check the anchor shape; source text/hash verification belongs to validation."""
    if not isinstance(citation, dict) or citation.get('location_status') != 'matched':
        return False
    start, end, quote = citation.get('start'), citation.get('end'), citation.get('quote')
    return bool(type(start) is int and type(end) is int and 0 <= start < end
        and isinstance(quote, str) and quote.strip() and end - start == len(quote)
        and isinstance(citation.get('source_id'), str) and citation['source_id'].strip()
        and isinstance(citation.get('sample_id'), str) and citation['sample_id'].strip()
        and isinstance(citation.get('sample_sha256'), str)
        and re.fullmatch(r'[0-9a-f]{64}', citation['sample_sha256']))


def evidence_is_located(evidence):
    return any(citation_is_located(citation) for citation in iter_citations(evidence))


def evidence_quote(evidence):
    """Original quotations for display, never a generated factual summary."""
    return '\n'.join(dict.fromkeys(c['quote'] for c in iter_citations(evidence)
        if isinstance(c, dict) and isinstance(c.get('quote'), str)))


def evidence_statement(evidence):
    if isinstance(evidence, dict) and isinstance(evidence.get('statement'), str):
        return evidence['statement']
    if isinstance(evidence, dict) and isinstance(evidence.get('quote'), str):
        return f"Source {evidence.get('source_id', 'unknown')} states: “{evidence['quote']}”"
    return ''


def citation_identity(citation):
    """Equal text in distinct documents remains distinct provenance."""
    return tuple(citation.get(key) for key in ('source_id', 'sample_id', 'quote',
        'start', 'end', 'location_status', 'sample_sha256'))


def merge_citations(current, additions):
    result = deepcopy(current)
    seen = {citation_identity(citation) for citation in result}
    for citation in additions:
        identity = citation_identity(citation)
        if identity not in seen:
            result.append(deepcopy(citation))
            seen.add(identity)
    return result


def upgrade_evidence(evidence):
    """Import a v1 quote as an attributed quotation, without inventing a summary."""
    if 'citations' in evidence:
        return deepcopy(evidence)
    return dict(evidence_id=evidence['evidence_id'], statement=evidence_statement(evidence),
                citations=[{key: deepcopy(value) for key, value in evidence.items() if key != 'evidence_id'}])


def upgrade_package_evidence(package):
    """Explicit in-memory write/import adapter; never changes a stored artifact."""
    result = deepcopy(package)
    versions = {LEGACY_GRAPH_VERSION: GRAPH_VERSION, LEGACY_FACTS_VERSION: FACTS_VERSION}
    version = result.get('schema_version')
    if version in versions:
        result['evidence'] = [upgrade_evidence(evidence) for evidence in result.get('evidence', [])]
        result['schema_version'] = versions[version]
    return result
