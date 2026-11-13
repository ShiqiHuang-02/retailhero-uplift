import math
import unittest
from src.audit_core import effect_scores, normal_summary, paired_summary, rank_order, weighted_topk_gain, bootstrap_topk


class PolicyMathTests(unittest.TestCase):
    def test_dr_matches_hand_calculation(self):
        actual = effect_scores([1, 0], [1, 0], [.2, .4], [.6, .7], .5)
        for x, y in zip(actual, [1.2, 1.1]):
            self.assertAlmostEqual(x, y)

    def test_ipw_uses_customer_specific_propensity(self):
        self.assertEqual(effect_scores([1, 0], [1, 1], [.3]*2, [.4]*2, [.25, .75], "IPW"), [4., -4.])

    def test_correct_randomization_removes_outcome_model_bias_in_expectation(self):
        # Each potential-outcome pair occurs once under each randomized arm.
        pairs = [(0, 1), (1, 1), (1, 0), (0, 1)]
        t, y = [], []
        for y0, y1 in pairs:
            t.extend([0, 1]); y.extend([y0, y1])
        gamma = effect_scores(t, y, [.9]*8, [.1]*8)
        self.assertAlmostEqual(sum(gamma)/8, sum(b-a for a, b in pairs)/4)

    def test_correct_outcome_models_remove_propensity_error_in_expectation(self):
        # Potential outcomes deterministic here; residuals vanish.
        gamma = effect_scores([1, 0], [1, 0], [0, 0], [1, 1], [.3, .7])
        self.assertEqual(gamma, [1., 1.])

    def test_paired_identical_policy_has_zero_uncertainty(self):
        self.assertEqual(paired_summary([2, -1, 3], [1, 0, 1], [1, 0, 1]), (0., 0., 0.))

    def test_gain_denominator_is_all_candidates(self):
        self.assertEqual(normal_summary([.1, 0, 0, 0])[0], 25.)

    def test_duplicate_bootstrap_copies_are_preserved(self):
        # Three copies of the best customer. Top two must both be that customer.
        self.assertEqual(weighted_topk_gain([.4, .1], [0, 1], [3, 1], 2), 200.)

    def test_weighted_selection_matches_explicit_resampled_population(self):
        gamma, scores, ids = [.4, -.3, .2], [.8, .8, .1], ["b", "a", "c"]
        counts = [2, 3, 1]
        order = rank_order(scores, ids)
        expanded = [i for i in order for _ in range(counts[i])]
        for k in range(7):
            expected = sum(gamma[i] for i in expanded[:k])/6*1000
            self.assertAlmostEqual(weighted_topk_gain(gamma, order, counts, k), expected)

    def test_ties_are_deterministic(self):
        self.assertEqual(rank_order([1, 1, 2], ["b", "a", "c"]), [2, 1, 0])

    def test_bootstrap_budget_endpoints_and_paired_baseline(self):
        gamma = [.1, .2, -.1, .3]
        rankings = {"Uplift": [4, 3, 2, 1], "Response": [1, 2, 3, 4]}
        for budget in [0, 1]:
            rows = bootstrap_topk(gamma, rankings, ["a", "b", "c", "d"], budget, 30, 7)
            for row in rows:
                if row["kind"] == "paired_difference":
                    for key in ["estimate_per_1000", "ci_low", "ci_high"]:
                        self.assertAlmostEqual(row[key], 0.)
                if budget == 0:
                    self.assertEqual(row["estimate_per_1000"], 0.)

    def test_reproducible_bootstrap(self):
        args = ([.1, .2, -.2], {"Uplift": [1, 2, 3]}, ["a", "b", "c"])
        self.assertEqual(bootstrap_topk(*args, repeats=20), bootstrap_topk(*args, repeats=20))

    def test_invalid_probabilities_and_labels_fail(self):
        for e in [0, 1, math.nan]:
            with self.assertRaises(ValueError):
                effect_scores([1, 0], [1, 0], [.2]*2, [.3]*2, e)
        with self.assertRaises(ValueError):
            effect_scores([2], [1], [.2], [.3])
        with self.assertRaises(ValueError):
            effect_scores([1], [1], [1.2], [.3])


if __name__ == "__main__":
    unittest.main()
