"""Registered paired analysis; failed worlds remain in the denominators."""
import argparse
from contextlib import closing
from datetime import datetime
import json
import math
from pathlib import Path
import random
import sqlite3
from .common import digest, write_json
from .e003 import unit_path, job_id
from .e003_protocol import score
from .e003_audit import answer_correct, audit_stage, validate_world, calculate


def paired_statistics(rows, seed=2026101912, replicates=10000):
    if not rows:
        raise ValueError('no registered worlds')
    differences = [int(r['T1'])-int(r['C1']) for r in rows]
    families = {f: [i for i, r in enumerate(rows) if r['family'] == f] for f in sorted({r['family'] for r in rows})}
    rng = random.Random(seed)
    samples = []
    for _ in range(replicates):
        indices = [rng.choice(group) for group in families.values() for __ in group]
        samples.append(sum(differences[i] for i in indices)/len(indices))
    samples.sort()
    t_only = sum(not r['C1'] and r['T1'] for r in rows)
    c_only = sum(r['C1'] and not r['T1'] for r in rows)
    discordant = t_only+c_only
    p = min(1.0, 2*sum(math.comb(discordant, k) for k in range(min(t_only, c_only)+1))/(2**discordant)) if discordant else 1.0
    estimate = sum(differences)/len(rows)
    lower, upper = samples[int(.025*(replicates-1))], samples[int(.975*(replicates-1))]
    return {'n_worlds': len(rows), 'C1_successes': sum(r['C1'] for r in rows), 'T1_successes': sum(r['T1'] for r in rows),
            'difference_T1_minus_C1': estimate, 'stratified_bootstrap_95_percentile': [lower, upper],
            'bootstrap_seed': seed, 'replicates': replicates, 'discordant_T1_only': t_only, 'discordant_C1_only': c_only,
            'exact_two_sided_p': p, 'registered_positive_evidence_rule_met': estimate >= .10 and lower > 0,
            'interpretation': 'Exploratory finite-corpus estimate. Nonsignificance is not equivalence. Degenerate all-success CI does not establish a zero population effect.'}


def load_json(path, default=None):
    return json.loads(Path(path).read_text(encoding='utf-8')) if Path(path).exists() else default


