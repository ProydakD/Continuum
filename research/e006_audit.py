"""Frozen E-006 outcomes; reused raw lineage audit and exact world sign-flips."""
from collections import Counter
import json
from pathlib import Path
import random
from .e003 import Jobs, job_id
from .e004_audit import reference, same
from .e005_audit import audit
from .e006_protocol import BUDGETS


def statistics(worlds, doubled_differences):
    """Integer differences are sums over two formats, avoiding floating sign ties."""
    values = [doubled_differences[w['id']] for w in worlds]
    if not values or any(type(v) is not int or abs(v) > 2 for v in values):
        raise ValueError('expected one integer high-minus-low sum in [-2,2] per world')
    n = len(values)
    groups = [[i for i, w in enumerate(worlds) if w['family'] == f]
              for f in sorted({w['family'] for w in worlds})]
    rng = random.Random(2026101907)
    samples = sorted(sum(values[rng.choice(g)] for g in groups for _ in g)/(2*n)
                     for _ in range(10000))
    counts = Counter({0: 1})
    for value in values:
        updated = Counter()
        for total, multiplicity in counts.items():
            updated[total-value] += multiplicity
            updated[total+value] += multiplicity
        counts = updated
    total = sum(values)
    interval = [samples[249], samples[9749]]
    estimate = total/(2*n)
    return {'difference_48_minus_24': estimate, 'bootstrap_95': interval,
            'exact_sign_flip_p': sum(v for k, v in counts.items() if abs(k) >= abs(total))/(2**n),
            'sign_assignments': 2**n, 'n_worlds': n,
            'positive_rule_met': estimate >= .10 and interval[0] > 0}


def score_answer(answer, world):
    expected = reference(world, 'intact')
    return isinstance(answer, dict) and all(k in answer and same(answer[k], expected[k])
                                           for k in ('predictions', 'sum', 'contrast'))


def summarize(worlds, rows):
    scores = {w['id']: {c: {str(b): 0 for b in BUDGETS} for c in ('C1', 'T1')} for w in worlds}
    for row in rows:
        job = row['job']
        if job['stage'] == 'C' and job['condition'] in ('C1', 'T1'):
            scores[job['world']][job['condition']][str(job['budget'])] = int(row['pass'] and row.get('rule_correct', False))
    differences = {w: sum(cell[c]['48']-cell[c]['24'] for c in ('C1', 'T1')) for w, cell in scores.items()}
    conditions = {}
    for c in ('C1', 'T1'):
        conditions[c] = {}
        for b in BUDGETS:
            group = [r for r in rows if r['job']['condition'] == c and r['job']['budget'] == b]
            writers = [r for r in group if r['job']['stage'] == 'A']
            readers = [r for r in group if r['job']['stage'] == 'C']
            saved = [r for r in writers if r['pass'] and r.get('saved')]
            conditions[c][str(b)] = {
                'denominator': len(readers), 'writers_saved': len(saved),
                'writers_used_second_attempt': sum(r.get('attempts') == 2 for r in writers),
                'writers_json': sum(r.get('json_object_or_array', False) for r in saved),
                'rule_correct': sum(r['pass'] and r.get('rule_correct', False) for r in readers),
                'numeric_correct': sum(r['pass'] and r.get('numeric_correct', False) for r in readers),
                'complete_correct': sum(r['pass'] and r.get('complete_correct', False) for r in readers),
                'reader_lineage_verified': sum(r['pass'] for r in readers),
                'mean_accepted_bytes': sum(r['bytes'] for r in saved)/len(saved) if saved else None,
                'fields': {k: sum(r.get('fields', {}).get(k, 0) for r in readers if r['pass'])
                           for k in ('correct', 'unknown', 'wrong')}}
    controls = {c: {'denominator': len(worlds),
                    'complete_correct': sum(r['pass'] and r.get('complete_correct', False) for r in rows if r['job']['condition'] == c),
                    'lineage_verified': sum(r['pass'] for r in rows if r['job']['condition'] == c)} for c in ('REF', 'EMPTY')}
    return {'primary': statistics(worlds, differences), 'conditions': conditions, 'controls': controls,
            'world_scores': scores, 'world_doubled_budget_differences': differences,
            'descriptive_format_difference_T1_minus_C1': sum(sum(s['T1'].values())-sum(s['C1'].values()) for s in scores.values())/(3*len(worlds))}


def evaluate(study):
    study = Path(study)
    inputs = json.loads((study/'oracle.json').read_text())
    states = Jobs(study/'jobs.sqlite3').state()
    network = [json.loads(s) for s in (study/'provider.jsonl').read_text().splitlines()]
    rows = []
    for job in inputs['schedule']:
        world = next(w for w in inputs['worlds'] if w['id'] == job['world'])
        status = states[job_id(job)]['status']
        run = study/'units'/job_id(job)
        checked = audit(run, world, job, network) if status in ('completed', 'budget_rejected') else {'pass': False}
        if checked['pass'] and job['stage'] == 'C':
            answer = json.loads((run/'result.json').read_text())['answer']
            checked['numeric_correct'] = score_answer(answer, world) if job['condition'] != 'EMPTY' else checked['complete_correct']
        rows.append({'job': job, 'status': status, **checked})
    responses = [e for e in network if e['event'] == 'response']
    report = {'terminal': all(v['status'] not in ('pending', 'running') for v in states.values()),
              'statuses': dict(sorted(Counter(v['status'] for v in states.values()).items())),
              **summarize(inputs['worlds'], rows),
              'usage': {'attempts': sum(e['event'] == 'request_started' for e in network), 'returned_responses': len(responses),
                        'input_tokens': sum(e['response'].get('usage', {}).get('input_tokens', 0) for e in responses),
                        'output_tokens': sum(e['response'].get('usage', {}).get('output_tokens', 0) for e in responses), 'billing': 'unknown'},
              'rows': rows}
    (study/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    import sys
    result = evaluate(sys.argv[1])
    print(json.dumps({k: v for k, v in result.items() if k not in ('rows', 'world_scores')}))
