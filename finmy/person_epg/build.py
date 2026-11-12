"""Build one confirmed person event using reusable evidence-bound fact phases.

Retrieval is deliberately absent. Execution needs explicit permission or an injected
transport for offline checks. Every successful output remains a content-review draft.
"""
from copy import deepcopy
from dataclasses import dataclass, asdict
import json
from pathlib import Path
import re
import time
from types import SimpleNamespace

from finmy.generic import DataSample, UserQueryInput
from finmy.search.state import digest, now, write_json
from finmy.search.summary import directory_lock
from .input import validate_input
from .validation import validate_person_epg
from .evidence import ground_person_evidence
from .building.person_fact_pipeline import build_canonical_facts
from .building.person_organization import apply_organization
from .building.organization_batches import organize_person_plan
from .building.organization_resume import OrganizationResume
from .building.completion_errors import IncompleteCompletionError


@dataclass
class PersonBuildConfig:
    lm_name: str = 'ark/doubao-seed-2-0-pro-260215'
    max_calls: int = 40
    max_json_attempts: int = 3
    max_new_tokens: int = 12288
    max_context_chars: int = 160000
    timeout: int = 900

    def __post_init__(self):
        if not isinstance(self.lm_name, str) or not self.lm_name.strip():
            raise ValueError('Choose an independent build model')
        for key in ('max_calls', 'max_json_attempts', 'max_new_tokens', 'max_context_chars', 'timeout'):
            if type(getattr(self, key)) is not int or getattr(self, key) < 1:
                raise ValueError(key + ' must be positive')


class BuildLimit(Exception):
    """Propagates through per-item recovery so a hard limit stops all new calls."""


def code_identity():
    root = Path(__file__).resolve().parents[1]
    return digest({str(p.relative_to(root)): digest(p.read_bytes()) for p in sorted(root.rglob('*'))
                   if p.is_file() and p.suffix in {'.py', '.json'} and 'url_collector' not in p.parts})


class Model:
    def __init__(self, config):
        self.config = config
        self.adapter = None
        self.last_usage = None

    def __call__(self, system, user, name):
        if self.adapter is None:
            from lmbase.inference.api_call import LangChainAPIInference
            self.adapter = LangChainAPIInference(lm_name=self.config.lm_name, generation_config={})
            self.adapter.client = self.adapter.client.with_options(max_retries=0, timeout=self.config.timeout)
        self.last_usage = None
        response = self.adapter.client.chat.completions.create(model=self.adapter.model_name,
            messages=[{'role':'system', 'content':system}, {'role':'user', 'content':user}],
            max_tokens=self.config.max_new_tokens, temperature=0.2, top_p=0.95)
        self.last_usage = response.usage.model_dump() if response.usage else None
        choice = response.choices[0] if response.choices else None
        if choice is None or choice.finish_reason != 'stop' or getattr(choice.message, 'refusal', None) or getattr(choice.message, 'tool_calls', None):
            raise IncompleteCompletionError(name, finish_reason=getattr(choice, 'finish_reason', None),
                refusal=bool(getattr(choice.message, 'refusal', None)) if choice else False,
                tool_calls=bool(getattr(choice.message, 'tool_calls', None)) if choice else False,
                output_limit=self.config.max_new_tokens)
        return choice.message.content


def parse_response(raw):
    if isinstance(raw, dict):
        return deepcopy(raw)
    if not isinstance(raw, str):
        raise ValueError('Expected a JSON object response')
    cleaned = raw.strip()
    if cleaned.startswith('```') and cleaned.endswith('```'):
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.I)[:-3].strip()
    value = json.loads(cleaned)
    if not isinstance(value, dict):
        raise ValueError('Expected a JSON object response')
    return value


