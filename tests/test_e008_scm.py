from fractions import Fraction
import itertools
import unittest

from research import e008_oracle as oracle
from research.e008_scm import (
    VARIABLES, answer_set, candidates, compatible, distribution, evidence,
    evidence_counts, model, quantity, revision_probe,
)


class CausalEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.relay = model("relay", VARIABLES, "and", [0, 0, 0])
        self.confounding = model("confounded", VARIABLES, "and", [0, 0, 0])

    def test_observational_equivalence_is_not_causal_equivalence(self):
        self.assertEqual(distribution(self.relay), distribution(self.confounding))
        do = {"kind": "probability", "target": "V1", "do": [["V0", 1]]}
        conditional = {"kind": "conditional", "target": "V1", "given": [["V0", 1]]}
        self.assertEqual(quantity(self.relay, do), Fraction(1))
        self.assertEqual(quantity(self.confounding, do), Fraction(1, 2))
        self.assertEqual(quantity(self.confounding, conditional), Fraction(1))
        for scm in (self.relay, self.confounding):
            for q in (do, conditional):
                self.assertEqual(quantity(scm, q), oracle.answer(scm, q))

    def test_intervention_severs_only_assigned_equation(self):
        fixed = [["V1", 1]]
        self.assertEqual(distribution(self.relay, fixed), oracle.census(self.relay["equations"], fixed))
        self.assertEqual(quantity(self.relay, {"kind": "probability", "target": "V2", "do": fixed}), 1)
        self.assertEqual(quantity(self.relay, {"kind": "probability", "target": "V0", "do": fixed}), Fraction(1, 2))

    def test_exact_class_size_and_hidden_truth_not_in_evidence(self):
        self.assertEqual(len(candidates()), 8640)
        record = evidence(self.relay, "EA")
        self.assertEqual(set(record), {"id", "kind", "do", "variables", "total", "counts"})
        self.assertNotIn("truth", record)
        self.assertEqual(evidence_counts(record), oracle.record_table(record))

    def test_abstention_uses_all_compatible_models_not_truth_only(self):
        models = (self.relay, self.confounding)
        record = evidence(self.relay, "EA")
        indices = oracle.compatible_models(models, [record])
        self.assertEqual(indices, [0, 1])
        q = {"kind": "edge", "source": "V0", "target": "V1"}
        result = oracle.identify(models, indices, q)
        self.assertFalse(result["identified"])
        self.assertEqual(result["possibilities"], {True, False})
        after = oracle.compatible_models(models, [record, evidence(self.relay, "EB", [["V0", 1]])])
        self.assertEqual(after, [0])
        self.assertTrue(oracle.identify(models, after, q)["value"])

    def test_dependent_claim_changes_under_confounding(self):
        q = {"kind": "probability", "target": "V4", "do": [["V0", 1]]}
        self.assertEqual(quantity(self.relay, q), Fraction(1, 2))
        self.assertEqual(quantity(self.confounding, q), Fraction(1, 4))
        self.assertTrue(quantity(self.relay, {"kind": "path", "source": "V0", "target": "V4"}))
        self.assertFalse(quantity(self.confounding, {"kind": "path", "source": "V0", "target": "V4"}))

    def test_independent_oracle_across_permutations_gates_flips_and_do(self):
        for family in ("relay", "fork", "confounded"):
            for gate in ("and", "or", "xor"):
                for bits in itertools.product((0, 1), repeat=3):
                    scm = model(family, tuple(reversed(VARIABLES)), gate, bits)
                    for do in ([], [["V1", 0]], [["V1", 1]], [["V0", 1], ["V4", 0]]):
                        self.assertEqual(distribution(scm, do), oracle.census(scm["equations"], do))

    def test_invalid_evidence_and_do_are_not_silently_abstentions(self):
        bad = evidence(self.relay, "EA")
        bad["counts"].append(bad["counts"][0])
        for fn in (evidence_counts, oracle.record_table):
            with self.assertRaises(ValueError):
                fn(bad)
        for fn in (lambda: distribution(self.relay, [["V0", 0], ["V0", 1]]),
                   lambda: oracle.census(self.relay["equations"], [["V0", True]]),
                   lambda: oracle.identify(candidates(), [], {"kind": "edge", "source": "V0", "target": "V1"})):
            with self.assertRaises(ValueError):
                fn()

    def test_true_model_never_excluded_by_its_own_observations(self):
        scm = candidates()[4782]
        indices = compatible([evidence(scm, "EA"), evidence(scm, "EB", [["V2", 0]])])
        self.assertIn(4782, indices)
        q = {"kind": "probability", "target": "V4", "do": [["V1", 1], ["V3", 0]]}
        self.assertIn(quantity(scm, q), answer_set(indices, q))

    def test_false_hypothesis_has_verified_dependent_consequences(self):
        records = [evidence(self.confounding, "EA"), evidence(self.confounding, "EB", [["V0", 1]])]
        initial, final = compatible(records[:1]), compatible(records)
        panel = [
            {"id": "P1", "kind": "probability", "target": "V1", "do": [["V0", 1]]},
            {"id": "P2", "kind": "probability", "target": "V4", "do": [["V0", 1]]},
        ]
        probe = revision_probe(initial, final, panel)
        self.assertIsNotNone(probe)
        hypothesis = probe["hypothesis"]
        self.assertEqual(oracle.compatible_models([hypothesis], records[:1]), [0])
        self.assertEqual(oracle.compatible_models([hypothesis], records), [])
        self.assertEqual(probe["dependent_question_ids"], ["P1", "P2"])
        for query in panel:
            self.assertNotIn(oracle.answer(hypothesis, query), answer_set(final, query))

    def test_no_false_revision_probe_when_no_hypothesis_is_excluded(self):
        indices = compatible([evidence(self.relay, "EA")])
        panel = [{"id": "P1", "kind": "path", "source": "V0", "target": "V4"}]
        self.assertIsNone(revision_probe(indices, indices, panel))


if __name__ == "__main__":
    unittest.main()
