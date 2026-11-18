"""Frozen organization snapshots and isolated relation-stage experiments."""
import argparse
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import time

from finmy.search.summary import directory_lock
from .records import IdMap, fingerprint, validate_input, sha256, json_bytes
from .runtime import EventBuildConfig, Execution, LimitReached, PauseRequested, write_json
from .validation import check_graph

FORMAT = 'person-relation-snapshot-1'


def capture(construction):
    """Called before the first relation task; retain upstream accounting separately."""
    run = construction.run
    construction.sync_coverage()
    body = dict(format=FORMAT, input=run.payload, config=asdict(run.config),
        facts=construction.facts, graph=construction.graph,
        coverage=construction.coverage, reports=construction.reports,
        id_map=construction.ids.mapping,
        origin=dict(run_id=run.state['run_id'], code_sha256=run.state['code_sha256'],
                    input_sha256=run.state['input_sha256'],
                    calls=[c for c in run.state['calls'] if c['task_id'].startswith(('extract.', 'consolidate.', 'organize'))],
                    reads=[r for r in run.state['reads'] if r['task_id'].startswith(('extract.', 'consolidate.', 'organize'))]))
    envelope = dict(snapshot=deepcopy(body), fingerprint=fingerprint(body))
    path, digest = run.save('organization-snapshot.json', envelope)
    run.state.update(organization_snapshot=path, organization_snapshot_sha256=digest)
    run.persist()
    return envelope


def load_snapshot(path):
    envelope = json.loads(Path(path).read_text(encoding='utf-8'))
    body = envelope['snapshot']
    if body.get('format') != FORMAT or fingerprint(body) != envelope['fingerprint']:
        raise ValueError('Snapshot format or fingerprint mismatch')
    if sha256(json_bytes(body['input'])) != body['origin']['input_sha256']:
        raise ValueError('Snapshot input differs from recorded origin')
    validate_input(body['input'])
    EventBuildConfig(**body['config'])
    for key in ('facts', 'graph'):
        if not check_graph(body[key], body['input'])['valid']:
            raise ValueError('Invalid upstream ' + key)
    if body['graph']['relations']:
        raise ValueError('Snapshot must precede relation construction')
    if (not body['coverage'] or any(r['body_status'] != 'processed' or
            r['proposal_status'] != 'resolved' for r in body['coverage'])
            or body['facts']['pending']):
        raise ValueError('Upstream extraction or consolidation is incomplete')
    from .build import Construction
    if any(Construction.outstanding(r)['rejected'] or Construction.outstanding(r)['pending']
           for r in body['reports']):
        raise ValueError('Upstream proposals remain unresolved')
    if {a['action_id'] for a in body['facts']['actions']} != {a['action_id'] for a in body['graph']['actions']}:
        raise ValueError('Snapshot Action identities differ')
    if not body['graph']['actions']:
        raise ValueError('Snapshot has no Actions')
    return envelope


