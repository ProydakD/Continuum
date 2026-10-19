import copy
import json
import unittest
from unittest.mock import Mock
from research.e004 import ReceptionBridge, transient
from research.e004_protocol import BUDGET, corpus, expected, memory, prompt
from research.e004_audit import decode, reference, same, statistics


class E004Tests(unittest.TestCase):
    def test_fixed_balanced_corpus(self):
        c = corpus()
        self.assertEqual(c, corpus())
        self.assertEqual(len(c['worlds']), 12)
        self.assertEqual(len(c['schedule']), 144)
        self.assertEqual(len({tuple(j.values()) for j in c['schedule']}), 144)
        for w in c['worlds']:
            self.assertEqual(len(set(w['queries'])), 5)
            self.assertEqual(w['queries'].count((w['rule']['x0'], w['rule']['z0'])), 1)

    def test_full_serialized_budget_and_equal_semantics(self):
        for w in corpus()['worlds']:
            for branch in ('intact', 'partial', 'empty'):
                a, b = [memory(w, c, branch) for c in ('C1', 'T1')]
                self.assertEqual(len(json.dumps(a).encode()), BUDGET)
                self.assertEqual(len(json.dumps(b).encode()), BUDGET)
                self.assertEqual(decode(a), decode(b))
                self.assertEqual(decode(a), reference(w, branch)['rule'])

    def test_independent_math_all_branches(self):
        for w in corpus()['worlds']:
            for branch in ('intact', 'partial', 'empty'):
                self.assertTrue(same(expected(w, branch), reference(w, branch)))

    def test_partial_is_underdetermined_not_zero(self):
        for w in corpus()['worlds']:
            changed = copy.deepcopy(w)
            changed['rule']['delta'] *= -1
            for c in ('C1', 'T1'):
                self.assertEqual(memory(w, c, 'partial'), memory(changed, c, 'partial'))
                self.assertNotEqual(memory(w, c, 'intact'), memory(changed, c, 'intact'))
            self.assertNotEqual(expected(w, 'intact'), expected(changed, 'intact'))
            self.assertEqual(expected(w, 'partial')['predictions'].count(None), 1)

    def test_prompts_do_not_include_truth_or_intervention(self):
        for w in corpus()['worlds']:
            other = copy.deepcopy(w)
            other['rule']['delta'] *= -1
            self.assertEqual(prompt(w), prompt(other))
            self.assertNotIn('C1', prompt(w))
            self.assertNotIn(w['id'], prompt(w))

    def test_strict_answer_types(self):
        self.assertFalse(same(True, 1))
        self.assertFalse(same(1.0, 1))
        self.assertFalse(same({'a': 1, 'extra': 0}, {'a': 1}))
        self.assertFalse(same([1], [1, 2]))

    def test_bridge_refuses_other_tools_and_repeated_reads(self):
        bridge = ReceptionBridge.__new__(ReceptionBridge)
        bridge.read = False
        bridge.tool = Mock()
        for name, args in [('save_memory', {}), ('read_memory', {'world': 1}), ('read_memory', [])]:
            with self.assertRaises(PermissionError):
                bridge.call(name, args)
        bridge.read = True
        with self.assertRaises(PermissionError):
            bridge.call('read_memory', {})
        bridge.tool.assert_not_called()

    def test_recovery_classifies_transport_not_model_results(self):
        self.assertTrue(transient({'failure_origin': 'provider', 'failure': 'provider HTTP status 502; no retry or redirect'}))
        self.assertFalse(transient({'failure_origin': 'provider', 'failure': 'provider HTTP status 401; no retry or redirect'}))
        self.assertFalse(transient({'failure_origin': 'provider', 'failure_type': 'SSLError'}))
        self.assertFalse(transient({'failure_origin': 'provider', 'failure_type': 'ValueError'}))
        self.assertFalse(transient({'failure_type': 'TimeoutError'}))

    def test_paired_statistics_and_ceiling_not_positive(self):
        worlds = corpus()['worlds']
        scores = {w['id']: {'C1': 1, 'T1': 1} for w in worlds}
        result = statistics(worlds, scores)
        self.assertEqual(result['difference_T1_minus_C1'], 0)
        self.assertEqual(result['exact_sign_flip_p'], 1)
        self.assertFalse(result['positive_rule_met'])
        scores = {w['id']: {'C1': 0, 'T1': 1} for w in worlds}
        self.assertTrue(statistics(worlds, scores)['positive_rule_met'])


if __name__ == '__main__':
    unittest.main()
