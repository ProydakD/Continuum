from itertools import product
import math
import unittest

from research.e009_power_full import binomial_summary, simulate_worlds
from research.e009_statistics import (analyze_worlds, bootstrap_means, bounded_difference_upper,
                                      bounded_mean_upper, exact_signflip, holm, quantile)


class StatisticsTests(unittest.TestCase):
    def test_exact_signflip_matches_exhaustive_sign_assignments(self):
        for differences in product((-2, -1, 0, 1, 2), repeat=4):
            threshold = abs(sum(differences))
            expected = sum(abs(sum(s * d for s, d in zip(signs, differences))) >= threshold
                           for signs in product((-1, 1), repeat=4)) / 16
            self.assertEqual(exact_signflip(list(differences)), expected, differences)

    def test_zero_variance_is_not_automatic_significance(self):
        self.assertEqual(exact_signflip([0] * 240), 1)
        self.assertEqual(exact_signflip([2] * 10), 2 / 1024)

    def test_signflip_rejects_unregistered_episode_scale(self):
        for values in ([], [0.5], [True], [3]):
            with self.assertRaises(ValueError): exact_signflip(values)

    def test_holm_unsorted_and_monotonic(self):
        self.assertEqual(holm([.04, .01, .03]), [.06, .03, .06])
        self.assertEqual(holm([0, 1, .9]), [0, 1, 1])

    def test_linear_quantile_matches_manual_interpolation(self):
        self.assertEqual(quantile([0, 10], .25), 2.5)
        self.assertEqual(quantile([2], .95), 2)

    def test_bootstrap_resamples_whole_paired_world_rows(self):
        rows = [[0, 3], [1, 5], [2, 7]]
        values = bootstrap_means(rows, 100, 987)
        self.assertEqual(values, bootstrap_means(rows, 100, 987))
        for a, b in values: self.assertAlmostEqual(b, 2 * a + 3)

    def test_zero_events_have_positive_safety_upper_bound(self):
        self.assertAlmostEqual(bounded_mean_upper(0, 60), 1 - .05 ** (1 / 60))
        self.assertGreater(bounded_difference_upper([0] * 120), .02)
        self.assertLess(bounded_difference_upper([0] * 240), .02)

    def test_bounded_upper_has_finite_sample_bernoulli_coverage(self):
        # Exact enumeration, independent of the root-finding formula.
        for n in (5, 10, 20):
            for p in (.01, .1, .3, .5, .8, .99):
                probability = sum(math.comb(n, k) * p**k * (1-p)**(n-k)
                                  for k in range(n+1) if bounded_mean_upper(k/n, n) < p - 1e-12)
                self.assertLessEqual(probability, .05 + 1e-12)

    def test_bounded_upper_edges_and_monotonicity(self):
        self.assertEqual(bounded_mean_upper(1, 240), 1)
        self.assertGreater(bounded_mean_upper(.02, 60), bounded_mean_upper(.02, 240))
        self.assertGreater(bounded_mean_upper(.03, 240), bounded_mean_upper(.02, 240))

    def test_safety_is_not_assumed_from_favorable_bri(self):
        worlds = [{"id": str(i), "successes": [0, 2, 0, 2], "worst_losses": [0, 4, 0, 4], "slots": 32} for i in range(30)]
        result = analyze_worlds(worlds, resamples=50)
        self.assertTrue(result["contrasts"][0]["decision_without_guardrail"])
        self.assertFalse(result["contrasts"][0]["decision"])

    def test_zero_success_is_retained_as_assigned_outcome(self):
        worlds = [{"id": str(i), "successes": [0]*4, "worst_losses": [32]*4, "slots": 32} for i in range(10)]
        result = analyze_worlds(worlds, resamples=50)
        self.assertTrue(all(c["p_exact"] == 1 and not c["decision"] for c in result["contrasts"]))

    def test_no_conditional_world_drop_or_unknown_denominator(self):
        worlds = [{"id": str(i), "successes": [0]*4, "worst_losses": [0]*4, "slots": 0} for i in range(2)]
        with self.assertRaises(ValueError): analyze_worlds(worlds)
        for w in worlds: w["slots"] = 32
        worlds[1]["id"] = worlds[0]["id"]
        with self.assertRaises(ValueError): analyze_worlds(worlds)

    def test_simulation_reproducible_finite_and_two_full_repeats(self):
        worlds, resources = simulate_worlds(8, "safe-strong", 123)
        self.assertEqual((worlds, resources), simulate_worlds(8, "safe-strong", 123))
        self.assertEqual(len({w["id"] for w in worlds}), 8)
        self.assertTrue(all(w["slots"] in (24, 32) for w in worlds))
        self.assertEqual(resources["assigned_contexts_per_condition"], 80)
        with self.assertRaises(ValueError): simulate_worlds(577, "null", 1)

    def test_harmful_assumption_changes_losses_not_only_bri(self):
        worlds, _ = simulate_worlds(240, "unsafe-v1", 124)
        self.assertGreater(sum(w["worst_losses"][1] for w in worlds), sum(w["worst_losses"][0] for w in worlds))

    def test_monte_carlo_zero_rate_is_not_zero_uncertainty(self):
        result = binomial_summary(0, 200)
        self.assertGreater(result["mc_wilson_95"][1], 0)


if __name__ == "__main__":
    unittest.main()
