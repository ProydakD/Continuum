"""Raw writer->MCP->reader proof, separate from production memory/scoring code."""
import base64
import hashlib
import itertools
import json
from pathlib import Path
import random
from .e003_audit import pairs, read_db
from .e004_audit import reference, same


def network_chain(run, result, events, provider_events):
    messages = [e['message'] for e in events if e.get('event') == 'worker_message']
    histories = [e['history'] for e in messages if e['channel'] == 'responses']
    stage = result['job']['stage']
    prompt = json.loads((run/'workers'/stage/'repo/PROMPT.txt').read_text())['prompt']
    if not histories or histories[0] != [{'role': 'user', 'content': prompt}]:
        raise ValueError('non-fresh or altered initial history')
    network = [e for e in provider_events if e.get('worker') == run.name]
    requests = [e for e in network if e['event'] == 'request_started']
    responses = [e for e in network if e['event'] == 'response']
    if len(requests) != len(histories) or len(responses) != len(requests):
        raise ValueError('network/history count mismatch')
    receipts = [e for e in events if e.get('event') == 'tool_result']
    actions = [e for e in messages if e['channel'] == 'tool']
    if len(actions) != len(receipts):
        raise ValueError('unanswered tool action')
    reconstructed, used, final = histories[0], 0, None
    for i, (request, response) in enumerate(zip(requests, responses)):
        if request['attempt'] != response['attempt'] or request['payload']['input'] != histories[i] or histories[i] != reconstructed:
            raise ValueError('request/response/history not bound')
        value = response['response']
        declared = 'scripted-fixture' if result['fixture'] else 'gpt-6-sol'
        if value['status'] != 'completed' or value['model'] != declared:
            raise ValueError('unregistered model/status')
        expected_tool = 'save_memory' if stage == 'A' else 'read_memory'
        if [t['name'] for t in request['payload']['tools']] != [expected_tool]:
            raise ValueError('wrong stage tools')
        reconstructed = reconstructed+value['output']
        calls = [v for v in value['output'] if v.get('type') == 'function_call']
        if calls:
            for call in calls:
                action, receipt = actions[used], receipts[used]
                args = json.loads(call['arguments'])
                if action['name'] != call['name'] or action['arguments'] != args or receipt['name'] != call['name'] or receipt['arguments'] != args:
                    raise ValueError('tool bytes not authored by returned model call')
                reconstructed.append({'type': 'function_call_output', 'call_id': call['call_id'], 'output': json.dumps(receipt['value'])})
                used += 1
        else:
            text = ''.join(c.get('text', '') for v in value['output'] if v.get('type') == 'message' for c in v.get('content', []))
            final = json.loads(text)
            if i != len(requests)-1:
                raise ValueError('continued after final')
    finals = [json.loads(m['line']) for m in messages if m['channel'] == 'worker']
    if used != len(receipts) or not same(final, result['answer']) or not same(finals, [final]):
        raise ValueError('unbound final or unused tool events')
    return receipts


def bound_object(db, calls, actor, model):
    if len(db['tasks']) != 1 or len(db['knowledge_objects']) != 1:
        raise ValueError('unexpected task/object count')
    task, obj = db['tasks'][0], db['knowledge_objects'][0]
    raw = obj['content']
    if hashlib.sha256(raw).hexdigest() != obj['sha256'] or json.loads(task['result']) != {'object_sha256': obj['sha256']}:
        raise ValueError('object digest/task binding mismatch')
    origin = json.loads(obj['origin'])
    if origin['actor'] != actor or origin['model_declared'] != model:
        raise ValueError('wrong memory author')
    return task, obj


