"""Explicit Responses runner, separate from the unchanged offline launch route."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import queue
import re
import subprocess
import threading
import time
from .common import PROJECT, ROOT, command, digest, runtime_identity, source_hashes, write_json
from .e002_protocol import TOOLS, prompt, score_answer, world, world_hash
from .e002_memory import MemoryBridge
from .profiles import create_worker
from .responses_provider import ResponsesProvider, SpendLedger
from .sandbox import container_command, image_id, isolation_probe
from .supervisor import Budget, read_lines


def prepare(study_id, seed, model, gate):
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,38}', study_id):
        raise ValueError('invalid study slug')
    gate = Path(gate).resolve()
    gate_report = json.loads(gate.read_text())
    if not gate_report['pass']:
        raise ValueError('evaluator gate failed')
    current = source_hashes()
    if any(current.get(k) != v for k, v in gate_report['implementation_hashes'].items()):
        raise ValueError('gate code changed')
    study = ROOT/'runs'/study_id
    study.mkdir(exist_ok=False)
    w = world(seed)
    write_json(study/'oracle.json', w)
    img = image_id('python:3.11-slim-bookworm')
    reg = {'experiment': 'E-002', 'seed': seed, 'order': w['order'], 'world_sha256': world_hash(w),
           'model_requested': model, 'provider': 'https://185.170.154.169/v1',
           'provider_provenance': 'gateway-declared; backend not independently attested',
           'primary': 'exact revised rule and all C predictions; same rubric for C1/T1',
           'secondary': ['MCP lineage', 'retained rejected explanations', 'observations preserved', 'condition convergence', 'tokens, cost, latency'],
           'sample': 'one paired world; 6 independent worker containers and one separate smoke; no significance claim',
           'stopping': 'one attempt per stage, no retry; stop on infrastructure/model/protocol failure; no further series',
           'limits': {'concurrency': 1, 'worker_seconds': 90, 'run_seconds': 300, 'network_seconds': 660, 'max_output_tokens': 2048,
                      'post_limit': None, 'spend_limit_usd': None, 'authorization': 'user explicitly authorized API_KEY and no spending/request limits'},
           'gate': str(gate), 'gate_sha256': digest(gate), 'instructions': 'No research skills; no engineering prompt; synthetic inputs only',
           'analysis': 'describe paired binary outcomes and mechanisms; no H-003/H-004 proof, CI or p-value at n=1'}
    write_json(study/'registration.json', reg)
    journal = PROJECT/'docs/research/journal.jsonl'
    records = [json.loads(l) for l in journal.read_text(encoding='utf-8').splitlines()]
    previous = [r for r in records if r['entity_id'] == 'E-002'][-1]
    event = {'event_id': 'E-002/'+str(int(previous['event_id'].split('/')[1])+1), 'entity_id': 'E-002', 'kind': 'experiment',
             'at_utc': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'), 'status': 'registered', 'evidence_tier': 'proposal',
             'summary': 'C1/T1: finite-rule revision pilot preregistered before first model response',
             'details': {'design': reg, 'inputs': str(study/'oracle.json'), 'evaluation': reg['primary'], 'conditions': reg['limits'],
                         'outcome': None, 'limitations': reg['analysis']}, 'refs': ['H-003', 'H-004', str(study/'registration.json')],
             'provenance': {'actor': 'engineering-e002-20261019', 'model_actual': 'host-model-not-exposed', 'source_snapshot': str(study/'manifest.json')},
             'supersedes': previous['event_id']}
    with journal.open('a', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(event, ensure_ascii=False)+'\n')
    hashes = source_hashes()
    runs, run_manifests = {}, {}
    for condition in ('C1', 'T1'):
        run = ROOT/'runs'/(study_id+'-'+condition.lower())
        run.mkdir(exist_ok=False)
        for part in ('supervisor', 'evaluator', 'workers', 'state'):
            (run/part).mkdir()
        instances = {}
        for stage in 'ABC':
            worker = run/'workers'/stage
            create_worker(worker, stage, 'none')
            # Only this stage's synthetic prompt enters this worker.
            write_json(worker/'repo/PROMPT.txt', {'prompt': prompt(w, condition, stage)})
            instances[stage] = {'actor': run.name+':'+stage, 'initial_hashes': source_hashes(worker)}
        write_json(run/'manifest.json', {'run_id': run.name, 'study': str(study), 'condition': condition,
            'execution_mode': 'responses', 'instances': instances, 'code_hashes': hashes, 'image': img,
            'runtime': runtime_identity(), 'model_requested': model, 'active_skills': [], 'tools': TOOLS})
        if not isolation_probe(img, run/'workers/A', run/'supervisor/isolation.json')['isolation_pass']:
            raise ValueError('fresh E-002 worker isolation probe failed')
        runs[condition] = str(run)
        run_manifests[condition] = digest(run/'manifest.json')
    write_json(study/'manifest.json', {'study_id': study_id, 'registration_sha256': digest(study/'registration.json'),
        'oracle_sha256': digest(study/'oracle.json'), 'code_hashes': hashes, 'runtime': runtime_identity(), 'runs': runs,
        'run_manifest_sha256': run_manifests,
        'model': model, 'image': img, 'gate_sha256': digest(gate), 'tool_schema_sha256': __import__('hashlib').sha256(json.dumps(TOOLS, sort_keys=True).encode()).hexdigest()})
    return {'study': str(study), 'registered': True, 'models_started': 0}


def load(study):
    study = Path(study).resolve(strict=True)
    if study.parent != (ROOT/'runs').resolve():
        raise ValueError('study outside research contour')
    manifest = json.loads((study/'manifest.json').read_text())
    if manifest['code_hashes'] != source_hashes() or manifest['runtime'] != runtime_identity():
        raise ValueError('source/runtime changed; no reuse of registered live run')
    if manifest['registration_sha256'] != digest(study/'registration.json') or manifest['oracle_sha256'] != digest(study/'oracle.json'):
        raise ValueError('immutable registration or inputs changed')
    reg = json.loads((study/'registration.json').read_text())
    if manifest['gate_sha256'] != digest(reg['gate']):
        raise ValueError('gate evidence changed')
    if any(digest(Path(path)/'manifest.json') != manifest['run_manifest_sha256'][c] for c, path in manifest['runs'].items()):
        raise ValueError('condition manifest changed')
    return study, manifest, reg


def provider(study, manifest, authorize, unbounded):
    if not authorize or not unbounded:
        raise PermissionError('explicit external-run and unbounded-spend authorization required for this registration')
    start = study/'network-start.json'
    if not start.exists():
        with start.open('x') as f:
            json.dump({'at': time.time()}, f)
    if time.time()-json.loads(start.read_text())['at'] >= 660:
        raise RuntimeError('registered network time exhausted')
    ledger = SpendLedger(study/'provider-ledger.sqlite3', unbounded=True)
    return ResponsesProvider('https://185.170.154.169/v1', manifest['model'], ledger,
                             study/'provider.jsonl', authorize=True)


def smoke(study, p):
    with (study/'smoke-started').open('x') as f:
        f.write('one smoke context; not part of scientific sample\n')
    tools = [{'type': 'function', 'name': 'echo', 'description': 'Return the supplied integer.',
              'parameters': {'type': 'object', 'properties': {'value': {'type': 'integer'}}, 'required': ['value'], 'additionalProperties': False}}]
    history = [{'role': 'user', 'content': 'Call echo with value 17. After the tool returns, reply only with JSON {"value":17}.'}]
    response = p.respond('compatibility-smoke', history, tools)
    calls = [x for x in response['output'] if x.get('type') == 'function_call']
    if len(calls) != 1 or calls[0]['name'] != 'echo' or json.loads(calls[0]['arguments']) != {'value': 17}:
        raise ValueError('smoke function call incompatible')
    history.extend(response['output'])
    history.append({'type': 'function_call_output', 'call_id': calls[0]['call_id'], 'output': '{"value":17}'})
    final = p.respond('compatibility-smoke', history, tools)
    text = ''.join(c.get('text', '') for i in final['output'] if i.get('type') == 'message' for c in i.get('content', []))
    if json.loads(text) != {'value': 17}:
        raise ValueError('smoke final JSON incompatible')
    report = {'pass': True, 'scientific_sample': False, 'model_returned': final['model'], 'responses': 2}
    write_json(study/'smoke.json', report)
    return report


def run_worker(study, manifest, condition, stage, p):
    if not json.loads((study/'smoke.json').read_text())['pass']:
        raise ValueError('compatibility smoke required')
    run = Path(manifest['runs'][condition])
    order = json.loads((study/'registration.json').read_text())['order']
    sequence = [(c, s) for c in order for s in 'ABC']
    index = sequence.index((condition, stage))
    if index:
        prior_c, prior_s = sequence[index-1]
        prior = Path(manifest['runs'][prior_c])/'supervisor'/f'{prior_s}-result.json'
        if not prior.exists() or json.loads(prior.read_text())['status'] != 'completed':
            raise ValueError('registered condition/stage order not completed')
    config = json.loads((run/'manifest.json').read_text())
    if config['code_hashes'] != manifest['code_hashes'] or config['image'] != manifest['image'] or config['model_requested'] != manifest['model']:
        raise ValueError('condition manifest differs from study')
    worker = run/'workers'/stage
    if source_hashes(worker) != config['instances'][stage]['initial_hashes']:
        raise ValueError('worker inputs changed')
    if stage in 'BC' and json.loads((run/'supervisor'/f'{chr(ord(stage)-1)}-result.json').read_text())['status'] != 'completed':
        raise ValueError('previous stage failed')
    budget = Budget(run/'supervisor/budget.sqlite3', {'max_launches': 3, 'max_concurrency': 1, 'total_seconds': 300})
    study_budget = Budget(study/'launches.sqlite3', {'max_launches': 6, 'max_concurrency': 1, 'total_seconds': 660})
    study_budget.reserve(condition+stage)
    budget.reserve(stage)
    name = 'continuum-'+run.name+'-'+stage.lower()
    argv = container_command(manifest['image'], name, worker, ['/runtime/e002_worker.py'])
    start = time.monotonic()
    proc, bridge = None, None
    report = {'status': 'failed', 'mode': 'responses', 'model_requested': manifest['model'], 'model_actual': None,
              'exit_status': None, 'failure': None, 'actor': run.name+':'+stage}
    with (run/'supervisor'/f'{stage}.jsonl').open('w', encoding='utf-8') as log, (run/'supervisor'/f'{stage}.stderr.txt').open('w', encoding='utf-8') as err:
        try:
            w = json.loads((study/'oracle.json').read_text())
            observations = w['observations_a'] if stage == 'A' else [w['observation_b']] if stage == 'B' else []
            bridge = MemoryBridge(run, stage, observations, log, manifest['model'])
            log.write(json.dumps({'event': 'command_execution', 'command': argv, 'mode': 'responses'})+'\n'); log.flush()
            proc = subprocess.Popen(argv, cwd=PROJECT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, text=True, encoding='utf-8')
            inbox = queue.Queue(maxsize=128)
            threading.Thread(target=read_lines, args=(proc.stdout, inbox, 'worker'), daemon=True).start()
            final = None
            while True:
                remaining = min(90-(time.monotonic()-start), budget.remaining(),
                                660-(time.time()-json.loads((study/'network-start.json').read_text())['at']))
                if remaining <= 0 or (study/'STOP').exists() or (run/'STOP').exists():
                    raise TimeoutError('deadline or operator STOP')
                _, line = inbox.get(timeout=remaining)
                if line is None:
                    break
                if len(line) > 262144:
                    raise ValueError('worker message too large')
                event = json.loads(line)
                if event['channel'] == 'responses':
                    response = p.respond(run.name+':'+stage, event['history'], TOOLS, timeout=min(30, remaining))
                    report['model_actual'] = response['model']
                elif event['channel'] == 'tool':
                    response = bridge.call(event['name'], event['arguments'])
                elif event['channel'] == 'worker':
                    log.write(json.dumps(event)+'\n'); log.flush()
                    if final is not None:
                        raise ValueError('multiple final responses')
                    final = json.loads(event['line'])
                    continue
                else:
                    raise PermissionError('unknown worker channel')
                proc.stdin.write(json.dumps({'result': response})+'\n'); proc.stdin.flush()
            report['exit_status'] = proc.wait(timeout=5)
            if report['exit_status'] != 0 or final is None:
                raise RuntimeError('worker failed without valid final result')
            bridge.finish(final)
            report['status'] = 'completed'
            write_json(run/'supervisor'/f'{stage}-answer.json', final)
        except Exception as exc:
            report['failure'] = type(exc).__name__+': '+str(exc)
        finally:
            if proc is not None and proc.poll() is None:
                command(['docker', 'rm', '-f', name], timeout=15)
                proc.wait(timeout=10)
            if proc is not None:
                report['exit_status'] = proc.returncode
                proc.stdin.close(); proc.stdout.close()
            if bridge:
                bridge.close()
    report['duration_seconds'] = time.monotonic()-start
    budget.finish(stage, report['status'])
    study_budget.finish(condition+stage, report['status'])
    write_json(run/'supervisor'/f'{stage}-result.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'metadata', 'smoke', 'run'])
    parser.add_argument('--study', type=Path)
    parser.add_argument('--study-id')
    parser.add_argument('--seed', type=int, default=2026101903)
    parser.add_argument('--model', default='gpt-6-sol')
    parser.add_argument('--gate', type=Path)
    parser.add_argument('--condition', choices=['C1', 'T1'])
    parser.add_argument('--stage', choices=list('ABC'))
    parser.add_argument('--authorize-responses', action='store_true')
    parser.add_argument('--unbounded-spend', action='store_true')
    args = parser.parse_args()
    if args.action == 'prepare':
        result = prepare(args.study_id, args.seed, args.model, args.gate)
    else:
        study, manifest, reg = load(args.study)
        p = provider(study, manifest, args.authorize_responses, args.unbounded_spend)
        if args.action == 'metadata':
            ids = p.models()
            result = {'available': manifest['model'] in ids, 'models': ids, 'provenance': reg['provider_provenance']}
            write_json(study/'metadata.json', result)
        else:
            if not json.loads((study/'metadata.json').read_text())['available']:
                raise ValueError('registered model not listed by gateway; do not probe alternatives')
            result = smoke(study, p) if args.action == 'smoke' else run_worker(study, manifest, args.condition, args.stage, p)
    print(json.dumps(result, ensure_ascii=False))
    if result.get('pass') is False or result.get('status') == 'failed' or result.get('available') is False:
        raise SystemExit(2)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, PermissionError, FileNotFoundError) as exc:
        print(json.dumps({'status': 'blocked', 'reason': str(exc)}))
        raise SystemExit(2)
