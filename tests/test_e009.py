from copy import deepcopy
import inspect
import unittest

from research.e009_oracle import Oracle, solve
from research.e009_planning import power_cell
from research.e009_revision import (canonical, check_references, memory_envelope, public_input,
                                    reference_revision, score_revision, sha)
from research.e009_scm import development_corpus, distribution, models, quantity


class E009Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = development_corpus()
        cls.world = cls.corpus["worlds"][0]
        cls.oracle = Oracle(models())

    def setUp(self):
        self.current, self.history, self.answer = reference_revision(self.world, self.oracle)

    def score(self):
        return score_revision(self.world, self.current, self.history, self.answer, self.oracle)

    def test_independent_constraint_solver(self):
        for i, model in enumerate(models()):
            for do in ((), (("X", 0),), (("Y", 0),), (("Z", 1),)):
                self.assertEqual(distribution(i, do), solve(model, do), (i, do))

    def test_probability_and_graph_oracles(self):
        for i in range(len(models())):
            for q in ({"kind": "probability", "target": "Q", "do": [["X", 0]]},
                      {"kind": "edge", "source": "Y", "target": "Z"},
                      {"kind": "path", "source": "Y", "target": "Q"}):
                self.assertEqual(quantity(i, q), self.oracle.quantity(i, q))

    def test_corpus_reproducible_and_unique(self):
        self.assertEqual(self.corpus, development_corpus())
        self.assertEqual(len({w["hidden_model"] for w in self.corpus["worlds"]}), 12)
        self.assertFalse(self.corpus["heldout"])

    def test_all_registered_opportunities(self):
        for world in self.corpus["worlds"]:
            args = reference_revision(world, self.oracle)
            result = score_revision(world, *args, self.oracle)
            self.assertEqual(result["bri"], 1)
            self.assertEqual(result["expected"], {"H": "refuted", "D1": "refuted", "D2": "refuted",
                                                 "K": "supported", "I": "supported"})

    def test_monotone_evidence_never_resurrects_model(self):
        for world in self.corpus["worlds"]:
            previous = set(range(len(models())))
            for n in range(1, 5):
                current = self.oracle.compatible(world["evidence"][:n])
                self.assertTrue(current <= previous)
                self.assertIn(world["hidden_model"], current)
                previous = current

    def test_withdrawal_is_unknown_not_false(self):
        for world in self.corpus["worlds"]:
            p = {k: world["withdrawal"][k] for k in ("query", "value")}
            self.assertEqual(self.oracle.status(self.oracle.compatible(world["evidence"][:2]), p), "supported")
            self.assertEqual(self.oracle.status(self.oracle.compatible(world["evidence"][:1]), p), "undetermined")

    def test_conflict_not_vacuous_truth(self):
        a = self.world["evidence"][0]
        b = deepcopy(a)
        b["id"] = "forged"
        b["counts"] = list(reversed(a["counts"]))
        if b["counts"] == a["counts"]:
            b["counts"] = [8] + [0] * 63
        candidates = self.oracle.compatible([a, b])
        self.assertFalse(candidates)
        self.assertEqual(self.oracle.status(candidates, self.world["claims"][0]["proposition"]), "conflicted")

    def test_observation_does_not_identify_causal_family(self):
        candidates = self.oracle.compatible(self.world["evidence"][:1])
        self.assertGreater(len({models()[i][0] for i in candidates}), 1)

    def test_correct_answer_alone_fails(self):
        for c in self.current[:3]:
            c["status"] = "supported"
        self.assertEqual(self.score()["bri"], 0)

    def test_correct_status_without_repair_fails(self):
        self.current[2]["bases"] = [["c:D1"]]
        self.assertEqual(self.score()["bri"], 0)

    def test_false_retraction_fails(self):
        self.current[3]["status"] = "refuted"
        self.assertFalse(self.score()["gates"]["N"])

    def test_independent_basis_must_survive(self):
        self.current[3]["bases"] = [["e:EA", "e:EB", "e:EC"]]
        self.assertFalse(self.score()["gates"]["A"])

    def test_valid_alternative_does_not_launder_stale_basis(self):
        self.current[3]["bases"].append(["c:H"])
        self.assertEqual(self.score()["bri"], 0)

    def test_unjustified_claim_cannot_prove_itself(self):
        self.current[3]["bases"] = [["c:K"]]
        self.assertEqual(self.score()["bri"], 0)

    def test_prior_bytes_origin_and_proposition_immutable(self):
        for field, value in (("previous_sha256", "0" * 64), ("origin", "rewritten"),
                             ("proposition", {"query": {"kind": "model", "index": 0}, "value": 1})):
            with self.subTest(field=field):
                saved = deepcopy(self.current)
                self.current[0][field] = value
                self.assertEqual(self.score()["bri"], 0)
                self.current = saved

    def test_deleted_history_fails(self):
        self.history.pop()
        self.assertFalse(self.score()["gates"]["P"])

    def test_boolean_proposition_is_not_same_bytes(self):
        self.current[0]["proposition"]["value"] = True
        self.assertEqual(self.score()["bri"], 0)

    def test_history_type_tampering_rejected(self):
        self.history[0]["proposition"]["value"] = True
        self.assertEqual(self.score()["bri"], 0)

    def test_malformed_status_fails_closed(self):
        self.current[0]["status"] = []
        self.assertEqual(self.score()["bri"], 0)

    def test_forged_source_fails(self):
        self.current[0]["bases"] = [["e:nonexistent"]]
        self.assertFalse(self.score()["gates"]["P"])

    def test_missing_duplicate_malformed_claims_fail(self):
        for records in (self.current[:-1], self.current + [self.current[0]], [{"id": "H"}], None):
            result = score_revision(self.world, records, self.history, self.answer, self.oracle)
            self.assertEqual(result["bri"], 0)

    def test_failed_chain_counts_zero(self):
        self.assertEqual(score_revision(self.world, self.current, self.history, self.answer,
                                        self.oracle, completed=False)["bri"], 0)

    def test_boolean_does_not_pass_as_numeric_answer(self):
        self.answer = bool(self.answer)
        self.assertEqual(self.score()["bri"], 0)

    def test_v1_not_oracle_and_nonmutating(self):
        before = sha(self.world["claims"])
        notices = check_references(self.world["claims"], {"EA", "EB", "EC"}, {"H"})
        self.assertTrue(any(n.get("claim") == "D2" for n in notices))
        self.assertEqual(before, sha(self.world["claims"]))
        self.assertEqual(set(inspect.signature(check_references).parameters),
                         {"claims", "active_sources", "changed_claims"})
        self.assertNotIn("refuted", canonical(notices).decode())

    def test_v1_missing_source_not_auto_retraction(self):
        notices = check_references(self.world["claims"], set())
        self.assertTrue(any(n["kind"] == "missing_source" for n in notices))
        self.assertEqual(self.world["claims"][0]["status"], "supported")

    def test_public_projection_no_gold_or_measurement(self):
        world = deepcopy(self.world)
        world.update(gold="PRIVATE-GOLD", measurement="PRIVATE-MEASUREMENT")
        for condition in ("F0", "F1", "S0", "S1", "C0", "FULL-JOURNAL"):
            for stage in "ABCDE":
                value = public_input(world, stage, "allowed-memory", condition)
                self.assertNotIn("PRIVATE", canonical(value).decode())
                self.assertNotIn("hidden_model", value)
                self.assertNotIn("claims", value)
                self.assertEqual("question" in value, stage == "E")
                if condition == "C0":
                    self.assertIsNone(value["memory"])

    def test_equal_factorial_information(self):
        for pair in (("F0", "F1"), ("S0", "S1")):
            a, b = [public_input(self.world, "C", "memory", c) for c in pair]
            a.pop("condition"); b.pop("condition")
            self.assertEqual(a, b)

    def test_budget_includes_unicode_and_envelope(self):
        value = memory_envelope("абв", "F")
        size = len(canonical(value))
        self.assertEqual(value, memory_envelope("абв", "F", size))
        with self.assertRaises(ValueError):
            memory_envelope("абв", "F", size - 1)
        with self.assertRaises(ValueError):
            memory_envelope({}, "F")

    def test_invalid_evidence_and_interventions_rejected(self):
        for change in ({"total": 4}, {"counts": [8]}, {"do": [["X", 0], ["X", 1]]},
                       {"kind": "interventional"}):
            record = {**self.world["evidence"][0], **change}
            with self.assertRaises(ValueError):
                self.oracle.compatible([record])

    def test_planning_reproducible_and_no_hidden_sample_selection(self):
        a = power_cell(10, .15, .03, 20)
        self.assertEqual(a, power_cell(10, .15, .03, 20))
        self.assertLess(a["chain_survival"], 1)
        self.assertLessEqual(a["decision_power_without_guardrail"], a["test_power_normal_bonferroni"])


if __name__ == "__main__":
    unittest.main()
