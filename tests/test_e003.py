from contextlib import closing
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from research.e003 import Jobs, job_id, run_series
from research.e003_protocol import make_corpus, score, prompt
from research.e003_audit import validate_world, calculate, answer_correct, pairs
from research.responses_provider import ResponsesProvider, SpendLedger
from research.e003_evaluate import paired_statistics


class SeriesProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = make_corpus()

    def test_harder_corpus_independently_identifiable(self):
        self.assertEqual(len(self.corpus['worlds']), 12)
        for w in self.corpus['worlds']:
            self.assertTrue(validate_world(w)['pass'], w['id'])
            self.assertGreater(w['proof']['candidate_count'], 45)  # E-002 had 45.

    def test_donor_is_same_family_different_rule_and_no_condition_crossover(self):
        worlds = {w['id']: w for w in self.corpus['worlds']}
        for key, donor in self.corpus['donors'].items():
            self.assertNotEqual(key, donor)
            a, b = worlds[key], worlds[donor]
            self.assertEqual(a['family'], b['family'])
            prediction = [calculate(a['family'], b['truth'], q['x'], q['z']) for q in a['questions']]
            self.assertGreaterEqual(sum(x != y for x, y in zip(prediction, a['answers'])), 2)

    def test_schedule_has_120_unique_contexts_with_all_AB_before_C(self):
        jobs = self.corpus['schedule']
        self.assertEqual(len(jobs), 120)
        self.assertEqual(len({job_id(j) for j in jobs}), 120)
        self.assertTrue(all(j['stage'] in 'AB' for j in jobs[:48]))
        self.assertTrue(all(j['stage'] == 'C' for j in jobs[48:]))
        for world in self.corpus['worlds']:
            for c in ('C1', 'T1'):
                selected = [j for j in jobs if j['world'] == world['id'] and j['condition'] == c]
                self.assertEqual(len(selected), 5)

    def test_equal_observation_information_and_no_control_or_answers_in_C_prompt(self):
        for w in self.corpus['worlds']:
            for c in ('C1', 'T1'):
                self.assertIn(json.dumps(w['observations_a']), prompt(w, c, 'A'))
                self.assertIn(json.dumps(w['observations_b']), prompt(w, c, 'B'))
                text = prompt(w, c, 'C')
                for forbidden in (json.dumps(w['answers']), 'swapped', 'deleted', 'donor'):
                    self.assertNotIn(forbidden, text)

    def test_primary_schema_and_separate_constraint_implementation(self):
        for w in self.corpus['worlds']:
            valid = {'status': 'completed', 'predictions': w['answers'], 'derived': w['derived']}
            self.assertTrue(score(valid, w)); self.assertTrue(answer_correct(valid, w))
            for field in ('predictions', 'derived'):
                invalid = copy.deepcopy(valid)
                if field == 'predictions': invalid[field][0] += 1
                else: invalid[field]['sum'] += 1
                self.assertFalse(score(invalid, w)); self.assertFalse(answer_correct(invalid, w))
            self.assertFalse(score({'status': 'needs_context'}, w))
            invalid = copy.deepcopy(valid); invalid['derived']['contrast'] = True
            self.assertFalse(score(invalid, w)); self.assertFalse(answer_correct(invalid, w))

    def test_pending_job_order_atomicity_and_no_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs = Jobs(Path(tmp)/'jobs.db', self.corpus['schedule'][:2])
            first, second = [job_id(j) for j in self.corpus['schedule'][:2]]
            with self.assertRaises(RuntimeError): jobs.claim(second)
            jobs.claim(first)
            with self.assertRaises(RuntimeError): jobs.claim(second)
            jobs.finish(first, {'status': 'failed', 'reason': 'observed failure'})
            with self.assertRaises(RuntimeError): jobs.claim(first)
            jobs.claim(second); jobs.finish(second, {'status': 'completed'})
            self.assertEqual(jobs.state()[first]['status'], 'failed')

    def test_wrong_request_identity_not_evidence(self):
        request = {'channel': 'mcp', 'connection': 'one', 'message': {'id': 1, 'method': 'tools/call', 'params': {'name': 'continuum_get_object', 'arguments': {'sha256': 'hash'}}}}
        response = {'event': 'mcp_response', 'connection': 'one', 'message': {'id': 1, 'result': {'structuredContent': {'sha256': 'hash'}}}}
        self.assertEqual(len(pairs([request, response])), 1)
        changed = copy.deepcopy(response); changed['connection'] = 'two'
        self.assertEqual(pairs([request, changed]), [])
        changed = copy.deepcopy(response); changed['message']['id'] = 2
        self.assertEqual(pairs([request, changed]), [])

    def test_paired_analysis_keeps_failures_and_does_not_call_ties_superiority(self):
        rows = [{'family': f, 'C1': True, 'T1': True} for f in ('a', 'b', 'c') for _ in range(4)]
        tied = paired_statistics(rows, replicates=100)
        self.assertEqual(tied['difference_T1_minus_C1'], 0)
        self.assertEqual(tied['exact_two_sided_p'], 1)
        self.assertFalse(tied['registered_positive_evidence_rule_met'])
        for r in rows:
            r['C1'] = False
        different = paired_statistics(rows, replicates=100)
        self.assertEqual(different['n_worlds'], 12)
        self.assertEqual(different['C1_successes'], 0)
        self.assertEqual(different['difference_T1_minus_C1'], 1)
        self.assertEqual(different['exact_two_sided_p'], 2 / 4096)

    def test_explicit_output_limit_preserves_old_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            p = ResponsesProvider('https://example.test/v1', 'm', SpendLedger(path/'budget', unbounded=True), path/'log', authorize=True, key='sentinel')
            with patch.object(p, 'request', return_value={'status': 'completed', 'model': 'm', 'output': []}) as send:
                p.respond('new', [], [], max_output_tokens=4096)
                self.assertEqual(send.call_args.args[2]['max_output_tokens'], 4096)
                p.respond('old', [], [])
                self.assertEqual(send.call_args.args[2]['max_output_tokens'], 2048)
            with self.assertRaises(ValueError): p.respond('invalid', [], [], max_output_tokens=True)

    def test_provider_timeout_stops_series_without_retrying_or_starting_next_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            study = Path(tmp)
            (study/'metadata.json').write_text('{"available": true}', encoding='utf-8')
            (study/'smoke.json').write_text('{}', encoding='utf-8')
            schedule = self.corpus['schedule'][:2]
            jobs = Jobs(study/'jobs.sqlite3', schedule)
            config = (study, {'model': 'fixture'}, {'provider': 'https://example.test/v1', 'limits': {'series_seconds': 60}}, {'schedule': schedule})
            failed = {'status': 'failed', 'failure_type': 'TimeoutError', 'failure_origin': 'provider', 'failure': 'TimeoutError: timed out'}
            with patch('research.e003.load', return_value=config), patch('research.e003.ResponsesProvider'), patch('research.e003.execute_worker', return_value=failed) as worker:
                with self.assertRaisesRegex(RuntimeError, 'provider transport'):
                    run_series(study, authorize=True, unbounded=True)
                self.assertEqual(worker.call_count, 1)
            states = jobs.state()
            self.assertEqual(states[job_id(schedule[0])]['status'], 'failed')
            self.assertEqual(states[job_id(schedule[1])]['status'], 'pending')


if __name__ == '__main__':
    unittest.main()
