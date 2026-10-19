"""Actual Docker/MCP handoffs; scripted replies and zero API requests."""
import copy
import json
from pathlib import Path
import shutil
from .common import ROOT, write_json
from .e003 import Jobs, implementation_hashes, job_id
from .e004_audit import calculate
from .e005 import execute, load
from .e006 import prepare
from .e006_audit import audit, evaluate
from .e006_protocol import FIELDS


class ScriptedProvider:
    fixture = True

    def __init__(self):
        self.events, self.attempt = [], 0

    def respond(self, worker, history, tools, **kwargs):
        self.attempt += 1
        def tool(name, args):
            return {'type': 'function_call', 'name': name, 'arguments': json.dumps(args), 'call_id': 'fixture-'+str(self.attempt)}
        def final(value):
            return {'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': json.dumps(value)}]}
        if tools[0]['name'] == 'save_memory':
            if len(history) == 1:
                item = tool('save_memory', {'memory': 'oversized'*100})
            elif len([x for x in history if x.get('type') == 'function_call_output']) == 1:
                rule = json.loads(history[0]['content'].split('Correct rule: ')[1])
                budget = int(history[0]['content'].split('Budget: ')[1].split(' bytes.')[0])
                memory = '?' if budget == 24 else 'oversized'*100 if budget == 32 else json.dumps([rule[k] for k in FIELDS], separators=(',', ':'))
                item = tool('save_memory', {'memory': memory})
            else:
                item = final({'status': 'saved' if json.loads(history[-1]['output'])['saved'] else 'not_saved'})
        elif len(history) == 1:
            item = tool('read_memory', {})
        else:
            text = json.loads(history[-1]['output'])['memory']
            encoded = json.loads(text) if text and text != '?' else None
            rule = dict(zip(FIELDS, encoded)) if isinstance(encoded, list) else encoded
            points = json.loads(history[0]['content'].split('Queries: ')[1])
            item = final(calculate(rule, points))
        response = {'status': 'completed', 'model': 'scripted-fixture', 'output': [item]}
        self.events.append(copy.deepcopy({'event': 'request_started', 'attempt': self.attempt, 'worker': worker,
                                         'payload': {'input': history, 'tools': tools}}))
        self.events.append(copy.deepcopy({'event': 'response', 'attempt': self.attempt, 'worker': worker, 'response': response}))
        return response


def run(identity):
    art = ROOT/'artifacts/e006-001'
    gate = art/(identity+'-setup.json')
    write_json(gate, {'pass': True, 'implementation_hashes': implementation_hashes(), 'scope': 'offline fixture setup, not live authorization'})
    study = prepare(identity, gate, fixture=True)
    reg, manifest, inputs = load(study)
    ledger, provider = Jobs(study/'jobs.sqlite3'), ScriptedProvider()
    outcomes = []
    for job in inputs['schedule']:
        ledger.claim(job_id(job))
        result = execute(study, reg, manifest, inputs, job, provider)
        ledger.finish(job_id(job), result)
        if result['status'] != 'skipped_dependency':
            checked = audit(study/'units'/job_id(job), inputs['worlds'][0], job, provider.events)
            assert checked['pass'], (result, checked)
            if job['stage'] == 'C':
                assert checked['complete_correct'] == (job['condition'] in ('REF', 'EMPTY') or job['budget'] == 48), checked
        else:
            checked = {'expected_dependency_skip': True}
        outcomes.append({'job': job, 'status': result['status'], 'audit': checked})
        print(json.dumps({'job': job_id(job), 'status': result['status'], 'check': checked.get('pass', 'expected_skip')}), flush=True)
    (study/'provider.jsonl').write_text('\n'.join(json.dumps(e) for e in provider.events)+'\n')
    target = next(j for j in inputs['schedule'] if j['stage'] == 'C' and j['condition'] == 'REF')
    copied = study/'negative'/job_id(target)
    shutil.copytree(study/'units'/job_id(target), copied)
    assert audit(copied, inputs['worlds'][0], target, provider.events)['pass']
    log = copied/'supervisor/C.jsonl'
    events = [json.loads(s) for s in log.read_text().splitlines()]
    request = next(e for e in events if e.get('channel') == 'mcp' and e['message'].get('params', {}).get('name') == 'continuum_get_object')
    events = [e for e in events if not (e.get('event') == 'mcp_response' and e.get('connection') == request['connection'] and e['message'].get('id') == request['message']['id'])]
    log.write_text('\n'.join(json.dumps(e) for e in events)+'\n')
    missing = audit(copied, inputs['worlds'][0], target, provider.events)
    assert not missing['pass'] and 'missing unique successful raw get_object' in missing['error'], missing
    writer = next(j for j in inputs['schedule'] if j['stage'] == 'A')
    altered_network = copy.deepcopy(provider.events)
    response = next(e for e in altered_network if e['event'] == 'response' and e['worker'] == job_id(writer))
    response['response']['output'][0]['arguments'] = '{"memory":"not the model-written bytes"}'
    authorship = audit(study/'units'/job_id(writer), inputs['worlds'][0], writer, altered_network)
    assert not authorship['pass'] and 'not authored' in authorship['error'], authorship
    evaluation = evaluate(study)
    assert evaluation['terminal'] and evaluation['primary']['difference_48_minus_24'] == 1
    assert evaluation['statuses'] == {'budget_rejected': 2, 'completed': 10, 'skipped_dependency': 2}
    report = {'pass': True, 'contexts': len(outcomes), 'model_requests': 0, 'outcomes': outcomes,
              'missing_read_rejected': missing, 'forged_writer_rejected': authorship,
              'implementation_hashes': implementation_hashes()}
    write_json(study/'fixture-report.json', report)
    print(json.dumps({'pass': True, 'positions': len(outcomes), 'negative_controls': 2, 'model_requests': 0}))
    return report


if __name__ == '__main__':
    import sys
    run(sys.argv[1])
