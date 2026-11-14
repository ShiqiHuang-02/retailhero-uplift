"""X-learner uplift meta-learner (Kunzel et al. 2019), implemented by hand.

The project already fits a T-learner and an S-learner with HistGradientBoosting
and evaluates strategies with a hand-rolled DR/IPW estimator. The X-learner
below follows the same dependency-light style instead of pulling in a heavy
causal-ML library, so the method remains easy to explain in an interview.

Reference: Kunzel, Sekhon, Bickel, Yu, "Metalearners for estimating
heterogeneous treatment effects using machine learning" (PNAS 2019).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from src.causal_robustness import (
    fit_propensity,
    fit_response_models,
    predict_response_models,
    validate_frame,
)


def _make_regressor(config, seed=42):
    """Same preprocessing as make_classifier, but with a regression target."""
    numeric = list(config["numeric_features"])
    pre = ColumnTransformer([
        ("numeric", SimpleImputer(strategy="median"), numeric),
        (
            "categorical",
            OneHotEncoder(handle_unknown="ignore", sparse_output=False),
            config["categorical_features"],
        ),
    ])
    model = HistGradientBoostingRegressor(
        learning_rate=0.05,
        max_iter=150,
        max_leaf_nodes=15,
        min_samples_leaf=100,
        l2_regularization=1.0,
        early_stopping=True,
        random_state=seed,
    )
    return Pipeline([("preprocessing", pre), ("regressor", model)])


def fit_xlearner(train, config, propensity_model=None, seed=42):
    """Fit a plain X-learner and return its fitted components.

    Steps:
      1. Fit two base outcome models: mu1 on treated, mu0 on control
         (reuses the project's T-learner base models).
      2. Impute counterfactuals to build pseudo-effects:
             control units  (T=0): D0 = mu1(x) - Y
             treated units  (T=1): D1 = Y - mu0(x)
      3. Regress the pseudo-effects on X separately per arm:
             tau0 fitted on control rows, tau1 fitted on treated rows.
      4. Combine with the propensity score g(x) = P(T=1 | x):
             tau(x) = g(x) * tau0(x) + (1 - g(x)) * tau1(x).

    This is the "plain" X-learner without K-fold cross-fitting: the pseudo-effect
    targets reuse the same training rows used to fit mu0/mu1, which can slightly
    overfit. Keep that caveat when reporting results.
    """
    validate_frame(train)
    base = fit_response_models(train, config)  # {"response", "m0", "m1"}
    scored = predict_response_models(train, base, config)  # adds p0, p1

    x = train[config["feature_columns"]]
    control = train.treatment_flg.eq(0)
    treated = train.treatment_flg.eq(1)

    d0 = (scored.loc[control, "p1"] - scored.loc[control, "target"]).to_numpy()
    d1 = (scored.loc[treated, "target"] - scored.loc[treated, "p0"]).to_numpy()

    tau0 = _make_regressor(config, seed=seed).fit(x[control], d0)
    tau1 = _make_regressor(config, seed=seed).fit(x[treated], d1)

    if propensity_model is None:
        propensity_model = fit_propensity(train, config)
    return {"tau0": tau0, "tau1": tau1, "propensity_model": propensity_model}


def predict_xlearner(data, xlearner, config):
    """Predict uplift scores for held-out customers (probability scale)."""
    x = data[config["feature_columns"]]
    tau0 = xlearner["tau0"].predict(x)
    tau1 = xlearner["tau1"].predict(x)
    g = np.clip(xlearner["propensity_model"].predict_proba(x)[:, 1], 0.01, 0.99)
    uplift = g * tau0 + (1.0 - g) * tau1
    return np.clip(uplift, -1.0, 1.0)
