import copy
import itertools
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from research.e006 import prepare
from research.e005_memory import AuthoredMemoryBridge
from research.e005_protocol import corpus as prior_corpus
from research.e006_protocol import BUDGETS, corpus, reader_prompt, writer_prompt, reference_memory, serialized
from research.e006_audit import score_answer, statistics, summarize
from research.e004_audit import reference


class E006Tests(unittest.TestCase):
    def test_live_preparation_never_overwrites_prior_registration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root/'project'
            (project/'docs/research').mkdir(parents=True)
            (root/'runs').mkdir()
            prior = project/'docs/research/E005-PREREGISTRATION.json'
            prior.write_bytes(b'preserve historical bytes\n')
            gate = root/'gate.json'
            gate.write_text(json.dumps({'pass': True, 'fixture_pass': True, 'implementation_hashes': {}}))
            sample = corpus()
            sample['worlds'] = sample['worlds'][:1]
            sample['schedule'] = [j for j in sample['schedule'] if j['world'] == 'w01']
            with patch.multiple('research.e006', ROOT=root, PROJECT=project,
                                corpus=Mock(return_value=sample), implementation_hashes=Mock(return_value={}),
                                image_id=Mock(return_value='fixture-image'), runtime_identity=Mock(return_value={}),
                                create_worker=Mock(), source_hashes=Mock(return_value={}),
                                isolation_probe=Mock(return_value={'isolation_pass': True}), append_journal=Mock()):
                study = prepare('e006-test', gate)
            self.assertEqual(prior.read_bytes(), b'preserve historical bytes\n')
            saved = project/'docs/research/E006-PREREGISTRATION.json'
            self.assertEqual(json.loads(saved.read_text())['experiment'], 'E-006')
            self.assertEqual(saved.read_bytes(), (study/'registration.json').read_bytes())

    def test_balanced_unique_independent_worlds_and_frozen_schedule(self):
        sample = corpus()
        self.assertEqual(sample, corpus())
        worlds, jobs = sample['worlds'], sample['schedule']
        self.assertEqual(len(worlds), 24)
        self.assertEqual(len(jobs), 336)
        self.assertEqual(sum(j['stage'] == 'A' for j in jobs), 144)
        self.assertEqual(len({tuple(j.values()) for j in jobs}), 336)
        self.assertTrue(all(j['stage'] == 'A' for j in jobs[:144]))
        self.assertTrue(all(j['stage'] == 'C' for j in jobs[144:]))
        rules = {json.dumps(w['rule'], sort_keys=True) for w in worlds}
        self.assertEqual(len(rules), 24)
        self.assertFalse(rules & {json.dumps(w['rule'], sort_keys=True) for w in prior_corpus()['worlds']})
        for family in ('linear', 'residue', 'switch'):
            self.assertEqual(sum(w['family'] == family for w in worlds), 8)
        self.assertEqual(BUDGETS, (24, 32, 48))

    def test_no_queries_in_writer_or_hidden_truth_in_reader(self):
        for w in corpus()['worlds']:
            changed = copy.deepcopy(w)
            changed['queries'] = [(0, 0)]*5
            self.assertEqual(writer_prompt(w, 'T1', 24), writer_prompt(changed, 'T1', 24))
            changed = copy.deepcopy(w)
            changed['rule']['delta'] *= -1
            self.assertEqual(reader_prompt(w), reader_prompt(changed))
            self.assertNotIn('Budget:', reader_prompt(w))
            self.assertLessEqual(len(serialized(reference_memory(w))), 192)

    def test_stricter_boundaries_keep_rejection_and_repair(self):
        for budget in BUDGETS:
            b = AuthoredMemoryBridge.__new__(AuthoredMemoryBridge)
            b.stage, b.saved, b.read = 'A', False, False
            b.configure(budget)
            b.persist = Mock(return_value={'saved': True})
            text = 'x'*(budget-14)
            self.assertEqual(len(serialized(text)), budget)
            self.assertFalse(b.call('save_memory', {'memory': text+'x'})['saved'])
            b.persist.assert_not_called()
            self.assertTrue(b.call('save_memory', {'memory': text})['saved'])
            b.persist.assert_called_once_with(text)

    def test_exact_sign_flip_dp_matches_exhaustive_small_case(self):
        worlds = corpus()['worlds'][:6]
        values = [2, -2, 1, 0, 1, -1]
        r = statistics(worlds, dict(zip((w['id'] for w in worlds), values)))
        flips = [sum(s*v for s, v in zip(signs, values)) for signs in itertools.product((-1, 1), repeat=6)]
        self.assertEqual(r['exact_sign_flip_p'], sum(abs(v) >= abs(sum(values)) for v in flips)/64)
        self.assertEqual(r['difference_48_minus_24'], sum(values)/12)

    def test_statistics_24_worlds_count_zero_differences(self):
        worlds = corpus()['worlds']
        zero = statistics(worlds, {w['id']: 0 for w in worlds})
        self.assertEqual(zero['sign_assignments'], 16777216)
        self.assertEqual(zero['exact_sign_flip_p'], 1)
        self.assertEqual(zero['bootstrap_95'], [0, 0])
        positive = statistics(worlds, {w['id']: 2 for w in worlds})
        self.assertTrue(positive['positive_rule_met'])
        self.assertEqual(positive['exact_sign_flip_p'], 2/16777216)
        self.assertEqual(positive['bootstrap_95'], [1, 1])

    def test_failed_and_skipped_positions_stay_in_denominators(self):
        sample = corpus()
        rows = [{'job': j, 'status': 'skipped_dependency' if j['stage'] == 'C' else 'failed', 'pass': False} for j in sample['schedule']]
        r = summarize(sample['worlds'], rows)
        for c in ('C1', 'T1'):
            for b in BUDGETS:
                self.assertEqual(r['conditions'][c][str(b)]['denominator'], 24)
                self.assertEqual(r['conditions'][c][str(b)]['rule_correct'], 0)
        self.assertEqual(r['primary']['difference_48_minus_24'], 0)

    def test_primary_equal_weights_worlds_and_conditions_not_contexts(self):
        sample = corpus()
        rows = [{'job': j, 'status': 'completed', 'pass': True,
                 'rule_correct': j['stage'] == 'C' and j['condition'] == 'C1' and j['budget'] == 48} for j in sample['schedule']]
        r = summarize(sample['worlds'], rows)
        self.assertEqual(r['primary']['difference_48_minus_24'], .5)
        self.assertEqual(r['primary']['n_worlds'], 24)
        self.assertAlmostEqual(r['descriptive_format_difference_T1_minus_C1'], -1/3)

    def test_numeric_accuracy_does_not_require_rule_and_rejects_bool(self):
        world = corpus()['worlds'][0]
        answer = reference(world, 'intact')
        answer['rule'] = None
        self.assertTrue(score_answer(answer, world))
        answer['predictions'][0] = True
        self.assertFalse(score_answer(answer, world))


if __name__ == '__main__':
    unittest.main()
