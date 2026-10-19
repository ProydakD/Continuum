"""Frozen E-004 runner: genuine isolated workers and real read-only MCP retrieval."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import queue
import re
import subprocess
import threading
import time
from .common import ROOT, PROJECT, command, digest, runtime_identity, source_hashes, write_json
from .e002 import smoke
from .e002_memory import MemoryBridge
from .e003 import Jobs, implementation_hashes, job_id
from .e004_protocol import BUDGET, TOOLS, corpus, memory, prompt
from .profiles import create_worker
from .responses_provider import ResponsesProvider, SpendLedger
from .sandbox import container_command, image_id, isolation_probe
from .supervisor import read_lines


class ReceptionBridge(MemoryBridge):
    def seed(self, payload):
        if self.tool('bootstrap')['open_tasks']:
            raise ValueError('fresh memory database required')
        raw = json.dumps(payload).encode('utf-8')
        if len(raw) != BUDGET:
            raise ValueError('incorrect byte budget')
        task = self.tool('create_task', title='Synthetic known-correct rule', objective='Read retained memory',
                         next_step='read', request_key='e004')
        task = self.tool('claim_task', task_id=task['id'], expected_revision=task['revision'], lease_seconds=600)
        sha = hashlib.sha256(raw).hexdigest()
        self.tool('put_object', content_base64=base64.b64encode(raw).decode(), sha256=sha, media_type='application/json')
        self.tool('checkpoint_task', task_id=task['id'], expected_revision=task['revision'], release=True,
                  result=json.dumps({'object_sha256': sha}), next_step='read')

    def call(self, name, arguments):
        if name != 'read_memory' or arguments != {} or self.read:
            raise PermissionError('only one read_memory({}) is registered')
        tasks = self.tool('bootstrap')['open_tasks']
        if len(tasks) != 1:
            raise ValueError('ambiguous memory')
        task = self.tool('get_task', task_id=tasks[0]['id'])
        sha = json.loads(task['result'])['object_sha256']
        obj = self.tool('get_object', sha256=sha)
        raw = base64.b64decode(obj['content_base64'], validate=True)
        if hashlib.sha256(raw).hexdigest() != sha or len(raw) != BUDGET:
            raise ValueError('memory integrity/budget mismatch')
        self.read = True
        return json.loads(raw)


def journal(status, summary, details, refs, tier='proposal'):
    path = PROJECT/'docs/research/journal.jsonl'
    prior = [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if json.loads(s)['entity_id'] == 'E-004']
    event = {'event_id': f'E-004/{len(prior)+1}', 'entity_id': 'E-004', 'kind': 'experiment',
             'at_utc': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'), 'status': status,
             'evidence_tier': tier, 'summary': summary, 'details': details, 'refs': refs,
             'provenance': {'actor': 'engineering-e004-20261019', 'model_actual': 'host-model-not-exposed' if tier == 'proposal' else 'gpt-6-sol (gateway-declared)',
                            'source_snapshot': 'e004-001/manifest.json'},
             'supersedes': prior[-1]['event_id'] if prior else None}
    with path.open('a', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(event, ensure_ascii=False)+'\n')


def prepare(identity, gate, fixture=False):
    if not re.fullmatch(r'e004-[a-z0-9-]{1,24}', identity):
        raise ValueError('invalid study id')
    verified = json.loads(Path(gate).read_text())
    if not verified['pass'] or verified['implementation_hashes'] != implementation_hashes():
        raise ValueError('fresh offline gate required')
    study = ROOT/'runs'/identity
    study.mkdir(exist_ok=False)
    inputs = corpus()
    if fixture:
        inputs['worlds'] = inputs['worlds'][:1]
        inputs['schedule'] = [j for j in inputs['schedule'] if j['world'] == 'w01' and j['stage'] == 'r1']
    write_json(study/'oracle.json', inputs)
    reg = {'experiment': 'E-004', 'registered_at': time.time(), 'fixture': fixture,
        'sample': {'worlds': len(inputs['worlds']), 'families': ['linear', 'residue', 'switch'],
                   'replicates': 2 if not fixture else 1, 'conditions': ['C1', 'T1'], 'branches': ['intact', 'partial', 'empty'],
                   'contexts': len(inputs['schedule']), 'seed': inputs['seed']},
        'hypotheses': ['H-003: explicit structured representation may improve correct reception.',
                       'H-004: equal semantic content in ordinary prose may be sufficient.'],
        'design': 'Controlled known-correct scripted upstream memory, not model-authored A/B. Same reader prompt and tools. C1 prose vs T1 JSON strings. Exactly 512 UTF-8 bytes of complete serialized read result including envelope and inert whitespace, for every condition/branch. Same semantic parameters; no automatic observations/history outside this budget.',
        'intervention': 'One additive exception at one of 81 domain points. Partial: remove only exception block BEFORE writing fresh Continuum DB; common block retained. Empty: both blocks absent. Original known-correct source retained only in trusted oracle. This is selective information loss, not storage corruption or endogenous forgetting. No intervention labels/world IDs in model prompt.',
        'primary': 'Intact rule-field reconstruction success T1 minus C1, averaged over 2 fresh contexts within each of 12 worlds. Arithmetic explicitly excluded from primary.',
        'secondary': ['complete arithmetic accuracy', 'partial calibrated answer (known values correct, unknown delta/dependent values null)', 'empty refusal', 'rule-correct but arithmetic-wrong cases', 'bytes and tokens'],
        'analysis': 'World is unit; 10000 family-stratified paired bootstrap world means, seed 2026101905, percentile 95%; exact two-sided paired sign-flip mean statistic over 4096 world assignments. Positive evidence requires difference>=0.10 and lower CI>0. Secondary descriptive only. Failures remain denominator. No equivalence claim from null/ceiling result.',
        'replication': 'Two fresh contexts, no shared history. API adapter has no seed parameter; not controlled model-seed replication or independent models. No claim of 144 independent worlds.',
        'model': 'gpt-6-sol', 'provider': 'https://185.170.154.169/v1', 'provenance': 'gateway-declared, not independently attested weights',
        'limits': {'worker_seconds': 180, 'request_seconds': 60, 'max_output_tokens': 2048, 'concurrency': 1,
                   'series_seconds': 21600, 'memory_bytes': BUDGET, 'requests': None, 'spend_usd': None, 'worker_retries': 0},
        'recovery': 'Terminal workers never rerun. On transient 502/503/504/429 or socket timeout/connection error, keep failure, check same-model catalog after 30,120,300 seconds; first successful catalog containing frozen model allows only NEXT pending worker. Three unsuccessful checks, auth/TLS, model mismatch, leakage, code/input change or STOP abort series. Catalog recovery does not guarantee next response. Smoke once; smoke failure aborts without retry. No replacement worlds/model search/outcome-based stopping.',
        'authorization': 'User authorized this experiment and API without limits; local commit only, no push.',
        'limitations': ['Controlled reception only: cannot estimate quality of model-authored memory.', 'Padding equalizes serialized bytes, not tokenizer tokens or semantic redundancy.', 'Small finite synthetic corpus; ceiling possible; no universal superiority/equivalence inference.', 'Partial absence is observable; not covert tamper detection.', 'Replicates share world and provider, not independently attested models.'],
        'tools': TOOLS, 'schedule': inputs['schedule'], 'image': image_id('python:3.11-slim-bookworm'),
        'implementation_hashes': implementation_hashes(), 'runtime': runtime_identity(), 'gate_sha256': digest(gate),
        'oracle_sha256': digest(study/'oracle.json')}
    write_json(study/'registration.json', reg)
    unit_hashes = {}
    for job in inputs['schedule']:
        run = study/'units'/job_id(job)
        for part in ('supervisor', 'state', 'workers'):
            (run/part).mkdir(parents=True)
        worker = run/'workers/C'
        create_worker(worker, 'C', 'none')
        world = next(w for w in inputs['worlds'] if w['id'] == job['world'])
        write_json(worker/'repo/PROMPT.txt', {'prompt': prompt(world)})
        unit_hashes[job_id(job)] = source_hashes(worker)
    first = study/'units'/job_id(inputs['schedule'][0])
    if not isolation_probe(reg['image'], first/'workers/C', study/'isolation.json')['isolation_pass']:
        raise ValueError('fresh OS isolation check failed')
    write_json(study/'manifest.json', {'registration_sha256': digest(study/'registration.json'), 'unit_hashes': unit_hashes})
    Jobs(study/'jobs.sqlite3', inputs['schedule'])
    if not fixture:
        journal('registered', 'Equal-byte controlled memory reception; rule retention separated from arithmetic, preregistered before API',
                {'design': reg['design'], 'inputs': str(study/'oracle.json'), 'evaluation': reg['primary'],
                 'conditions': reg['sample'], 'outcome': None, 'limitations': reg['limitations']},
                ['E-003', 'H-003', 'H-004', str(study/'registration.json')])
        write_json(PROJECT/'docs/research/E004-PREREGISTRATION.json', reg)
    return study


def load(study):
    study = Path(study).resolve(strict=True)
    if study.parent != (ROOT/'runs').resolve():
        raise ValueError('study outside research contour')
    reg = json.loads((study/'registration.json').read_text())
    manifest = json.loads((study/'manifest.json').read_text())
    if (reg['implementation_hashes'] != implementation_hashes() or reg['runtime'] != runtime_identity()
            or digest(study/'registration.json') != manifest['registration_sha256']
            or digest(study/'oracle.json') != reg['oracle_sha256']):
        raise ValueError('frozen implementation, registration or input changed')
    return reg, manifest, json.loads((study/'oracle.json').read_text())


def execute(study, reg, manifest, inputs, job, provider):
    if reg['fixture'] != bool(getattr(provider, 'fixture', False)):
        raise ValueError('live/fixture identity mismatch')
    identity = job_id(job)
    run = study/'units'/identity
    worker = run/'workers/C'
    if source_hashes(worker) != manifest['unit_hashes'][identity]:
        raise ValueError('worker context changed/reused')
    world = next(w for w in inputs['worlds'] if w['id'] == job['world'])
    name = 'continuum-'+study.name+'-'+identity.lower()
    argv = container_command(reg['image'], name, worker, ['/runtime/e002_worker.py'])
    start = time.monotonic()
    report = {'status': 'failed', 'exit_status': None, 'job': job, 'fixture': reg['fixture']}
    bridge = process = timer = None
    with (run/'supervisor/C.jsonl').open('w', encoding='utf-8') as log, (run/'supervisor/C.stderr.txt').open('w', encoding='utf-8') as err:
        try:
            # The retained object is authored by the trusted seeder, not the LLM.
            bridge = ReceptionBridge(run, 'C', [], log, 'scripted-known-correct-upstream')
            bridge.seed(memory(world, job['condition'], job['branch']))
            bridge.emit({'event': 'command_execution', 'command': argv, 'at': time.time()})
            process = subprocess.Popen(argv, cwd=PROJECT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, text=True, encoding='utf-8')
            timer = threading.Timer(reg['limits']['worker_seconds'], lambda: command(['docker', 'rm', '-f', name], timeout=15))
            timer.daemon = True
            timer.start()
            inbox = queue.Queue(maxsize=128)
            threading.Thread(target=read_lines, args=(process.stdout, inbox, 'worker'), daemon=True).start()
            final = None
            while True:
                remaining = reg['limits']['worker_seconds']-(time.monotonic()-start)
                if remaining <= 0 or (study/'STOP').exists():
                    raise TimeoutError('worker deadline or STOP')
                _, line = inbox.get(timeout=remaining)
                if line is None:
                    break
                if len(line) > 262144:
                    raise ValueError('oversized worker message')
                event = json.loads(line)
                bridge.emit({'event': 'worker_message', 'message': event})
                if event['channel'] == 'responses':
                    try:
                        response = provider.respond(identity, event['history'], TOOLS,
                            timeout=min(remaining, reg['limits']['request_seconds']), max_output_tokens=reg['limits']['max_output_tokens'])
                    except Exception:
                        report['failure_origin'] = 'provider'
                        raise
                elif event['channel'] == 'tool':
                    response = bridge.call(event['name'], event['arguments'])
                    bridge.emit({'event': 'delivered_memory', 'value': response})
                elif event['channel'] == 'worker':
                    if final is not None:
                        raise ValueError('multiple final answers')
                    final = json.loads(event['line'])
                    continue
                else:
                    raise PermissionError('unregistered worker channel')
                process.stdin.write(json.dumps({'result': response})+'\n')
                process.stdin.flush()
            report['exit_status'] = process.wait(timeout=10)
            if report['exit_status'] != 0 or final is None or not bridge.read:
                raise ValueError('worker failed or did not retrieve memory')
            report.update(status='completed', answer=final)
        except Exception as exc:
            report.update(failure_type=type(exc).__name__, failure=str(exc))
        finally:
            if timer:
                timer.cancel()
            if process:
                if process.poll() is None:
                    command(['docker', 'rm', '-f', name], timeout=15)
                    process.wait(timeout=15)
                report['exit_status'] = process.returncode
                process.stdin.close()
                process.stdout.close()
            if bridge:
                bridge.close()
    report['seconds'] = time.monotonic()-start
    write_json(run/'result.json', report)
    return report


def transient(result):
    return result.get('failure_origin') == 'provider' and (
        result.get('failure_type') in ('TimeoutError', 'ConnectionError', 'ConnectionResetError', 'RemoteDisconnected')
        or any(('provider HTTP status '+s+';') in result.get('failure', '') for s in ('429', '502', '503', '504')))


def recover(provider, study):
    for seconds in (30, 120, 300):
        if (study/'STOP').exists():
            raise RuntimeError('operator STOP')
        time.sleep(seconds)
        try:
            available = provider.model in provider.models()
            error = None
        except Exception as exc:
            available, error = False, type(exc).__name__
        with (study/'recovery.jsonl').open('a') as f:
            f.write(json.dumps({'at': time.time(), 'delay': seconds, 'available': available, 'error_type': error})+'\n')
        if available:
            return
    raise RuntimeError('registered recovery exhausted; terminal workers not retried')


def run(study, authorize=False):
    reg, manifest, inputs = load(study)
    if reg['fixture'] or not authorize:
        raise PermissionError('explicit authorized real study required')
    provider = ResponsesProvider(reg['provider'], reg['model'], SpendLedger(study/'provider-ledger.sqlite3', unbounded=True),
                                 study/'provider.jsonl', authorize=True)
    ledger = Jobs(study/'jobs.sqlite3')
    # No hidden restart bypassing the preregistered recovery/overall deadline.
    with (study/'network-start.json').open('x') as f:
        json.dump({'at': time.time()}, f)
    start = time.monotonic()
    if provider.model not in provider.models():
        recover(provider, study)
    smoke(study, provider)
    for job in inputs['schedule']:
        load(study)
        if (study/'STOP').exists() or time.monotonic()-start >= reg['limits']['series_seconds']:
            raise RuntimeError('registered stop/deadline')
        identity = job_id(job)
        ledger.claim(identity)
        print(json.dumps({'event': 'job_started', 'job': identity}), flush=True)
        result = execute(study, reg, manifest, inputs, job, provider)
        ledger.finish(identity, result)
        print(json.dumps({'event': 'job_result', 'job': identity, 'status': result['status'], 'failure': result.get('failure')}), flush=True)
        if transient(result):
            recover(provider, study)
        elif result.get('failure_origin') == 'provider' or result.get('failure_type') in ('PermissionError', 'SSLError', 'SSLCertVerificationError'):
            raise RuntimeError('provider/safeguard failure; no automatic continuation')
    return {'status': 'completed', 'jobs': len(ledger.state())}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run'])
    parser.add_argument('--study-id')
    parser.add_argument('--study', type=Path)
    parser.add_argument('--gate', type=Path)
    parser.add_argument('--authorize-api', action='store_true')
    args = parser.parse_args()
    print(prepare(args.study_id, args.gate) if args.action == 'prepare' else run(args.study, args.authorize_api))