def audit(run, world, job, provider_events):
    run = Path(run)
    try:
        result = json.loads((run/'result.json').read_text())
        if result['status'] not in ('completed', 'budget_rejected') or result['exit_status'] != 0:
            raise ValueError('not a completed executed context')
        events = [json.loads(s) for s in (run/'supervisor'/f"{job['stage']}.jsonl").read_text().splitlines()]
        receipts = network_chain(run, result, events, provider_events)
        calls = pairs(events)
        db = read_db(run/'state/continuum.sqlite3')
        memory, size = None, 0
        if job['stage'] == 'A':
            if not 1 <= len(receipts) <= 2 or len(receipts) != result['save_attempts']:
                raise ValueError('writer attempt quota mismatch')
            accepted = []
            for i, r in enumerate(receipts):
                text = r['arguments']['memory']
                raw = json.dumps({'memory': text}).encode('utf-8')
                expected = {'saved': True, 'bytes': len(raw)} if text and len(raw) <= job['budget'] else {
                    'saved': False, 'bytes': len(raw), 'budget': job['budget'], 'attempts_left': 1-i}
                if not same(r['value'], expected):
                    raise ValueError('byte feedback or accept/reject mismatch')
                if expected['saved']:
                    accepted.append(raw)
            if not accepted:
                if result['status'] != 'budget_rejected' or any(db[k] for k in ('tasks', 'knowledge_objects', 'events')):
                    raise ValueError('rejected memory was persisted or reported saved')
                return {'pass': True, 'saved': False, 'attempts': len(receipts), 'bytes': 0}
            if len(accepted) != 1 or not receipts[-1]['value']['saved'] or result['status'] != 'completed':
                raise ValueError('invalid accepted transition')
            task, obj = bound_object(db, calls, run.name+':A', 'scripted-fixture' if result['fixture'] else 'gpt-6-sol')
            if obj['content'] != accepted[0]:
                raise ValueError('stored object differs from model-written bytes')
            put = next(c for c in calls if c['name'] == 'continuum_put_object' and c['value']['sha256'] == obj['sha256']
                       and base64.b64decode(c['arguments']['content_base64']) == obj['content'])
            next(c for c in calls if c['name'] == 'continuum_checkpoint_task' and c['start'] > put['end']
                 and c['value']['id'] == task['id'] and c['value']['updated_seq'] == task['updated_seq'])
            memory, size = json.loads(obj['content'])['memory'], len(obj['content'])
            try:
                structured = isinstance(json.loads(memory), (dict, list))
            except ValueError:
                structured = False
            return {'pass': True, 'saved': True, 'attempts': len(receipts), 'bytes': size, 'json_object_or_array': structured,
                    'memory': memory, 'object_sha256': obj['sha256']}
        if len(receipts) != 1 or receipts[0]['name'] != 'read_memory':
            raise ValueError('reader did not do exactly one retrieval')
        if job['condition'] == 'EMPTY':
            if any(db[k] for k in ('tasks', 'knowledge_objects', 'events')) or receipts[0]['value'] != {'memory': None}:
                raise ValueError('empty control not truly empty')
            if any(c['name'] == 'continuum_get_object' for c in calls):
                raise ValueError('fabricated empty retrieval')
        else:
            if job['condition'] == 'REF':
                author, model = run.name+':C', 'scripted-known-correct-upstream'
            else:
                source = json.loads((run/'source.json').read_text())
                expected_source = run.parent/('-'.join([job['world'], job['condition'], job['branch'], 'A']))
                if Path(source['writer']) != expected_source or source['history_copied']:
                    raise ValueError('wrong writer or copied history')
                origin = expected_source/'state/continuum.sqlite3'
                if hashlib.sha256(origin.read_bytes()).hexdigest() != source['writer_db_sha256'] or read_db(origin) != db:
                    raise ValueError('writer source changed or unfaithful logical database copy')
                author, model = expected_source.name+':A', 'scripted-fixture' if result['fixture'] else 'gpt-6-sol'
            task, obj = bound_object(db, calls, author, model)
            get_task = next(c for c in calls if c['name'] == 'continuum_get_task' and c['arguments']['task_id'] == task['id']
                            and c['value']['result'] == task['result'])
            fetched = [c for c in calls if c['name'] == 'continuum_get_object' and c['start'] > get_task['end']
                       and c['arguments']['sha256'] == obj['sha256'] and base64.b64decode(c['value']['content_base64']) == obj['content']]
            if len(fetched) != 1:
                raise ValueError('missing unique successful raw get_object')
            raw = json.dumps(receipts[0]['value']).encode('utf-8')
            if raw != obj['content'] or len(raw) > job['budget']:
                raise ValueError('delivered bytes differ or exceed budget')
            memory, size = receipts[0]['value']['memory'], len(raw)
            if job['condition'] == 'REF' and not same(json.loads(memory), world['rule']):
                raise ValueError('positive reference is not true rule')
        expected = reference(world, 'empty' if job['condition'] == 'EMPTY' else 'intact')
        answer = result['answer']
        schema = isinstance(answer, dict) and set(answer) == set(expected)
        fields = answer.get('rule') if isinstance(answer, dict) else None
        counts = {'correct': 0, 'unknown': 0, 'wrong': 0}
        for key, value in world['rule'].items():
            observed = fields.get(key) if isinstance(fields, dict) else None
            counts['unknown' if observed is None else 'correct' if same(observed, value) else 'wrong'] += 1
        rule_correct = schema and same(fields, expected['rule'])
        return {'pass': True, 'bytes': size, 'rule_correct': rule_correct, 'complete_correct': same(answer, expected),
                'rule_correct_arithmetic_wrong': rule_correct and not same(answer, expected), 'fields': counts}
    except (ValueError, KeyError, IndexError, TypeError, StopIteration, OSError) as exc:
        return {'pass': False, 'error': type(exc).__name__+': '+str(exc)}