def run_relations(snapshot, directory, *, config=None, model=None, allow_network=False, resume=False):
    """Start with zero downstream usage; resume only this exact experimental run."""
    from .build import Construction
    envelope = load_snapshot(snapshot)
    body = envelope['snapshot']
    directory = Path(directory).resolve()
    settings = (json.loads((directory / 'config.json').read_text()) if resume
                else deepcopy(body['config']))
    if not resume:
        settings['final_repair_rounds'] = 0
    settings.update(config or {})
    config = EventBuildConfig(**settings)
    # Stage isolation must not allow final organization repair to alter the frozen input.
    if config.final_repair_rounds:
        raise ValueError('Isolated relation experiments require final_repair_rounds=0')
    if model is None and not allow_network:
        raise PermissionError('Model execution requires --allow-model')
    directory = Path(directory).resolve()
    if directory == Path(snapshot).resolve() or directory in Path(snapshot).resolve().parents:
        raise ValueError('Use a separate experiment directory')
    if not resume:
        directory.mkdir(parents=True, exist_ok=False)
    elif not directory.is_dir():
        raise ValueError('No experiment exists to resume')
    provenance = dict(experiment='relations', snapshot_fingerprint=envelope['fingerprint'])
    with directory_lock(directory):
        if model is None:
            from ..building.model_transport import StreamingModel
            model = StreamingModel(config)
        if resume:
            retained = load_snapshot(directory / 'organization-snapshot.json')
            if retained != envelope:
                raise ValueError('Experiment snapshot changed')
        execution = Execution(directory, body['input'], config, model,
                              resume=resume, provenance=provenance)
        if not resume:
            write_json(directory / 'organization-snapshot.json', envelope)
            execution.state['id_map'] = deepcopy(body['id_map'])
        builder = Construction(execution)
        builder.facts, builder.graph = deepcopy(body['facts']), deepcopy(body['graph'])
        builder.coverage, builder.reports = deepcopy(body['coverage']), deepcopy(body['reports'])
        builder.ids = IdMap(execution.state['id_map'])
        started = time.monotonic()
        status, reason = 'finished', None
        try:
            builder.relate()
        except PauseRequested as exc:
            status, reason = 'paused', str(exc)
            (directory / 'pause_requested').unlink(missing_ok=True)
        except LimitReached as exc:
            status, reason = 'limit', str(exc)
        except (KeyboardInterrupt, SystemExit):
            builder.finish('interrupted', 'Experiment interrupted')
            raise
        except Exception as exc:
            status, reason = 'failed', type(exc).__name__
        state = builder.finish(status, reason)
        # Raw usage is retained; absent usage is never presented as zero cost.
        calls = state['calls']
        summary = dict(snapshot_fingerprint=envelope['fingerprint'],
            source_code_sha256=body['origin']['code_sha256'],
            experiment_code_sha256=state['code_sha256'], config=asdict(config),
            upstream_calls=len(body['origin']['calls']), stage_calls=len(calls),
            stage_reads=len(state['reads']),
            stage_read_chars=sum(r['chars'] for r in state['reads']),
            stage_model_seconds=sum(c.get('duration_seconds', 0) for c in calls), usage=[c.get('usage') for c in calls],
            calls_without_usage=sum(c.get('usage') is None for c in calls),
            invocation_elapsed_seconds=time.monotonic() - started,
            execution_status=status, result_status=state['result_status'],
            relation_count=len(builder.graph['relations']), graph_path=state['output'],
            checks_path=state['checks'], discovery_path=state['relation_discovery'], semantic_review_required=True)
        write_json(directory / 'relation-summary.json', summary)
        return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name, input_name in [('prepare', 'input'), ('run', 'snapshot')]:
        sub = commands.add_parser(name)
        sub.add_argument(input_name, type=Path)
        sub.add_argument('--output', required=True, type=Path)
        sub.add_argument('--config', type=Path, help='JSON configuration; run merges overrides into snapshot settings')
        sub.add_argument('--allow-model', action='store_true')
        if name == 'run':
            sub.add_argument('--resume', action='store_true')
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text()) if args.config else None
    try:
        if args.command == 'prepare':
            from .build import run_event
            if args.output.exists():
                raise ValueError('Preparation requires a new output directory')
            state = run_event(json.loads(args.input.read_text()), args.output, config,
                allow_network=args.allow_model, stop_after_organization=True)
            print(json.dumps({k: state.get(k) for k in ('execution_status', 'organization_snapshot', 'reason')}))
            if not state.get('organization_snapshot'):
                return 1
            load_snapshot(args.output / state['organization_snapshot'])
            return 0
        state = run_relations(args.snapshot, args.output, config=config,
                              allow_network=args.allow_model, resume=args.resume)
        print(json.dumps({k: state.get(k) for k in ('execution_status', 'result_status', 'output', 'reason')}))
        return 0 if state['execution_status'] == 'finished' else 1
    except (ValueError, OSError, KeyError, PermissionError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    raise SystemExit(main())
