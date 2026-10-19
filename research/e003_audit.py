"""Independent math and raw evidence reader: no Store, production scorer or eval."""
import base64
from contextlib import closing
import hashlib
from itertools import product
import json
from pathlib import Path
import sqlite3


def calculate(family, rule, x, z):
    a, b, c, d, e, t = [rule[k] for k in ('a', 'b', 'c', 'd', 'e', 't')]
    odd_x = x-2*(x//2)
    odd_z = z-2*(z//2)
    if family == 'threshold':
        result = c+a*x+b*z+e*odd_z
        return result+d if x >= t else result
    if family == 'residue':
        result = c+a*x+b*z+e*odd_x*odd_z
        return result+d if x-3*(x//3) == t else result
    if family == 'switch':
        if x+z < t:
            return c+a*x+b*z+e*odd_x
        return c+b*x-a*z+d+e*odd_x
    raise ValueError('unknown family')


def validate_world(w):
    candidates = [dict(zip(('a', 'b', 'c', 'd', 'e', 't'), values))
                  for values in product(*[w['domains'][k] for k in ('a', 'b', 'c', 'd', 'e', 't')])]
    def fits(rule, observations):
        return all(calculate(w['family'], rule, o['x'], o['z']) == o['y'] for o in observations)
    a = [r for r in candidates if fits(r, w['observations_a'])]
    ab = [r for r in a if fits(r, w['observations_b'])]
    b = [r for r in candidates if fits(r, w['observations_b'])]
    expected = [calculate(w['family'], w['truth'], q['x'], q['z']) for q in w['questions']]
    seen = {(o['x'], o['z']) for o in w['observations_a']+w['observations_b']}
    passed = (len(candidates) == 1728 and 4 <= len(a) <= 24 and ab == [w['truth']] and len(b) >= 2
              and expected == w['answers'] and sum(expected) == w['derived']['sum']
              and expected[0]-expected[-1] == w['derived']['contrast']
              and all((q['x'], q['z']) not in seen for q in w['questions']))
    return {'pass': passed, 'compatible_a': len(a), 'compatible_ab': len(ab), 'compatible_b': len(b)}


def answer_correct(answer, w, rule=None):
    if not isinstance(answer, dict) or set(answer) != {'status', 'predictions', 'derived'} or answer['status'] != 'completed':
        return False
    values = answer['predictions']
    totals = answer['derived']
    if not isinstance(values, list) or len(values) != 6 or any(type(v) is not int for v in values):
        return False
    if not isinstance(totals, dict) or set(totals) != {'sum', 'contrast'} or any(type(v) is not int for v in totals.values()):
        return False
    outputs = [calculate(w['family'], rule or w['truth'], q['x'], q['z']) for q in w['questions']]
    return values == outputs and totals == {'sum': sum(outputs), 'contrast': outputs[0]-outputs[-1]}


def pairs(log):
    requests, answered, result = {}, set(), []
    for index, event in enumerate(log):
        msg = event.get('message', {})
        key = event.get('connection'), msg.get('id')
        if event.get('channel') == 'mcp' and msg.get('method') == 'tools/call':
            if key in requests:
                raise ValueError('duplicate request identity')
            requests[key] = index, msg['params']
        elif event.get('event') == 'mcp_response' and key in requests:
            if key in answered:
                raise ValueError('duplicate response identity')
            answered.add(key)
            response = msg.get('result', {})
            if 'error' in msg or response.get('isError') or not response:
                continue
            payload = response.get('structuredContent')
            if payload is None:
                payload = json.loads(response['content'][0]['text'])
            start, params = requests[key]
            result.append({'name': params['name'], 'arguments': params.get('arguments', {}), 'value': payload,
                           'start': start, 'end': index, 'connection': key[0], 'request_id': key[1]})
    return result


def read_db(path):
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        result = {}
        for table in ('tasks', 'events', 'knowledge_objects', 'claims', 'evidence'):
            result[table] = [dict(r) for r in db.execute('SELECT * FROM '+table)]
        return result


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit_stage(run, stage, w, source_world=None):
    run = Path(run)
    references, memory, errors = {}, None, []
    report_path = run/'supervisor'/f'{stage}-result.json'
    if not report_path.exists():
        return {'pass': False, 'errors': ['missing worker result'], 'references': {}}
    report = json.loads(report_path.read_text())
    if report['status'] != 'completed' or report['exit_status'] != 0:
        return {'pass': False, 'errors': ['worker not completed'], 'references': {str(report_path): sha(report_path)}}
    try:
        log_path = run/'supervisor'/f'{stage}.jsonl'
        references[str(log_path)] = sha(log_path)
        calls = pairs([json.loads(l) for l in log_path.read_text().splitlines()])
        db = read_db(run/'state/continuum.sqlite3')
        actor = run.name+':'+stage
        boot = next(c for c in calls if c['name'] == 'continuum_bootstrap' and c['value']['actor'] == actor)
        def matching(name, predicate, after=-1):
            found = [c for c in calls if c['name'] == 'continuum_'+name and c['start'] > after and predicate(c)]
            if not found:
                raise ValueError('missing bound '+name)
            return found[0]
        if stage == 'C':
            intervention = json.loads((run/'intervention.json').read_text())
            if sha(run/'state/before-C.sqlite3') != intervention['snapshot_sha256']:
                raise ValueError('fork snapshot changed')
            source_db = Path(intervention['source_db'])
            if sha(source_db) != intervention['source_db_sha256']:
                raise ValueError('source state changed after fork')
            snapshot = read_db(run/'state/before-C.sqlite3')
            origin = read_db(source_db)
            # Exact logical state identity, including original actors/events, not copied summaries.
            if snapshot != origin:
                raise ValueError('fork is not a faithful database snapshot')
            source_w = source_world or w
            if intervention['source_world'] != source_w['id'] or intervention['target_world'] != w['id']:
                raise ValueError('wrong preregistered donor or target')
            if intervention['kind'] == 'deleted':
                if boot['value']['open_tasks'] or any(db[t] for t in ('tasks', 'events', 'knowledge_objects', 'claims', 'evidence')):
                    raise ValueError('deletion did not remove task memory')
                if any(c['name'] in ('continuum_claim_task', 'continuum_finish_task', 'continuum_get_object') for c in calls):
                    raise ValueError('invented deleted-memory continuation')
                return {'pass': True, 'errors': [], 'references': references, 'intervention': 'deleted', 'memory': None}
            task = snapshot['tasks'][0]
            previous = json.loads(task['result'])
            obj = next(o for o in snapshot['knowledge_objects'] if o['sha256'] == previous['object_sha256'])
            expected_obs = source_w['observations_a']+source_w['observations_b']
            if json.loads(obj['content'])['observations'] != expected_obs:
                raise ValueError('forked observations differ from source world')
            read_task = matching('get_task', lambda c: c['arguments'].get('task_id') == task['id']
                                 and c['value']['result'] == task['result'] and c['value']['updated_seq'] == task['updated_seq'], boot['end'])
            fetched = matching('get_object', lambda c: c['arguments'].get('sha256') == obj['sha256']
                               and c['value']['sha256'] == obj['sha256']
                               and base64.b64decode(c['value']['content_base64']) == obj['content'], read_task['end'])
            completed = [e for e in db['events'] if e['actor'] == actor and e['action'] == 'completed']
            if len(completed) != 1:
                raise ValueError('missing C completion event')
            event = completed[0]
            result = json.loads(json.loads(event['payload'])['result'])
            answer = json.loads((run/'supervisor/C-answer.json').read_text())
            if result != {'stage': 'C', 'predecessor': previous, 'answer': answer}:
                raise ValueError('C final answer differs from recorded transition')
            matching('finish_task', lambda c: c['arguments'].get('task_id') == task['id']
                     and c['value']['updated_seq'] == event['seq'] and json.loads(c['value']['result']) == result, fetched['end'])
            memory = json.loads(obj['content'])['memory']
        else:
            events = [e for e in db['events'] if e['actor'] == actor and e['action'] == 'checkpointed']
            if len(events) != 1:
                raise ValueError('missing A/B checkpoint')
            event = events[0]
            result = json.loads(json.loads(event['payload'])['result'])
            obj = next(o for o in db['knowledge_objects'] if o['sha256'] == result['object_sha256'])
            if sha_bytes(obj['content']) != obj['sha256'] or json.loads(obj['origin'])['actor'] != actor:
                raise ValueError('object content/provenance mismatch')
            payload = json.loads(obj['content'])
            if payload['observations'] != w['observations_a']+(w['observations_b'] if stage == 'B' else []):
                raise ValueError('observation preservation failed')
            claim = next(c for c in db['claims'] if c['id'] == result['claim_id'])
            if json.loads(claim['proposition']) != {'subject': obj['sha256'], 'predicate': 'model_memory', 'object': stage}:
                raise ValueError('claim not bound to object')
            matching('put_object', lambda c: c['arguments'].get('sha256') == obj['sha256'] and c['value']['sha256'] == obj['sha256'])
            matching('add_evidence', lambda c: c['arguments'].get('claim_id') == claim['id'] and c['arguments'].get('sha256') == obj['sha256'])
            matching('checkpoint_task', lambda c: c['arguments'].get('task_id') == event['entity_id']
                     and c['value']['updated_seq'] == event['seq'] and json.loads(c['value']['result']) == result)
            if stage == 'B':
                prior = next(e for e in db['events'] if e['action'] == 'checkpointed' and e['seq'] < event['seq'])
                checkpoint = json.loads(prior['payload'])['result']
                task_read = matching('get_task', lambda c: c['arguments'].get('task_id') == prior['entity_id']
                                     and c['value']['result'] == checkpoint and c['value']['updated_seq'] == prior['seq'], boot['end'])
                matching('get_object', lambda c: c['arguments'].get('sha256') == json.loads(checkpoint)['object_sha256']
                         and c['value']['sha256'] == json.loads(checkpoint)['object_sha256'], task_read['end'])
            memory = payload['memory']
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError, IndexError, StopIteration) as exc:
        errors.append(type(exc).__name__+': '+str(exc))
    return {'pass': not errors, 'errors': errors, 'references': references, 'memory': memory,
            'method': 'independent read-only SQL and connection/request pairing; no production evaluate or Store'}


def sha_bytes(raw):
    return hashlib.sha256(raw).hexdigest()
