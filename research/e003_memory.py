"""E-003 uses the same narrow tools and real MCP transport as E-002."""
import base64
import hashlib
import json
from .e002_memory import MemoryBridge


class SeriesMemoryBridge(MemoryBridge):
    def call(self, name, arguments):
        if not isinstance(arguments, dict):
            raise ValueError('tool arguments must be an object')
        if name == 'read_memory' and not arguments:
            state = self.tool('bootstrap')
            self.read = True
            if self.stage == 'A':
                if state['open_tasks']:
                    raise ValueError('A requires an empty experimental DB')
                return {'memory': None, 'observations': self.observations}
            if not state['open_tasks']:
                # A real absence of stored state is observable, not a fabricated result.
                self.task, self.previous = None, None
                return {'status': 'missing', 'memory': None, 'observations': []}
            if len(state['open_tasks']) != 1:
                raise ValueError('ambiguous experimental DB')
            self.task = self.tool('get_task', task_id=state['open_tasks'][0]['id'])
            checkpoint = json.loads(self.task['result'])
            if checkpoint['stage'] != ('A' if self.stage == 'B' else 'B'):
                raise ValueError('incorrect predecessor')
            obj = self.tool('get_object', sha256=checkpoint['object_sha256'])
            raw = base64.b64decode(obj['content_base64'], validate=True)
            if hashlib.sha256(raw).hexdigest() != checkpoint['object_sha256']:
                raise ValueError('memory digest mismatch')
            self.previous = json.loads(raw)
            return self.previous
        if name != 'save_memory' or set(arguments) != {'memory'} or not isinstance(arguments['memory'], str):
            raise PermissionError('tool outside registered memory protocol')
        if not self.read or self.saved or self.stage == 'C' or not 1 <= len(arguments['memory']) <= 24000:
            raise PermissionError('invalid memory transition')
        if self.stage == 'A':
            self.task = self.tool('create_task', title='Synthetic rule task', objective='Revise rule knowledge from exact observations',
                                  next_step='B', request_key='e003')
            observations = self.observations
        else:
            if self.previous is None:
                raise ValueError('cannot fabricate predecessor observations')
            observations = self.previous['observations']+self.observations
        self.task = self.tool('claim_task', task_id=self.task['id'], expected_revision=self.task['revision'], lease_seconds=600)
        raw = json.dumps({'stage': self.stage, 'observations': observations, 'memory': arguments['memory']}, sort_keys=True).encode()
        sha = hashlib.sha256(raw).hexdigest()
        self.tool('put_object', content_base64=base64.b64encode(raw).decode(), sha256=sha, media_type='application/json')
        claim = self.tool('add_claim', subject=sha, predicate='model_memory', object=self.stage)
        self.tool('add_evidence', claim_id=claim['id'], expected_revision=claim['revision'], stance='supports',
                  reference='sha256:'+sha, sha256=sha, note='Model-reported explanation; not independent verification')
        self.task = self.tool('checkpoint_task', task_id=self.task['id'], expected_revision=self.task['revision'], release=True,
                             result=json.dumps({'stage': self.stage, 'object_sha256': sha, 'claim_id': claim['id']}),
                             next_step='B' if self.stage == 'A' else 'C')
        self.saved = True
        return {'saved': True, 'stage': self.stage}

    def finish(self, answer):
        if self.stage != 'C':
            if (not self.saved or not isinstance(answer, dict) or set(answer) != {'status', 'stage', 'working_rule'}
                    or answer['status'] != 'saved' or answer['stage'] != self.stage
                    or not isinstance(answer['working_rule'], dict) or set(answer['working_rule']) != {'a', 'b', 'c', 'd', 'e', 't'}
                    or any(type(v) is not int for v in answer['working_rule'].values())):
                raise ValueError('invalid A/B final schema or unsaved memory')
            # Do not judge the model's working rule here; evaluator sees it later.
            return
        if not self.read:
            raise ValueError('C must actually request memory')
        if self.task is None:
            return  # The evaluator distinguishes valid refusal from unsupported guesses.
        task = self.tool('claim_task', task_id=self.task['id'], expected_revision=self.task['revision'], lease_seconds=600)
        self.tool('finish_task', task_id=task['id'], expected_revision=task['revision'],
                  result=json.dumps({'stage': 'C', 'predecessor': json.loads(task['result']), 'answer': answer}))
