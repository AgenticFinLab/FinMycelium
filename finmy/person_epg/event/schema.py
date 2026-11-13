"""Machine-readable contracts for docs/person-event-builder (no model or I/O)."""
from copy import deepcopy

GRAPH_VERSION = 'person-event-1.0'
FACTS_VERSION = 'person-event-facts-1.0'
RELATION_TYPES = ('precedes', 'overlaps', 'order_unknown', 'responds_to', 'enables',
                  'triggers', 'prevents', 'continues', 'resumes', 'interrupted_by', 'joint_action')
COLLECTION_IDS = {'entities': 'entity_id', 'stages': 'stage_id', 'phases': 'phase_id',
                  'actions': 'action_id', 'relations': 'relation_id', 'contexts': 'context_id',
                  'sources': 'source_id', 'evidence': 'evidence_id', 'relation_candidates': 'candidate_id'}
TEXT = {'type': 'string', 'minLength': 1, 'pattern': r'\S'}
STRING = {'type': 'string'}
NULL_TEXT = {'anyOf': [TEXT, {'type': 'null'}]}
POINTER = {'type': 'string', 'pattern': r'^(?:/(?:[^~]|~[01])*)*$'}


def enum(*values):
    return {'enum': list(values)}


def ref(name):
    return {'$ref': '#/$defs/' + name}


def array(item, **kwargs):
    return {'type': 'array', 'items': item, **kwargs}


def obj(properties, required=None):
    return {'type': 'object', 'properties': properties,
            'required': list(properties) if required is None else required, 'additionalProperties': False}


def semantic(properties, required=None):
    return obj({**properties, 'gaps': array(ref('Gap')), 'conflicts': array(ref('Conflict'))},
               list(properties) if required is None else required)


DEFS = {}
DEFS['ObjectRef'] = obj(dict(collection=enum('person', 'storyline', 'event', 'entities', 'stages',
                                           'phases', 'actions', 'relations', 'contexts'),
                            object_id=TEXT, field=POINTER))
DEFS['StepRef'] = deepcopy(DEFS['ObjectRef'])
DEFS['StepRef']['properties']['collection']['enum'].append('relation_candidates')
DEFS['Time'] = obj(dict(text=NULL_TEXT, kind=enum('occurrence_window', 'duration', 'unknown'),
                       start={'type': ['string', 'null'], 'format': 'date'},
                       end={'type': ['string', 'null'], 'format': 'date'},
                       start_precision=enum('year', 'month', 'day', 'unknown'),
                       end_precision=enum('year', 'month', 'day', 'unknown')))
DEFS['Support'] = obj(dict(target=POINTER, mode=enum('O', 'A', 'I'), evidence_ids=array(TEXT, uniqueItems=True),
                          premise_refs=array(ref('ObjectRef')), reason=TEXT), ['target', 'mode', 'evidence_ids'])
DEFS['Support']['allOf'] = [
    {'if': {'properties': {'mode': {'const': 'I'}}},
     'then': {'required': ['reason'], 'anyOf': [
         {'properties': {'evidence_ids': {'minItems': 1}}},
         {'required': ['premise_refs'], 'properties': {'premise_refs': {'minItems': 1}}}]},
     'else': {'properties': {'evidence_ids': {'minItems': 1}}}}]
DEFS['Gap'] = obj(dict(target=POINTER, reason=TEXT))
DEFS['Conflict'] = obj(dict(target=POINTER, alternatives=array(obj(
    dict(value={}, support=array(ref('Support')), gaps=array(ref('Gap'))), ['value', 'support']), minItems=2),
    reason=TEXT, related_refs=array(ref('ObjectRef'))), ['target', 'alternatives', 'reason'])
DEFS['Scope'] = obj(dict(period=STRING, include=TEXT, exclude=STRING))
DEFS['Person'] = obj(dict(person_id=TEXT, name=TEXT, aliases=array(STRING), event_ids=array(TEXT, minItems=1, maxItems=1)))
DEFS['Storyline'] = obj(dict(storyline_id=TEXT, person_id=TEXT, name=TEXT))
DEFS['Event'] = semantic(dict(event_id=TEXT, person_id=TEXT, storyline_id=TEXT, name=TEXT,
                              scope=ref('Scope'), time=ref('Time'), summary=TEXT, support=array(ref('Support'))))
DEFS['Entity'] = semantic(dict(entity_id=TEXT, name=TEXT, type=enum('person', 'organization', 'other'), aliases=array(STRING)))
DEFS['Stage'] = semantic(dict(stage_id=TEXT, event_id=TEXT, name=TEXT, description=TEXT,
                              time=ref('Time'), boundary_reason=TEXT, support=array(ref('Support'))))
DEFS['Phase'] = semantic(dict(phase_id=TEXT, stage_id=TEXT, name=TEXT, description=TEXT, time=ref('Time'),
                              boundary_reason=TEXT, support=array(ref('Support')), baseline_context_refs=array(ref('ContextRef'))))
DEFS['Context'] = semantic(dict(context_id=TEXT, category=enum('environment', 'relations', 'person_state'),
                                description=TEXT, entity_refs=array(TEXT, uniqueItems=True), time=ref('Time'),
                                perspective=enum('world', 'belief', 'post_hoc', 'unknown'), support=array(ref('Support'))))
