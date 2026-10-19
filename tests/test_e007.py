"""Offline regression of information boundaries, codec failure modes and frozen schedule."""
import copy
import json
import unittest
import itertools
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch
from collections import Counter
from research.e007_audit import expected, score
from research.e007_codec import bounds, fixed_encode, fixed_decode, reference_encode, reference_decode
from research.e007_protocol import corpus, prompt, schedule
from research.e007_analysis import exact_sign_flip, holm, statistics, break_even
from research.e007_provider import MeasuredProvider
from research.e007 import run_position, append_journal


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.inputs=corpus(17)
        self.world=self.inputs['splits']['test'][0]

    def test_new_disjoint_corpus(self):
        rules=[json.dumps(w['rule'],sort_keys=True) for split in self.inputs['splits'].values() for w in split]
        self.assertEqual(len(rules),39)
        self.assertEqual(len(set(rules)),39)
        later=corpus(17,rules)
        self.assertFalse(set(rules)&{json.dumps(w['rule'],sort_keys=True) for s in later['splits'].values() for w in s})

    def test_codec_bounds_and_roundtrip(self):
        self.assertEqual(bounds()['total_rules'],2099520)
        self.assertEqual(bounds()['minimum_fixed_binary_bits'],22)
        for split in self.inputs['splits'].values():
            for w in split:
                self.assertEqual(fixed_decode(fixed_encode(w['rule'])),w['rule'])
                self.assertEqual(reference_decode(reference_encode(w['rule'])),w['rule'])

    def test_codec_rejects_damage_and_types(self):
        message=fixed_encode(self.world['rule'])
        for damaged in ('',message[:-1],message+'1','?'+message[1:],message[:-1]+str((int(message[-1])+1)%10),message[:2]+'9'+message[3:]):
            with self.assertRaises(ValueError):
                fixed_decode(damaged)
        with self.assertRaises(ValueError):
            fixed_encode(dict(self.world['rule'],a=True))
        for invalid in ('','0____8','1AAAAA','0?????'):
            with self.assertRaises(ValueError):
                reference_decode(invalid)

    def test_matrix_and_dependency_order(self):
        jobs=schedule(self.inputs)
        self.assertEqual(len(jobs),991)
        self.assertEqual(Counter(j['role'] for j in jobs),{'designer':6,'critic':6,'writer':432,'reader':540,'feedback':6,'lock':1})
        by_id={j['id']:i for i,j in enumerate(jobs)}
        self.assertEqual(len(by_id),len(jobs))
        lock=next(i for i,j in enumerate(jobs) if j['role']=='lock')
        for i,j in enumerate(jobs):
            if j.get('split')=='test':
                self.assertGreater(i,lock)
            if 'source' in j:
                self.assertLess(by_id[j['source']],i)
        missing=[j for j in jobs if j.get('control')=='missing']
        self.assertEqual(len(missing),48)
        self.assertEqual(len([j for j in jobs if j.get('control')=='cross_model']),12)

    def test_prompts_separate_truth_history_and_definition(self):
        jobs=schedule(self.inputs)
        designer=next(j for j in jobs if j['role']=='designer')
        text=prompt(designer)
        self.assertNotIn('FabcdefghK',text)
        self.assertNotIn('fixed-v1',text)
        reader=next(j for j in jobs if j['role']=='reader' and j['phase']=='test')
        text=prompt(reader,self.world)
        self.assertNotIn('Correct rule:',text)
        self.assertNotIn(json.dumps(self.world['rule'],separators=(',',':')),text)
        self.assertNotIn(self.world['id'],text)

    def test_ambiguous_expected_preserves_common_information(self):
        truth=expected(self.world)
        ambiguous=expected(self.world,'ambiguous')
        self.assertIsNone(ambiguous['rule']['a'])
        self.assertEqual(ambiguous['rule']['b'],truth['rule']['b'])
        self.assertTrue(score(truth,self.world)['rule_correct'])
        self.assertTrue(score(ambiguous,self.world,'ambiguous')['control_expected_correct'])
        self.assertFalse(score(ambiguous,self.world)['rule_correct'])
        bad=copy.deepcopy(truth)
        bad['rule']['a']=True
        self.assertFalse(score(bad,self.world)['rule_correct'])
        self.assertTrue(score(dict(truth,sum=truth['sum']+1),self.world)['arithmetic_error_with_correct_rule'])
        world={'rule':dict(family='linear',a=2,b=1,c=0,e=0,t=0,x0=0,z0=0,delta=7),
               'queries':[(0,1),(1,0),(-1,0),(0,0),(2,0)]}
        self.assertEqual(expected(world)['predictions'],[1,2,-2,7,4])
        self.assertEqual(expected(world)['sum'],12)
        self.assertEqual(expected(world,'ambiguous')['predictions'],[1,None,None,7,None])
        self.assertIsNone(expected(world,'ambiguous')['contrast'])

    def test_test_seal_rejects_before_oracle_open(self):
        with tempfile.TemporaryDirectory() as directory:
            study=Path(directory)
            for name in ('heads.json','head-hashes.json'):
                (study/name).write_text('{}')
            job={'id':'j0001','world':'test-01','split':'test','role':'reader'}
            with self.assertRaisesRegex(PermissionError,'test still sealed'):
                run_position(study,{},job,None)
            self.assertFalse((study/'oracle.json').exists())

    def test_journal_uses_required_utc_z_without_rewriting_history(self):
        from research.common import PROJECT
        from docs.research.validate_journal import validate,read
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'docs/research/journal.jsonl';path.parent.mkdir(parents=True)
            before=(PROJECT/'docs/research/journal.jsonl').read_bytes()
            path.write_bytes(before)
            study=root/'study';study.mkdir()
            (study/'registration.json').write_text(json.dumps({'design':'test','primary':'test','sample':{},'limitations':[]}))
            with patch('research.e007.PROJECT',root):
                append_journal(study,'registered')
            self.assertTrue(path.read_bytes().startswith(before))
            self.assertTrue(read(path)[-1]['at_utc'].endswith('Z'))
            self.assertFalse(validate(read(path))['truth_verified'])

    def test_sign_flip_matches_enumeration_with_zero_differences(self):
        for differences in ([.5,0,-1,1],[0]*4,[.5]*4):
            flips=[sum(d*s for d,s in zip(differences,signs)) for signs in itertools.product((-1,1),repeat=len(differences))]
            self.assertEqual(exact_sign_flip(differences),sum(abs(v)>=abs(sum(differences)) for v in flips)/len(flips))
        self.assertEqual(exact_sign_flip([.5]*24),2/2**24)

    def test_holm_monotonic_and_bounded(self):
        self.assertEqual(holm({'a':.001,'b':.02,'c':.03}),{'a':.003,'b':.04,'c':.04})
        self.assertEqual(holm({'a':1,'b':1}),{'a':1,'b':1})

    def test_statistics_world_unit_and_null(self):
        worlds=self.inputs['splits']['test']
        scores={w['id']:{k:0 for k in ('C1','T1','T2v3','T2v1','missing')} for w in worlds}
        result=statistics(worlds,scores)
        self.assertEqual(result['T2v3-T1']['n_worlds'],24)
        self.assertEqual(result['T2v3-T1']['holm_p'],1)
        self.assertFalse(result['T2v3-T1']['positive_rule_met'])

    def test_break_even_accounts_for_success_and_setup(self):
        baseline={'probability':.5,'setup_bytes':0,'per_use_bytes':100}
        candidate={'probability':1,'setup_bytes':1000,'per_use_bytes':100}
        self.assertEqual(break_even(candidate,baseline)['first_positive_integer_N'],11)
        self.assertIsNone(break_even(dict(candidate,probability=0),baseline)['first_positive_integer_N'])
        self.assertIsNone(break_even(dict(candidate,per_use_bytes=300),baseline)['first_positive_integer_N'])

    def test_measured_transport_counts_actual_bodies_without_headers(self):
        provider=MeasuredProvider.__new__(MeasuredProvider)
        provider.host='fixture.invalid';provider.port=443;provider.key='fixture-only-not-a-key'
        provider.record=Mock()
        conn=Mock();response=Mock();response.status=200
        response.read.return_value=b'{ "unicode": "ok" }\n'
        conn.getresponse.return_value=response
        payload={'unicode':'\u044f'}
        with patch('research.e007_provider.http.client.HTTPSConnection',return_value=conn):
            self.assertEqual(provider.request('POST','/v1/responses',payload),{'unicode':'ok'})
        measured=provider.record.call_args.args[0]
        self.assertEqual(measured['request_body_bytes'],len(json.dumps(payload,ensure_ascii=False).encode()))
        self.assertEqual(measured['response_body_bytes'],len(response.read.return_value))
        self.assertTrue(measured['response_complete'])
        self.assertNotIn('fixture-only-not-a-key',json.dumps(measured))
        with self.assertRaises(PermissionError):
            provider.request('GET','/unregistered')


if __name__=='__main__':
    unittest.main()