class Execution:
    def __init__(self, directory, state, config, model, attempt):
        self.directory, self.state, self.config, self.model = directory, state, config, model
        self.attempt = attempt
        self._call_records = state['calls']
        self._organization_resume_artifacts = {}
        checkpoint = directory / 'PersonOrganizationCheckpoint-Result.json'
        if checkpoint.exists():
            self._organization_resume_artifacts[checkpoint.name] = checkpoint.read_text()

    def persist(self):
        self.state['updated_at'] = now()
        write_json(self.directory / 'state.json', self.state)

    def save(self, value, name):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', name):
            raise ValueError('Invalid artifact name')
        write_json(self.attempt / (name + '.json'), value)
        if name == 'PersonCanonicalFacts':
            self.facts = deepcopy(value)
        if name == 'PersonCanonicalAudit':
            if digest(self.facts) != value['package_sha256']:
                raise ValueError('Canonical checkpoint is inconsistent')
            write_json(self.directory / 'canonical-checkpoint.json', {'package':self.facts, 'audit':value})

    def _save_agent_result(self, value, name):
        self.save(value, name)
        if name == 'PersonOrganizationCheckpoint':
            write_json(self.directory / (name + '-Result.json'), value)

    def _infer_and_parse_json(self, agent, system, user, inputs, name, *, validator):
        return self.infer(system, user, name, validator)

    def infer(self, system, user, name, validator):
        original = user
        for attempt in range(1, self.config.max_json_attempts + 1):
            if len(self.state['calls']) >= self.config.max_calls:
                raise BuildLimit('model_calls')
            if len(system) + len(user) > self.config.max_context_chars:
                raise BuildLimit('model_context_chars')
            record = {'phase':name, 'attempt':attempt, 'started':now(), 'status':'submitted'}
            self.state['calls'].append(record)
            self.persist()  # Reserve usage before submission; resumed runs retain it.
            started = time.monotonic()
            try:
                raw = self.model(system, user, name)
                value = parse_response(raw)
                validator(value)
                record['status'] = 'accepted'
                return value
            except IncompleteCompletionError:
                record['status'] = 'incomplete'
                raise  # Hu's bounded phase subdivision handles length errors.
            except (ValueError, TypeError, KeyError) as exc:
                record.update(status='invalid_output', error_type=type(exc).__name__)
                if attempt == self.config.max_json_attempts:
                    raise
                user = original + '\n\nCorrect the response to match the supplied contract. Validation: ' + str(exc)[:1200]
            except Exception as exc:
                record.update(status='transport_error', error_type=type(exc).__name__)
                raise RuntimeError(type(exc).__name__) from exc
            finally:
                record.update(duration_seconds=round(time.monotonic()-started, 3),
                              usage=deepcopy(getattr(self.model, 'last_usage', None)))
                self.persist()


def check_identity(package, event):
    validation = validate_person_epg(package)
    if not validation['valid']:
        raise ValueError('Invalid native person graph: ' + str(validation['errors'][:2]))
    if package['graph']['subject_entity_id'] != event['person_id']:
        raise ValueError('Person identity changed during construction')
    if [(d['domain_id'], d['label']) for d in package['domain']] != [(event['storyline_id'], event['storyline_name'])]:
        raise ValueError('The confirmed storyline changed during construction')
    if [(e['event_id'], e['domain_id'], e['label']) for e in package['event']] != [(event['event_id'], event['storyline_id'], event['event_name'])]:
        raise ValueError('Construction must contain exactly the confirmed event')
    return validation


