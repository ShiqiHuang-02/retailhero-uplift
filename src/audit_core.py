"""Dependency-free policy mathematics; inputs must be held-out predictions.

Bootstrap conditions on fitted models/nuisance estimates, and resamples customers.
It reselects top-k in each replicate. It does not account for model selection,
unobserved confounding, or uncertainty from fitting the nuisance functions.
"""
from math import isfinite, sqrt
from numbers import Real
from random import Random
from statistics import mean, stdev


def effect_scores(treatment, outcome, p0, p1, propensity=0.5, method="DR"):
    t, y, a, b = map(list, (treatment, outcome, p0, p1))
    n = len(t)
    e = [float(propensity)] * n if isinstance(propensity, Real) else list(propensity)
    if not n or any(len(v) != n for v in (y, a, b, e)):
        raise ValueError("All inputs must have the same nonzero length")
    if method not in ("DR", "IPW"):
        raise ValueError("method must be DR or IPW")
    result = []
    for ti, yi, ai, bi, ei in zip(t, y, a, b, e):
        if ti not in (0, 1) or yi not in (0, 1):
            raise ValueError("Treatment and outcome must be binary")
        if not all(isfinite(float(v)) for v in (ai, bi, ei)):
            raise ValueError("Predictions and propensity must be finite")
        if not (0 <= ai <= 1 and 0 <= bi <= 1 and 0 < ei < 1):
            raise ValueError("Invalid probability or lack of overlap")
        if method == "DR":
            value = bi - ai + ti / ei * (yi - bi) - (1 - ti) / (1 - ei) * (yi - ai)
        else:
            value = ti / ei * yi - (1 - ti) / (1 - ei) * yi
        result.append(float(value))
    return result


def normal_summary(values, scale=1000):
    values = list(values)
    if len(values) < 2 or not all(isfinite(float(x)) for x in values):
        raise ValueError("At least two finite contributions are required")
    estimate = mean(values) * scale
    se = stdev(values) / sqrt(len(values)) * scale
    return estimate, estimate - 1.96 * se, estimate + 1.96 * se


def paired_summary(gamma, policy, baseline):
    if not (len(gamma) == len(policy) == len(baseline)):
        raise ValueError("Paired inputs must be aligned")
    return normal_summary([(a-b)*g for a, b, g in zip(policy, baseline, gamma)])


def rank_order(scores, client_ids):
    scores, client_ids = list(scores), list(client_ids)
    if len(scores) != len(client_ids) or not scores:
        raise ValueError("Scores and identifiers must have the same nonzero length")
    if any(x is None for x in client_ids) or len(set(client_ids)) != len(client_ids):
        raise ValueError("Original customer identifiers must be unique and nonmissing")
    if not all(isfinite(float(x)) for x in scores):
        raise ValueError("Ranking scores must be finite")
    return sorted(range(len(scores)), key=lambda i: (-float(scores[i]), str(client_ids[i])))


def weighted_topk_gain(gamma, order, counts, k):
    """Select k bootstrap copies, preserving multiplicities and original tie order."""
    if len(gamma) != len(order) or len(gamma) != len(counts):
        raise ValueError("Bootstrap arrays must align")
    n = sum(counts)
    if not n or k < 0 or k > n:
        raise ValueError("Invalid bootstrap size or budget")
    total, remaining = 0.0, k
    for i in order:
        take = min(counts[i], remaining)
        total += take * gamma[i]
        remaining -= take
        if remaining == 0:
            break
    return total / n * 1000


def percentile(values, q):
    ordered = sorted(values)
    if not ordered or not 0 <= q <= 1:
        raise ValueError("Invalid percentile")
    position = (len(ordered) - 1) * q
    low = int(position)
    high = min(low + 1, len(ordered)-1)
    return ordered[low] + (position-low) * (ordered[high]-ordered[low])


def bootstrap_topk(gamma, rankings, client_ids, budget=0.2, repeats=500, seed=20261113):
    """Paired percentile intervals for fixed scorers on new iid customer batches.

    rankings maps strategy names to scores. Do not pass Random: it is the
    expected random-budget baseline, with no simulated assignment noise.
    Customer resampling uses counts; duplicates are NEVER discarded.
    """
    gamma, client_ids = list(gamma), list(client_ids)
    n = len(gamma)
    if n < 2 or len(client_ids) != n or not 0 <= budget <= 1 or repeats < 2:
        raise ValueError("Invalid bootstrap inputs")
    if not all(isfinite(float(x)) for x in gamma):
        raise ValueError("Effect scores must be finite")
    if "Random" in rankings or "Uplift" not in rankings:
        raise ValueError("Supply Uplift and optional score baselines; Random is automatic")
    orders = {name: rank_order(scores, client_ids) for name, scores in rankings.items()}
    if any(len(order) != n for order in orders.values()):
        raise ValueError("Ranking and effect score lengths differ")
    k = round(n * budget)
    def gains(counts):
        result = {name: weighted_topk_gain(gamma, order, counts, k) for name, order in orders.items()}
        result["Random"] = k / n * sum(c*g for c, g in zip(counts, gamma)) / n * 1000
        return result
    point = gains([1]*n)
    names = list(point)
    draws = {name: [] for name in names}
    diffs = {name: [] for name in names if name != "Uplift"}
    rng = Random(seed)
    for _ in range(repeats):
        counts = [0]*n
        for _ in range(n):
            counts[rng.randrange(n)] += 1
        g = gains(counts)
        for name in names:
            draws[name].append(g[name])
        for name in diffs:
            diffs[name].append(g["Uplift"]-g[name])
    rows = []
    for name, vals in draws.items():
        rows.append(dict(kind="gain", comparison=name, estimate_per_1000=point[name],
                         ci_low=percentile(vals, .025), ci_high=percentile(vals, .975)))
    for name, vals in diffs.items():
        rows.append(dict(kind="paired_difference", comparison="Uplift - " + name,
                         estimate_per_1000=point["Uplift"]-point[name],
                         ci_low=percentile(vals, .025), ci_high=percentile(vals, .975)))
    for row in rows:
        row.update(repeats=repeats, seed=seed, interval="percentile_customer_bootstrap_fixed_models")
    return rows
