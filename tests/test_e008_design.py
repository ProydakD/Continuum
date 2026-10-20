from collections import Counter
import itertools
import unittest
from unittest.mock import patch

from research.e008_analysis import exact_sign_flip, holm, precision_plan, summarize
from research.e008_design import MEMORY_BUDGETS, SPLIT_COUNTS, bounds, corpus, schedule, select_budget, select_protocol
from research.e008_scm import FAMILIES, VARIABLES


def worlds(per_family=None):
    return [{"id": f"{split}-{family}-{i}", "split": split, "truth": {"family": family},
             "design_audit": {"integrative_question_ids": ["Q01", "Q02"]}}
            for split, count in (SPLIT_COUNTS if per_family is None else per_family).items()
            for family in FAMILIES for i in range(count)]


class DesignTests(unittest.TestCase):
    def test_full_matrix_and_no_forward_sources(self):
        data = worlds()
        jobs = schedule(data)
        self.assertEqual(jobs, schedule(data))
        self.assertEqual(len(jobs), 3426)
        self.assertEqual(Counter(j["phase"] for j in jobs),
                         {"calibration": 150, "development": 12, "validation": 288, "test": 2400, "robustness": 576})
        seen = {}
        for job in jobs:
            if job["source"]:
                self.assertIn(job["source"], seen)
                source = seen[job["source"]]
                for key in ("world", "condition", "lineage", "replicate"):
                    self.assertEqual(job[key], source[key])
                self.assertEqual(ord(job["stage"]), ord(source["stage"]) + 1)
            seen[job["id"]] = job
        self.assertEqual(bounds(jobs)["maximum_response_attempts"], 34262)
        self.assertEqual(bounds(jobs)["independent_test_worlds"], 60)

    def test_controls_use_only_registered_main_predecessor_not_a_new_writer(self):
        jobs = schedule(worlds())
        index = {j["id"]: j for j in jobs}
        crossed = [j for j in jobs if j["control"] == "cross_model"]
        self.assertEqual(len(crossed), 48)
        self.assertTrue(all(j["stage"] == "D" and j["model_role"] == "secondary"
                            and index[j["source"]]["phase"] == "test" for j in crossed))
        self.assertEqual(len([j for j in jobs if j["control"] == "crash" and j["stage"] == "C"]), 48)

    def test_splits_are_not_exposed_as_extra_training_positions(self):
        data, jobs = worlds(), schedule(worlds())
        index = {w["id"]: w["split"] for w in data}
        for job in jobs:
            if job["world"] is None:
                self.assertIn(job["role"], ("designer", "critic"))
            elif job["phase"] in ("calibration", "validation"):
                self.assertEqual(index[job["world"]], job["phase"])
            else:
                self.assertEqual(index[job["world"]], "test")
        self.assertEqual(len([j for j in jobs if j["role"] == "designer"]), 6)

    def test_disjoint_corpus_reproducibility_and_exclusions(self):
        def fake(rng, family, identity):
            assignment = {"family": family, "order": rng.sample(list(VARIABLES), 5),
                          "gate": "and", "flips": [rng.randrange(2) for _ in range(3)]}
            return {"id": identity, "truth": assignment, "evidence": [assignment]}
        with patch("research.e008_design.design_world", side_effect=fake):
            first = corpus(2026, per_family={s: 1 for s in SPLIT_COUNTS})
            repeated = corpus(2026, per_family={s: 1 for s in SPLIT_COUNTS})
            second = corpus(2026, per_family={s: 1 for s in SPLIT_COUNTS}, excluded_worlds=first["worlds"])
        self.assertEqual(first, repeated)
        self.assertEqual(len(first["worlds"]), 12)
        self.assertTrue(all(w["truth"] not in [p["truth"] for p in first["worlds"]] for w in second["worlds"]))

    def test_capacity_selection_uses_absolute_level_and_exact_tie(self):
        ids = ["a", "b"]
        records = {(w, c, budget): {"identified_correct": {1024: 1, 2048: 5, 4096: 9}[budget], "identified_total": 10}
                   for w in ids for c in ("C1", "T1") for budget in MEMORY_BUDGETS}
        self.assertEqual(select_budget(records, ids)["budget"], 2048)
        for w in ids:
            records[(w, "C1", 1024)]["identified_correct"] = 4
            records[(w, "T1", 1024)]["identified_correct"] = 5
            records[(w, "C1", 2048)]["identified_correct"] = 5
            records[(w, "T1", 2048)]["identified_correct"] = 6
        self.assertEqual(select_budget(records, ids)["budget"], 1024)
        swapped = {(w, "T1" if c == "C1" else "C1", b): score for (w, c, b), score in records.items()}
        self.assertEqual(select_budget(swapped, ids)["budget"], 1024)

    def test_selection_preserves_floor_and_failed_versions(self):
        ids = ["a"]
        scores = {(w, c, b): {"identified_correct": 0, "identified_total": 6}
                  for w in ids for c in ("C1", "T1") for b in MEMORY_BUDGETS}
        picked = select_budget(scores, ids)
        self.assertEqual(picked["budget"], 1024)
        self.assertFalse(picked["within_target"])
        values = {(v, w): 0 for v in (1, 2, 3) for w in ids}
        self.assertEqual(select_protocol(values, ids, available_versions=[2, 3])["version"], 2)
        self.assertIsNone(select_protocol(values, ids, available_versions=[])["version"])
        values[(3, "a")] = 7
        self.assertEqual(select_protocol(values, ids)["version"], 3)
        del values[(1, "a")]
        with self.assertRaises(ValueError):
            select_protocol(values, ids)

    def test_capacity_selection_weights_worlds_not_questions(self):
        records = {(w, c, b): {"identified_correct": 1 if w == "a" else 4, "identified_total": 1 if w == "a" else 9}
                   for w in ("a", "b") for c in ("C1", "T1") for b in MEMORY_BUDGETS}
        chosen = select_budget(records, ["a", "b"])
        self.assertAlmostEqual(chosen["candidates"][0]["rates"]["C1"], (1 + 4 / 9) / 2)
        self.assertNotEqual(chosen["candidates"][0]["rates"]["C1"], .5)


