"""Search setup failures that require an operator change before retrying."""


class SearchConfigurationError(ValueError):
    """Use only safe messages constructed locally, never raw service errors."""


def api_configuration_error(error, service):
    """Recognize rejected API access/settings without logging response bodies."""
    status = getattr(error, 'status_code', None)
    if status is None:
        status = getattr(getattr(error, 'response', None), 'status_code', None)
    if status in (401, 403):
        return SearchConfigurationError(
            f'{service} rejected access (HTTP {status}); check the API key and permissions, then retry this task.')
    if status in (400, 404, 422):
        return SearchConfigurationError(
            f'{service} rejected the request (HTTP {status}); check the endpoint and request configuration, then retry this task.')
    return None
