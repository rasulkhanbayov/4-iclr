#!/usr/bin/env python3
"""
physweep_metrics.py -- PhysWeep metrics, uncertainty, and mechanism selection.

This module computes every quantity the paper reports. It computes; it never
asserts a fabricated outcome. Running it directly executes a synthetic smoke
test that validates each estimator against closed-form ground truth.

Dependencies: numpy only.

    python3 physweep_metrics.py            # run the smoke test
    python3 physweep_metrics.py --verbose  # smoke test with per-check detail

Definitions here match the main paper section by section:

    PRE(S)  = mean over theta_i in S, over seeds j, of
              |theta_hat_ij - theta_i| / (|theta_i| + delta)
    EG      = PRE(S_out) - PRE(S_in)
    beta    = least-squares slope of theta_hat on theta over S_in
    rho_s   = Spearman rank correlation over the full sweep
    PRI     = 1 - alpha_hat from theta_hat = alpha*theta + (1-alpha)*theta_0
    CBI     = 1 - RSS_clamp / RSS_null  on the out-of-range data

A model-axis pair is labeled "neither" unless one hypothesis achieves a
POSITIVE leave-one-theta-out R^2. That gate is why every adjudicated pair in
the paper is reported as neither: AIC prefers the prior-reversion shape, but
held-out R^2 is negative because the reversion target is seed-conditional
rather than a single global theta_0.

ANONYMITY NOTE: this file contains no author names, institutions, or paths.
Keep it that way; WACV desk-rejects supplementary code that de-anonymizes.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass, field

import numpy as np

DEFAULT_DELTA = 1e-6
DEFAULT_GATE = 0.8          # fit-quality gate rho used throughout the paper
DEFAULT_BOOTSTRAP = 10_000
DEFAULT_SEED = 0


# ---------------------------------------------------------------------------
# Core metrics
# ---------------------------------------------------------------------------

def parameter_recovery_error(theta, theta_hat, delta=DEFAULT_DELTA):
    """Normalized recovery error PRE. Lower is better; 0 is perfect."""
    theta = np.asarray(theta, dtype=float)
    theta_hat = np.asarray(theta_hat, dtype=float)
    if theta.size == 0:
        return float("nan")
    return float(np.mean(np.abs(theta_hat - theta) / (np.abs(theta) + delta)))


def extrapolation_gap(theta_in, hat_in, theta_out, hat_out,
                      delta=DEFAULT_DELTA):
    """EG = PRE(S_out) - PRE(S_in). NaN if either split is empty."""
    pre_in = parameter_recovery_error(theta_in, hat_in, delta)
    pre_out = parameter_recovery_error(theta_out, hat_out, delta)
    return pre_out - pre_in


def faithfulness_slope(theta, theta_hat):
    """Least-squares slope of theta_hat on theta. beta~1 faithful, ~0 ignores.

    Returns NaN when theta has no variation (a single grid point survives the
    gate), which is the honest answer rather than a spurious 0.
    """
    theta = np.asarray(theta, dtype=float)
    theta_hat = np.asarray(theta_hat, dtype=float)
    if theta.size < 2 or np.allclose(theta, theta[0]):
        return float("nan")
    A = np.vstack([theta, np.ones_like(theta)]).T
    slope, _ = np.linalg.lstsq(A, theta_hat, rcond=None)[0]
    return float(slope)


def _rankdata(x):
    """Average-tie ranks, so Spearman is correct on grids with repeats."""
    x = np.asarray(x, dtype=float)
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(x.size, dtype=float)
    ranks[order] = np.arange(1, x.size + 1, dtype=float)
    # average ties
    sx = x[order]
    i = 0
    while i < sx.size:
        j = i
        while j + 1 < sx.size and sx[j + 1] == sx[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = ranks[order[i:j + 1]].mean()
        i = j + 1
    return ranks


def spearman_rho(theta, theta_hat):
    """Spearman rank correlation. NaN if either side is constant."""
    theta = np.asarray(theta, dtype=float)
    theta_hat = np.asarray(theta_hat, dtype=float)
    if theta.size < 3:
        return float("nan")
    a, b = _rankdata(theta), _rankdata(theta_hat)
    if np.std(a) == 0 or np.std(b) == 0:
        return float("nan")
    a = (a - a.mean()) / np.std(a)
    b = (b - b.mean()) / np.std(b)
    return float(np.mean(a * b))


def gate_rate(fit_r2, gate=DEFAULT_GATE):
    """Fraction of clips FAILING the fit-quality gate.

    The paper reports this as a primary result, not a silent exclusion.
    """
    fit_r2 = np.asarray(fit_r2, dtype=float)
    if fit_r2.size == 0:
        return float("nan")
    return float(np.mean(fit_r2 < gate))


def apply_gate(theta, theta_hat, fit_r2, gate=DEFAULT_GATE):
    """Return (theta, theta_hat) restricted to clips clearing the gate."""
    keep = np.asarray(fit_r2, dtype=float) >= gate
    return np.asarray(theta, float)[keep], np.asarray(theta_hat, float)[keep]


# ---------------------------------------------------------------------------
# Uncertainty
# ---------------------------------------------------------------------------

def bootstrap_ci(stat_fn, *arrays, n_boot=DEFAULT_BOOTSTRAP, alpha=0.05,
                 seed=DEFAULT_SEED):
    """Percentile bootstrap CI, resampling (theta_i, seed) pairs jointly.

    Returns (point_estimate, lo, hi). NaN replicates are dropped, which is
    what happens when a resample loses all variation in theta.
    """
    arrays = [np.asarray(a) for a in arrays]
    n = arrays[0].shape[0]
    point = stat_fn(*arrays)
    if n == 0:
        return point, float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    reps = np.empty(n_boot, dtype=float)
    for b in range(n_boot):
        idx = rng.integers(0, n, n)
        reps[b] = stat_fn(*[a[idx] for a in arrays])
    reps = reps[np.isfinite(reps)]
    if reps.size == 0:
        return point, float("nan"), float("nan")
    lo, hi = np.percentile(reps, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(point), float(lo), float(hi)


def paired_bootstrap_pre_difference(theta_in, hat_in, theta_out, hat_out,
                                    n_boot=DEFAULT_BOOTSTRAP,
                                    delta=DEFAULT_DELTA, seed=DEFAULT_SEED):
    """Test PRE(S_out) > PRE(S_in) by paired bootstrap.

    Returns (difference, lo, hi, p_one_sided). The one-sided p is the
    bootstrap fraction of replicates with difference <= 0, i.e. evidence
    AGAINST the hypothesized worse-out-of-range direction. A p near 1.0 means
    the effect went the other way; it does NOT mean "significant".
    """
    theta_in = np.asarray(theta_in, float)
    hat_in = np.asarray(hat_in, float)
    theta_out = np.asarray(theta_out, float)
    hat_out = np.asarray(hat_out, float)
    if theta_in.size == 0 or theta_out.size == 0:
        return (float("nan"),) * 4
    rng = np.random.default_rng(seed)
    obs = extrapolation_gap(theta_in, hat_in, theta_out, hat_out, delta)
    reps = np.empty(n_boot, dtype=float)
    for b in range(n_boot):
        i = rng.integers(0, theta_in.size, theta_in.size)
        o = rng.integers(0, theta_out.size, theta_out.size)
        reps[b] = extrapolation_gap(theta_in[i], hat_in[i],
                                    theta_out[o], hat_out[o], delta)
    reps = reps[np.isfinite(reps)]
    lo, hi = np.percentile(reps, [2.5, 97.5])
    p = float(np.mean(reps <= 0.0))
    return float(obs), float(lo), float(hi), p


def holm_adjust(pvals):
    """Holm step-down adjustment. Use this whenever several pairs are tested.

    The paper runs six paired-bootstrap extrapolation tests on one dataset;
    reporting raw p-values across all six would overstate significance.
    """
    p = np.asarray(pvals, dtype=float)
    m = p.size
    order = np.argsort(p)
    adj = np.empty(m, dtype=float)
    running = 0.0
    for rank, idx in enumerate(order):
        val = (m - rank) * p[idx]
        running = max(running, val)
        adj[idx] = min(1.0, running)
    return adj


# ---------------------------------------------------------------------------
# Failure-form indices and mechanism selection
# ---------------------------------------------------------------------------

def fit_prior_reversion(theta, theta_hat, theta_0=None):
    """Fit theta_hat = alpha*theta + (1-alpha)*theta_0.

    If theta_0 is None it is estimated jointly. Returns (alpha, theta_0, RSS).
    """
    theta = np.asarray(theta, float)
    theta_hat = np.asarray(theta_hat, float)
    if theta.size < 2:
        return float("nan"), float("nan"), float("nan")
    if theta_0 is None:
        # theta_hat = a*theta + b, with b = (1-a)*theta_0
        A = np.vstack([theta, np.ones_like(theta)]).T
        coef, *_ = np.linalg.lstsq(A, theta_hat, rcond=None)
        a, b = float(coef[0]), float(coef[1])
        t0 = b / (1.0 - a) if not math.isclose(a, 1.0, abs_tol=1e-9) else float("nan")
    else:
        # theta_hat - theta_0 = a*(theta - theta_0)
        x = theta - theta_0
        y = theta_hat - theta_0
        denom = float(np.dot(x, x))
        a = float(np.dot(x, y) / denom) if denom > 0 else float("nan")
        t0 = float(theta_0)
    pred = a * theta + (1.0 - a) * (t0 if np.isfinite(t0) else 0.0)
    rss = float(np.sum((theta_hat - pred) ** 2))
    return a, t0, rss


def fit_case_clamping(theta, theta_hat, theta_edge):
    """Fit theta_hat = min(theta, theta_edge). Returns (CBI, RSS_clamp)."""
    theta = np.asarray(theta, float)
    theta_hat = np.asarray(theta_hat, float)
    if theta.size < 2:
        return float("nan"), float("nan")
    pred = np.minimum(theta, theta_edge)
    rss_clamp = float(np.sum((theta_hat - pred) ** 2))
    rss_null = float(np.sum((theta_hat - np.mean(theta_hat)) ** 2))
    cbi = 1.0 - rss_clamp / rss_null if rss_null > 0 else float("nan")
    return cbi, rss_clamp


def _aic(rss, n, k):
    if n <= 0 or rss <= 0:
        return float("nan")
    return n * math.log(rss / n) + 2 * k


def _loo_r2(theta, theta_hat, fitter):
    """Leave-one-theta-out R^2. Negative means worse than the mean."""
    theta = np.asarray(theta, float)
    theta_hat = np.asarray(theta_hat, float)
    uniq = np.unique(theta)
    if uniq.size < 4:              # select_mechanism's own minimum
        return float("nan")
    errs = []
    for t in uniq:
        held = theta == t
        pred = fitter(theta[~held], theta_hat[~held], theta[held])
        if pred is None or not np.all(np.isfinite(pred)):
            return float("nan")
        errs.append(np.sum((theta_hat[held] - pred) ** 2))
    ss_res = float(np.sum(errs))
    ss_tot = float(np.sum((theta_hat - np.mean(theta_hat)) ** 2))
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")


@dataclass
class MechanismResult:
    label: str                      # "prior_reversion" | "case_clamping" | "neither"
    pri: float = float("nan")
    cbi: float = float("nan")
    theta_0: float = float("nan")
    delta_aic: float = float("nan")  # AIC(prior) - AIC(clamp); <0 favors prior
    loo_r2_prior: float = float("nan")
    loo_r2_clamp: float = float("nan")
    n_out: int = 0
    notes: list = field(default_factory=list)


def select_mechanism(theta_out, hat_out, theta_edge, theta_0=None,
                     min_points=4, min_loo_r2=0.1):
    """Adjudicate prior reversion vs case clamping on out-of-range data.

    Labels "neither" unless a hypothesis achieves held-out R^2 above
    min_loo_r2. Reporting AIC preference alone would overstate the result:
    AIC is a within-sample comparison of two shapes and does not certify that
    either shape predicts unseen theta.

    WHY A MARGIN AND NOT A SIGN TEST. An earlier version accepted any
    POSITIVE held-out R^2. That misfires: when theta carries no information
    about theta_hat, the held-out R^2 is centred on zero and its sign is
    noise, so unstructured data are labelled "prior_reversion" roughly half
    the time. The synthetic smoke test reproduces exactly that failure at
    min_loo_r2=0, with pure noise scoring +0.035 and being mislabelled. A
    margin of 0.1 removes it while leaving genuine reversion (held-out R^2
    well above 0.5 in the smoke test) untouched.
    """
    theta_out = np.asarray(theta_out, float)
    hat_out = np.asarray(hat_out, float)
    res = MechanismResult(label="neither", n_out=int(theta_out.size))

    if theta_out.size < min_points:
        res.notes.append(
            f"only {theta_out.size} gated out-of-range points; "
            f"minimum for leave-one-out is {min_points}")
        return res

    alpha, t0, rss_prior = fit_prior_reversion(theta_out, hat_out, theta_0)
    res.pri = float(np.clip(1.0 - alpha, 0.0, 1.0)) if np.isfinite(alpha) else float("nan")
    res.theta_0 = t0
    res.cbi, rss_clamp = fit_case_clamping(theta_out, hat_out, theta_edge)

    k_prior = 2 if theta_0 is None else 1
    res.delta_aic = _aic(rss_prior, theta_out.size, k_prior) - \
        _aic(rss_clamp, theta_out.size, 0)

    def prior_fitter(tr_t, tr_h, te_t):
        a, b, _ = fit_prior_reversion(tr_t, tr_h, theta_0)
        if not np.isfinite(a):
            return None
        base = b if np.isfinite(b) else 0.0
        return a * te_t + (1.0 - a) * base

    def clamp_fitter(tr_t, tr_h, te_t):
        return np.minimum(te_t, theta_edge)

    res.loo_r2_prior = _loo_r2(theta_out, hat_out, prior_fitter)
    res.loo_r2_clamp = _loo_r2(theta_out, hat_out, clamp_fitter)

    best = max((res.loo_r2_prior, "prior_reversion"),
               (res.loo_r2_clamp, "case_clamping"),
               key=lambda z: (-np.inf if not np.isfinite(z[0]) else z[0]))
    if np.isfinite(best[0]) and best[0] > min_loo_r2:
        res.label = best[1]
    else:
        res.notes.append(
            f"neither hypothesis clears the held-out R^2 margin "
            f"({min_loo_r2}); "
            "reported as neither. NOTE: this outcome is NOT self-explaining. "
            "A high PRI with near-zero held-out R^2 is produced BOTH by a "
            "seed-conditional default AND by unstructured noise. Call "
            "seed_determination_index() to tell them apart; PRI alone cannot.")
    return res


# ---------------------------------------------------------------------------
# Seed determination: the statistic that isolates the paper's claimed mechanism
# ---------------------------------------------------------------------------
#
# PRI and leave-one-theta-out R^2 CANNOT distinguish a seed-conditional default
# from unstructured noise: both regimes give PRI ~ 1 and held-out R^2 ~ 0,
# because in both cases theta carries no information about theta_hat. Isolating
# "the seed picks the physics" requires a statistic that conditions on the seed.
# That is what these two functions do, and the smoke test below asserts the
# separation on synthetic data with known ground truth.

def variance_decomposition(theta, seed, theta_hat):
    """Two-way variance share of theta_hat over (grid value, seed).

    Returns (FDI, SDI_raw, residual_share):
        FDI  -- share of Var(theta_hat) attributable to the REQUESTED value.
                ~1 for a faithful generator.
        SDI_raw -- share attributable to the SAMPLING SEED. ~1 when the seed
                picks the physics. Upward-biased in small designs; prefer
                seed_determination_index() for a corrected estimate.
        residual -- everything else (unstructured noise).

    Returns NaN everywhere if theta_hat is constant (0/0) or the design is
    too small, rather than emitting a spurious number.
    """
    theta = np.asarray(theta); seed = np.asarray(seed)
    hat = np.asarray(theta_hat, dtype=float)
    if hat.size < 4 or np.unique(seed).size < 2:
        return (float("nan"),) * 3
    gm = hat.mean()
    ss_tot = float(np.sum((hat - gm) ** 2))
    if ss_tot <= 0:
        return (float("nan"),) * 3
    ss_th = sum(float(np.sum(theta == u)) * (hat[theta == u].mean() - gm) ** 2
                for u in np.unique(theta))
    ss_z = sum(float(np.sum(seed == v)) * (hat[seed == v].mean() - gm) ** 2
               for v in np.unique(seed))
    return (float(ss_th / ss_tot), float(ss_z / ss_tot),
            float(1.0 - (ss_th + ss_z) / ss_tot))


def seed_determination_index(seed, theta_hat):
    """Bias-corrected SDI: one-way random-effects ICC over sampling seeds.

    Estimates sigma_c^2 / (sigma_c^2 + sigma_eps^2), the fraction of the
    recovered-parameter variance the seed accounts for. SDI -> 1 means the
    seed determines the realized physics; SDI -> 0 means it does not.

    Use this rather than the raw share from variance_decomposition(): the raw
    share is strongly upward-biased under the null (about 0.18 where the truth
    is 0.00 at this study's design size), which is exactly where a false
    positive would be most damaging.

    Returns NaN, never a number, when fewer than two seeds are present, when
    theta_hat is constant, or when the design has no within-seed replication.
    """
    seed = np.asarray(seed)
    hat = np.asarray(theta_hat, dtype=float)
    groups = [hat[seed == v] for v in np.unique(seed)]
    k, n = len(groups), hat.size
    if k < 2 or n <= k:
        return float("nan")
    n0 = n / k
    gm = hat.mean()
    ss_b = sum(g.size * (g.mean() - gm) ** 2 for g in groups)
    ss_w = sum(float(np.sum((g - g.mean()) ** 2)) for g in groups)
    if ss_b + ss_w <= 0:
        return float("nan")
    ms_b, ms_w = ss_b / (k - 1), ss_w / (n - k)
    den = ms_b + (n0 - 1) * ms_w
    if den <= 0:
        return float("nan")
    return float(np.clip((ms_b - ms_w) / den, 0.0, 1.0))


def classify_regime(theta, seed, theta_hat, sdi_hi=0.6, fdi_hi=0.6):
    """Label a model-axis pair from the decomposition. Returns a string.

    'faithful'      theta drives the recovered value
    'seed-locked'   the sampling seed drives it
    'unstructured'  neither does; the variance is residual noise
    'undetermined'  the design cannot support the call
    """
    fdi, _, resid = variance_decomposition(theta, seed, theta_hat)
    sdi = seed_determination_index(seed, theta_hat)
    if not np.isfinite(fdi) or not np.isfinite(sdi):
        return "undetermined"
    if fdi >= fdi_hi:
        return "faithful"
    if sdi >= sdi_hi:
        return "seed-locked"
    return "unstructured"

# ---------------------------------------------------------------------------
# Closed-form generators used only by the smoke test
# ---------------------------------------------------------------------------

def projectile_heights(g, t, h0=1.0, v0=0.0):
    return h0 + v0 * t - 0.5 * g * t ** 2


def fit_g_from_heights(t, h):
    """Recover g from a parabola. Inverse of projectile_heights."""
    A = np.vstack([t ** 2, t, np.ones_like(t)]).T
    coef, *_ = np.linalg.lstsq(A, h, rcond=None)
    return -2.0 * float(coef[0])


def fit_r2(y, y_pred):
    ss_res = float(np.sum((y - y_pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")


def bounce_heights(e, h0=1.0, n=5):
    return np.array([h0 * e ** (2 * k) for k in range(n)], dtype=float)


def fit_e_from_bounces(heights):
    ratios = heights[1:] / heights[:-1]
    return float(np.sqrt(np.mean(ratios)))


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

def smoke_test(verbose=False):
    """Validate every estimator against closed-form ground truth.

    This is the check the paper's LLM-use statement refers to. It must pass
    before any fitter is used in an experiment.
    """
    checks, failures = 0, []

    def ok(name, cond, detail=""):
        nonlocal checks
        checks += 1
        if cond:
            if verbose:
                print(f"  PASS  {name}  {detail}")
        else:
            failures.append(f"{name}: {detail}")
            print(f"  FAIL  {name}  {detail}")

    print("PhysWeep smoke test")
    print("-" * 58)

    # 1. Projectile fitter recovers g exactly from noiseless trajectories.
    t = np.linspace(0.0, 1.0, 24)
    for g_true in [1.6, 5.0, 9.8, 15.0, 25.0]:
        g_rec = fit_g_from_heights(t, projectile_heights(g_true, t))
        ok("projectile fitter", abs(g_rec - g_true) < 1e-9,
           f"g={g_true} -> {g_rec:.10f}")

    # 2. Bouncing-ball fitter recovers e.
    for e_true in [0.2, 0.6, 0.9, 0.97]:
        e_rec = fit_e_from_bounces(bounce_heights(e_true))
        ok("restitution fitter", abs(e_rec - e_true) < 1e-9,
           f"e={e_true} -> {e_rec:.10f}")

    # 3. PRE is 0 on perfect recovery and positive otherwise.
    th = np.array([5.0, 7.0, 9.8, 12.0, 15.0])
    ok("PRE zero on exact", parameter_recovery_error(th, th) == 0.0)
    ok("PRE positive on biased",
       parameter_recovery_error(th, th + 1.0) > 0.0)

    # 4. Negative control: a faithful "generator" gives slope 1.
    #    This mirrors the simulator-video control reported in the paper.
    beta = faithfulness_slope(th, th)
    ok("negative control slope", abs(beta - 1.0) < 1e-12, f"beta={beta:.6f}")

    # 5. A seed-locked "generator" that ignores theta gives slope 0.
    beta0 = faithfulness_slope(th, np.full_like(th, 11.4))
    ok("seed-locked slope", abs(beta0) < 1e-12, f"beta={beta0:.6f}")

    # 6. Spearman is 1 for order-preserving, -1 for reversed.
    ok("spearman monotone", abs(spearman_rho(th, 2 * th) - 1.0) < 1e-9)
    ok("spearman reversed", abs(spearman_rho(th, -th) + 1.0) < 1e-9)

    # 7. Gate rate counts FAILURES, not survivors.
    r2 = np.array([0.99, 0.95, 0.5, 0.1, 0.7])
    ok("gate rate", abs(gate_rate(r2) - 0.6) < 1e-12, f"{gate_rate(r2):.2f}")

    # 8. select_mechanism RECOVERS prior reversion when it is really there.
    #    Without this, "neither" everywhere would be uninformative: we must
    #    show the selector can fire.
    t_out = np.repeat([20.0, 25.0, 30.0, 35.0, 40.0], 5)
    rng = np.random.default_rng(7)
    hat_pr = 0.2 * t_out + 0.8 * 9.81 + rng.normal(0, 0.05, t_out.size)
    r_pr = select_mechanism(t_out, hat_pr, theta_edge=15.0, theta_0=9.81)
    ok("selector detects prior reversion", r_pr.label == "prior_reversion",
       f"label={r_pr.label} PRI={r_pr.pri:.3f} looR2={r_pr.loo_r2_prior:.3f}")
    ok("PRI high under reversion", r_pr.pri > 0.7, f"PRI={r_pr.pri:.3f}")

    # 9. select_mechanism RECOVERS clamping when it is really there.
    #    NOTE: this requires a TWO-SIDED out-of-range grid, i.e. one that
    #    straddles the in-range band, which is what the paper's grids are
    #    (projectile S_out = {1.6, 3, 20, 25} around S_in = 5..15). See
    #    check 9b for why a one-sided grid cannot identify clamping at all.
    t_two = np.repeat([1.6, 3.0, 20.0, 25.0, 30.0], 5)
    hat_cl = np.minimum(t_two, 15.0) + rng.normal(0, 0.05, t_two.size)
    r_cl = select_mechanism(t_two, hat_cl, theta_edge=15.0, theta_0=9.81)
    ok("selector detects clamping (two-sided grid)",
       r_cl.label == "case_clamping",
       f"label={r_cl.label} CBI={r_cl.cbi:.3f}")

    # 9b. Documented limitation, asserted so it cannot regress silently:
    #     on a ONE-SIDED out-of-range grid (all theta beyond the edge), the
    #     clamp prediction min(theta, edge) is constant, so it is
    #     indistinguishable from the null mean model and CBI is not
    #     identifiable. Any axis whose S_out lies entirely on one side of
    #     S_in therefore cannot adjudicate clamping, regardless of sample
    #     size, and select_mechanism correctly returns "neither".
    t_one = np.repeat([20.0, 25.0, 30.0, 35.0, 40.0], 5)
    hat_one = np.minimum(t_one, 15.0) + rng.normal(0, 0.05, t_one.size)
    r_one = select_mechanism(t_one, hat_one, theta_edge=15.0, theta_0=9.81)
    ok("clamping unidentifiable on one-sided grid (known limitation)",
       r_one.label == "neither" and abs(r_one.cbi) < 0.5,
       f"label={r_one.label} CBI={r_one.cbi:.3f}")

    # 10. select_mechanism returns "neither" on a SEED-CONDITIONAL default,
    #     which is the paper's actual finding. Two seeds, two fixed values,
    #     no dependence on theta.
    hat_seed = np.where(np.arange(t_out.size) % 2 == 0, 11.4, 7.1)
    hat_seed = hat_seed + rng.normal(0, 0.03, t_out.size)
    r_sd = select_mechanism(t_out, hat_seed, theta_edge=15.0, theta_0=9.81)
    ok("selector returns neither on seed-conditional default",
       r_sd.label == "neither",
       f"label={r_sd.label} PRI={r_sd.pri:.3f} "
       f"looR2_prior={r_sd.loo_r2_prior:.3f}")

    # 11. Too few points -> neither, with a reason, not a silent number.
    r_few = select_mechanism([20.0, 25.0], [9.8, 9.8], theta_edge=15.0)
    ok("selector refuses below minimum", r_few.label == "neither" and r_few.notes)

    # 11b. THE MECHANISM-ISOLATION CHECKS. PRI and held-out R^2 give the same
    #      answer for seed-locking and for pure noise, so they cannot isolate
    #      the paper's claimed mechanism. SDI must separate them, and must NOT
    #      fire on a faithful generator, on noise, or on a single global
    #      default. Each case below has known ground truth.
    grid = np.array([5.0, 7.0, 9.8, 12.0, 15.0])
    nz = 5
    th_g = np.repeat(grid, nz)
    zz_g = np.tile(np.arange(nz), grid.size)
    rg = np.random.default_rng(11)

    faithful = th_g + rg.normal(0, 0.05, th_g.size)
    seedlock = np.tile(rg.normal(9.8, 2.0, nz), grid.size) + rg.normal(0, 0.05, th_g.size)
    purenoise = 9.8 + rg.normal(0, 2.0, th_g.size)
    onedefault = np.full(th_g.size, 9.81) + rg.normal(0, 0.05, th_g.size)

    ok("SDI ~ 0 on a faithful generator",
       seed_determination_index(zz_g, faithful) < 0.2,
       f"SDI={seed_determination_index(zz_g, faithful):.3f}")
    ok("SDI ~ 1 on a seed-locked generator",
       seed_determination_index(zz_g, seedlock) > 0.8,
       f"SDI={seed_determination_index(zz_g, seedlock):.3f}")
    ok("SDI stays low on pure noise (no false positive)",
       seed_determination_index(zz_g, purenoise) < 0.3,
       f"SDI={seed_determination_index(zz_g, purenoise):.3f}")
    ok("SDI stays low on a single global default",
       seed_determination_index(zz_g, onedefault) < 0.3,
       f"SDI={seed_determination_index(zz_g, onedefault):.3f}")
    ok("classify_regime labels faithful",
       classify_regime(th_g, zz_g, faithful) == "faithful")
    ok("classify_regime labels seed-locked",
       classify_regime(th_g, zz_g, seedlock) == "seed-locked")
    ok("classify_regime labels unstructured",
       classify_regime(th_g, zz_g, purenoise) == "unstructured")

    # 11c. The corollary the paper now states: PRI and held-out R^2 are the
    #      SAME for seed-locking and for noise. Asserted so the claim in the
    #      paper cannot silently become false.
    r_lock = select_mechanism(th_g, seedlock, theta_edge=15.0, theta_0=9.81)
    r_noise = select_mechanism(th_g, purenoise, theta_edge=15.0, theta_0=9.81)
    ok("PRI/LOO cannot separate seed-locking from noise (paper's corollary)",
       r_lock.label == "neither" and r_noise.label == "neither"
       and r_lock.pri > 0.7 and r_noise.pri > 0.7,
       f"lock PRI={r_lock.pri:.2f}/{r_lock.label}, "
       f"noise PRI={r_noise.pri:.2f}/{r_noise.label}, "
       f"SDI {seed_determination_index(zz_g, seedlock):.2f} vs "
       f"{seed_determination_index(zz_g, purenoise):.2f} separates them")

    # 11e. The margin matters: with a bare sign test the SAME noise sample is
    #      mislabelled as prior reversion. Asserted so the margin cannot be
    #      removed without a test failing.
    bad = select_mechanism(th_g, purenoise, theta_edge=15.0, theta_0=9.81,
                           min_loo_r2=0.0)
    ok("sign-test rule mislabels noise; margin rule does not",
       bad.label == "prior_reversion" and r_noise.label == "neither",
       f"margin=0 -> {bad.label}; margin=0.1 -> {r_noise.label}")

    # 11d. Degenerate designs must refuse, not guess.
    ok("SDI refuses with one seed",
       not np.isfinite(seed_determination_index(np.zeros(9), np.arange(9.0)))) 
    ok("SDI refuses on constant theta_hat",
       not np.isfinite(seed_determination_index(zz_g, np.full(th_g.size, 7.0))))
    ok("decomposition refuses on constant theta_hat",
       not np.isfinite(variance_decomposition(th_g, zz_g, np.full(th_g.size, 7.0))[0]))

    # 12. Bootstrap CI covers the truth for a faithful estimator.
    point, lo, hi = bootstrap_ci(faithfulness_slope, th, th, n_boot=2000)
    ok("bootstrap covers slope 1", lo <= 1.0 <= hi,
       f"[{lo:.4f},{hi:.4f}]")

    # 13. Paired bootstrap one-sided p behaves in BOTH directions.
    worse = paired_bootstrap_pre_difference(th, th, th, th * 3.0, n_boot=2000)
    ok("paired bootstrap detects worse-out", worse[0] > 0 and worse[3] < 0.05,
       f"diff={worse[0]:.3f} p={worse[3]:.4f}")
    better = paired_bootstrap_pre_difference(th, th * 3.0, th, th, n_boot=2000)
    ok("paired bootstrap p~1 when effect reverses",
       better[0] < 0 and better[3] > 0.95,
       f"diff={better[0]:.3f} p={better[3]:.4f}")

    # 14. Holm adjustment is monotone and never shrinks a p-value.
    raw = [0.0055, 0.04, 0.2, 0.5, 0.9, 1.0]
    adj = holm_adjust(raw)
    ok("holm never decreases p", bool(np.all(adj >= np.array(raw) - 1e-12)),
       f"{np.round(adj, 4).tolist()}")
    ok("holm keeps smallest significant", adj[0] < 0.05, f"adj[0]={adj[0]:.4f}")

    # 15. Fit R^2 sanity, since the gate depends on it.
    ok("R2 is 1 on exact fit",
       abs(fit_r2(np.array([1.0, 2.0, 3.0]), np.array([1.0, 2.0, 3.0])) - 1.0) < 1e-12)

    print("-" * 58)
    if failures:
        print(f"FAILED {len(failures)} of {checks} checks:")
        for f in failures:
            print("  -", f)
        return 1
    print(f"All {checks} checks passed.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    raise SystemExit(smoke_test(verbose=args.verbose))