DEFS['ContextRef'] = semantic(dict(context_ref_id=TEXT, context_id=TEXT,
    relation_type=enum('participation', 'condition', 'trigger', 'constraint', 'result', 'knowledge-source'),
    support=array(ref('Support')), entity_id=TEXT, role=TEXT, interaction_type=TEXT, qualification=TEXT),
    ['context_ref_id', 'context_id', 'relation_type', 'support'])
DEFS['Exclusion'] = obj(dict(context_ref_id=TEXT, reason=TEXT, support=array(ref('Support'), minItems=1)))
DEFS['Exclusion']['properties']['support']['items'] = {'allOf': [ref('Support'),
    {'properties': {'target': enum('/context_ref_id', '/reason')}}]}
DEFS['Action'] = semantic(dict(action_id=TEXT, name=TEXT, description=TEXT,
    actor=obj(dict(entity_id=TEXT, capacity=enum('personal', 'official', 'delegated', 'unknown'),
                   role=TEXT, on_behalf_of=TEXT), ['entity_id', 'capacity']),
    time=ref('Time'), phase_id=TEXT, support=array(ref('Support')), action_type=TEXT,
    object=obj(dict(description=TEXT, entity_refs=array(TEXT, uniqueItems=True))),
    delta_context_refs=array(ref('ContextRef')), baseline_context_exclusions=array(ref('Exclusion'))),
    ['action_id', 'name', 'description', 'actor', 'time', 'phase_id', 'support'])
DEFS['Relation'] = semantic(dict(relation_id=TEXT, from_action_id=TEXT, to_action_id=TEXT,
    type=enum(*RELATION_TYPES), basis=enum('observed', 'asserted', 'inferred', 'derived'),
    support=array(ref('Support')), description=TEXT),
    ['relation_id', 'from_action_id', 'to_action_id', 'type', 'basis', 'support'])
DEFS['Source'] = obj(dict(source_id=TEXT, title=NULL_TEXT, url=NULL_TEXT, origin=NULL_TEXT,
    published_at=NULL_TEXT, retrieved_at=NULL_TEXT, source_type=TEXT, content_status=TEXT),
    ['source_id', 'title', 'url', 'origin', 'published_at', 'retrieved_at'])
DEFS['Source']['anyOf'] = [{'properties': {'url': TEXT}}, {'properties': {'origin': TEXT}}]
DEFS['Evidence'] = obj(dict(evidence_id=TEXT, sample_id=TEXT, source_id=TEXT, quote=TEXT,
    start={'type': ['integer', 'null'], 'minimum': 0}, end={'type': ['integer', 'null'], 'minimum': 0},
    location_status=enum('matched', 'ambiguous', 'unmatched'),
    sample_sha256={'type': 'string', 'pattern': '^[0-9a-f]{64}$'}, locator={'type': 'object'}),
    ['evidence_id', 'sample_id', 'source_id', 'quote', 'start', 'end', 'location_status', 'sample_sha256'])
DEFS['Evidence']['allOf'] = [{'if': {'properties': {'location_status': {'const': 'matched'}}},
    'then': {'properties': {'start': {'type': 'integer'}, 'end': {'type': 'integer'}}},
    'else': {'properties': {'start': {'type': 'null'}, 'end': {'type': 'null'}}}}]
DEFS['Candidate'] = semantic(dict(candidate_id=TEXT, from_action_id=NULL_TEXT, to_action_id=NULL_TEXT,
    type=enum(*RELATION_TYPES, None), description=TEXT, support=array(ref('Support'))))
DEFS['Pending'] = obj(dict(refs=array(ref('StepRef')), reason=TEXT, evidence_ids=array(TEXT)))
DEFS['Lineage'] = obj(dict(operation=enum('keep', 'merge', 'split', 'exclude', 'pending'),
    input_refs=array(ref('StepRef')), output_refs=array(ref('StepRef')), reason=TEXT, step_id=TEXT))


def schema_for(name):
    return {'$schema': 'https://json-schema.org/draft/2020-12/schema', '$defs': deepcopy(DEFS), **ref(name)}


GRAPH_SCHEMA = {**obj(dict(schema_version={'const': GRAPH_VERSION}, person=ref('Person'),
    storyline=ref('Storyline'), event=ref('Event'), entities=array(ref('Entity')),
    stages=array(ref('Stage'), minItems=1), phases=array(ref('Phase'), minItems=1),
    actions=array(ref('Action')), relations=array(ref('Relation')), contexts=array(ref('Context')),
    sources=array(ref('Source')), evidence=array(ref('Evidence')))),
    '$schema': 'https://json-schema.org/draft/2020-12/schema', '$defs': deepcopy(DEFS)}
PARTIAL_SCHEMA = deepcopy(GRAPH_SCHEMA)
for key in ('stages', 'phases'):
    PARTIAL_SCHEMA['properties'][key].pop('minItems')
PARTIAL_SCHEMA['$defs']['Action']['properties']['phase_id'] = NULL_TEXT
PARTIAL_SCHEMA['$defs']['Event']['required'] = ['event_id', 'person_id', 'storyline_id', 'name', 'scope']
FACTS_SCHEMA = deepcopy(PARTIAL_SCHEMA)
FACTS_SCHEMA['properties']['schema_version'] = {'const': FACTS_VERSION}
for key in ('stages', 'phases', 'relations'):
    FACTS_SCHEMA['properties'].pop(key)
FACTS_SCHEMA['properties'].update(relation_candidates=array(ref('Candidate')), pending=array(ref('Pending')), lineage=array(ref('Lineage')))
FACTS_SCHEMA['required'] = list(FACTS_SCHEMA['properties'])
