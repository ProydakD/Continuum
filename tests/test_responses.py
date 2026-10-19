from contextlib import closing
import io
import json
from pathlib import Path
import sqlite3
import ssl
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from research.e002_protocol import world, prompt, score_answer
from research.e002_memory import MemoryBridge
from research.responses_provider import ResponsesProvider, SpendLedger


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_default_deny(self):
        with self.assertRaises(PermissionError):
            ResponsesProvider('https://example.test/v1', 'model', None, self.root/'log')
        with self.assertRaises(PermissionError):
            SpendLedger(self.root/'ledger')

    def test_aggregate_reservation_no_refund_for_failure(self):
        a = SpendLedger(self.root/'ledger', budget_usd='0.25', upper_request_usd='0.10')
        b = SpendLedger(self.root/'ledger', budget_usd='0.25', upper_request_usd='0.10')
        first = a.reserve('C1:A')
        with self.assertRaises(RuntimeError): b.reserve('T1:A')
        a.finish(first, 'failed_or_unknown')
        b.finish(b.reserve('T1:A'), 'completed', {'total_tokens': 1})
        with self.assertRaises(PermissionError): a.reserve('smoke')
        with self.assertRaises(PermissionError): SpendLedger(self.root/'ledger', unbounded=True)

    def test_request_error_is_one_attempt_and_does_not_log_key(self):
        ledger = SpendLedger(self.root/'ledger', unbounded=True)
        p = ResponsesProvider('https://example.test/v1', 'model', ledger, self.root/'log', authorize=True, key='SECRET_SENTINEL')
        with patch.object(p, 'request', side_effect=TimeoutError('SECRET_SENTINEL')) as send:
            with self.assertRaises(TimeoutError): p.respond('smoke', [], [])
            self.assertEqual(send.call_count, 1)
        self.assertNotIn('SECRET_SENTINEL', (self.root/'log').read_text())
        with closing(sqlite3.connect(self.root/'ledger')) as db:
            self.assertEqual(db.execute('SELECT outcome FROM attempts').fetchone()[0], 'failed_or_unknown')

    def test_fixed_origin_tls_and_no_redirect(self):
        for url in ('http://example.test/v1', 'https://user:pass@example.test/v1', 'https://example.test/v1?x=1'):
            with self.assertRaises(ValueError):
                ResponsesProvider(url, 'm', None, self.root/'log', authorize=True, key='sentinel')
        p = ResponsesProvider('https://example.test/v1', 'm', None, self.root/'log', authorize=True, key='sentinel')
        with patch('research.responses_provider.http.client.HTTPSConnection') as http:
            http.return_value.getresponse.return_value.status = 302
            http.return_value.getresponse.return_value.read.return_value = b'{}'
            with self.assertRaises(RuntimeError): p.models()
            self.assertEqual(http.call_count, 1)
            context = http.call_args.kwargs['context']
            self.assertTrue(context.check_hostname)
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        with self.assertRaises(PermissionError): p.request('GET', '/arbitrary')

    def test_stateless_payload_and_usage(self):
        p = ResponsesProvider('https://example.test/v1', 'm', SpendLedger(self.root/'l', unbounded=True),
                              self.root/'log', authorize=True, key='sentinel')
        response = {'status': 'completed', 'model': 'm', 'output': [], 'usage': {'input_tokens': 3, 'output_tokens': 2}}
        with patch.object(p, 'request', return_value=response) as send:
            p.respond('C1:A', [{'role': 'user', 'content': 'synthetic'}], [])
            payload = send.call_args.args[2]
            self.assertFalse(payload['store'])
            self.assertNotIn('previous_response_id', payload)
            self.assertEqual(payload['max_output_tokens'], 2048)


class ProtocolTests(unittest.TestCase):
    def test_finite_world_and_equal_input_information(self):
        for seed in range(20):
            w = world(seed)
            self.assertGreaterEqual(len(w['compatible_a']), 2)
            self.assertEqual(len(w['compatible_b']), 1)
            for condition in ('C1', 'T1'):
                self.assertIn(json.dumps(w['observations_a']), prompt(w, condition, 'A'))
                self.assertIn(json.dumps(w['observation_b']), prompt(w, condition, 'B'))
                self.assertNotIn(json.dumps(w['answers']), prompt(w, condition, 'C'))
            answer = {'status': 'completed', 'rule': w['truth'], 'predictions': w['answers']}
            self.assertTrue(score_answer(answer, w))
            answer['predictions'] = list(reversed(w['answers']))
            self.assertFalse(score_answer(answer, w))

    def test_real_mcp_memory_handoff_and_narrow_tools(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp)/'memory-case'; (run/'supervisor').mkdir(parents=True)
            w = world(711)
            for stage in 'ABC':
                observations = w['observations_a'] if stage == 'A' else [w['observation_b']] if stage == 'B' else []
                bridge = MemoryBridge(run, stage, observations, io.StringIO(), 'test-fixture-no-model')
                try:
                    with self.assertRaises(PermissionError): bridge.call('shell', {'command': 'anything'})
                    memory = bridge.call('read_memory', {})
                    if stage == 'B': self.assertEqual(memory['observations'], w['observations_a'])
                    if stage == 'C': self.assertEqual(memory['observations'], w['observations_a']+[w['observation_b']])
                    if stage != 'C':
                        bridge.call('save_memory', {'memory': 'synthetic reasoning '+stage})
                        with self.assertRaises(PermissionError): bridge.call('save_memory', {'memory': 'duplicate'})
                        bridge.finish({'status': 'saved', 'stage': stage})
                    else:
                        bridge.finish({'status': 'completed', 'rule': w['truth'], 'predictions': w['answers']})
                finally:
                    bridge.close()


if __name__ == '__main__':
    unittest.main()
