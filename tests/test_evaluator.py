"""E-001 regression cases. Temporary real SQLite; synthetic RPC transcripts."""
import base64
from contextlib import closing
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from continuum.store import Store
from research.common import write_json
from research.evaluator import evaluate, final_result, input_commitment


def synthetic_run(run, values=None):
    values = [2, 3] if values is None else values
    manifest = {'control': 'handoff', 'run_id': run.name,
                'instances': {s: {'actor': run.name+':'+s} for s in 'ABC'}}
    write_json(run/'manifest.json', manifest)
    write_json(run/'evaluator/oracle.json', {'expected': 13, 'canary': 'TEST_CANARY',
                                           'input_sha256': input_commitment([2, 3])})
    raw = json.dumps({'values': values}).encode()
    sha = hashlib.sha256(raw).hexdigest()
    task, claim = None, None
    for stage in 'ABC':
        store = Store(run/'state/continuum.sqlite3', actor=manifest['instances'][stage]['actor'],
                      scope='lab', origin={'run_id': run.name})
        messages = []

        def call(name, args, invoke):
            request_id = len(messages)+1
            messages.append({'channel': 'mcp', 'connection': 'a'*32, 'message': {
                'id': request_id, 'method': 'tools/call', 'params': {'name': 'continuum_'+name, 'arguments': args}}})
            value = invoke()
            messages.append({'event': 'mcp_response', 'connection': 'a'*32,
                             'message': {'id': request_id, 'result': {'structuredContent': value}}})
            return value

        call('bootstrap', {}, store.bootstrap)
        if stage == 'A':
            task = call('create_task', {}, lambda: store.create_task('Square sum', 'squares', 'measure'))
        else:
            task = call('get_task', {'task_id': task['id']}, lambda: store.get_task(task['id']))
            call('get_object', {'sha256': sha}, lambda: store.get_object(sha))
        task = call('claim_task', {'task_id': task['id'], 'expected_revision': task['revision']},
                    lambda: store.claim_task(task['id'], expected_revision=task['revision']))
        call('put_object', {'sha256': sha}, lambda: store.put_object(base64.b64encode(raw).decode(), sha, 'application/json'))
        if stage == 'A':
            claim = call('add_claim', {}, lambda: store.add_claim({'subject': sha, 'predicate': 'sum_of_squares', 'object': '13'}))
        claim = call('get_claim', {'claim_id': claim['id']}, lambda: store.get_claim(claim['id']))
        claim = call('add_evidence', {'claim_id': claim['id'], 'sha256': sha, 'stance': 'supports'},
                     lambda: store.add_evidence(claim['id'], 'supports', 'sha256:'+sha, 'test',
                                               sha256=sha, expected_revision=claim['revision']))
        result = json.dumps({'stage': stage, 'total': 13, 'object_sha256': sha, 'claim_id': claim['id']})
        args = {'task_id': task['id'], 'result': result}
        if stage == 'C':
            task = call('finish_task', args, lambda: store.finish_task(task['id'], result, expected_revision=task['revision']))
        else:
            task = call('checkpoint_task', args, lambda: store.checkpoint_task(task['id'], 'verify', result, expected_revision=task['revision']))
        messages.append({'channel': 'worker', 'line': json.dumps({'status': 'completed_stage', 'stage': stage, 'total': 13})})
        write_json(run/'supervisor'/f'{stage}-result.json', {'status': 'completed', 'exit_status': 0, 'mode': 'fixture'})
        (run/'supervisor'/f'{stage}.jsonl').write_text(''.join(json.dumps(m)+'\n' for m in messages), encoding='utf-8')
    return manifest


class EvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.run = Path(self.temp.name)/'case'

    def tearDown(self):
        self.temp.cleanup()

    def evaluate(self, manifest):
        with patch('research.evaluator.load_manifest', return_value=manifest):
            return evaluate(self.run)

    def mutate_log(self, change):
        p = self.run/'supervisor/B.jsonl'
        log = [json.loads(line) for line in p.read_text().splitlines()]
        change(log)
        p.write_text(''.join(json.dumps(m)+'\n' for m in log), encoding='utf-8')

    def test_valid_handoff(self):
        m = synthetic_run(self.run)
        result = self.evaluate(m)
        self.assertTrue(result['pass'], result)

    def test_wrong_values_and_same_sum_rejected(self):
        for values in ([0], [3, 2], [-2, 3], [True, 2], 'not-an-array'):
            with self.subTest(values=values), tempfile.TemporaryDirectory() as temp:
                self.run = Path(temp)/'case'
                self.assertFalse(self.evaluate(synthetic_run(self.run, values))['pass'])

    def test_bound_read_failures(self):
        for mutation in ('wrong_object', 'failed', 'wrong_id', 'wrong_connection', 'wrong_task', 'wrong_checkpoint', 'wrong_claim'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp:
                self.run = Path(temp)/'case'
                m = synthetic_run(self.run)
                def change(log):
                    for i, e in enumerate(log):
                        name = e.get('message', {}).get('params', {}).get('name')
                        if name == 'continuum_get_object':
                            if mutation == 'wrong_object': e['message']['params']['arguments']['sha256'] = '0'*64
                            if mutation == 'failed': log[i+1]['message']['result']['isError'] = True
                            if mutation == 'wrong_id': log[i+1]['message']['id'] = 12345
                            if mutation == 'wrong_connection': log[i+1]['connection'] = 'b'*32
                        if name == 'continuum_get_task':
                            if mutation == 'wrong_task': e['message']['params']['arguments']['task_id'] = 'other'
                            if mutation == 'wrong_checkpoint': log[i+1]['message']['result']['structuredContent']['result'] = '{}'
                        if name == 'continuum_get_claim' and mutation == 'wrong_claim':
                            e['message']['params']['arguments']['claim_id'] = 'other'
                self.mutate_log(change)
                self.assertFalse(self.evaluate(m)['pass'])

    def test_intermediate_event_substitution(self):
        m = synthetic_run(self.run)
        with closing(sqlite3.connect(self.run/'state/continuum.sqlite3')) as db:
            # Deliberately corrupt only this disposable fixture, not a real ledger.
            for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='events'").fetchall():
                db.execute('DROP TRIGGER "'+name.replace('"', '""')+'"')
            seq, payload = db.execute("SELECT seq,payload FROM events WHERE action='checkpointed' ORDER BY seq DESC LIMIT 1").fetchone()
            payload = json.loads(payload)
            result = json.loads(payload['result']); result['object_sha256'] = '0'*64
            payload['result'] = json.dumps(result)
            db.execute('UPDATE events SET payload=? WHERE seq=?', (json.dumps(payload), seq))
            db.commit()
        self.assertFalse(self.evaluate(m)['pass'])

    def test_invalid_schema(self):
        m = synthetic_run(self.run)
        with closing(sqlite3.connect(self.run/'state/continuum.sqlite3')) as db:
            db.execute("UPDATE knowledge_objects SET media_type='text/plain'")
            db.commit()
        self.assertFalse(self.evaluate(m)['pass'])

    def test_final_forms_and_tool_quote(self):
        forms = ['{"status":"needs_context"}', '{"status": "needs_context"}', 'needs_context']
        for text in forms:
            self.assertEqual(final_result([text])['status'], 'needs_context')
            envelope = json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': text}})
            self.assertEqual(final_result([envelope])['status'], 'needs_context')
        quote = json.dumps({'type': 'item.completed', 'item': {'type': 'mcp_tool_call', 'output': forms[0]}})
        self.assertIsNone(final_result([quote]))
        invalid_last = json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'done'}})
        self.assertIsNone(final_result([forms[0], invalid_last]))

    def test_negative_end_to_end_forms(self):
        m = {'control': 'empty'}
        write_json(self.run/'evaluator/oracle.json', {'expected': 13, 'canary': 'TEST_CANARY'})
        write_json(self.run/'supervisor/B-result.json', {'status': 'completed', 'exit_status': 0, 'mode': 'fixture'})
        for text, expected in [('{"status":"needs_context"}', True), ('needs_context', True),
                               (json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '{"status":"needs_context"}'}}), True),
                               (json.dumps({'type': 'item.completed', 'item': {'type': 'mcp_tool_call', 'output': '{"status":"needs_context"}'}}), False)]:
            (self.run/'supervisor/B.jsonl').write_text(json.dumps({'channel': 'worker', 'line': text})+'\n')
            self.assertEqual(self.evaluate(m)['pass'], expected)


if __name__ == '__main__':
    unittest.main()
