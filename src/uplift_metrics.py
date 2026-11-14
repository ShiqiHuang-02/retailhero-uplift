"""Offline uplift ranking metrics: Qini-style curve and AUUC.

Implemented with DR effect scores so the evaluation is consistent with the
project's primary DR strategy-value estimator. These metrics judge an uplift
model by how well its ranking concentrates gain at the top, which is exactly the
right target when contacts are budget-constrained.
"""

from __future__ import annotations

import numpy as np


def qini_curve(scores, gamma):
    """Return (x, y) for a Qini-style cumulative gain curve.

    Parameters
    ----------
    scores : 1-D array of uplift scores used to rank customers (highest first).
    gamma : 1-D array of DR (or IPW) effect scores aligned with `scores`.

    Returns
    -------
    x : cumulative contact fraction in [0, 1].
    y : cumulative gain per 1000 candidates = 1000 * cumsum(gamma[order]) / n.
    """
    scores = np.asarray(scores, dtype=float)
    gamma = np.asarray(gamma, dtype=float)
    if scores.shape != gamma.shape or scores.ndim != 1 or len(scores) < 2:
        raise ValueError("scores and gamma must be equal-length 1-D arrays")
    if not np.isfinite(scores).all() or not np.isfinite(gamma).all():
        raise ValueError("scores and gamma must be finite")
    order = np.argsort(-scores)
    n = len(gamma)
    x = np.arange(1, n + 1) / n
    y = np.cumsum(gamma[order]) / n * 1000.0
    return x, y


def auuc(scores, gamma):
    """Area under the uplift curve, relative to a random-contact baseline.

    Returns the extra gain per 1000 candidates above random selection,
    integrated over the contact fraction in [0, 1]. A positive value means the
    ranking concentrates more gain at the top than random contact would.
    """
    x, y = qini_curve(scores, gamma)
    random = x * np.mean(np.asarray(gamma, dtype=float)) * 1000.0
    return float(np.trapezoid(y - random, x))
