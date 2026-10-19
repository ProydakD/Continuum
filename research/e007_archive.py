"""Append-only protocol objects through real MCP; model tools cannot change the evaluator."""
import base64
import hashlib
import json
from .e002_memory import MemoryBridge
from .e005_protocol import serialized


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


class Archive(MemoryBridge):
    def index(self):
        tasks = self.tool('bootstrap')['open_tasks']
        if not tasks:
            return None, {}
        if len(tasks) != 1:
            raise ValueError('ambiguous E007 archive')
        task = self.tool('get_task', task_id=tasks[0]['id'])
        return task, json.loads(task['result']) if task['result'] else {}

    def blob(self, sha):
        obj = self.tool('get_object', sha256=sha)
        raw = base64.b64decode(obj['content_base64'], validate=True)
        if hashlib.sha256(raw).hexdigest() != sha:
            raise ValueError('archive checksum')
        return raw

    def get(self, key):
        _, index = self.index()
        if key not in index:
            return None
        return json.loads(self.blob(index[key]))

    def put_blob(self, raw, media_type='application/json'):
        sha = hashlib.sha256(raw).hexdigest()
        self.tool('put_object', content_base64=base64.b64encode(raw).decode(), sha256=sha, media_type=media_type)
        return sha

    def put(self, key, value):
        task, index = self.index()
        if key in index:
            raise ValueError('immutable archive slot already exists')
        if task is None:
            task = self.tool('create_task', title='E007 protocol archive', objective='Preserve attributed immutable research objects',
                             next_step='registered controller only', request_key='e007-archive')
        task = self.tool('claim_task', task_id=task['id'], expected_revision=task['revision'], lease_seconds=600)
        sha = self.put_blob(canonical(value))
        index[key] = sha
        self.tool('checkpoint_task', task_id=task['id'], expected_revision=task['revision'], release=True,
                  result=json.dumps(index, sort_keys=True), next_step='registered controller only')
        return sha

    def protocol(self, version):
        record = self.get('protocol:'+version)
        if record is None:
            return None
        raw = self.blob(record['blob_sha256'])
        body = raw.decode('utf-8') if record['encoding'] == 'utf8' else base64.b64encode(raw).decode()
        return {'version': version, 'sha256': record['blob_sha256'], 'encoding': record['encoding'],
                'media_type': record['media_type'], 'body': body}


