"""Conservative source metadata, independent of event dates and model output."""
from datetime import datetime


def publication_metadata(source):
    """Keep provider claims; agree at day precision or report a conflict/unknown.

    No date is inferred from the URL, PDF filename, retrieval time or event scope.
    Differing provider dates may describe publication versus an update; neither is
    silently preferred. Original values and providers remain available for review.
    """
    candidates = []
    for discovery in [source, *source.get('discoveries', [])]:
        value = discovery.get('published_at')
        if not isinstance(value, str) or not value.strip():
            continue
        candidate = dict(value=value, provider=discovery.get('provider', 'source'))
        try:
            candidate['date'] = datetime.fromisoformat(value.strip().replace('Z', '+00:00')).date().isoformat()
        except ValueError:
            candidate['date'] = None
        if candidate not in candidates:
            candidates.append(candidate)
    dates = {c['date'] for c in candidates if c['date']}
    unknown = any(c['date'] is None for c in candidates)
    status = 'conflicted' if len(dates) > 1 else 'unverified' if unknown else 'reported' if dates else 'unknown'
    return dict(published_at=next(iter(dates)) if status == 'reported' else None,
                publication_status=status, publication_candidates=candidates)


def source_metadata(source, document):
    return dict(source_url=source['url'], title=source.get('title') or None,
                retrieved_at=document.get('retrieved_at'), content_status=document.get('status'),
                **publication_metadata(source))
