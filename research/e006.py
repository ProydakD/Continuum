"""E-006 controller: bounded authored memory, frozen writer/reader schedule."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time
from .common import ROOT, PROJECT, digest, runtime_identity, source_hashes, write_json
from .e003 import Jobs, implementation_hashes, job_id
from .e005 import run
from .e006_protocol import BUDGETS, READ_TOOLS, WRITE_TOOLS, corpus, reader_prompt, writer_prompt
from .profiles import create_worker
from .sandbox import image_id, isolation_probe


def append_journal(study, status, outcome=None):
    reg = json.loads((study/'registration.json').read_text())
    path = PROJECT/'docs/research/journal.jsonl'
    prior = [r for r in map(json.loads, path.read_text(encoding='utf-8').splitlines()) if r['entity_id'] == 'E-006']
    row = {'event_id': f'E-006/{len(prior)+1}', 'entity_id': 'E-006', 'kind': 'experiment',
           'at_utc': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'), 'status': status,
           'evidence_tier': 'proposal' if outcome is None else 'observed_model',
           'summary': 'Model-authored memory at fixed complete-result byte budgets; separate rule retention and arithmetic',
           'details': {'design': reg['design'], 'inputs': str(study/'oracle.json'), 'evaluation': reg['primary'],
                       'conditions': reg['sample'], 'outcome': outcome, 'limitations': reg['limitations']},
           'refs': ['E-005', 'H-003', 'H-004', str(study/'registration.json')],
           'provenance': {'actor': 'engineering-e006-20261019', 'model_actual': 'host-model-not-exposed' if outcome is None else 'gpt-6-sol (gateway-declared)',
                          'source_snapshot': str(study/'manifest.json')}, 'supersedes': prior[-1]['event_id'] if prior else None}
    with path.open('a', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(row, ensure_ascii=False)+'\n')


def prepare(identity, gate, fixture=False):
    if not re.fullmatch(r'e006-[a-z0-9-]{1,24}', identity):
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
    reg = {'experiment': 'E-006', 'registered_at': time.time(), 'fixture': fixture,
        'sample': {'worlds': len(inputs['worlds']), 'families': ['linear', 'residue', 'switch'], 'per_family': 8 if not fixture else None,
                   'conditions': ['C1', 'T1'], 'budgets_bytes': list(BUDGETS), 'paired_replicates': 1,
                   'model_writers': sum(j['stage'] == 'A' for j in inputs['schedule']),
                   'reader_positions': sum(j['stage'] == 'C' for j in inputs['schedule']),
                   'controls': ['one REF and one EMPTY reader per world'], 'contexts': len(inputs['schedule']), 'seed': inputs['seed']},
        'design': 'Known-correct rules supplied only to model writers. C1 compact ordinary text vs T1 compact structured JSON instruction (intention-to-treat; broker does not enforce syntax). Writers choose memory. Fixed complete serialized tool-result budgets 24/32/48 bytes; at most two save attempts with exact byte-count feedback. No truncation, no source observations, no writer final/history copied. Fresh C reads only saved bytes from a faithful own-writer Continuum DB copy. Queries hidden from writer. All A before randomized C.',
        'primary': 'Exact reconstruction of all nine fields: 48-byte minus 24-byte success, averaged equally over C1 and T1 within each of 24 worlds, then across worlds. Failed/unsaved writers and dependent skips remain failures. Primary concerns byte budget, NOT format superiority.',
        'secondary': ['rule reconstruction by condition and budget', 'descriptive T1 minus C1 over all three budgets',
                      'complete arithmetic accuracy separate from rule fields', 'wrong vs null rule fields',
                      'writer rejection/repair, accepted memory bytes and format convergence', 'REF correct-memory readers and EMPTY abstention controls', 'MCP/network lineage, tokens and time'],
        'analysis': 'World is unit (n=24), not 336 contexts. 10000 paired world-mean bootstrap samples stratified by family (8 worlds each), seed 2026101907, empirical sorted indices 249/9749. Exact two-sided sign-flip on 24 world differences (16777216 assignments), computed by an integer multiplicity dynamic program; no Monte Carlo p-value. Positive evidence: estimate>=0.10 and lower CI>0. Secondary descriptive, no additional superiority tests. Nonsignificance or ceiling is not equivalence.',
        'information': 'Only memory string inside constant {memory:...} wrapper crosses A->C; byte budget counts exact json.dumps(wrapper).encode(utf8), including JSON escaping. No padding or hidden observation preservation. Immutable writer DB is backed up to reader-specific DB; object provenance and bytes independently checked. EMPTY is truly empty DB; REF is scripted known-correct JSON within 192 bytes, not a model writer.',
        'model': 'gpt-6-sol', 'provider': 'https://185.170.154.169/v1', 'provenance': 'gateway-declared; weights and model seed not independently attested',
        'replication': 'One fresh writer-reader chain per cell; invest in 24 independent worlds instead of E005 within-cell replicates. No model seed parameter, no independent model replication.',
        'limits': {'concurrency': 1, 'writer_seconds': 300, 'reader_seconds': 180, 'request_seconds': 90,
                   'writer_output_tokens': 4096, 'reader_output_tokens': 2048, 'save_attempts': 2,
                   'series_seconds': 21600, 'worker_retries': 0, 'requests': None, 'spend_usd': None},
        'recovery': 'Keep terminal failures, never retry workers. On 429/502/503/504, timeout or connection failure, check frozen-model catalog after 30,120,300 seconds; first successful availability permits only next pending position. Auth/TLS/non-transient errors in POST OR catalog, changed inputs/code, leakage or STOP abort. Three unsuccessful availability checks abort. Smoke once, no retry. No outcome-based model/world replacement. Dependency requires completed saved writer, even if failed writer left bytes.',
        'authorization': 'Current user authorizes E006 and API without limits; local commits only, no push.',
        'limitations': ['24 independent synthetic worlds, eight per family; finite artificial corpus, not broad validation or a guaranteed power target.',
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
        write_json(PROJECT/'docs/research/E006-PREREGISTRATION.json', reg)
    return study



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run'])
    parser.add_argument('--study-id')
    parser.add_argument('--study', type=Path)
    parser.add_argument('--gate', type=Path)
    parser.add_argument('--authorize-api', action='store_true')
    args = parser.parse_args()
    print(prepare(args.study_id, args.gate) if args.action == 'prepare' else run(args.study, args.authorize_api))
