"""Apply bounded, local JSON Patch operations to a copy of a SubjectGraph."""
import copy
import re


_PROTECTED = {"schema_version", "graph_id", "subject_id", "subject_type",
              "coverage_start", "coverage_end"}


def _tokens(path):
    if not isinstance(path, str) or not path.startswith('/') or path == '/':
        raise ValueError("Repair requires a non-root JSON pointer")
    if re.search(r'~(?![01])', path):
        raise ValueError("Invalid JSON pointer escape")
    return [part.replace('~1', '/').replace('~0', '~') for part in path[1:].split('/')]


def _key(parent, token):
    if isinstance(parent, list):
        if not re.fullmatch(r'0|[1-9][0-9]*', token) or int(token) >= len(parent):
            raise ValueError("Repair array index is out of range")
        return int(token)
    if not isinstance(parent, dict):
        raise ValueError("Repair path traverses a scalar")
    return token


def apply_graph_patch(graph, response, errors):
    """Apply atomically; array positions refer to the original graph.

    Only error-containing records/fields can be edited. Collection and record
    replacement is forbidden: repairs must name individual fields. The caller
    still validates the full merged graph against its original sources.
    """
    if not isinstance(response, dict) or set(response) != {'patches'}:
        raise ValueError("SubjectGraphRepair must return {'patches': [...]}, not a whole graph")
    patches = response['patches']
    if not isinstance(patches, list) or len(patches) > 128:
        raise ValueError("Repair patches must be a list of at most 128 operations")
    scopes = []
    for error in errors:
        path = error.get('path', '')
        if path and path != '/':
            parts = _tokens(path)
            # A reference/date error may need a related field in the same record.
            scopes.append(parts[:2] if parts[0] in ('events', 'entities', 'relations', 'descriptions')
                          and len(parts) >= 2 else parts[:1])
    operations, paths = [], []
    result = copy.deepcopy(graph)
    for patch in patches:
        if not isinstance(patch, dict):
            raise ValueError("Repair operation must be an object")
        op = patch.get('op')
        expected = {'op', 'path'} if op == 'remove' else {'op', 'path', 'value'}
        if op not in ('add', 'replace', 'remove') or set(patch) != expected:
            raise ValueError("Repair supports only add, replace and remove")
        parts = _tokens(patch['path'])
        if parts[0] in _PROTECTED:
            raise ValueError("Repair cannot change configured graph identity/coverage")
        if parts[0] in ('events', 'entities', 'relations') and len(parts) < 3:
            raise ValueError("Repair must edit fields, not replace or remove entire records")
        if not any(parts[:len(scope)] == scope for scope in scopes):
            raise ValueError("Repair path is outside the reported errors")
        if any(parts[:len(other)] == other or other[:len(parts)] == parts for other in paths):
            raise ValueError("Repair paths must not overlap or repeat")
        parent = result
        try:
            for token in parts[:-1]:
                parent = parent[_key(parent, token)]
            key = _key(parent, parts[-1])
            if op == 'add':
                if not isinstance(parent, dict) or key in parent:
                    raise ValueError("Repair add is only for a missing object field")
            elif isinstance(parent, dict) and key not in parent:
                raise ValueError("Repair target does not exist")
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("Repair target does not exist") from exc
        paths.append(parts)
        operations.append((op, parent, key, patch.get('value')))
    # Resolve every target before mutation. Delete array elements from the end
    # so one removal cannot change another operation's original index.
    for op, parent, key, value in operations:
        if op != 'remove':
            parent[key] = copy.deepcopy(value)
    removals = [item for item in operations if item[0] == 'remove']
    for _, parent, key, _ in sorted(removals, key=lambda item: item[2] if isinstance(item[2], int) else -1, reverse=True):
        del parent[key]
    return result
