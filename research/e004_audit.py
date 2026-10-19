"""Independent E-004 arithmetic, raw MCP/database lineage and paired analysis."""
import base64
import hashlib
import itertools
import json
from pathlib import Path
import random
import re
from .e003_audit import pairs, read_db


def decode(payload):
    if payload['common'] is None:
        return None
    common = payload['common']
    if common.startswith('{'):
        rule = json.loads(common)
    else:
        rule = {'family': re.search(r'base family is (\w+)', common)[1]}
        rule.update({k: int(v) for k, v in re.findall(r'\b(a|b|c|e|t|x0|z0)=(-?\d+)', common)})
    exception = payload['exception']
    rule['delta'] = None if exception is None else (json.loads(exception)['delta'] if exception.startswith('{')
                                                   else int(re.search(r'delta=(-?\d+)', exception)[1]))
    return rule


def calculate(rule, points):
    if rule is None:
        values = [None for _ in points]
    else:
        values = []
        for x, z in points:
            terms = [rule['c'], x*rule['a'], z*rule['b']]
            if rule['family'] == 'residue':
                terms.append(rule['e']*(x-3*(x//3)))
            if rule['family'] == 'switch' and x+z >= rule['t']:
                terms.append(rule['e'])
            special = x == rule['x0'] and z == rule['z0']
            values.append(None if special and rule['delta'] is None else sum(terms)+(rule['delta'] if special else 0))
    return {'rule': rule, 'predictions': values,
            'sum': sum(values) if all(type(v) is int for v in values) else None,
            'contrast': values[0]-values[-1] if type(values[0]) is int and type(values[-1]) is int else None}


def reference(world, branch):
    rule = dict(world['rule']) if branch != 'empty' else None
    if branch == 'partial':
        rule['delta'] = None
    return calculate(rule, world['queries'])


def same(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(same(left[k], right[k]) for k in right)
    if isinstance(left, list):
        return len(left) == len(right) and all(same(a, b) for a, b in zip(left, right))
    return left == right


def audit(run, world, job, provider_events=None):
    run = Path(run)
    try:
        result = json.loads((run/'result.json').read_text())
        if result['status'] != 'completed' or result['exit_status'] != 0:
            raise ValueError('worker did not complete')
        events = [json.loads(s) for s in (run/'supervisor/C.jsonl').read_text().splitlines()]
        calls = pairs(events)
        db = read_db(run/'state/continuum.sqlite3')
        if len(db['tasks']) != 1 or len(db['knowledge_objects']) != 1:
            raise ValueError('unexpected task/object count')
        task, obj = db['tasks'][0], db['knowledge_objects'][0]
        raw = obj['content']
        sha = hashlib.sha256(raw).hexdigest()
        if len(raw) != 512 or sha != obj['sha256'] or json.loads(task['result']) != {'object_sha256': sha}:
            raise ValueError('budget/digest/task binding mismatch')
        actor = run.name+':C'
        origin = json.loads(obj['origin'])
        if origin['actor'] != actor or origin['model_declared'] != 'scripted-known-correct-upstream':
            raise ValueError('object provenance mismatch')
        checkpoint = next(c for c in calls if c['name'] == 'continuum_checkpoint_task'
                          and c['value']['id'] == task['id'] and c['value']['updated_seq'] == task['updated_seq'])
        read_task = next(c for c in calls if c['name'] == 'continuum_get_task' and c['start'] > checkpoint['end']
                         and c['value']['result'] == task['result'] and c['arguments']['task_id'] == task['id'])
        fetched = [c for c in calls if c['name'] == 'continuum_get_object' and c['start'] > read_task['end']
                   and c['arguments']['sha256'] == sha and c['value']['sha256'] == sha
                   and base64.b64decode(c['value']['content_base64'], validate=True) == raw]
        if len(fetched) != 1:
            raise ValueError('missing unique successful raw get_object')
        payload = json.loads(raw)
        expected = reference(world, job['branch'])
        if not same(decode(payload), expected['rule']) or set(payload) != {'common', 'exception', 'padding'} or payload['padding'].strip():
            raise ValueError('memory semantics/absence differs from registered intervention')
        delivered = [e['value'] for e in events if e.get('event') == 'delivered_memory']
        if delivered != [payload]:
            raise ValueError('delivered memory differs from actual MCP object')
        messages = [e['message'] for e in events if e.get('event') == 'worker_message']
        histories = [e['history'] for e in messages if e.get('channel') == 'responses']
        if len(histories) != 2 or len(histories[0]) != 1:
            raise ValueError('non-fresh or unexpected reader history')
        worker_prompt = json.loads((run/'workers/C/repo/PROMPT.txt').read_text())['prompt']
        if histories[0] != [{'role': 'user', 'content': worker_prompt}]:
            raise ValueError('history differs from registered worker prompt')
        if histories[1][-1]['type'] != 'function_call_output' or histories[1][-1]['output'].encode() != raw:
            raise ValueError('model input differs from byte-budgeted MCP payload')
        finals = [json.loads(e['line']) for e in messages if e.get('channel') == 'worker']
        if finals != [result['answer']]:
            raise ValueError('final answer not bound to worker output')
        if provider_events is not None:
            network = [e for e in provider_events if e.get('worker') == run.name]
            requests = [e for e in network if e['event'] == 'request_started']
            responses = [e for e in network if e['event'] == 'response']
            if len(requests) != 2 or len(responses) != 2 or [r['payload']['input'] for r in requests] != histories:
                raise ValueError('network trace not bound to isolated history')
            if any(r['response']['model'] != 'gpt-6-sol' or r['response']['status'] != 'completed' for r in responses):
                raise ValueError('provider identity/status mismatch')
            output = responses[-1]['response']['output']
            text = ''.join(c.get('text', '') for item in output if item.get('type') == 'message' for c in item.get('content', []))
            if not same(json.loads(text), result['answer']):
                raise ValueError('final answer not bound to returned model output')
        answer = result['answer']
        schema = isinstance(answer, dict) and set(answer) == set(expected)
        rule_correct = schema and same(answer['rule'], expected['rule'])
        return {'pass': True, 'rule_correct': rule_correct, 'complete_correct': same(answer, expected),
                'rule_correct_arithmetic_wrong': rule_correct and not same(answer, expected),
                'memory_bytes': len(raw), 'object_sha256': sha}
    except (ValueError, KeyError, IndexError, TypeError, StopIteration, OSError) as exc:
        return {'pass': False, 'error': type(exc).__name__+': '+str(exc), 'rule_correct': False, 'complete_correct': False}


def statistics(worlds, scores):
    differences = [scores[w['id']]['T1']-scores[w['id']]['C1'] for w in worlds]
    observed = sum(differences)/len(differences)
    rng = random.Random(2026101905)
    groups = [[i for i, w in enumerate(worlds) if w['family'] == f] for f in sorted({w['family'] for w in worlds})]
    samples = sorted(sum(differences[rng.choice(g)] for g in groups for _ in g)/len(worlds) for _ in range(10000))
    permutations = [sum(d*s for d, s in zip(differences, signs))/len(differences)
                    for signs in itertools.product((-1, 1), repeat=len(differences))]
    interval = [samples[249], samples[9749]]
    return {'difference_T1_minus_C1': observed, 'bootstrap_95': interval,
            'exact_sign_flip_p': sum(abs(v) >= abs(observed)-1e-12 for v in permutations)/len(permutations),
            'positive_rule_met': observed >= .10 and interval[0] > 0, 'unit': 'world mean over two contexts'}


def evaluate(study):
    from .e003 import Jobs, job_id
    study = Path(study)
    inputs = json.loads((study/'oracle.json').read_text())
    states = Jobs(study/'jobs.sqlite3').state()
    events = [json.loads(s) for s in (study/'provider.jsonl').read_text().splitlines()]
    rows = []
    scores = {w['id']: dict(C1=0, T1=0) for w in inputs['worlds']}
    for job in inputs['schedule']:
        w = next(w for w in inputs['worlds'] if w['id'] == job['world'])
        status = states[job_id(job)]['status']
        checked = audit(study/'units'/job_id(job), w, job, events) if status == 'completed' else {'pass': False, 'rule_correct': False, 'complete_correct': False}
        rows.append({'job': job, 'status': status, **checked})
        if job['branch'] == 'intact':
            scores[w['id']][job['condition']] += int(checked['rule_correct'])/2
    summary = {}
    for condition in ('C1', 'T1'):
        summary[condition] = {}
        for branch in ('intact', 'partial', 'empty'):
            group = [r for r in rows if r['job']['condition'] == condition and r['job']['branch'] == branch]
            summary[condition][branch] = {'denominator': len(group), 'rule_correct': sum(r['rule_correct'] for r in group),
                'complete_correct': sum(r['complete_correct'] for r in group), 'lineage_verified': sum(r['pass'] for r in group),
                'rule_correct_arithmetic_wrong': sum(r.get('rule_correct_arithmetic_wrong', False) for r in group)}
    responses = [e for e in events if e['event'] == 'response']
    usage = {'attempts': sum(e['event'] == 'request_started' for e in events), 'returned_responses': len(responses),
             'input_tokens': sum(e['response'].get('usage', {}).get('input_tokens', 0) for e in responses),
             'output_tokens': sum(e['response'].get('usage', {}).get('output_tokens', 0) for e in responses),
             'billing': 'unknown; returned usage only, failed attempt usage unknown'}
    result = {'terminal': all(v['status'] not in ('pending', 'running') for v in states.values()),
              'statuses': {s: sum(v['status'] == s for v in states.values()) for s in sorted({v['status'] for v in states.values()})},
              'primary': statistics(inputs['worlds'], scores), 'conditions': summary, 'world_scores': scores, 'usage': usage, 'rows': rows}
    (study/'report.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    import sys
    result = evaluate(Path(sys.argv[1]))
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}))
