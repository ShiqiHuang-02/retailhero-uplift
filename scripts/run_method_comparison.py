"""Compare uplift meta-learners (T / S / X) on the validation set.

Judges each learner two ways, both consistent with the project's primary
evaluation and both on the VALIDATION set only (the test set is never touched):

  1. Qini curve and AUUC: how well the ranking concentrates DR gain at the top.
  2. 20% DR strategy value: the same policy-evaluation used in notebook 03.

Run from the project root with the project interpreter:
    .venv/bin/python -B scripts/run_method_comparison.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.causal_robustness import (  # noqa: E402
    build_policies,
    effect_scores,
    fit_response_models,
    make_classifier,
    normal_summary,
    paired_summary,
    predict_response_models,
)
from src.uplift_metrics import auuc, qini_curve  # noqa: E402
from src.xlearner import fit_xlearner, predict_xlearner  # noqa: E402

LEARNER_SCORES = {"T-learner": "uplift_score", "S-learner": "slearner_score", "X-learner": "xlearner_score"}


def load_frames():
    train = duckdb.read_parquet(str(ROOT / "data/processed/train.parquet")).df()
    valid = duckdb.read_parquet(str(ROOT / "data/processed/validation.parquet")).df()
    return train, valid


def fit_and_score(train, valid, config):
    """Fit T/S/X learners on train and score the validation set in-place."""
    scored = valid.copy().reset_index(drop=True)

    # T-learner (reuses the project's base response models).
    tmodels = fit_response_models(train, config)
    scored = predict_response_models(scored, tmodels, config)  # adds uplift_score, p0, p1

    # S-learner: treatment as a feature.
    s_columns = config["feature_columns"] + ["treatment_flg"]
    smodel = make_classifier(config, treatment_feature=True).fit(train[s_columns], train.target)
    sx = scored[s_columns].copy()
    scored["slearner_score"] = (
        smodel.predict_proba(sx.assign(treatment_flg=1))[:, 1]
        - smodel.predict_proba(sx.assign(treatment_flg=0))[:, 1]
    )

    # X-learner (plain, no cross-fitting; see src/xlearner.py).
    xlearner = fit_xlearner(train, config)
    scored["xlearner_score"] = predict_xlearner(scored, xlearner, config)

    return scored


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--propensity", type=float, default=0.5, help="Treatment propensity for DR/IPW (default: 0.5)")
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "method_comparison")
    args = parser.parse_args(argv)

    train, valid = load_frames()
    config = json.loads((ROOT / "models" / "model_config.json").read_text(encoding="utf-8"))
    policy_config = json.loads((ROOT / "models" / "policy_config.json").read_text(encoding="utf-8"))

    scored = fit_and_score(train, valid, config)

    # DR effect scores (aligned with the project's primary evaluation).
    gamma = np.asarray(effect_scores(
        scored.treatment_flg, scored.target, scored.p0, scored.p1, args.propensity, "DR"
    ))

    # ---- 1. Qini / AUUC ----
    auuc_rows = []
    for name, column in LEARNER_SCORES.items():
        scores = scored[column].to_numpy()
        auuc_rows.append({"learner": name, "auuc_per_1000": auuc(scores, gamma)})

    # ---- 2. 20% DR strategy value (same policies as notebook 03) ----
    settings = dict(policy_config)
    settings["ranking_columns"] = {
        **policy_config["ranking_columns"],  # RFM, Response, Response_p1, Uplift (T-learner)
        "S-learner": "slearner_score",
        "X-learner": "xlearner_score",
    }
    df, policies = build_policies(scored, settings)

    gain_rows = []
    for name, policy in policies.items():
        avg, lo, hi = normal_summary(policy * gamma)
        gain_rows.append(dict(
            strategy=name, contacts_per_1000=float(policy.mean() * 1000),
            gain_per_1000=avg, ci_low=lo, ci_high=hi,
        ))

    # Policy keys differ from display names: the T-learner's uplift score is
    # named "Uplift" in policy_config (matching notebooks 03/05).
    pairwise_specs = [
        ("X-learner", "X-learner", "T-learner", "Uplift"),
        ("X-learner", "X-learner", "S-learner", "S-learner"),
        ("S-learner", "S-learner", "T-learner", "Uplift"),
    ]
    pairwise_rows = []
    for a_label, a_key, b_label, b_key in pairwise_specs:
        avg, lo, hi = paired_summary(gamma, policies[a_key], policies[b_key])
        pairwise_rows.append(dict(comparison=f"{a_label} - {b_label}", extra_gain_per_1000=avg, ci_low=lo, ci_high=hi))

    # ---- Write outputs ----
    out = args.output
    (out / "figures").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(auuc_rows).to_csv(out / "auuc.csv", index=False)
    pd.DataFrame(gain_rows).to_csv(out / "learner_gains.csv", index=False)
    pd.DataFrame(pairwise_rows).to_csv(out / "learner_pairwise.csv", index=False)

    # Qini plot.
    fig, ax = plt.subplots(figsize=(8, 5))
    x = np.arange(1, len(gamma) + 1) / len(gamma)
    for name, column in LEARNER_SCORES.items():
        qx, qy = qini_curve(scored[column].to_numpy(), gamma)
        ax.plot(qx, qy, label=name, linewidth=2)
    ax.plot(x, x * gamma.mean() * 1000.0, "k--", linewidth=1.2, label="Random")
    ax.axvline(policy_config["budget_share"], color="gray", linestyle=":", alpha=0.6)
    ax.set_xlabel("Cumulative contact fraction")
    ax.set_ylabel("Cumulative gain per 1000 candidates")
    ax.set_title("Qini curves (validation, DR scores)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "figures" / "qini_curves.png", dpi=110)
    plt.close(fig)

    print("AUUC (per 1000):")
    print(pd.DataFrame(auuc_rows).to_string(index=False))
    print("\n20% DR strategy value:")
    print(pd.DataFrame(gain_rows).to_string(index=False))
    print("\nLearner pairwise differences:")
    print(pd.DataFrame(pairwise_rows).to_string(index=False))
    print(f"\nWrote outputs to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