class SessionBridge(Archive):
    def configure(self, job):
        self.job = job
        self.reads = set()
        self.attempts = 0
        self.saved = False

    def read_once(self, name):
        if name in self.reads:
            raise ValueError('duplicate retrieval')
        self.reads.add(name)

    def call(self, name, arguments):
        if not isinstance(arguments, dict):
            raise ValueError('arguments must be an object')
        role = self.job['role']
        if name == 'read_development' and arguments == {} and role in ('designer', 'critic'):
            self.read_once(name)
            _, index = self.index()
            permitted = sorted(k for k in index if k == 'training' or k.startswith(('protocol:', 'review:', 'feedback:')))
            result = {k: self.get(k) for k in permitted}
            result['definitions'] = {k: self.protocol(k.split(':', 1)[1]) for k in permitted if k.startswith('protocol:')}
            return result
        if name == 'read_protocol' and arguments == {} and role in ('writer', 'reader'):
            self.read_once(name)
            version = self.job.get('protocol_version')
            control = self.job.get('control') if role == 'reader' else None
            if control == 'missing':
                version = None
            elif control == 'stale':
                version = self.job['campaign']+'-v1'
            selected = self.protocol(version) if version else None
            from .e007_protocol import AMBIGUOUS, INCOMPATIBLE
            overlay = {'ambiguous': AMBIGUOUS, 'incompatible': INCOMPATIBLE}.get(control)
            if overlay and selected is not None:
                selected = dict(selected, controlled_interpretation=overlay)
            return {'protocol': selected}
        if name == 'read_memory' and arguments == {} and role == 'reader':
            self.read_once(name)
            value = self.get('message')
            if value and self.job.get('control') == 'corrupt':
                text = value['memory']
                position = len(text)//2
                value = {'memory': text[:position]+('!' if text[position]=='?' else '?')+text[position+1:]}
            return {'memory': None} if value is None else value
        if name == 'save_memory' and role == 'writer' and set(arguments) == {'memory'} and isinstance(arguments['memory'], str):
            if 'read_protocol' not in self.reads or self.saved or self.attempts >= 2:
                raise ValueError('invalid writer transition')
            self.attempts += 1
            text = arguments['memory']
            size = len(serialized(text))
            if not text or size > self.job['budget']:
                return {'saved': False, 'bytes': size, 'budget': self.job['budget'], 'attempts_left': 2-self.attempts}
            # Store the exact default-json read result, not compact canonical JSON.
            task, index = self.index()
            if 'message' in index:
                raise ValueError('message already exists')
            if task is None:
                task = self.tool('create_task', title='E007 message', objective='Only model-written bounded memory', next_step='reader', request_key='e007-message')
            task = self.tool('claim_task', task_id=task['id'], expected_revision=task['revision'], lease_seconds=600)
            sha = self.put_blob(serialized(text))
            index['message'] = sha
            self.tool('checkpoint_task', task_id=task['id'], expected_revision=task['revision'], release=True,
                      result=json.dumps(index, sort_keys=True), next_step='reader')
            self.saved = True
            return {'saved': True, 'bytes': size}
        if name == 'publish_protocol' and role == 'designer':
            if self.saved or 'read_development' not in self.reads:
                raise ValueError('invalid publication transition')
            expected = {'body', 'encoding', 'media_type', 'reason', 'compatibility', 'accepted', 'rejected'}
            if set(arguments) != expected or arguments['encoding'] not in ('utf8', 'base64'):
                raise ValueError('protocol record schema')
            if any(not isinstance(arguments[k], str) for k in ('body', 'media_type', 'reason', 'compatibility')):
                raise ValueError('protocol scalar type')
            if any(not isinstance(arguments[k], list) or len(arguments[k]) > 8 or any(not isinstance(v, str) or len(v) > 512 for v in arguments[k]) for k in ('accepted', 'rejected')):
                raise ValueError('protocol alternatives schema')
            raw = arguments['body'].encode('utf-8') if arguments['encoding'] == 'utf8' else base64.b64decode(arguments['body'], validate=True)
            if not 1 <= len(raw) <= 4096 or len(canonical(arguments)) > 16384:
                raise ValueError('protocol publication byte ceiling')
            version = self.job['publish_version']
            sha = self.put_blob(raw, arguments['media_type'])
            record = {k: v for k, v in arguments.items() if k != 'body'}
            record.update(version=version, blob_sha256=sha, author=self.actor, claim_status='model_proposed_not_universally_verified')
            self.put('protocol:'+version, record)
            self.saved = True
            return {'published': version, 'sha256': sha, 'body_bytes': len(raw)}
        if name == 'publish_review' and role == 'critic' and set(arguments) == {'review'} and isinstance(arguments['review'], str):
            if self.saved or 'read_development' not in self.reads or not 1 <= len(arguments['review'].encode()) <= 4096:
                raise ValueError('invalid review publication')
            self.put('review:'+self.job['review_version'], {'review': arguments['review'], 'author': self.actor, 'claim_status': 'model_commentary_not_verification'})
            self.saved = True
            return {'saved': True}
        raise PermissionError('tool outside frozen role')

    def finish(self, answer):
        role = self.job['role']
        if role in ('designer', 'critic'):
            if not self.saved or answer != {'status': 'saved'}:
                raise ValueError('publication final not bound to MCP save')
        elif role == 'writer':
            if self.attempts == 0 or answer != {'status': 'saved' if self.saved else 'not_saved'}:
                raise ValueError('writer final not bound to memory')
        elif self.reads != {'read_protocol', 'read_memory'}:
            raise ValueError('reader must retrieve exactly assigned protocol and memory')