def run_event(payload, directory, config=None, *, allow_network=False, model=None, resume=False):
    config = PersonBuildConfig(**config) if isinstance(config, dict) else config or PersonBuildConfig()
    event = validate_input(payload)
    if model is None and not allow_network:
        raise PermissionError('Model execution requires explicit permission')
    try:
        inputs = SimpleNamespace(user_query=UserQueryInput(**payload['user_query']),
                                 samples=[DataSample(**s) for s in payload['samples']])
    except TypeError as exc:
        raise ValueError('Invalid query or sample fields') from exc
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    with directory_lock(directory):
        state_path = directory / 'state.json'
        identity = {'input_sha256':digest(payload), 'code_sha256':code_identity()}
        if state_path.exists():
            if not resume:
                raise ValueError('Existing run requires explicit resume or a new run directory')
            state = json.loads(state_path.read_text())
            if any(state.get(k) != v for k, v in identity.items()):
                raise ValueError('Input or implementation changed; retain this run and create a new task')
            previous = state['config']
            if any(previous[k] != v for k, v in asdict(config).items() if k != 'max_calls') or config.max_calls < previous['max_calls']:
                raise ValueError('Resume must retain model settings and cannot reduce its cumulative call limit')
            if state.get('output'):
                from finmy.dataset import within
                saved = json.loads(within(directory, state['output']).read_text())
                if digest(saved) != state['graph_sha256']:
                    raise ValueError('Saved draft integrity mismatch')
                check_identity(saved, event)
            if state['status'] == 'completed':
                return state
        else:
            if resume:
                raise ValueError('No run exists to resume')
            state = {**identity, 'created_at':now(), 'calls':[], 'attempts':0, 'status':'ready'}
            write_json(directory / 'input.json', payload)
        for key in ('reason', 'error_type', 'error_detail', 'finished_at'):
            state.pop(key, None)
        state.update(config=asdict(config), status='running', attempts=state['attempts']+1)
        attempt = directory / 'attempts' / f"{state['attempts']:04d}"
        attempt.mkdir(parents=True, exist_ok=False)
        execution = Execution(directory, state, config, model or Model(config), attempt)
        execution.persist()
        subject = {'subject_id':event['person_id'], 'name':event['person_name'], 'aliases':event.get('aliases', []),
                   'scope':deepcopy(event['scope']), 'coverage_start':None, 'coverage_end':None}
        try:
            path = directory / 'canonical-checkpoint.json'
            checkpoint = json.loads(path.read_text()) if path.exists() else None
            facts, audit = build_canonical_facts(inputs, subject, infer=execution.infer, save=execution.save,
                                                 checkpoint=checkpoint, storyline_plan=event, output_language='English')
            execution.save({'offset_origin':'sample.content', 'sources':[
                {'document_id':document['document_id'], 'sample_id':sample['sample_id'],
                 'raw_data_id':sample['raw_data_id'], 'content_sha256':digest(sample['content'])}
                for document,sample in zip(facts['source_document'],payload['samples'])]}, 'SourceMap')
            if not facts['activity']:
                state.update(status='insufficient', reason='no_usable_facts')
                return state
            organizer = OrganizationResume(execution)
            plan = organize_person_plan(facts, {}, subject, 'English', organizer.infer, execution.save, confirmed_event=event)
            package, organization = apply_organization(facts, plan)
            grounding = ground_person_evidence(package)
            check_identity(package, event)
            execution.save(plan, 'PersonOrganizationPlan')
            execution.save(organization, 'PersonOrganizationReport')
            execution.save(grounding, 'EvidenceReport')
            incomplete = audit['status'] != 'completed' or organization['status'].startswith('partial')
            relation_path = attempt / 'PersonOrganization-RelationCandidates.json'
            if relation_path.exists() and json.loads(relation_path.read_text()).get('unreviewed_batches'):
                incomplete = True
            report = {'status':'partial' if incomplete else 'draft_requires_content_review',
                      'semantic_support_checked':False, 'event':deepcopy(event),
                      'canonical_status':audit['status'], 'organization':organization,
                      'unmatched_quote_count':grounding['unmatched_quote_count'],
                      'graph_sha256':digest(package), 'input_sha256':identity['input_sha256']}
            write_json(attempt / 'epg.json', package)
            write_json(attempt / 'checks.json', report)
            state.update(status='partial' if incomplete else 'completed', output=str((attempt/'epg.json').relative_to(directory)),
                         checks=str((attempt/'checks.json').relative_to(directory)), graph_sha256=digest(package),
                         review_required=True)
            from .rendering import save_gantt
            state['visualization'] = save_gantt(package, directory, attempt/'epg.json')
        except BuildLimit as exc:
            state.update(status='limit', reason=str(exc))
        except Exception as exc:
            state.update(status='failed', error_type=type(exc).__name__,
                         error_detail=str(exc)[:2000] if isinstance(exc, (ValueError, KeyError)) else type(exc).__name__)
        finally:
            state['finished_at'] = now()
            execution.persist()
        return deepcopy(state)
