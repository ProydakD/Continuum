"""Real Docker/MCP intervention fixture, scripted model replies; no HTTP or LLM."""
import argparse
import json
from pathlib import Path
from .common import ROOT, write_json, source_hashes
from .e003 import execute_worker, unit_path
from .e003_protocol import make_corpus, prompt, compatible, rules, value, score
from .e003_audit import audit_stage
from .profiles import create_worker
from .sandbox import image_id, isolation_probe


class ScriptedProvider:
    fixture = True

    def __init__(self, world, stage):
        self.world, self.stage, self.calls, self.working = world, stage, 0, None

    def respond(self, worker, history, tools, timeout=30, **kwargs):
        self.calls += 1
        def tool(name, args):
            return {'type': 'function_call', 'name': name, 'arguments': json.dumps(args), 'call_id': 'fixture-'+str(self.calls)}
        def final(answer):
            return {'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': json.dumps(answer)}]}
        if self.calls == 1:
            output = tool('read_memory', {})
        elif self.calls == 2:
            state = json.loads(history[-1]['output'])
            if state.get('status') == 'missing':
                output = final({'status': 'needs_context'})
            else:
                observations = state['observations']+(self.world['observations_b'] if self.stage == 'B' else [])
                fits = compatible(self.world['family'], observations)
                self.working = rules(self.world['family'])[fits[0]]
                if self.stage == 'C':
                    predictions = [value(self.world['family'], self.working, (q['x'], q['z'])) for q in self.world['questions']]
                    output = final({'status': 'completed', 'predictions': predictions,
                                    'derived': {'sum': sum(predictions), 'contrast': predictions[0]-predictions[-1]}})
                else:
                    output = tool('save_memory', {'memory': json.dumps({'fixture': True, 'working_rule': self.working, 'compatible_count': len(fits)})})
        elif self.calls == 3 and self.stage in 'AB':
            output = final({'status': 'saved', 'stage': self.stage, 'working_rule': self.working})
        else:
            raise ValueError('fixture tool loop deviated; do not hide it')
        return {'status': 'completed', 'model': 'deterministic-fixture', 'output': [output]}


def run(identity):
    study = ROOT/'runs'/identity
    study.mkdir(exist_ok=False)
    full = make_corpus()
    worlds = full['worlds'][:2]
    corpus = {'worlds': worlds, 'donors': {worlds[0]['id']: worlds[1]['id'], worlds[1]['id']: worlds[0]['id']}}
    image = image_id('python:3.11-slim-bookworm')
    manifest = {'image': image, 'model': 'deterministic-fixture'}
    reg = {'limits': {'worker_seconds': 90, 'request_seconds': 30, 'max_output_tokens': 4096}}
    schedule = []
    for w in worlds:
        for condition in ('C1', 'T1'):
            for branch in ('base', 'intact', 'deleted', 'swapped'):
                unit = unit_path(study, w['id'], condition, branch)
                for part in ('supervisor', 'evaluator', 'state', 'workers'):
                    (unit/part).mkdir(parents=True)
                instances = {}
                for stage in ('AB' if branch == 'base' else 'C'):
                    worker = unit/'workers'/stage
                    create_worker(worker, stage, 'none')
                    write_json(worker/'repo/PROMPT.txt', {'prompt': prompt(w, condition, stage)})
                    instances[stage] = {'initial_hashes': source_hashes(worker)}
                write_json(unit/'manifest.json', {'instances': instances})
            schedule.extend({'world': w['id'], 'condition': condition, 'branch': 'base', 'stage': stage} for stage in 'AB')
    for w in worlds:
        for condition in ('C1', 'T1'):
            schedule.extend({'world': w['id'], 'condition': condition, 'branch': branch, 'stage': 'C'} for branch in ('intact', 'deleted', 'swapped'))
    probe = isolation_probe(image, unit_path(study, worlds[0]['id'], 'C1', 'base')/'workers/A', study/'isolation.json')
    assert probe['isolation_pass']
    outcomes = []
    for job in schedule:
        w = next(w for w in worlds if w['id'] == job['world'])
        result = execute_worker(study, manifest, reg, corpus, job, ScriptedProvider(w, job['stage']), mode='fixture')
        if result['status'] != 'completed':
            raise RuntimeError(result)
        unit = unit_path(study, job['world'], job['condition'], job['branch'])
        donor = next(w for w in worlds if w['id'] == corpus['donors'][job['world']])
        audit = audit_stage(unit, job['stage'], w, donor if job['branch'] == 'swapped' else None)
        assert audit['pass'], audit
        if job['stage'] == 'C':
            answer = json.loads((unit/'supervisor/C-answer.json').read_text())
            if job['branch'] == 'intact':
                assert score(answer, w)
            elif job['branch'] == 'deleted':
                assert answer == {'status': 'needs_context'}
            else:
                predictions = [value(w['family'], donor['truth'], (q['x'], q['z'])) for q in w['questions']]
                assert answer['predictions'] == predictions and not score(answer, w)
        outcomes.append({'job': job, 'status': result['status'], 'audit_pass': audit['pass']})
        print(json.dumps(outcomes[-1]), flush=True)
    report = {'pass': True, 'contexts': len(outcomes), 'model_requests': 0, 'mode': 'deterministic_fixture',
              'outcomes': outcomes, 'code_hashes': source_hashes(), 'corpus': corpus}
    write_json(study/'fixture-report.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    result = run(args.run_id)
    print(json.dumps({'pass': result['pass'], 'contexts': result['contexts'], 'model_requests': 0}))
