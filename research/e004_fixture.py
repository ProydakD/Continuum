"""Offline six-context actual Docker/MCP fixture plus missing-evidence sensitivity."""
import json
from pathlib import Path
import shutil
from .common import ROOT, write_json
from .e003 import Jobs, implementation_hashes, job_id
from .e004 import execute, load, prepare
from .e004_audit import audit, calculate, decode


class ScriptedProvider:
    fixture = True

    def respond(self, worker, history, tools, **kwargs):
        if len(history) == 1:
            item = {'type': 'function_call', 'name': 'read_memory', 'arguments': '{}', 'call_id': 'fixture-read'}
        else:
            points = json.loads(history[0]['content'].split('Queries: ')[1])
            # Solve only the actually delivered memory, never the hidden oracle.
            answer = calculate(decode(json.loads(history[-1]['output'])), points)
            item = {'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': json.dumps(answer)}]}
        return {'status': 'completed', 'model': 'scripted-fixture', 'output': [item]}


def run(identity):
    gate = ROOT/'artifacts/e004-001'/f'{identity}-unit-gate.json'
    write_json(gate, {'pass': True, 'implementation_hashes': implementation_hashes(), 'scope': 'fixture setup only, not authorization for live run'})
    study = prepare(identity, gate, fixture=True)
    reg, manifest, inputs = load(study)
    jobs = Jobs(study/'jobs.sqlite3')
    results = []
    for job in inputs['schedule']:
        jobs.claim(job_id(job))
        result = execute(study, reg, manifest, inputs, job, ScriptedProvider())
        jobs.finish(job_id(job), result)
        checked = audit(study/'units'/job_id(job), inputs['worlds'][0], job)
        assert result['status'] == 'completed' and checked['pass'] and checked['complete_correct'], (result, checked)
        results.append(checked)
        print(json.dumps({'job': job_id(job), **checked}), flush=True)
    job = inputs['schedule'][0]
    mutated = study/'missing-get-object-response'
    # Keep actor identity (audit binds it), while changing only one raw response.
    mutated_named = mutated/job_id(job)
    shutil.copytree(study/'units'/job_id(job), mutated_named)
    assert audit(mutated_named, inputs['worlds'][0], job)['pass']
    log = mutated_named/'supervisor/C.jsonl'
    events = [json.loads(s) for s in log.read_text().splitlines()]
    request = next(e for e in events if e.get('channel') == 'mcp' and e['message'].get('params', {}).get('name') == 'continuum_get_object')
    events = [e for e in events if not (e.get('event') == 'mcp_response' and e.get('connection') == request['connection'] and e['message'].get('id') == request['message']['id'])]
    log.write_text('\n'.join(json.dumps(e) for e in events)+'\n')
    sensitivity = audit(mutated_named, inputs['worlds'][0], job)
    assert not sensitivity['pass'] and 'missing unique successful raw get_object' in sensitivity['error'], sensitivity
    report = {'pass': True, 'contexts': len(results), 'model_requests': 0, 'results': results, 'sensitivity': sensitivity,
              'implementation_hashes': implementation_hashes()}
    write_json(study/'fixture-report.json', report)
    print(json.dumps({'pass': True, 'contexts': len(results), 'sensitivity_rejected': True}))
    return report


if __name__ == '__main__':
    import sys
    run(sys.argv[1])
