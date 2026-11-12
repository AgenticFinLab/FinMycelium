"""Reuse complete saved model replies only when their factual request still matches."""
import copy
import json
from finmy.search.state import digest

TASK_SEPARATOR = '\n\nBATCH TASK:\n'


def request_identity(user):
    decoder = json.JSONDecoder()
    request, end = decoder.raw_decode(user.lstrip())
    tail = user.lstrip()[end:]
    task = {}
    if tail.startswith(TASK_SEPARATOR):
        task, _ = decoder.raw_decode(tail[len(TASK_SEPARATOR):])
    # Semantic instructions and response contracts participate in identity.
    # A structural validator cannot certify that an older response follows a
    # newly fixed semantic rule, even when its factual inputs are unchanged.
    # Older runners omitted this derived catalog. Exact factual rows are still
    # compared and today's detail guard recomputes/validates the keys.
    request.pop('available_detail_indices', None)
    task.pop('available_detail_indices', None)
    return digest({'request': request, 'task': task})


class OrganizationResume:
    def __init__(self, builder):
        self.builder = builder
        self.artifacts = getattr(builder, '_organization_resume_artifacts', {})
        self.audit = []
        self.checkpoints = []
        raw = self.artifacts.get('PersonOrganizationCheckpoint-Result.json')
        if raw:
            payload = json.loads(raw)
            if payload.get('version') == 1:
                self.checkpoints = payload.get('entries', [])

    def _checkpoint(self, name, identity, system, result, *, source=None):
        entry = {'save_name': name, 'request_sha256': identity, 'system_sha256': digest(system),
                 'result': copy.deepcopy(result), 'result_sha256': digest(result),
                 'source': source or 'current_inference'}
        self.checkpoints = [row for row in self.checkpoints
                            if (row.get('save_name'), row.get('request_sha256'), row.get('system_sha256')) !=
                               (name, identity, digest(system))]
        self.checkpoints.append(entry)
        self.builder._save_agent_result({'version': 1, 'entries': copy.deepcopy(self.checkpoints)},
                                        'PersonOrganizationCheckpoint')

    def _reused(self, name, identity, system, result, source):
        self.builder._save_agent_result(result, name)
        self.audit.append({'save_name': name, 'source': source, 'request_sha256': identity,
                           'result_sha256': digest(result), 'new_model_calls': 0})
        self.builder._save_agent_result({'reused': copy.deepcopy(self.audit)}, 'PersonOrganizationReuse')
        self._checkpoint(name, identity, system, result, source=source)
        return result

    def infer(self, system, user, name, validator):
        from .organization_call_guard import guard_organization_call
        _, _, checked = guard_organization_call(system, user, validator, phase=name)
        identity = request_identity(user)
        for entry in reversed(self.checkpoints):
            if (entry.get('save_name') != name or entry.get('request_sha256') != identity
                    or entry.get('system_sha256') != digest(system)
                    or not isinstance(entry.get('result'), dict)
                    or digest(entry.get('result')) != entry.get('result_sha256')):
                continue
            unresolved = any(value for key, value in entry['result'].items() if key.startswith('pending_'))
            # Reuse accepted rows from the original placement, then retry only
            # its pending IDs. A failed targeted repair is never a terminal hit.
            if unresolved and ('-Repair' in name or 'RelationsReview-' in name):
                continue
            try:
                candidate = copy.deepcopy(entry['result'])
                checked(candidate)
            except (ValueError, TypeError, KeyError):
                continue
            return self._reused(name, identity, system, candidate, 'phase_checkpoint')
        start = len(getattr(self.builder, '_call_records', []))
        try:
            result = self.builder._infer_and_parse_json('PersonOrganization', system, user, {}, name,
                                                        validator=validator)
            self._checkpoint(name, identity, system, result)
            return result
        except Exception as error:
            calls = getattr(self.builder, '_call_records', [])[start:]
            if (calls and calls[-1].get('status') == 'transport_error'
                    and not isinstance(error, AssertionError)):
                raise RuntimeError('Organization provider call unavailable: ' + type(error).__name__) from error
            raise
