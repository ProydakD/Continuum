import unittest

from research.e008_analysis import CONDITIONS
from research.e008_efficiency import breakeven, cells, comparison, summarize
from research.e008_measurements import measure


def fixture():
    worlds = [{"id": "w1", "split": "test", "truth": {"family": "relay"}},
              {"id": "w2", "split": "test", "truth": {"family": "relay"}}]
    jobs, outcomes, positions = [], {}, {}
    for w in worlds:
        for c in CONDITIONS:
            for line in (("L1", "L2") if c == "T2" else (None,)):
                for rep in (1, 2):
                    identity = f'{w["id"]}-{c}-{line}-{rep}'
                    job = {"id": identity, "world": w["id"], "condition": c, "stage": "D",
                           "phase": "test", "lineage": line, "replicate": rep, "source": None}
                    jobs.append(job)
                    outcomes[identity] = {"status": "completed", "audit": {"pass": True}, "score": {"questions": [
                        {"id": "Q01", "target_expected": "1", "target_correct": True, "valid": True, "integrative": True},
                        {"id": "Q02", "target_expected": None, "target_correct": True, "valid": True, "integrative": False}]}}
                    tokens = 20 if c == "T1" else (100 if line == "L1" else 60)
                    positions[identity] = {"input_tokens": measure(tokens), "output_tokens": measure(10),
                                           "api_plus_mcp_bytes": measure(100), "context_seconds": measure(1)}
    return worlds, jobs, outcomes, {"per_position": positions}


class EfficiencyTests(unittest.TestCase):
    def test_repetitions_and_lines_are_inside_world_not_sample_size(self):
        worlds, jobs, outcomes, resources = fixture()
        report = summarize(worlds, jobs, outcomes, resources, draws=100)
        self.assertEqual(report["n_independent_worlds"], 2)
        self.assertEqual(report["world_cells"]["w1"]["T2"]["cost"]["total_tokens"]["observed"], 90)
        self.assertEqual(report["world_cells"]["w1"]["T1"]["yields"]["integrative_new"], 1)
        ratio = report["comparisons"]["T1-C1"]["total_tokens"]["integrative_new"]
        self.assertAlmostEqual(ratio["reuses"]["100"]["ratio"], 30 / 70)
        self.assertAlmostEqual(ratio["paired_bootstrap_primary"]["ratio_95"][0], 30 / 70)
        self.assertFalse(report["confirmatory_H6_claim"])

    def test_unknown_charge_prevents_interval_and_favorable_claim(self):
        worlds, jobs, outcomes, resources = fixture()
        for j in jobs:
            if j["condition"] == "T1":
                resources["per_position"][j["id"]]["input_tokens"] = measure(10, 1)
        report = summarize(worlds, jobs, outcomes, resources,
                           primary={"contrasts": {"T1-C1": {"positive_evidence": True}}}, draws=100)
        self.assertFalse(report["favorable_secondary_descriptive_evidence"])
        self.assertIsNone(report["comparisons"]["T1-C1"]["total_tokens"]["integrative_new"]["paired_bootstrap_primary"]["ratio_95"])

    def test_zero_results_not_removed_or_replaced_with_null_success(self):
        worlds, jobs, outcomes, resources = fixture()
        for j in jobs:
            if j["condition"] == "T1":
                outcomes[j["id"]]["score"]["questions"][0]["target_correct"] = False
        report = summarize(worlds, jobs, outcomes, resources, draws=100)
        value = report["comparisons"]["T1-C1"]["total_tokens"]
        self.assertIsNone(value["integrative_new"]["reuses"]["100"]["ratio"])
        self.assertIsNotNone(value["correct_decisions"]["reuses"]["100"]["ratio"])
        self.assertEqual(value["integrative_new"]["paired_bootstrap_primary"]["undefined_draws"], 100)

    def test_both_lines_and_rejected_validation_paid_before_amortization(self):
        worlds, jobs, outcomes, resources = fixture()
        for identity, phase in (("dev1", "development"), ("dev2", "validation")):
            jobs.append({"id": identity, "phase": phase, "condition": "T2"})
            outcomes[identity] = {"status": "failed_controller", "audit": {"pass": False}}
            resources["per_position"][identity] = {"input_tokens": measure(1000), "output_tokens": measure(0),
                                                  "api_plus_mcp_bytes": measure(10), "context_seconds": measure(1)}
        table, setup = cells(worlds, jobs, outcomes, resources)
        self.assertEqual(setup["T2"]["total_tokens"], measure(2000))
        self.assertEqual(setup["T1"]["total_tokens"], measure())

    def test_missing_repetition_and_pending_outcome_cannot_reduce_denominator(self):
        worlds, jobs, outcomes, resources = fixture()
        with self.assertRaises(ValueError):
            cells(worlds, jobs[1:], outcomes, resources)
        outcomes[jobs[0]["id"]]["status"] = "pending"
        with self.assertRaises(ValueError):
            cells(worlds, jobs, outcomes, resources)

    def test_breakeven_is_not_guaranteed_by_one_low_cost_ratio(self):
        left = {"cost": {"tokens": measure(2)}, "yields": {"integrative": 1}}
        right = {"cost": {"tokens": measure(4)}, "yields": {"integrative": 1}}
        a, b = {"tokens": measure(20)}, {"tokens": measure()}
        self.assertEqual(breakeven(left, right, a, b, "tokens", "integrative")["first_reuse_not_more_expensive"], 10)
        self.assertGreater(comparison(left, right, a, b, "tokens", "integrative", 1)["ratio"], 1)
        self.assertLess(comparison(left, right, a, b, "tokens", "integrative", 100)["ratio"], 1)
        a["tokens"] = measure(20, 1)
        self.assertIsNone(breakeven(left, right, a, b, "tokens", "integrative")["first_reuse_not_more_expensive"])


if __name__ == "__main__":
    unittest.main()
