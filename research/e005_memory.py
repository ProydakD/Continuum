"""Only model-supplied bounded bytes cross A->C, through actual Continuum MCP."""
import base64
import hashlib
import json
from .e002_memory import MemoryBridge
from .e005_protocol import serialized


class AuthoredMemoryBridge(MemoryBridge):
    def configure(self, budget):
        self.budget, self.attempts = budget, 0

    def persist(self, text):
        raw = serialized(text)
        if not isinstance(text, str) or not text or len(raw) > self.budget:
            raise ValueError('invalid checkpoint')
        if self.tool('bootstrap')['open_tasks']:
            raise ValueError('checkpoint must start in an empty database')
        task = self.tool('create_task', title='Synthetic authored memory', objective='Preserve only bounded checkpoint', next_step='C', request_key='e005')
        task = self.tool('claim_task', task_id=task['id'], expected_revision=task['revision'], lease_seconds=600)
        sha = hashlib.sha256(raw).hexdigest()
        self.tool('put_object', content_base64=base64.b64encode(raw).decode(), sha256=sha, media_type='application/json')
        self.tool('checkpoint_task', task_id=task['id'], expected_revision=task['revision'], release=True,
                  result=json.dumps({'object_sha256': sha}), next_step='C')
        self.saved = True
        return {'saved': True, 'bytes': len(raw)}

    def call(self, name, arguments):
        if self.stage == 'A' and name == 'save_memory' and isinstance(arguments, dict) and set(arguments) == {'memory'} and isinstance(arguments['memory'], str):
            if self.saved or self.attempts >= 2:
                raise ValueError('save quota exceeded or already saved')
            self.attempts += 1
            size = len(serialized(arguments['memory']))
            if not arguments['memory'] or size > self.budget:
                return {'saved': False, 'bytes': size, 'budget': self.budget, 'attempts_left': 2-self.attempts}
            return self.persist(arguments['memory'])
        if self.stage != 'C' or name != 'read_memory' or arguments != {}:
            raise PermissionError('tool outside assigned stage')
        if self.read:
            raise ValueError('only one read is registered')
        self.read = True
        tasks = self.tool('bootstrap')['open_tasks']
        if not tasks:
            return {'memory': None}
        if len(tasks) != 1:
            raise ValueError('ambiguous predecessor')
        task = self.tool('get_task', task_id=tasks[0]['id'])
        sha = json.loads(task['result'])['object_sha256']
        obj = self.tool('get_object', sha256=sha)
        raw = base64.b64decode(obj['content_base64'], validate=True)
        payload = json.loads(raw)
        if hashlib.sha256(raw).hexdigest() != sha or raw != serialized(payload['memory']) or len(raw) > self.budget:
            raise ValueError('invalid transferred checkpoint or byte budget')
        return payload

    def finish(self, answer):
        if self.stage == 'A':
            expected = {'status': 'saved' if self.saved else 'not_saved'}
            if answer != expected or self.attempts == 0:
                raise ValueError('writer final status not bound to save attempts')
        elif not self.read:
            raise ValueError('reader did not request memory')
