"""Execution settings and effective budgets shared by every event entry point."""
from dataclasses import asdict, dataclass
from finmy.model_config import person_build_effort_options, person_build_json_mode_supported
from .schema import GRAPH_VERSION


@dataclass
class EventBuildConfig:
    lm_name: str = 'ark/kimi-k3-1-pro-261024'
    max_calls: int = 40
    max_json_attempts: int = 3
    max_new_tokens: int = 12288
    max_context_chars: int = 160000
    timeout: int = 900
    stall_timeout: int = 60
    max_transport_retries: int = 5
    extraction_chars: int = 12000
    extraction_overlap: int = 400
    max_read_calls: int = 24
    max_read_rounds: int = 2
    read_call_extension: int = 0
    read_round_extension: int = 0
    read_char_extension: int = 0
    max_read_chars: int = 48000
    read_chars: int = 4000
    retrieval_top_k: int = 4
    final_repair_rounds: int = 1
    graph_schema_version: str = GRAPH_VERSION
    api_json_mode: bool = False
    full_corpus_supplement: bool = True
    reasoning_effort: str | None = 'auto'
    extraction_workers: int = 1

    @classmethod
    def from_saved(cls, values):
        """Restore historical defaults for fields absent from saved tasks."""
        return cls(**{'reasoning_effort': None, 'full_corpus_supplement': False, **values})

    def __post_init__(self):
        if not isinstance(self.lm_name, str) or not self.lm_name.strip():
            raise ValueError('Choose an independent build model')
        if type(self.full_corpus_supplement) is not bool:
            raise ValueError('full_corpus_supplement must be a boolean')
        if type(self.api_json_mode) is not bool:
            raise ValueError('api_json_mode must be a boolean')
        if self.api_json_mode and not person_build_json_mode_supported(self.lm_name):
            raise ValueError('API JSON mode is currently supported for Ark Kimi K3.1 Pro only')
        effort_options = person_build_effort_options(self.lm_name)
        if self.reasoning_effort == 'auto':
            self.reasoning_effort = effort_options[0]
        elif self.reasoning_effort not in effort_options:
            raise ValueError('reasoning_effort accepts by_stage, low, high or max for Kimi K3.1 Pro, or None for the service default')
        for key, value in asdict(self).items():
            if key in ('lm_name', 'graph_schema_version', 'api_json_mode', 'full_corpus_supplement', 'reasoning_effort'):
                continue
            minimum = 0 if key in ('extraction_overlap', 'final_repair_rounds', 'max_read_calls', 'max_read_rounds', 'max_transport_retries',
                                  'read_call_extension', 'read_round_extension', 'read_char_extension') else 1
            if type(value) is not int or value < minimum:
                raise ValueError(key + ' is outside its supported range')
        if self.graph_schema_version != GRAPH_VERSION:
            raise ValueError('This executor only writes ' + GRAPH_VERSION)
        if self.extraction_overlap >= self.extraction_chars:
            raise ValueError('Extraction overlap must be smaller than the batch')
        if self.final_repair_rounds > 1:
            raise ValueError('At most one final targeted repair round is supported')
        if not 1 <= self.extraction_workers <= 10:
            raise ValueError('extraction_workers must be between 1 and 10')


def effective_read_limits(config):
    return dict(read_calls=config.max_read_calls + config.read_call_extension,
                read_rounds=config.max_read_rounds + config.read_round_extension,
                read_chars=config.max_read_chars + config.read_char_extension)


def resume_settings(state, *, extra_calls=60, extra_read_calls=0, max_read_rounds=None, extra_read_chars=0, reset_timeout=True):
    """One definition of the existing resume policy; never reset spent budgets."""
    if extra_calls < 1 or extra_read_calls < 0 or extra_read_chars < 0 or (max_read_rounds is not None and max_read_rounds < 0):
        raise ValueError('Additional calls must be positive; read budgets cannot be negative')
    previous = EventBuildConfig.from_saved(state['config'])
    defaults = EventBuildConfig()
    return dict(timeout=defaults.timeout if reset_timeout else previous.timeout, stall_timeout=defaults.stall_timeout,
        max_transport_retries=defaults.max_transport_retries,
        max_calls=max(previous.max_calls, len(state['calls']) + extra_calls),
        read_call_extension=max(previous.read_call_extension,
            len(state.get('reads', [])) + extra_read_calls - previous.max_read_calls),
        read_round_extension=max(previous.read_round_extension,
            (max_read_rounds or previous.max_read_rounds) - previous.max_read_rounds),
        read_char_extension=previous.read_char_extension + extra_read_chars)


def budget_summary(state):
    config = EventBuildConfig.from_saved(state['config'])
    limits = effective_read_limits(config)
    return dict(model_calls=dict(used=len(state.get('calls', [])), limit=config.max_calls),
        read_calls=dict(used=len(state.get('reads', [])), limit=limits['read_calls']),
        read_chars=dict(used=state.get('read_budget', {}).get('charged_chars',
                        0 if not state.get('reads') else None), limit=limits['read_chars']),
        read_rounds=dict(max_used=max((len(v) for v in state.get('read_rounds', {}).values()), default=0),
                         limit_per_task=limits['read_rounds']),
        timeout=config.timeout, stall_timeout=config.stall_timeout,
        retries=config.max_transport_retries, workers=config.extraction_workers)