def statistics(worlds, scores):
    differences = [scores[w['id']]['T1']-scores[w['id']]['C1'] for w in worlds]
    observed = sum(differences)/len(worlds)
    groups = [[i for i, w in enumerate(worlds) if w['family'] == f] for f in sorted({w['family'] for w in worlds})]
    rng = random.Random(2026101906)
    samples = sorted(sum(differences[rng.choice(g)] for g in groups for _ in g)/len(worlds) for _ in range(10000))
    flips = [sum(d*s for d, s in zip(differences, signs))/len(worlds) for signs in itertools.product((-1, 1), repeat=len(worlds))]
    interval = [samples[249], samples[9749]]
    return {'difference_T1_minus_C1': observed, 'bootstrap_95': interval,
            'exact_sign_flip_p': sum(abs(v) >= abs(observed)-1e-12 for v in flips)/len(flips),
            'positive_rule_met': observed >= .10 and interval[0] > 0, 'n_worlds': len(worlds)}


def evaluate(study):
    from .e003 import Jobs, job_id
    study = Path(study)
    inputs = json.loads((study/'oracle.json').read_text())
    states = Jobs(study/'jobs.sqlite3').state()
    network = [json.loads(s) for s in (study/'provider.jsonl').read_text().splitlines()]
    rows, scores = [], {w['id']: {'C1': 0, 'T1': 0} for w in inputs['worlds']}
    for job in inputs['schedule']:
        w = next(w for w in inputs['worlds'] if w['id'] == job['world'])
        status = states[job_id(job)]['status']
        checked = audit(study/'units'/job_id(job), w, job, network) if status in ('completed', 'budget_rejected') else {'pass': False}
        rows.append({'job': job, 'status': status, **checked})
        if job['stage'] == 'C' and job['condition'] in ('C1', 'T1'):
            scores[w['id']][job['condition']] += int(checked.get('rule_correct', False))/6
    conditions = {}
    for condition in ('C1', 'T1'):
        conditions[condition] = {}
        for budget in (48, 96, 192):
            group = [r for r in rows if r['job']['condition'] == condition and r['job']['budget'] == budget]
            writers = [r for r in group if r['job']['stage'] == 'A']
            readers = [r for r in group if r['job']['stage'] == 'C']
            conditions[condition][str(budget)] = {'denominator': len(readers),
                'writers_saved': sum(r.get('saved', False) and r['pass'] for r in writers),
                'writers_used_second_attempt': sum(r.get('attempts', 0) == 2 for r in writers),
                'writers_json': sum(r.get('json_object_or_array', False) for r in writers),
                'rule_correct': sum(r.get('rule_correct', False) for r in readers),
                'complete_correct': sum(r.get('complete_correct', False) for r in readers),
                'reader_lineage_verified': sum(r['pass'] for r in readers),
                'mean_accepted_bytes': (sum(r.get('bytes', 0) for r in writers)/sum(r.get('saved', False) for r in writers)) if any(r.get('saved') for r in writers) else None}
    controls = {c: {'denominator': len(inputs['worlds']), 'complete_correct': sum(r.get('complete_correct', False) for r in rows if r['job']['condition'] == c),
                    'lineage_verified': sum(r['pass'] for r in rows if r['job']['condition'] == c)} for c in ('REF', 'EMPTY')}
    responses = [e for e in network if e['event'] == 'response']
    report = {'terminal': all(v['status'] not in ('pending', 'running') for v in states.values()),
        'statuses': {s: sum(v['status'] == s for v in states.values()) for s in sorted({v['status'] for v in states.values()})},
        'primary': statistics(inputs['worlds'], scores), 'conditions': conditions, 'controls': controls, 'world_scores': scores,
        'usage': {'attempts': sum(e['event'] == 'request_started' for e in network), 'returned_responses': len(responses),
                  'input_tokens': sum(e['response'].get('usage', {}).get('input_tokens', 0) for e in responses),
                  'output_tokens': sum(e['response'].get('usage', {}).get('output_tokens', 0) for e in responses), 'billing': 'unknown'}, 'rows': rows}
    (study/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    import sys
    r = evaluate(Path(sys.argv[1]))
    print(json.dumps({k: v for k, v in r.items() if k not in ('rows', 'world_scores')}))
