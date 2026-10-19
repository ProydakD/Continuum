"""Trusted narrow memory broker. Actual stdio MCP exchanges are recorded verbatim."""
import base64
import hashlib
import json
import queue
import subprocess
import sys
import threading
import uuid
from .common import PROJECT, server_env
from .supervisor import read_lines


class MemoryBridge:
    def __init__(self, run, stage, observations, log, model):
        self.run, self.stage, self.observations, self.log = run, stage, observations, log
        self.actor = run.name+':'+stage
        self.connection = uuid.uuid4().hex
        self.counter, self.task, self.previous, self.saved = 0, None, None, False
        self.read = False
        self.stderr = (run/'supervisor'/f'{stage}-mcp.stderr.txt').open('w', encoding='utf-8')
        self.process = subprocess.Popen([sys.executable, '-m', 'continuum.mcp_server'], cwd=PROJECT,
            env=server_env(run/'state/continuum.sqlite3', self.actor, run.name, model),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr, text=True, encoding='utf-8')
        self.inbox = queue.Queue()
        threading.Thread(target=read_lines, args=(self.process.stdout, self.inbox, 'mcp'), daemon=True).start()
        self.rpc('initialize', {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'e002-broker', 'version': '1'}})
        self.process.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n'); self.process.stdin.flush()
        self.rpc('tools/list', {})

    def emit(self, value):
        self.log.write(json.dumps(value)+'\n'); self.log.flush()

    def rpc(self, method, params):
        self.counter += 1
        msg = {'jsonrpc': '2.0', 'id': self.counter, 'method': method, 'params': params}
        self.emit({'channel': 'mcp', 'connection': self.connection, 'message': msg})
        self.process.stdin.write(json.dumps(msg)+'\n'); self.process.stdin.flush()
        while True:
            _, line = self.inbox.get(timeout=15)
            if not line:
                raise RuntimeError('MCP disconnected')
            value = json.loads(line)
            self.emit({'event': 'mcp_response', 'connection': self.connection, 'message': value})
            if value.get('id') != self.counter:
                continue
            if 'error' in value or value.get('result', {}).get('isError'):
                raise RuntimeError('MCP request failed')
            return value['result']

    def tool(self, name, **kwargs):
        value = self.rpc('tools/call', {'name': 'continuum_'+name, 'arguments': kwargs})
        return value.get('structuredContent') or json.loads(value['content'][0]['text'])

    def call(self, name, arguments):
        if not isinstance(arguments, dict):
            raise ValueError('tool arguments must be an object')
        if name == 'read_memory' and not arguments:
            state = self.tool('bootstrap')
            self.read = True
            if self.stage == 'A':
                if state['open_tasks']:
                    raise ValueError('A requires a fresh DB')
                return {'memory': None, 'observations': self.observations}
            if len(state['open_tasks']) != 1:
                raise ValueError('predecessor state missing')
            self.task = self.tool('get_task', task_id=state['open_tasks'][0]['id'])
            result = json.loads(self.task['result'])
            if result['stage'] != ('A' if self.stage == 'B' else 'B'):
                raise ValueError('wrong predecessor stage')
            obj = self.tool('get_object', sha256=result['object_sha256'])
            raw = base64.b64decode(obj['content_base64'], validate=True)
            if hashlib.sha256(raw).hexdigest() != result['object_sha256']:
                raise ValueError('memory digest mismatch')
            self.previous = json.loads(raw)
            return self.previous
        if name != 'save_memory' or set(arguments) != {'memory'} or not isinstance(arguments['memory'], str):
            raise PermissionError('tool outside narrow protocol')
        if not self.read or self.saved or self.stage == 'C' or not 1 <= len(arguments['memory']) <= 16000:
            raise PermissionError('invalid memory transition')
        if self.stage == 'A':
            self.task = self.tool('create_task', title='E-002 synthetic rules', objective='Revise knowledge from observations',
                                  next_step='B', request_key='e002')
            observations = self.observations
        else:
            observations = self.previous['observations'] + self.observations
        self.task = self.tool('claim_task', task_id=self.task['id'], expected_revision=self.task['revision'], lease_seconds=600)
        payload = {'stage': self.stage, 'observations': observations, 'memory': arguments['memory']}
        raw = json.dumps(payload, sort_keys=True).encode()
        sha = hashlib.sha256(raw).hexdigest()
        self.tool('put_object', content_base64=base64.b64encode(raw).decode(), sha256=sha, media_type='application/json')
        claim = self.tool('add_claim', subject=sha, predicate='model_memory', object=self.stage)
        self.tool('add_evidence', claim_id=claim['id'], expected_revision=claim['revision'], stance='supports',
                  reference='sha256:'+sha, sha256=sha, note='Model-reported reasoning; not verified truth')
        self.task = self.tool('checkpoint_task', task_id=self.task['id'], expected_revision=self.task['revision'], release=True,
                             result=json.dumps({'stage': self.stage, 'object_sha256': sha, 'claim_id': claim['id']}),
                             next_step='B' if self.stage == 'A' else 'C')
        self.saved = True
        return {'saved': True, 'stage': self.stage}

    def finish(self, answer):
        if self.stage != 'C':
            if not self.saved or answer != {'status': 'saved', 'stage': self.stage}:
                raise ValueError('worker did not save expected stage')
            return
        if not self.read or not self.previous:
            raise ValueError('C did not retrieve predecessor memory')
        task = self.tool('claim_task', task_id=self.task['id'], expected_revision=self.task['revision'], lease_seconds=600)
        prior = json.loads(task['result'])
        self.tool('finish_task', task_id=task['id'], expected_revision=task['revision'],
                  result=json.dumps({'stage': 'C', 'predecessor': prior, 'answer': answer}))

    def close(self):
        self.process.terminate()
        self.process.wait(timeout=10)
        for pipe in (self.process.stdin, self.process.stdout):
            pipe.close()
        self.stderr.close()
