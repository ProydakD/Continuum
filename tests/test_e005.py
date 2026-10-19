import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from research.e005 import recover
from research.e005_memory import AuthoredMemoryBridge
from research.e005_protocol import BUDGETS, corpus, reader_prompt, writer_prompt, reference_memory, serialized
from research.e005_audit import statistics


class E005Tests(unittest.TestCase):
    def test_balanced_frozen_schedule_and_dependencies(self):
        c = corpus()
        self.assertEqual(c, corpus())
        self.assertEqual(len(c['worlds']), 6)
        self.assertEqual(len(c['schedule']), 156)
        self.assertEqual(sum(j['stage'] == 'A' for j in c['schedule']), 72)
        self.assertEqual(len({(j['world'], j['condition'], j['branch'], j['stage']) for j in c['schedule']}), 156)
        self.assertTrue(all(j['stage'] == 'A' for j in c['schedule'][:72]))
        self.assertTrue(all(j['stage'] == 'C' for j in c['schedule'][72:]))
        self.assertEqual(BUDGETS, (48, 96, 192))

    def test_writer_never_gets_queries_reader_never_gets_truth_or_budget(self):
        for w in corpus()['worlds']:
            other = copy.deepcopy(w)
            other['queries'] = [(0, 0)]*5
            self.assertEqual(writer_prompt(w, 'C1', 48), writer_prompt(other, 'C1', 48))
            other = copy.deepcopy(w)
            other['rule']['delta'] *= -1
            self.assertEqual(reader_prompt(w), reader_prompt(other))
            self.assertNotIn('Budget:', reader_prompt(w))
            self.assertNotIn('C1', reader_prompt(w))
            self.assertNotIn('T1', reader_prompt(w))

    def test_whole_result_counts_escaping_and_unicode(self):
        for value in ('abc', '"\\', 'я', '\n'):
            self.assertEqual(serialized(value), json.dumps({'memory': value}).encode('utf-8'))
        self.assertGreater(len(serialized('я')), len(serialized('a')))

    def test_correct_reference_fits_largest_budget(self):
        for w in corpus()['worlds']:
            text = reference_memory(w)
            self.assertEqual(json.loads(text), w['rule'])
            self.assertLessEqual(len(serialized(text)), 192)

    def bridge(self, budget=48):
        b = AuthoredMemoryBridge.__new__(AuthoredMemoryBridge)
        b.stage, b.saved, b.read = 'A', False, False
        b.configure(budget)
        b.persist = Mock(return_value={'saved': True, 'bytes': len(serialized('ok'))})
        return b

    def test_reject_then_repair_no_truncation_or_persist_on_reject(self):
        b = self.bridge()
        text = 'x'*100
        r = b.call('save_memory', {'memory': text})
        self.assertFalse(r['saved'])
        self.assertEqual(r['bytes'], len(serialized(text)))
        b.persist.assert_not_called()
        self.assertTrue(b.call('save_memory', {'memory': 'ok'})['saved'])
        b.persist.assert_called_once_with('ok')
        with self.assertRaises(ValueError):
            b.call('save_memory', {'memory': 'ok'})

    def test_exact_budget_boundary_and_stage_tools(self):
        text = 'a'*34
        self.assertEqual(len(serialized(text)), 48)
        b = self.bridge()
        b.call('save_memory', {'memory': text})
        b.persist.assert_called_once_with(text)
        with self.assertRaises(PermissionError):
            b.call('read_memory', {})
        b = self.bridge()
        self.assertFalse(b.call('save_memory', {'memory': text+'a'})['saved'])

    def test_saved_flag_is_not_sufficient_for_valid_final(self):
        b = self.bridge()
        with self.assertRaises(ValueError):
            b.finish({'status': 'saved'})
        b.attempts, b.saved = 1, True
        b.finish({'status': 'saved'})
        with self.assertRaises(ValueError):
            b.finish({'status': 'not_saved'})

    def test_recovery_fails_closed_on_catalog_auth_error(self):
        with tempfile.TemporaryDirectory() as d, patch('research.e005.time.sleep') as sleep:
            provider = Mock(model='gpt-6-sol')
            provider.models.side_effect = RuntimeError('provider HTTP status 401; no retry or redirect')
            with self.assertRaises(RuntimeError):
                recover(provider, Path(d))
            provider.models.assert_called_once()
            sleep.assert_called_once_with(30)
            provider.respond.assert_not_called()

    def test_recovery_only_catalog_until_frozen_model_present(self):
        with tempfile.TemporaryDirectory() as d, patch('research.e005.time.sleep') as sleep:
            provider = Mock(model='gpt-6-sol')
            provider.models.side_effect = [TimeoutError('timeout'), ['other'], ['gpt-6-sol']]
            recover(provider, Path(d))
            self.assertEqual([c.args[0] for c in sleep.call_args_list], [30, 120, 300])
            provider.respond.assert_not_called()

    def test_paired_world_mean_statistics(self):
        worlds = corpus()['worlds']
        scores = {w['id']: {'C1': .5, 'T1': .5} for w in worlds}
        r = statistics(worlds, scores)
        self.assertEqual(r['n_worlds'], 6)
        self.assertEqual(r['exact_sign_flip_p'], 1)
        self.assertFalse(r['positive_rule_met'])
        scores = {w['id']: {'C1': 0, 'T1': 1} for w in worlds}
        self.assertTrue(statistics(worlds, scores)['positive_rule_met'])


if __name__ == '__main__':
    unittest.main()
