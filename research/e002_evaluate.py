"""Post-run scoring: closed oracle plus separate raw SQL/constraint cross-check."""
import argparse
import base64
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
from .common import digest, write_json
from .e002_protocol import score_answer


def independent(run, w):
    """Does not call production score_answer, evaluate, Store or model code."""
    errors, memory = [], {}
    observed = w['observations_a']+[w['observation_b']]
    candidates = [(a, b, c) for a in range(1, 4) for b in range(-2, 3) for c in (0, 2, 4)
                  if all(a*o['x']+b+c*(o['x'] % 2) == o['y'] for o in observed)]
    primary = False
    try:
        answer = json.loads((run/'supervisor/C-answer.json').read_text())
        a, b, c = candidates[0]
        primary = (len(candidates) == 1 and answer['status'] == 'completed'
                   and answer['rule'] == {'a': a, 'b': b, 'c': c}
                   and answer['predictions'] == [{'x': x, 'y': a*x+b+c*(x % 2)} for x in w['questions_c']])
    except (OSError, KeyError, ValueError, IndexError):
        errors.append('missing or invalid final answer')
    try:
        with closing(sqlite3.connect((run/'state/continuum.sqlite3').resolve().as_uri()+'?mode=ro', uri=True)) as db:
            db.row_factory = sqlite3.Row
            tasks = list(db.execute('SELECT * FROM tasks'))
            transitions = list(db.execute("SELECT * FROM events WHERE action IN ('checkpointed','completed') ORDER BY seq"))
            assert len(tasks) == 1 and tasks[0]['status'] == 'done' and len(transitions) == 3
            prior = None
            for stage, event in zip('ABC', transitions):
                payload = json.loads(event['payload'])
                result = json.loads(payload['result'])
                assert event['actor'] == run.name+':'+stage and event['entity_id'] == tasks[0]['id'] and result['stage'] == stage
                log = [json.loads(l) for l in (run/'supervisor'/f'{stage}.jsonl').read_text().splitlines()]
                pairs = []
                requests = {}
                for e in log:
                    msg = e.get('message', {})
                    key = (e.get('connection'), msg.get('id'))
                    if e.get('channel') == 'mcp' and msg.get('method') == 'tools/call':
                        assert key not in requests
                        requests[key] = msg['params']
                    if e.get('event') == 'mcp_response' and key in requests:
                        r = msg.get('result', {})
                        if not r.get('isError') and 'error' not in msg:
                            v = r.get('structuredContent') or json.loads(r['content'][0]['text'])
                            pairs.append((requests[key], v))
                if prior:
                    assert any(p['name'] == 'continuum_get_task' and p['arguments']['task_id'] == tasks[0]['id']
                               and v['updated_seq'] == prior[1] and json.loads(v['result']) == prior[0] for p, v in pairs)
                    assert any(p['name'] == 'continuum_get_object' and p['arguments']['sha256'] == prior[0]['object_sha256']
                               and v['sha256'] == prior[0]['object_sha256']
                               and hashlib.sha256(base64.b64decode(v['content_base64'])).hexdigest() == v['sha256'] for p, v in pairs)
                verb = 'continuum_finish_task' if stage == 'C' else 'continuum_checkpoint_task'
                assert any(p['name'] == verb and p['arguments']['task_id'] == tasks[0]['id']
                           and p['arguments']['result'] == payload['result'] and v['updated_seq'] == event['seq'] for p, v in pairs)
                if stage != 'C':
                    row = db.execute('SELECT * FROM knowledge_objects WHERE sha256=?', (result['object_sha256'],)).fetchone()
                    assert hashlib.sha256(row['content']).hexdigest() == result['object_sha256']
                    obj = json.loads(row['content'])
                    assert obj['observations'] == (w['observations_a'] if stage == 'A' else observed)
                    memory[stage] = obj['memory']
                else:
                    assert result['answer'] == answer and result['predecessor'] == prior[0]
                prior = result, event['seq']
    except (OSError, sqlite3.Error, AssertionError, KeyError, ValueError, TypeError):
        errors.append('raw MCP/task/object/checkpoint lineage incomplete')
    return {'primary_correct': primary, 'process_pass': not errors, 'errors': errors, 'memory': memory,
            'method': 'read-only SQL, raw request/response pairing, enumerate compatible rules; no Store/evaluate'}


def evaluate(study):
    study = Path(study)
    manifest = json.loads((study/'manifest.json').read_text())
    w = json.loads((study/'oracle.json').read_text())
    results = {}
    for condition, path in manifest['runs'].items():
        run = Path(path)
        stages = {}
        for s in 'ABC':
            p = run/'supervisor'/f'{s}-result.json'
            stages[s] = json.loads(p.read_text()) if p.exists() else {'status': 'not_run'}
        answer_path = run/'supervisor/C-answer.json'
        answer = json.loads(answer_path.read_text()) if answer_path.exists() else None
        raw = independent(run, w)
        primary = score_answer(answer, w)
        report = {'primary_correct': primary, 'independent_agrees': primary == raw['primary_correct'],
                  'process_pass': raw['process_pass'], 'stages': stages, 'independent': raw,
                  'input_preservation': 'broker preserves all source observations equally, not model-invented oracle',
                  'secondary_review': 'Inspect A/B memory for rejected alternatives and spontaneous C1/T1 convergence; not primary metric'}
        write_json(run/'evaluator/report.json', report)
        results[condition] = report
    provider = [json.loads(l) for l in (study/'provider.jsonl').read_text().splitlines()] if (study/'provider.jsonl').exists() else []
    responses = [e for e in provider if e['event'] == 'response']
    requests = [e for e in provider if e['event'] == 'request_started']
    report = {'pilot_status': 'completed' if all(all(s['status'] == 'completed' for s in r['stages'].values()) for r in results.values())
              else 'partial' if any(s['status'] != 'not_run' for r in results.values() for s in r['stages'].values()) else 'not_run',
              'conditions': results, 'model_requests_including_smoke': len(requests),
              'usage': [e['response'].get('usage') for e in responses], 'cost_usd': None,
              'cost_status': 'unbounded spending explicitly authorized; gateway billing not reported/verified',
              'model_returned': sorted({e['response'].get('model', 'missing') for e in responses}),
              'conclusion': 'One paired world cannot establish H-003 superiority, H-004 equivalence or statistical significance.',
              'sources': {str(p): digest(p) for p in [study/'registration.json', study/'manifest.json', study/'oracle.json']}}
    write_json(study/'report.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--study', type=Path, required=True)
    result = evaluate(parser.parse_args().study)
    print(json.dumps(result, ensure_ascii=False))