def evaluate(study):
    study = Path(study).resolve()
    manifest = load_json(study/'manifest.json')
    registration = load_json(study/'registration.json')
    corpus = load_json(study/'oracle.json')
    if digest(study/'registration.json') != manifest['registration_sha256'] or digest(study/'oracle.json') != manifest['oracle_sha256']:
        raise ValueError('registered input or protocol changed')
    with closing(sqlite3.connect((study/'jobs.sqlite3').as_uri()+'?mode=ro', uri=True)) as db:
        states = {r[0]: {'status': r[1], 'report': json.loads(r[2]) if r[2] else None} for r in db.execute('SELECT id,status,report FROM jobs ORDER BY ordinal')}
    expected_ids = {job_id(j) for j in corpus['schedule']}
    if set(states) != expected_ids:
        raise ValueError('job ledger differs from registered sample')
    proof = {w['id']: validate_world(w) for w in corpus['worlds']}
    if not all(p['pass'] for p in proof.values()):
        raise ValueError('independent mathematical proof failed')
    world_map = {w['id']: w for w in corpus['worlds']}
    results, comparisons = {}, []
    for w in corpus['worlds']:
        conditions = {}
        for condition in ('C1', 'T1'):
            base = unit_path(study, w['id'], condition, 'base')
            ab = {}
            for stage in 'AB':
                answer = load_json(base/'supervisor'/f'{stage}-answer.json')
                status = load_json(base/'supervisor'/f'{stage}-result.json', {'status': 'not_run'})
                audit = audit_stage(base, stage, w)
                working = (answer or {}).get('working_rule')
                ab[stage] = {'status': status, 'answer': answer, 'working_rule_correct': working == w['truth'], 'audit': audit}
            branches = {}
            for branch in ('intact', 'deleted', 'swapped'):
                unit = unit_path(study, w['id'], condition, branch)
                answer = load_json(unit/'supervisor/C-answer.json')
                status = load_json(unit/'supervisor/C-result.json', {'status': 'not_run'})
                donor = world_map[corpus['donors'][w['id']]]
                audit = audit_stage(unit, 'C', w, donor if branch == 'swapped' else None)
                production, independent = score(answer, w), answer_correct(answer, w)
                if production != independent:
                    raise ValueError('production/independent primary scoring disagreement')
                predictions = answer.get('predictions', []) if isinstance(answer, dict) else []
                correct_points = sum(type(a) is int and a == b for a, b in zip(predictions, w['answers'])) if isinstance(predictions, list) else 0
                branch_result = {'status': status, 'answer': answer, 'semantic_answer_correct': production,
                    'primary_success': production and status['status'] == 'completed', 'correct_points_of_6': correct_points,
                    'needs_context': answer == {'status': 'needs_context'} and status['status'] == 'completed',
                    'independent_agrees': True, 'lineage_pass': audit['pass'], 'audit': audit,
                    'donor_semantic_success': answer_correct(answer, w, donor['truth']) if branch == 'swapped' else None}
                branches[branch] = branch_result
                write_json(unit/'evaluator/report.json', branch_result)
            correction = (ab['A']['status']['status'] == 'completed' and not ab['A']['working_rule_correct']
                          and ab['B']['status']['status'] == 'completed' and ab['B']['working_rule_correct'])
            conditions[condition] = {'AB': ab, 'branches': branches, 'provisional_wrong_to_correct': correction}
        results[w['id']] = {'family': w['family'], 'conditions': conditions}
        comparisons.append({'world': w['id'], 'family': w['family'],
                            **{c: conditions[c]['branches']['intact']['primary_success'] for c in ('C1', 'T1')}})
    controls = {}
    for condition in ('C1', 'T1'):
        subset = [r['conditions'][condition] for r in results.values()]
        controls[condition] = {'denominator_worlds': 12,
            'intact_correct': sum(r['branches']['intact']['primary_success'] for r in subset),
            'deleted_correct': sum(r['branches']['deleted']['primary_success'] for r in subset),
            'deleted_needs_context': sum(r['branches']['deleted']['needs_context'] for r in subset),
            'swapped_target_correct': sum(r['branches']['swapped']['primary_success'] for r in subset),
            'swapped_donor_correct': sum(r['branches']['swapped']['donor_semantic_success'] for r in subset),
            'provisional_wrong_to_correct': sum(r['provisional_wrong_to_correct'] for r in subset),
            'A_working_rule_wrong': sum(r['AB']['A']['status']['status'] == 'completed' and not r['AB']['A']['working_rule_correct'] for r in subset),
            'completed_C_contexts': sum(r['branches'][b]['status']['status'] == 'completed' for r in subset for b in ('intact', 'deleted', 'swapped')),
            'lineage_verified_C': sum(r['branches'][b]['lineage_pass'] for r in subset for b in ('intact', 'deleted', 'swapped'))}
    provider = [json.loads(l) for l in (study/'provider.jsonl').read_text().splitlines()] if (study/'provider.jsonl').exists() else []
    usage = {}
    for event in provider:
        if event['event'] != 'response':
            continue
        row = usage.setdefault(event['worker'], {'responses': 0, 'input_tokens': 0, 'output_tokens': 0, 'reasoning_tokens_subset': 0, 'api_seconds': 0})
        observed = event['response'].get('usage', {})
        row['responses'] += 1
        row['input_tokens'] += observed.get('input_tokens', 0)
        row['output_tokens'] += observed.get('output_tokens', 0)
        row['reasoning_tokens_subset'] += observed.get('output_tokens_details', {}).get('reasoning_tokens', 0)
        row['api_seconds'] += event['seconds']
    prereg_before = None
    if (study/'provider-ledger.sqlite3').exists():
        with closing(sqlite3.connect(study/'provider-ledger.sqlite3')) as db:
            first = db.execute('SELECT MIN(started) FROM attempts').fetchone()[0]
        if first is not None:
            prereg_before = datetime.fromisoformat(registration['registered_at_utc']).timestamp() < first
    summary = {'experiment': 'E-003', 'status': 'completed' if all(v['status'] not in ('pending', 'running') for v in states.values()) else 'partial',
        'registered_contexts': 120, 'terminal_contexts': sum(v['status'] not in ('pending', 'running') for v in states.values()),
        'context_outcomes': {s: sum(v['status'] == s for v in states.values()) for s in sorted({v['status'] for v in states.values()})},
        'preregistration_precedes_first_response_request': prereg_before,
        'primary': paired_statistics(comparisons), 'controls': controls, 'independent_world_proofs': proof,
        'model_requests_including_smoke': sum(e['event'] == 'request_started' for e in provider),
        'returned_models': sorted({e['response'].get('model', 'missing') for e in provider if e['event'] == 'response'}),
        'usage_by_context': usage, 'cost_usd': None, 'cost_reason': 'Unbounded API use authorized; gateway tariff and billing unknown.',
        'limitations': registration['limitations']+['Correctness after full coherent substitution is scored separately against target and donor; following donor is evidence of dependence, not successful target continuity.'],
        'sources': {str(study/n): digest(study/n) for n in ('registration.json', 'manifest.json', 'oracle.json')}}
    write_json(study/'detailed-results.json', results)
    write_json(study/'report.json', summary)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--study', type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.study)
    print(json.dumps({k: v for k, v in result.items() if k not in ('usage_by_context', 'independent_world_proofs')}, ensure_ascii=False))
