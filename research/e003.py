"""Preregistered E-003 series controller; resume pending jobs, never retry a worker."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import queue
import re
import shutil
import sqlite3
import subprocess
import threading
import time
from .common import PROJECT, ROOT, command, digest, runtime_identity, source_hashes, write_json
from .e002 import smoke
from .e002_protocol import TOOLS
from .e003_protocol import make_corpus, prompt
from .e003_memory import SeriesMemoryBridge
from .profiles import create_worker
from .responses_provider import ResponsesProvider, SpendLedger
from .sandbox import container_command, image_id, isolation_probe
from .supervisor import read_lines


def job_id(job):
    return '-'.join(job[k] for k in ('world', 'condition', 'branch', 'stage'))


def unit_path(study, world, condition, branch):
    return study/'units'/f'{study.name}-{world}-{condition.lower()}-{branch}'


def implementation_hashes():
    return {k: v for k, v in source_hashes().items()
            if k.endswith('.py') or k.startswith('prompts/') or k.startswith('worker_seed/')}


class Jobs:
    def __init__(self, path, schedule=None):
        self.path = path
        with closing(sqlite3.connect(path)) as db:
            db.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, ordinal INTEGER UNIQUE, status TEXT, started REAL, finished REAL, report TEXT)')
            if schedule is not None:
                if db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]:
                    raise ValueError('job ledger already initialized')
                db.executemany('INSERT INTO jobs(id,ordinal,status) VALUES(?,?,?)', [(job_id(j), i, 'pending') for i, j in enumerate(schedule)])
            db.commit()

    def state(self):
        with closing(sqlite3.connect(self.path)) as db:
            return {r[0]: {'ordinal': r[1], 'status': r[2], 'report': json.loads(r[3]) if r[3] else None}
                    for r in db.execute('SELECT id,ordinal,status,report FROM jobs ORDER BY ordinal')}

    def claim(self, identity):
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM jobs WHERE status='running'").fetchone():
                raise RuntimeError('live or orphaned worker exists; inspect actual process, never retry')
            row = db.execute("SELECT id FROM jobs WHERE status='pending' ORDER BY ordinal LIMIT 1").fetchone()
            if row is None or row[0] != identity:
                raise RuntimeError('not the first unfinished registered job')
            db.execute("UPDATE jobs SET status='running',started=? WHERE id=?", (time.time(), identity))
            db.commit()

    def finish(self, identity, report):
        with closing(sqlite3.connect(self.path)) as db:
            changed = db.execute("UPDATE jobs SET status=?,finished=?,report=? WHERE id=? AND status='running'",
                                 (report['status'], time.time(), json.dumps(report), identity)).rowcount
            if changed != 1:
                raise RuntimeError('cannot overwrite terminal or unclaimed job')
            db.commit()


def prepare(identity, gate, seed=2026101911):
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,24}', identity):
        raise ValueError('invalid study identity')
    gate = Path(gate).resolve()
    verified = json.loads(gate.read_text())
    if not verified['pass'] or verified['implementation_hashes'] != implementation_hashes():
        raise ValueError('fresh full evaluator/provider/series gate required')
    study = ROOT/'runs'/identity
    study.mkdir(exist_ok=False)
    corpus = make_corpus(seed)
    write_json(study/'oracle.json', corpus)
    image = image_id('python:3.11-slim-bookworm')
    registration = {
        'experiment': 'E-003', 'study_id': identity, 'registered_at_utc': datetime.now(timezone.utc).isoformat(),
        'sample': {'worlds': 12, 'families': ['threshold', 'residue', 'switch'], 'per_family': 4,
                   'conditions': ['C1', 'T1'], 'AB_contexts': 48, 'C_contexts': 72, 'smoke_contexts': 1,
                   'candidate_rules_per_world': 1728, 'observation_A_compatible_rules': '4..24',
                   'no_replacement_worlds': True, 'seed': seed},
        'interventions': {
            'intact': 'C reads a SQLite copy of its own A/B state.',
            'deleted': 'C gets a genuinely empty experimental DB; original A/B snapshot preserved outside worker.',
            'swapped': 'C gets a full B-state copy from the preregistered different world in the same family and SAME condition. No cross-condition borrowing. C receives no branch/donor label.',
            'fork_point': 'After all A/B sessions finish. Only persistent memory is forked, not model histories. All C contexts are fresh.',
            'donors': corpus['donors'], 'substitution_expectation': 'Accuracy against target may fall and follow donor; refusal is not required for coherent wrong-world memory.'},
        'primary': 'Paired difference T1-C1 of all-six-predictions AND both-derived-answers correct at intact C, across all 12 worlds.',
        'secondary': ['pointwise accuracy', 'A wrong working-rule to B correct working-rule correction',
                      'intact-minus-deleted accuracy and deleted refusal rate', 'intact-minus-swapped accuracy and donor-following rate',
                      'MCP/task/object lineage', 'retention and C1/T1 convergence', 'tokens, bytes, latency, reported usage'],
        'analysis': {'unit': 'world, not stage/token/branch', 'bootstrap': '10000 stratified-by-family paired world resamples, seed=2026101912, percentile 95% CI',
                     'primary_test': 'two-sided exact sign/McNemar test on discordant intact pairs; descriptive exploratory finite-corpus evidence, not universal validation',
                     'useful_effect': 0.10, 'evidence_rule': 'estimate >=0.10 and lower CI >0; otherwise inconclusive, never infer equivalence from nonsignificance',
                     'secondary_tests': 'descriptive, no additional significance claims',
                     'errors': 'Timeout/invalid/missing output=primary failure, kept in denominator. Report infrastructure errors separately. No filtering of unsuccessful worlds.'},
        'model': 'gpt-6-sol', 'provider': 'https://185.170.154.169/v1', 'provenance': 'gateway-declared, not attested OpenAI backend',
        'runtime': runtime_identity(), 'image': image, 'tools': TOOLS, 'skills': [],
        'limits': {'concurrency': 1, 'worker_seconds': 180, 'request_seconds': 60, 'max_output_tokens': 4096,
                   'memory_characters': 24000, 'series_seconds': 21600, 'retry': 0, 'requests': None, 'spend_usd': None},
        'authorization': 'Current user explicitly authorized harder C1/T1 series, deletion/substitution controls and API without limits.',
        'stopping': 'Run every preregistered eligible job once. Failed A prevents its B/C branches; failed donor prevents swapped branch, recorded as skipped_dependency. Continue unrelated worlds. Stop entire series on TLS/auth/provider transport failure, changed source/inputs, leakage or operator STOP. No new/replacement worlds.',
        'information_equivalence': 'Broker retains all source observations in both conditions; only memory-protocol prompt differs. C branch prompts are byte-identical within each world/condition.',
        'gate_path': str(gate), 'gate_sha256': digest(gate), 'oracle_sha256': digest(study/'oracle.json'),
        'schedule': corpus['schedule'],
        'limitations': ['12 worlds is an exploratory finite corpus, not a powered universal superiority/equivalence study.',
                        'Same model weights; repeated branches share A/B ancestor and are not independent worlds.',
                        'Full-state substitution tests semantic dependence, not a stealth-attack detector.',
                        'Structured plus derived content is a protocol package; not isolated JSON syntax effect.']}
    write_json(study/'registration.json', registration)
    journal = PROJECT/'docs/research/journal.jsonl'
    records = [json.loads(x) for x in journal.read_text(encoding='utf-8').splitlines()]
    prior = [x for x in records if x['entity_id'] == 'E-003']
    row = {'event_id': 'E-003/'+str(len(prior)+1), 'entity_id': 'E-003', 'kind': 'experiment',
           'at_utc': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'), 'status': 'registered', 'evidence_tier': 'proposal',
           'summary': 'Harder 12-world C1/T1 series with blinded C memory deletion and same-family substitution, registered before responses',
           'details': {'design': registration['sample'], 'inputs': str(study/'oracle.json'), 'evaluation': registration['primary'],
                       'conditions': registration['limits'], 'outcome': None, 'limitations': registration['limitations']},
           'refs': ['H-003', 'H-004', 'E-002', str(study/'registration.json')],
           'provenance': {'actor': 'engineering-e003-20261019', 'model_actual': 'host-model-not-exposed', 'source_snapshot': str(study/'manifest.json')},
           'supersedes': prior[-1]['event_id'] if prior else None}
    with journal.open('a', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(row, ensure_ascii=False)+'\n')
    code = source_hashes()
    units = {}
    for w in corpus['worlds']:
        for condition in ('C1', 'T1'):
            for branch in ('base', 'intact', 'deleted', 'swapped'):
                run = unit_path(study, w['id'], condition, branch)
                for folder in ('supervisor', 'workers', 'state', 'evaluator'):
                    (run/folder).mkdir(parents=True, exist_ok=False)
                instances = {}
                for stage in ('AB' if branch == 'base' else 'C'):
                    worker = run/'workers'/stage
                    create_worker(worker, stage, 'none')
                    write_json(worker/'repo/PROMPT.txt', {'prompt': prompt(w, condition, stage)})
                    instances[stage] = {'actor': run.name+':'+stage, 'initial_hashes': source_hashes(worker)}
                write_json(run/'manifest.json', {'world': w['id'], 'condition': condition, 'branch': branch, 'run_id': run.name,
                    'instances': instances, 'image': image, 'model': registration['model'], 'active_skills': [],
                    'code_hashes': code, 'runtime': registration['runtime']})
                units[run.name] = digest(run/'manifest.json')
    # Fresh OS probes in both a source worker and a C intervention worker.
    for world_id, condition, branch, stage in [('w01', 'C1', 'base', 'A'), ('w01', 'T1', 'deleted', 'C')]:
        run = unit_path(study, world_id, condition, branch)
        if not isolation_probe(image, run/'workers'/stage, run/'supervisor/isolation.json')['isolation_pass']:
            raise ValueError('new-series isolation preflight failed')
    Jobs(study/'jobs.sqlite3', corpus['schedule'])
    write_json(study/'manifest.json', {'study_id': identity, 'registration_sha256': digest(study/'registration.json'),
        'oracle_sha256': digest(study/'oracle.json'), 'implementation_hashes': implementation_hashes(),
        'full_source_hashes': code, 'unit_manifests': units, 'runtime': runtime_identity(), 'model': registration['model'],
        'image': image, 'gate_sha256': digest(gate)})
    write_json(study/'status.json', {'status': 'prepared', 'terminal': 0, 'total': 120, 'next_job': job_id(corpus['schedule'][0])})
    return {'study': str(study), 'worlds': 12, 'registered_jobs': 120, 'model_requests': 0}


def load(study):
    study = Path(study).resolve(strict=True)
    if study.parent != (ROOT/'runs').resolve():
        raise ValueError('study outside research contour')
    manifest = json.loads((study/'manifest.json').read_text())
    if manifest['implementation_hashes'] != implementation_hashes() or manifest['runtime'] != runtime_identity():
        raise ValueError('registered code/runtime changed')
    if digest(study/'registration.json') != manifest['registration_sha256'] or digest(study/'oracle.json') != manifest['oracle_sha256']:
        raise ValueError('registered inputs changed')
    registration = json.loads((study/'registration.json').read_text())
    if digest(registration['gate_path']) != manifest['gate_sha256']:
        raise ValueError('gate changed')
    if any(digest(study/'units'/name/'manifest.json') != sha for name, sha in manifest['unit_manifests'].items()):
        raise ValueError('unit manifest changed')
    return study, manifest, registration, json.loads((study/'oracle.json').read_text())


def copy_database(source, destination):
    if destination.exists():
        raise ValueError('never overwrite an experimental database')
    with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro', uri=True)) as origin:
        with closing(sqlite3.connect(destination)) as target:
            origin.backup(target)


def materialize_branch(study, job, corpus):
    run = unit_path(study, job['world'], job['condition'], job['branch'])
    own = unit_path(study, job['world'], job['condition'], 'base')
    donor = corpus['donors'][job['world']]
    source = unit_path(study, donor, job['condition'], 'base') if job['branch'] == 'swapped' else own
    if job['branch'] == 'base':
        return None
    snapshot = run/'state/before-C.sqlite3'
    copy_database(source/'state/continuum.sqlite3', snapshot)
    if job['branch'] != 'deleted':
        shutil.copy2(snapshot, run/'state/continuum.sqlite3')
    else:
        with closing(sqlite3.connect(run/'state/continuum.sqlite3')) as db:
            db.execute('PRAGMA user_version=0')
    intervention = {'kind': job['branch'], 'target_world': job['world'], 'condition': job['condition'],
                    'source_world': donor if job['branch'] == 'swapped' else job['world'],
                    'source_db': str(source/'state/continuum.sqlite3'), 'source_db_sha256': digest(source/'state/continuum.sqlite3'),
                    'snapshot_sha256': digest(snapshot), 'initial_db_sha256': digest(run/'state/continuum.sqlite3'),
                    'model_history_copied': False, 'worker_received_branch_label': False}
    write_json(run/'intervention.json', intervention)
    return intervention


def dependency_error(study, job, corpus):
    requirements = []
    if job['stage'] == 'B':
        requirements.append(unit_path(study, job['world'], job['condition'], 'base')/'supervisor/A-result.json')
    if job['stage'] == 'C':
        requirements.append(unit_path(study, job['world'], job['condition'], 'base')/'supervisor/B-result.json')
        if job['branch'] == 'swapped':
            requirements.append(unit_path(study, corpus['donors'][job['world']], job['condition'], 'base')/'supervisor/B-result.json')
    for p in requirements:
        if not p.exists() or json.loads(p.read_text())['status'] != 'completed':
            return 'required predecessor not completed: '+str(p)
    return None


def execute_worker(study, manifest, reg, corpus, job, provider, mode='responses'):
    if mode not in ('responses', 'fixture') or (mode == 'fixture') != bool(getattr(provider, 'fixture', False)):
        raise ValueError('fixture and live provider modes cannot be mixed')
    run = unit_path(study, job['world'], job['condition'], job['branch'])
    stage = job['stage']
    cfg = json.loads((run/'manifest.json').read_text())
    worker = run/'workers'/stage
    if source_hashes(worker) != cfg['instances'][stage]['initial_hashes']:
        raise ValueError('worker context altered or reused')
    dependency = dependency_error(study, job, corpus)
    if dependency:
        result = {'status': 'skipped_dependency', 'reason': dependency, 'exit_status': None, 'mode': mode}
        write_json(run/'supervisor'/f'{stage}-result.json', result)
        return result
    if stage == 'C':
        materialize_branch(study, job, corpus)
    world = next(w for w in corpus['worlds'] if w['id'] == job['world'])
    observations = world['observations_a'] if stage == 'A' else world['observations_b'] if stage == 'B' else []
    name = 'continuum-'+run.name+'-'+stage.lower()
    argv = container_command(manifest['image'], name, worker, ['/runtime/e002_worker.py'])
    start = time.monotonic()
    deadline = start+reg['limits']['worker_seconds']
    report = {'status': 'failed', 'mode': mode, 'model_requested': manifest['model'], 'model_actual': None,
              'exit_status': None, 'failure': None, 'actor': run.name+':'+stage, 'job': job}
    process, bridge, timer = None, None, None
    with (run/'supervisor'/f'{stage}.jsonl').open('w', encoding='utf-8') as log, (run/'supervisor'/f'{stage}.stderr.txt').open('w', encoding='utf-8') as err:
        try:
            bridge = SeriesMemoryBridge(run, stage, observations, log, manifest['model'])
            log.write(json.dumps({'event': 'command_execution', 'command': argv, 'at': time.time()})+'\n'); log.flush()
            process = subprocess.Popen(argv, cwd=PROJECT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, text=True, encoding='utf-8')
            timer = threading.Timer(max(0.001, deadline-time.monotonic()), lambda: command(['docker', 'rm', '-f', name], timeout=15))
            timer.daemon = True; timer.start()
            inbox = queue.Queue(maxsize=128)
            threading.Thread(target=read_lines, args=(process.stdout, inbox, 'worker'), daemon=True).start()
            final = None
            while True:
                remaining = deadline-time.monotonic()
                if remaining <= 0 or (study/'STOP').exists():
                    raise TimeoutError('worker deadline or operator STOP')
                _, line = inbox.get(timeout=remaining)
                if line is None:
                    break
                if len(line) > 262144:
                    raise ValueError('worker message too large')
                event = json.loads(line)
                if event['channel'] == 'responses':
                    try:
                        response = provider.respond(job_id(job), event['history'], TOOLS,
                            timeout=min(reg['limits']['request_seconds'], remaining), max_output_tokens=reg['limits']['max_output_tokens'])
                    except Exception:
                        report['failure_origin'] = 'provider'
                        raise
                    report['model_actual'] = response['model']
                elif event['channel'] == 'tool':
                    response = bridge.call(event['name'], event['arguments'])
                elif event['channel'] == 'worker':
                    log.write(json.dumps(event)+'\n'); log.flush()
                    if final is not None:
                        raise ValueError('multiple final messages')
                    final = json.loads(event['line'])
                    write_json(run/'supervisor'/f'{stage}-answer.json', final)
                    continue
                else:
                    raise PermissionError('unknown worker channel')
                process.stdin.write(json.dumps({'result': response})+'\n'); process.stdin.flush()
            report['exit_status'] = process.wait(timeout=5)
            if report['exit_status'] != 0 or final is None:
                raise RuntimeError('worker process failed or final answer missing')
            if time.monotonic() >= deadline:
                raise TimeoutError('worker deadline expired')
            bridge.finish(final)
            report['status'] = 'completed'
        except Exception as exc:
            report['failure'] = type(exc).__name__+': '+str(exc)
            report['failure_type'] = type(exc).__name__
        finally:
            if timer:
                timer.cancel()
            if process is not None and process.poll() is None:
                command(['docker', 'rm', '-f', name], timeout=15)
                process.wait(timeout=10)
            if process is not None:
                report['exit_status'] = process.returncode
                process.stdin.close(); process.stdout.close()
            if bridge:
                bridge.close()
    report['duration_seconds'] = time.monotonic()-start
    write_json(run/'supervisor'/f'{stage}-result.json', report)
    return report


def run_series(study, authorize=False, unbounded=False):
    if not authorize or not unbounded:
        raise PermissionError('explicit API and unbounded-spend authorization required')
    study, manifest, reg, corpus = load(study)
    ledger = Jobs(study/'jobs.sqlite3')
    provider = ResponsesProvider(reg['provider'], manifest['model'], SpendLedger(study/'provider-ledger.sqlite3', unbounded=True),
                                 study/'provider.jsonl', authorize=True)
    start_path = study/'network-start.json'
    if not start_path.exists():
        with start_path.open('x') as f: json.dump({'at': time.time()}, f)
    if not (study/'metadata.json').exists():
        ids = provider.models()
        write_json(study/'metadata.json', {'models': ids, 'available': manifest['model'] in ids})
    if not json.loads((study/'metadata.json').read_text())['available']:
        raise RuntimeError('registered model not available; no quality-based model search')
    if not (study/'smoke.json').exists():
        smoke(study, provider)
    for job in corpus['schedule']:
        identity = job_id(job)
        states = ledger.state()
        if states[identity]['status'] != 'pending':
            if states[identity]['status'] == 'running':
                raise RuntimeError('worker still running or orphaned; inspect, do not restart')
            continue
        if (study/'STOP').exists() or time.time()-json.loads(start_path.read_text())['at'] >= reg['limits']['series_seconds']:
            raise RuntimeError('registered stop/deadline')
        load(study)  # Detect code/input edits before each new context.
        ledger.claim(identity)
        write_json(study/'status.json', {'status': 'running', 'job': identity,
                   'terminal': sum(s['status'] not in ('pending', 'running') for s in states.values()), 'total': 120})
        print(json.dumps({'event': 'job_started', 'job': identity}), flush=True)
        try:
            result = execute_worker(study, manifest, reg, corpus, job, provider)
        except Exception as exc:
            result = {'status': 'failed_controller', 'failure': type(exc).__name__+': '+str(exc), 'exit_status': None}
        ledger.finish(identity, result)
        print(json.dumps({'event': 'job_result', 'job': identity, 'status': result['status'],
                          'failure': result.get('failure'), 'duration': result.get('duration_seconds')}), flush=True)
        if result['status'] == 'failed_controller' or result.get('failure_type') in ('SSLError', 'SSLCertVerificationError', 'PermissionError'):
            raise RuntimeError('series stopped on infrastructure/safeguard failure')
        if result.get('failure_origin') == 'provider' and result.get('failure_type') != 'ValueError':
            raise RuntimeError('series stopped on provider transport failure')
        # Provider HTTP/transport failures are not model errors; do not keep spending through outages.
        if (result.get('failure') or '').startswith(('RuntimeError: provider HTTP', 'ConnectionError:', 'ConnectionResetError:', 'RemoteDisconnected:')):
            raise RuntimeError('series stopped on provider transport failure')
    states = ledger.state()
    write_json(study/'status.json', {'status': 'completed', 'terminal': len(states), 'total': 120,
                                   'outcomes': {s: sum(v['status'] == s for v in states.values()) for s in sorted({v['status'] for v in states.values()})}})
    return json.loads((study/'status.json').read_text())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run', 'status'])
    parser.add_argument('--study', type=Path)
    parser.add_argument('--study-id')
    parser.add_argument('--gate', type=Path)
    parser.add_argument('--authorize-responses', action='store_true')
    parser.add_argument('--unbounded-spend', action='store_true')
    args = parser.parse_args()
    if args.action == 'prepare':
        result = prepare(args.study_id, args.gate)
    elif args.action == 'run':
        result = run_series(args.study, args.authorize_responses, args.unbounded_spend)
    else:
        result = Jobs(args.study/'jobs.sqlite3').state()
    print(json.dumps(result, ensure_ascii=False))
