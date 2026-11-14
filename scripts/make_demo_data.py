"""Generate a small synthetic dataset with a known uplift signal for the demo.

The real X5 RetailHero dataset (~581 MB of gzipped CSVs) is intentionally kept
out of the repository, together with the processed data, trained models and the
fixed customer split. This script writes synthetic raw files with the SAME
schema as the real data plus a matching split manifest, so a reviewer can run
the core pipeline (01 -> 02 -> 03) end-to-end in well under a minute.

Data generating process (DGP) — kept explicit so the demo result is explainable:

  * Each customer i has a latent "activity" level a_i in [0, 1].
  * Activity drives the purchase history that notebook 01 turns into RFM
    features: more active -> more transactions, lower recency, higher spend.
  * Base purchase probability INCREASES with activity:
        logit(P(Y=1 | T=0)) = -1.0 + 2.0 * a_i
  * The causal effect of the message DECREASES with activity:
        uplift (logit scale) = 1.5 * (1 - a_i)
    i.e. inactive customers are the "persuadables" whose behaviour the message
    can change, while active customers would buy anyway.
  * Treatment is assigned at random with probability 0.5, so the true
    propensity is 0.5 everywhere (matching the project's primary e=0.5 setting).
  * Outcome: Y ~ Bernoulli(logit(base + T * uplift)).

Because base probability and uplift point in opposite directions, a response
model ranks active (low-uplift) customers first while an uplift model ranks
inactive (high-uplift) customers first; the DR evaluation therefore shows the
Uplift strategy clearly ahead of Response. That is exactly the point the project
illustrates, on data whose ground truth is fully known.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FEATURE_CUTOFF = pd.Timestamp("2019-03-19 00:00:00")

# Column order must match data/raw/purchases.csv.gz exactly.
PURCHASE_COLUMNS = [
    "client_id", "transaction_id", "transaction_datetime",
    "regular_points_received", "express_points_received",
    "regular_points_spent", "express_points_spent",
    "purchase_sum", "store_id", "product_id", "product_quantity",
    "trn_sum_from_iss", "trn_sum_from_red",
]

# DGP hyper-parameters (explicit and documented, not a black box).
# The uplift scale is deliberately large so the demo signal clearly exceeds the
# DR estimator's sampling noise at the demo's small sample size.
BASE_LOGIT_INTERCEPT = -1.0
BASE_LOGIT_ACTIVITY = 2.0
UPLIFT_LOGIT_SCALE = 1.5
TREATMENT_PROBABILITY = 0.5


def _logistic(x):
    return 1.0 / (1.0 + np.exp(-np.clip(np.asarray(x, dtype=float), -50.0, 50.0)))


def _make_clients(rng, client_ids):
    n = len(client_ids)
    issue = pd.Timestamp("2016-01-01") + pd.to_timedelta(rng.integers(0, 1100, size=n), unit="D")
    has_redeem = rng.random(n) < 0.75
    redeem = issue + pd.to_timedelta(rng.integers(1, 365, size=n), unit="D")
    issue_str = issue.strftime("%Y-%m-%d %H:%M:%S").to_numpy()
    redeem_str = redeem.strftime("%Y-%m-%d %H:%M:%S").to_numpy()
    return pd.DataFrame({
        "client_id": list(client_ids),
        "first_issue_date": issue_str,
        "first_redeem_date": np.where(has_redeem, redeem_str, None),
        "age": rng.integers(18, 81, size=n),
        "gender": rng.choice(["F", "M", "U"], size=n, p=[0.45, 0.45, 0.10]),
    })


def _make_purchases(rng, client_ids, activity):
    rows = []
    txn_counter = 0
    for cid, act in zip(client_ids, activity):
        n_txn = int(max(2, rng.normal(3 + 15 * act, 1.5)))
        # recency in days ago: active -> recent, inactive -> lapsed
        recency = int(max(1, rng.normal(340 * (1 - act), 15)))
        days_ago = np.clip(recency + rng.integers(0, 90, size=n_txn), 1, None)
        datetimes = FEATURE_CUTOFF - pd.to_timedelta(days_ago, unit="D")
        # transaction amount: active -> larger
        amounts = np.maximum(
            np.round(np.exp(rng.normal(np.log(250) + 0.9 * act, 0.3, size=n_txn)), 2),
            1.0,
        )
        for t in range(n_txn):
            txn_id = f"t{txn_counter:09d}"
            txn_counter += 1
            dt = datetimes[t].strftime("%Y-%m-%d %H:%M:%S")
            store_id = f"s{rng.integers(0, 10 ** 5):06d}"
            total = float(amounts[t])
            n_products = int(rng.integers(1, 4))
            for _ in range(n_products):
                product_id = f"p{rng.integers(0, 10 ** 6):07d}"
                quantity = float(rng.integers(1, 4))
                share = round(total / n_products, 2)
                rows.append([
                    cid, txn_id, dt,
                    0.0, 0.0, 0.0, 0.0,
                    total, store_id, product_id, quantity,
                    share, 0.0,
                ])
    return pd.DataFrame(rows, columns=PURCHASE_COLUMNS)


def generate(n_clients=20000, seed=42):
    """Return (clients, uplift_train, purchases) with a known uplift signal."""
    rng = np.random.default_rng(seed)
    # Letter prefixes keep every id column VARCHAR under read_csv_auto, avoiding
    # leading-zero loss or BIGINT mis-inference on pure-digit ids.
    client_ids = np.array([f"c{i:09d}" for i in range(n_clients)])
    activity = rng.uniform(0.0, 1.0, size=n_clients)

    clients = _make_clients(rng, client_ids)
    purchases = _make_purchases(rng, client_ids, activity)

    treatment = rng.binomial(1, TREATMENT_PROBABILITY, size=n_clients).astype(int)
    base_logit = BASE_LOGIT_INTERCEPT + BASE_LOGIT_ACTIVITY * activity
    uplift_logit = UPLIFT_LOGIT_SCALE * (1.0 - activity)
    prob = _logistic(base_logit + treatment * uplift_logit)
    target = rng.binomial(1, prob).astype(int)

    uplift_train = pd.DataFrame({
        "client_id": list(client_ids),
        "treatment_flg": treatment,
        "target": target,
    })
    return clients, uplift_train, purchases


def make_splits(uplift_train, seed):
    """Random 60/20/20 split, stratified on treatment_flg; never silently overwrites."""
    from src.splits import SPLITS, validate_assignments
    rng = np.random.default_rng(seed)
    n = len(uplift_train)
    split_of = np.empty(n, dtype=object)
    for t in (0, 1):
        idx = np.flatnonzero(uplift_train.treatment_flg.to_numpy() == t)
        rng.shuffle(idx)
        k = len(idx)
        n_train = int(round(0.6 * k))
        n_valid = int(round(0.2 * k))
        labels = np.array(
            ["train"] * n_train + ["validation"] * n_valid + ["test"] * (k - n_train - n_valid),
            dtype=object,
        )
        split_of[idx] = labels
    records = []
    for split in SPLITS:
        row_indices = [i for i in range(n) if split_of[i] == split]
        row_indices.sort(key=lambda i: uplift_train.client_id.iloc[i])
        for position, row_i in enumerate(row_indices):
            records.append({
                "client_id": uplift_train.client_id.iloc[row_i],
                "split": split,
                "position": position,
                "treatment_flg": int(uplift_train.treatment_flg.iloc[row_i]),
                "target": int(uplift_train.target.iloc[row_i]),
            })
    assignments = pd.DataFrame(
        records,
        columns=["client_id", "split", "position", "treatment_flg", "target"],
    )
    validate_assignments(assignments)
    return assignments


def write_all(root=ROOT, n_clients=20000, seed=42, force=False):
    root = Path(root)
    raw = root / "data" / "raw"
    splits_dir = root / "data" / "splits"
    # Only these signal REAL data (all git-ignored, so absent in a fresh clone).
    # data/splits/metadata.json is tracked in the repo but meaningless without
    # assignments.csv, so the demo always (re)writes it rather than treating it
    # as protected real data.
    protected = [
        raw / "clients.csv.gz",
        raw / "uplift_train.csv.gz",
        raw / "purchases.csv.gz",
        splits_dir / "assignments.csv",
    ]
    existing = [str(p.relative_to(root)) for p in protected if p.exists()]
    if existing and not force:
        raise FileExistsError(
            "Refusing to overwrite real data files:\n  "
            + "\n  ".join(existing)
            + "\nRun --demo in a clean clone (these paths are git-ignored and absent), "
            "or pass --force only in a throwaway copy that contains no real data."
        )
    raw.mkdir(parents=True, exist_ok=True)
    splits_dir.mkdir(parents=True, exist_ok=True)

    clients, uplift_train, purchases = generate(n_clients, seed)
    clients.to_csv(raw / "clients.csv.gz", index=False, compression="gzip")
    uplift_train.to_csv(raw / "uplift_train.csv.gz", index=False, compression="gzip")
    purchases.to_csv(raw / "purchases.csv.gz", index=False, compression="gzip")

    assignments = make_splits(uplift_train, seed + 1)
    csv_path = splits_dir / "assignments.csv"
    assignments.to_csv(csv_path, index=False, lineterminator="\n")

    from src.splits import sha256
    metadata = {
        "schema_version": 1,
        "origin": "Synthetic demo data generated by scripts/make_demo_data.py; NOT the real X5 RetailHero sample.",
        "n_clients": int(n_clients),
        "seed": int(seed),
        "counts": {name: int(assignments.split.eq(name).sum()) for name in ("train", "validation", "test")},
        "assignments_sha256": sha256(csv_path),
    }
    (splits_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"clients": int(len(clients)), "purchases": int(len(purchases)), "splits": metadata["counts"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate synthetic demo data with a known uplift signal.")
    parser.add_argument("--n-clients", type=int, default=20000, help="Number of synthetic customers (default: 20000)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    parser.add_argument("--root", type=Path, default=ROOT, help="Project root to write into (default: repo root)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files (DANGEROUS: only in a clean clone)")
    args = parser.parse_args(argv)
    summary = write_all(root=args.root, n_clients=args.n_clients, seed=args.seed, force=args.force)
    print("Wrote synthetic demo data:", summary)


if __name__ == "__main__":
    main()
