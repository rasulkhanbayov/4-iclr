"""
physweep/decomposition.py
=========================
What determines the realized parameter: the request, the scene, or the noise?

theta_hat on valid clips is decomposed over three categorical factors:
  request  the requested theta (categorical, so a non-linear response counts)
  scene    scene_seed
  noise    noise_seed
Shares are LMG / Shapley shares of an additive dummy-coded OLS model: each
factor's R^2 contribution averaged over all orderings. This works on an
unbalanced design, which matters because invalid clips are removed. The
residual share (1 - R^2 of the full model) is interactions plus
unstructured noise.

With few levels per factor (e.g. 4 scenes), a factor explains some variance
by chance. For each factor we report a chance-corrected share
max(0, share - (k-1)/(n-p) * residual share), with p the number of model
parameters (adjusted-R^2 / omega^2 logic), plus a permutation p-value and the
shuffled-label null mean for transparency.

If scene and noise labels are perfectly confounded (the v1 design: one seed
for both), they cannot be separated. `confounded` is then True and only
their combined share is meaningful.
"""

from __future__ import annotations

from itertools import combinations
from math import factorial

import numpy as np

FACTORS = ("request", "scene", "noise")


def _dummies(labels: np.ndarray) -> np.ndarray:
    levels = np.unique(labels)
    return (labels[:, None] == levels[None, 1:]).astype(float)  # drop the first level


def _r2(y: np.ndarray, cols: list[np.ndarray]) -> float:
    X = np.column_stack([np.ones(len(y))] + cols) if cols else np.ones((len(y), 1))
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    tss = np.sum((y - y.mean()) ** 2)
    return 0.0 if tss == 0 else 1.0 - np.sum(resid ** 2) / tss


def lmg_shares(y, labels: dict) -> dict:
    names = list(labels)
    d = {n: _dummies(np.asarray(labels[n])) for n in names}
    p = len(names)
    r2 = {}
    for k in range(p + 1):
        for S in combinations(names, k):
            r2[frozenset(S)] = _r2(y, [d[n] for n in S])
    shares = {}
    for f in names:
        others = [n for n in names if n != f]
        tot = 0.0
        for k in range(p):
            w = factorial(k) * factorial(p - k - 1) / factorial(p)
            for S in combinations(others, k):
                tot += w * (r2[frozenset(S) | {f}] - r2[frozenset(S)])
        shares[f] = tot
    shares["residual"] = 1.0 - r2[frozenset(names)]
    return shares


def _confounded(a, b) -> bool:
    a, b = np.asarray(a), np.asarray(b)
    fwd = {}
    bwd = {}
    for x, y in zip(a, b):
        if fwd.setdefault(x, y) != y or bwd.setdefault(y, x) != x:
            return False
    return True


def variance_shares(theta, scene, noise, theta_hat, n_perm: int = 500, n_boot: int = 500,
                    seed: int = 0) -> dict:
    y = np.asarray(theta_hat, float)
    labels = {"request": np.asarray(theta), "scene": np.asarray(scene), "noise": np.asarray(noise)}
    n = len(y)
    out = dict(n=int(n), total_variance=float(np.var(y, ddof=1)) if n > 1 else float("nan"),
               confounded=_confounded(labels["scene"], labels["noise"]))
    if n < 4 or np.var(y) == 0:
        out["shares"] = None
        return out

    rng = np.random.default_rng(seed)
    obs = lmg_shares(y, labels)
    out["shares"] = obs

    null_mean, pval = {}, {}
    for f in FACTORS:
        null = np.empty(n_perm)
        for i in range(n_perm):
            perm = dict(labels)
            perm[f] = rng.permutation(labels[f])
            null[i] = lmg_shares(y, perm)[f]
        null_mean[f] = float(null.mean())
        pval[f] = float((1 + np.sum(null >= obs[f])) / (1 + n_perm))
    out["null_mean"] = null_mean
    out["p_value"] = pval
    # Chance correction in the adjusted-R^2 / omega^2 style: a factor with
    # k levels picks up about (k-1)/(n-p) of the UNEXPLAINED variance by
    # chance. (A first version subtracted the shuffled-label null mean, which
    # over-corrects when a factor truly explains most of the variance; see
    # REVISION/LOG.md, step 3.)
    k = {f: len(np.unique(labels[f])) for f in FACTORS}
    p = 1 + sum(k[f] - 1 for f in FACTORS)
    df_resid = max(n - p, 1)
    out["corrected"] = {f: max(0.0, obs[f] - (k[f] - 1) / df_resid * obs["residual"]) for f in FACTORS}

    boots = {f: [] for f in list(FACTORS) + ["residual"]}
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        if len(np.unique(y[idx])) < 2:
            continue
        b = lmg_shares(y[idx], {k: v[idx] for k, v in labels.items()})
        for k in boots:
            boots[k].append(b[k])
    out["ci95"] = {k: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] for k, v in boots.items() if v}
    return out
