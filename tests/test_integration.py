"""Synthetic end-to-end smoke tests; require the project's scientific packages."""
import importlib.util
import unittest

DEPS = all(importlib.util.find_spec(name) is not None for name in ("numpy", "pandas", "sklearn"))


@unittest.skipUnless(DEPS, "numpy/pandas/scikit-learn unavailable; integration NOT verified")
class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import numpy as np
        import pandas as pd
        from src.causal_robustness import fit_response_models, predict_response_models
        rng = np.random.default_rng(42)
        n = 2400
        x = rng.uniform(size=n)
        t = rng.binomial(1, .5, n)
        y = rng.binomial(1, .2 + .35*x + t*(.04 + .12*x))
        frame = pd.DataFrame(dict(client_id=[f"c{i:06}" for i in range(n)],
            age_clean=20+50*x, age_review_flag=np.zeros(n), recency_days=1+(25*x).astype(int),
            txn_count_history=1+(50*x).astype(int), spend_history=5000*x+1,
            avg_transaction_amount=100+100*x, txn_count_30d=1+(15*x).astype(int),
            spend_30d=1500*x+1, zero_amount_txn_count=np.zeros(n),
            gender=rng.choice(["F", "M", "U"], n), treatment_flg=t, target=y))
        numeric = [c for c in frame if c not in ("client_id", "gender", "treatment_flg", "target")]
        cls.config = dict(numeric_features=numeric, categorical_features=["gender"], feature_columns=numeric+["gender"])
        cls.train, cls.valid, cls.test = frame.iloc[:1400].copy(), frame.iloc[1400:2000].copy(), frame.iloc[2000:].copy()
        cls.models = fit_response_models(cls.train, cls.config)
        cls.evaluation = predict_response_models(cls.valid, cls.models, cls.config)
        cls.policy = dict(budget_share=.2, propensity=.5,
            rfm_thresholds={c: cls.train[c].quantile([.2,.4,.6,.8]).tolist() for c in ("recency_days", "txn_count_history", "spend_history")},
            ranking_columns={"RFM":"rfm_score", "Response":"response_score", "Response_p1":"p1", "Uplift":"uplift_score"},
            comparison_baselines=["Response", "Response_p1", "Random", "RFM"])

    def test_budget_and_gamma_agree_with_vectorized_reference(self):
        import numpy as np
        from src.causal_robustness import build_policies, evaluate_policies
        df, policies = build_policies(self.evaluation, self.policy)
        gamma = df.p1-df.p0+df.treatment_flg/.5*(df.target-df.p1)-(1-df.treatment_flg)/.5*(df.target-df.p0)
        gains, differences = evaluate_policies(df, self.policy)
        for name, mask in policies.items():
            self.assertAlmostEqual(mask.sum(), round(len(df)*.2))
            actual = gains.set_index("strategy").loc[name, "gain_per_1000"]
            self.assertAlmostEqual(actual, np.mean(mask*gamma)*1000)
        actual = differences.set_index("comparison").loc["Uplift - Response", "extra_gain_per_1000"]
        self.assertAlmostEqual(actual, np.mean((policies["Uplift"]-policies["Response"])*gamma)*1000)

    def test_all_new_analyses_on_synthetic_data(self):
        from src.causal_robustness import (propensity_sensitivity, slearner_comparison,
            customer_profiles, bootstrap_policies, repeated_split_stability)
        gains, contrasts, diagnostics, raw, _ = propensity_sensitivity(self.train, self.evaluation, self.config, self.policy)
        self.assertEqual(len(gains), 3*2*5)
        self.assertEqual(len(contrasts), 3*2*4)
        self.assertTrue(((raw > 0) & (raw < 1)).all())
        s_gains, s_diff, _ = slearner_comparison(self.train, self.evaluation, self.config, self.policy)
        self.assertEqual(s_diff.comparison.eq("Uplift - Slearner").sum(), 2)
        profile, gender, overlap = customer_profiles(self.evaluation, self.policy)
        self.assertEqual(len(overlap), 2)
        self.assertTrue(gender.groupby("group").proportion.sum().round(10).eq(1).all())
        boot = bootstrap_policies(self.evaluation, self.policy, repeats=20)
        self.assertEqual(len(boot), 9)
        detail, summary = repeated_split_stability(self.train, self.valid, self.test, self.config, self.policy, seeds=(101,202))
        self.assertEqual(len(detail), 2*2*4)
        self.assertTrue(summary.repetitions.eq(2).all())

    def test_original_test_customer_overlap_is_rejected(self):
        from src.causal_robustness import validate_splits
        with self.assertRaises(ValueError):
            validate_splits(self.train, self.valid, self.train.iloc[:20])


if __name__ == "__main__":
    unittest.main()
