"""E-005 controller: bounded authored memory, frozen writer/reader schedule."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import queue
import re
import subprocess
import threading
import time
from .common import ROOT, PROJECT, command, digest, runtime_identity, source_hashes, write_json
from .e002 import smoke
from .e003 import Jobs, copy_database, implementation_hashes, job_id
from .e004 import transient
from .e005_memory import AuthoredMemoryBridge
from .e005_protocol import BUDGETS, WRITE_TOOLS, READ_TOOLS, corpus, reader_prompt, writer_prompt, reference_memory
from .profiles import create_worker
from .responses_provider import ResponsesProvider, SpendLedger
from .sandbox import container_command, image_id, isolation_probe
from .supervisor import read_lines


def append_journal(study, status, outcome=None):
    reg = json.loads((study/'registration.json').read_text())
    path = PROJECT/'docs/research/journal.jsonl'
    prior = [r for r in map(json.loads, path.read_text(encoding='utf-8').splitlines()) if r['entity_id'] == 'E-005']
    row = {'event_id': f'E-005/{len(prior)+1}', 'entity_id': 'E-005', 'kind': 'experiment',
           'at_utc': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'), 'status': status,
           'evidence_tier': 'proposal' if outcome is None else 'observed_model',
           'summary': 'Model-authored memory at fixed complete-result byte budgets; separate rule retention and arithmetic',
           'details': {'design': reg['design'], 'inputs': str(study/'oracle.json'), 'evaluation': reg['primary'],
                       'conditions': reg['sample'], 'outcome': outcome, 'limitations': reg['limitations']},
           'refs': ['E-004', 'H-003', 'H-004', str(study/'registration.json')],
           'provenance': {'actor': 'engineering-e005-20261019', 'model_actual': 'host-model-not-exposed' if outcome is None else 'gpt-6-sol (gateway-declared)',
                          'source_snapshot': str(study/'manifest.json')}, 'supersedes': prior[-1]['event_id'] if prior else None}
    with path.open('a', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(row, ensure_ascii=False)+'\n')


def prepare(identity, gate, fixture=False):
    if not re.fullmatch(r'e005-[a-z0-9-]{1,24}', identity):
        raise ValueError('invalid study identity')
    gate = Path(gate).resolve()
    verified = json.loads(gate.read_text())
    if not verified['pass'] or verified['implementation_hashes'] != implementation_hashes() or (not fixture and not verified.get('fixture_pass')):
        raise ValueError('fresh offline unit/real-MCP fixture gate required')
    study = ROOT/'runs'/identity
    study.mkdir(exist_ok=False)
    inputs = corpus()
    if fixture:
        inputs['worlds'] = inputs['worlds'][:1]
        inputs['schedule'] = [j for j in inputs['schedule'] if j['world'] == 'w01' and j['replicate'] == 1]
    write_json(study/'oracle.json', inputs)
    reg = {'experiment': 'E-005', 'registered_at': time.time(), 'fixture': fixture,
        'sample': {'worlds': len(inputs['worlds']), 'families': ['linear', 'residue', 'switch'], 'per_family': 2,
                   'conditions': ['C1', 'T1'], 'budgets_bytes': list(BUDGETS), 'paired_replicates': 2,
                   'model_writers': sum(j['stage'] == 'A' for j in inputs['schedule']),
                   'reader_positions': sum(j['stage'] == 'C' for j in inputs['schedule']),
                   'controls': ['one REF and one EMPTY reader per world'], 'contexts': len(inputs['schedule']), 'seed': inputs['seed']},
        'design': 'Known-correct rules supplied only to model writers. C1 compact ordinary text vs T1 compact structured JSON instruction (intention-to-treat; broker does not enforce syntax). Writers choose memory. Fixed complete serialized tool-result budgets 48/96/192 bytes; at most two save attempts with exact byte-count feedback. No truncation, no source observations, no writer final/history copied. Fresh C reads only saved bytes from a faithful own-writer Continuum DB copy. Queries hidden from writer. All A before randomized C.',
        'primary': 'T1 minus C1 exact reader reconstruction of all nine rule fields, averaged EQUALLY over three budgets and two writer-reader replicates within each of six worlds. Failed/unsaved writers and dependent skips remain failures in this denominator.',
        'secondary': ['rule reconstruction by fixed budget', 'largest-minus-smallest budget effect within condition',
                      'complete arithmetic accuracy separate from rule fields', 'wrong vs null rule fields',
                      'writer rejection/repair, accepted memory bytes and format convergence', 'REF correct-memory readers and EMPTY abstention controls', 'MCP/network lineage, tokens and time'],
        'analysis': 'World is unit (n=6), not 156 contexts. 10000 paired world-mean bootstrap samples stratified by family (2 worlds each), seed 2026101906, empirical sorted indices 249/9749. Exact two-sided sign-flip on six world differences (64 assignments). Positive evidence: estimate>=0.10 and lower CI>0. Secondary descriptive, no additional superiority tests. Nonsignificance or ceiling is not equivalence.',
        'information': 'Only memory string inside constant {memory:...} wrapper crosses A->C; byte budget counts exact json.dumps(wrapper).encode(utf8), including JSON escaping. No padding or hidden observation preservation. Immutable writer DB is backed up to reader-specific DB; object provenance and bytes independently checked. EMPTY is truly empty DB; REF is scripted known-correct JSON within 192 bytes, not a model writer.',
        'model': 'gpt-6-sol', 'provider': 'https://185.170.154.169/v1', 'provenance': 'gateway-declared; weights and model seed not independently attested',
        'replication': 'Two fresh writer-reader chains per cell; no seed parameter in adapter, not controlled model-seed replication.',
        'limits': {'concurrency': 1, 'writer_seconds': 300, 'reader_seconds': 180, 'request_seconds': 90,
                   'writer_output_tokens': 4096, 'reader_output_tokens': 2048, 'save_attempts': 2,
                   'series_seconds': 21600, 'worker_retries': 0, 'requests': None, 'spend_usd': None},
        'recovery': 'Keep terminal failures, never retry workers. On 429/502/503/504, timeout or connection failure, check frozen-model catalog after 30,120,300 seconds; first successful availability permits only next pending position. Auth/TLS/non-transient errors in POST OR catalog, changed inputs/code, leakage or STOP abort. Three unsuccessful availability checks abort. Smoke once, no retry. No outcome-based model/world replacement. Dependency requires completed saved writer, even if failed writer left bytes.',
        'authorization': 'Current user authorizes E005 and API without limits; local commits only, no push.',
        'limitations': ['Six independent synthetic worlds: exploratory and low power, not broad validation.',
                        'Known-correct source rules, not discovery/revision from observations.', 'Format instruction is a protocol package; syntax adherence is measured, not used to exclude outputs.',
                        'Budget equals serialized bytes, not model tokens or semantic information.', 'Tightest budget selected before outcomes; no claim of information-theoretic impossibility.',
                        'Unknown handling explicitly instructed; not spontaneous self-monitoring.', 'Same-model fresh contexts are not independent models.'],
        'tools': {'A': WRITE_TOOLS, 'C': READ_TOOLS}, 'schedule': inputs['schedule'],
        'image': image_id('python:3.11-slim-bookworm'), 'runtime': runtime_identity(),
        'implementation_hashes': implementation_hashes(), 'gate_path': str(gate), 'gate_sha256': digest(gate),
        'oracle_sha256': digest(study/'oracle.json')}
    write_json(study/'registration.json', reg)
    unit_hashes = {}
    for job in inputs['schedule']:
        run = study/'units'/job_id(job)
        for part in ('supervisor', 'state', 'workers'):
            (run/part).mkdir(parents=True)
        worker = run/'workers'/job['stage']
        create_worker(worker, job['stage'], 'none')
        world = next(w for w in inputs['worlds'] if w['id'] == job['world'])
        text = writer_prompt(world, job['condition'], job['budget']) if job['stage'] == 'A' else reader_prompt(world)
        write_json(worker/'repo/PROMPT.txt', {'prompt': text})
        unit_hashes[job_id(job)] = source_hashes(worker)
    first = inputs['schedule'][0]
    if not isolation_probe(reg['image'], study/'units'/job_id(first)/'workers'/first['stage'], study/'isolation.json')['isolation_pass']:
        raise ValueError('OS isolation gate failed')
    write_json(study/'manifest.json', {'registration_sha256': digest(study/'registration.json'), 'unit_hashes': unit_hashes})
    Jobs(study/'jobs.sqlite3', inputs['schedule'])
    if not fixture:
        append_journal(study, 'registered')
        write_json(PROJECT/'docs/research/E005-PREREGISTRATION.json', reg)
    return study


def load(study):
    study = Path(study).resolve(strict=True)
    if study.parent != (ROOT/'runs').resolve():
        raise ValueError('study outside research contour')
    reg = json.loads((study/'registration.json').read_text())
    manifest = json.loads((study/'manifest.json').read_text())
    if (reg['implementation_hashes'] != implementation_hashes() or reg['runtime'] != runtime_identity()
            or digest(study/'registration.json') != manifest['registration_sha256']
            or digest(study/'oracle.json') != reg['oracle_sha256'] or digest(reg['gate_path']) != reg['gate_sha256']):
        raise ValueError('registered code/runtime/inputs/gate changed')
    return reg, manifest, json.loads((study/'oracle.json').read_text())


def writer_run(study, job):
    return study/'units'/job_id(dict(job, stage='A'))


def execute(study, reg, manifest, inputs, job, provider):
    if reg['fixture'] != bool(getattr(provider, 'fixture', False)):
        raise ValueError('fixture/live provider mismatch')
    identity, stage = job_id(job), job['stage']
    run = study/'units'/identity
    worker = run/'workers'/stage
    if source_hashes(worker) != manifest['unit_hashes'][identity]:
        raise ValueError('worker context changed/reused')
    if stage == 'C' and job['condition'] in ('C1', 'T1'):
        source = writer_run(study, job)
        prior = json.loads((source/'result.json').read_text())
        if prior['status'] != 'completed' or not prior.get('saved'):
            result = {'status': 'skipped_dependency', 'job': job, 'exit_status': None, 'reason': 'writer not completed with accepted memory'}
            write_json(run/'result.json', result)
            return result
        copy_database(source/'state/continuum.sqlite3', run/'state/continuum.sqlite3')
        write_json(run/'source.json', {'writer': str(source), 'writer_db_sha256': digest(source/'state/continuum.sqlite3'),
                                     'copy_sha256': digest(run/'state/continuum.sqlite3'), 'history_copied': False})
    world = next(w for w in inputs['worlds'] if w['id'] == job['world'])
    name = 'continuum-'+study.name+'-'+identity.lower()
    argv = container_command(reg['image'], name, worker, ['/runtime/e002_worker.py'])
    limit = reg['limits']['writer_seconds' if stage == 'A' else 'reader_seconds']
    start = time.monotonic()
    report = {'status': 'failed', 'exit_status': None, 'job': job, 'fixture': reg['fixture']}
    bridge = process = timer = None
    with (run/'supervisor'/f'{stage}.jsonl').open('w', encoding='utf-8') as log, (run/'supervisor'/f'{stage}.stderr.txt').open('w', encoding='utf-8') as err:
        try:
            declared = 'scripted-known-correct-upstream' if job['condition'] == 'REF' else 'scripted-fixture' if reg['fixture'] else reg['model']
            bridge = AuthoredMemoryBridge(run, stage, [], log, declared)
            bridge.configure(job['budget'])
            if job['condition'] == 'REF':
                bridge.persist(reference_memory(world))
            bridge.emit({'event': 'command_execution', 'command': argv, 'at': time.time()})
            process = subprocess.Popen(argv, cwd=PROJECT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, text=True, encoding='utf-8')
            timer = threading.Timer(limit, lambda: command(['docker', 'rm', '-f', name], timeout=15))
            timer.daemon = True
            timer.start()
            inbox = queue.Queue(maxsize=128)
            threading.Thread(target=read_lines, args=(process.stdout, inbox, 'worker'), daemon=True).start()
            final = None
            while True:
                remaining = limit-(time.monotonic()-start)
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
                        response = provider.respond(identity, event['history'], WRITE_TOOLS if stage == 'A' else READ_TOOLS,
                            timeout=min(remaining, reg['limits']['request_seconds']),
                            max_output_tokens=reg['limits']['writer_output_tokens' if stage == 'A' else 'reader_output_tokens'])
                    except Exception:
                        report['failure_origin'] = 'provider'
                        raise
                elif event['channel'] == 'tool':
                    response = bridge.call(event['name'], event['arguments'])
                    bridge.emit({'event': 'tool_result', 'name': event['name'], 'arguments': event['arguments'], 'value': response})
                elif event['channel'] == 'worker':
                    if final is not None:
                        raise ValueError('multiple finals')
                    final = json.loads(event['line'])
                    continue
                else:
                    raise PermissionError('unregistered channel')
                process.stdin.write(json.dumps({'result': response})+'\n')
                process.stdin.flush()
            report['exit_status'] = process.wait(timeout=10)
            if process.returncode != 0 or final is None:
                raise ValueError('no successful final output')
            bridge.finish(final)
            report.update(status='budget_rejected' if stage == 'A' and not bridge.saved else 'completed', answer=final)
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
                report.update(saved=bridge.saved, save_attempts=bridge.attempts)
                bridge.close()
    report['seconds'] = time.monotonic()-start
    write_json(run/'result.json', report)
    return report


def recover(provider, study):
    for delay in (30, 120, 300):
        if (study/'STOP').exists():
            raise RuntimeError('operator STOP')
        time.sleep(delay)
        try:
            available, error = provider.model in provider.models(), None
        except Exception as exc:
            if not transient({'failure_origin': 'provider', 'failure_type': type(exc).__name__, 'failure': str(exc)}):
                raise
            available, error = False, type(exc).__name__
        with (study/'recovery.jsonl').open('a') as f:
            f.write(json.dumps({'at': time.time(), 'delay': delay, 'available': available, 'error_type': error})+'\n')
        if available:
            return
    raise RuntimeError('registered recovery exhausted')


def run(study, authorize=False):
    reg, manifest, inputs = load(study)
    if reg['fixture'] or not authorize:
        raise PermissionError('explicit API authorization required')
    provider = ResponsesProvider(reg['provider'], reg['model'], SpendLedger(study/'provider-ledger.sqlite3', unbounded=True), study/'provider.jsonl', authorize=True)
    ledger = Jobs(study/'jobs.sqlite3')
    with (study/'network-start.json').open('x') as f:
        json.dump({'at': time.time()}, f)
    start = time.monotonic()
    try:
        available = provider.model in provider.models()
    except Exception as exc:
        if not transient({'failure_origin': 'provider', 'failure_type': type(exc).__name__, 'failure': str(exc)}):
            raise
        available = False
    if not available:
        recover(provider, study)
    smoke(study, provider)
    for job in inputs['schedule']:
        load(study)
        if (study/'STOP').exists() or time.monotonic()-start >= reg['limits']['series_seconds']:
            raise RuntimeError('registered stop/deadline')
        identity = job_id(job)
        ledger.claim(identity)
        print(json.dumps({'event': 'job_started', 'job': identity}), flush=True)
        try:
            result = execute(study, reg, manifest, inputs, job, provider)
        except Exception as exc:
            result = {'status': 'failed_controller', 'failure': type(exc).__name__+': '+str(exc), 'job': job}
            write_json(study/'units'/identity/'result.json', result)
        ledger.finish(identity, result)
        print(json.dumps({'event': 'job_result', 'job': identity, 'status': result['status'], 'failure': result.get('failure')}), flush=True)
        if transient(result):
            recover(provider, study)
        elif result['status'] == 'failed_controller' or result.get('failure_origin') == 'provider' or result.get('failure_type') == 'PermissionError':
            raise RuntimeError('provider/controller/safeguard failure, no retry')
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