class AnalysisTests(unittest.TestCase):
    def test_exact_sign_flip_matches_enumeration_with_zeros(self):
        values = [0, 1, -2, 1, 3]
        tail = sum(abs(sum(v * s for v, s in zip(values, signs))) >= abs(sum(values))
                   for signs in itertools.product((-1, 1), repeat=len(values)))
        self.assertEqual(exact_sign_flip(values)["tail_assignments"], tail)
        self.assertEqual(exact_sign_flip([0] * 60)["p"], 1)
        self.assertEqual(exact_sign_flip([1] * 60)["tail_assignments"], 2)

    def test_holm_is_monotone_and_bounded(self):
        self.assertEqual(holm({"a": .01, "b": .04, "c": .03}), {"a": .03, "c": .06, "b": .06})
        self.assertEqual(holm({"a": 1, "b": 1}), {"a": 1, "b": 1})

    def prepare(self):
        data = worlds({s: 1 for s in SPLIT_COUNTS})
        jobs = schedule(data)
        outcomes = {}
        for job in jobs:
            if job["phase"] == "test" and job["stage"] == "D":
                count = (10 if job["lineage"] == "L1" else 0) if job["condition"] == "T2" else (8 if job["condition"] == "C1" else 9)
                outcomes[job["id"]] = {"status": "completed", "audit": {"pass": True},
                                       "score": {"new_correct": count, "new_target_correct": count,
                                                 "new_epistemic_correct": count, "new_total": 10,
                                                 "integrative_correct": min(count, 2), "target_integrative_correct": min(count, 2),
                                                 "integrative_total": 2}}
        return data, jobs, outcomes

    def test_world_is_unit_and_t2_lineages_average_inside_world(self):
        data, jobs, outcomes = self.prepare()
        report = summarize(data, jobs, outcomes, bootstrap_samples=100)
        self.assertEqual(report["n_independent_worlds"], 3)
        self.assertEqual(report["assigned_successors"], 48)
        self.assertTrue(all(cell["T2"] == .5 for cell in report["world_scores"].values()))
        self.assertEqual(report["contrasts"]["T1-C1"]["estimate"], .1)
        self.assertEqual(report["contrasts"]["T2-T1"]["estimate"], -.4)
        self.assertEqual(report["contrasts"]["T1-C1"]["sign_assignments"], 8)

    def test_failures_remain_zero_and_unfinished_is_an_error(self):
        data, jobs, outcomes = self.prepare()
        failed = next(j for j in jobs if j["phase"] == "test" and j["stage"] == "D" and j["condition"] == "C1")
        outcomes[failed["id"]] = {"status": "skipped_dependency"}
        report = summarize(data, jobs, outcomes, bootstrap_samples=100)
        self.assertEqual(report["failed_or_unverified"], 1)
        self.assertEqual(report["world_scores"][failed["world"]]["C1"], .4)
        outcomes[failed["id"]] = {"status": "running"}
        with self.assertRaises(ValueError):
            summarize(data, jobs, outcomes, bootstrap_samples=100)

    def test_integration_gate_requires_integrative_success_not_just_other_questions(self):
        data, jobs, outcomes = self.prepare()
        for row in outcomes.values():
            row["score"]["integrative_correct"] = 0
            row["score"]["target_integrative_correct"] = 0
        result = summarize(data, jobs, outcomes, bootstrap_samples=100)
        self.assertEqual(result["integration"]["C1_mean"], 0)
        self.assertFalse(result["integration_positive"])

    def test_control_prediction_is_not_zeroed_by_different_epistemic_target(self):
        data, jobs, outcomes = self.prepare()
        for assigned in jobs:
            if assigned["phase"] == "test" and assigned["stage"] == "D" and assigned["condition"] == "C0":
                score = outcomes[assigned["id"]]["score"]
                score.update(new_correct=0, new_epistemic_correct=0)
        result = summarize(data, jobs, outcomes, bootstrap_samples=100)
        self.assertTrue(all(w["C0"] == .9 for w in result["world_scores"].values()))
        self.assertTrue(all(w["C0"] == 0 for w in result["epistemic_world_scores"].values()))
        self.assertEqual(result["contrasts"]["C1-C0"]["estimate"], -.1)

    def test_precision_is_explicit_assumption_not_claimed_power(self):
        plan = precision_plan()
        self.assertEqual(plan["n_independent_worlds"], 60)
        self.assertEqual(plan["familywise_tests"], 8)
        self.assertGreater(plan["approximate_detectable_difference_by_paired_sd"]["1.0"], .4)
        self.assertLess(plan["approximate_detectable_difference_by_paired_sd"]["0.2"], .1)


if __name__ == "__main__":
    unittest.main()
