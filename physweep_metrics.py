#!/usr/bin/env python3
"""
physweep_metrics.py
===================
Reference implementation of the PhysWeep metrics for measuring parameter
faithfulness and extrapolation in pretrained image-to-video generators.

This module COMPUTES quantities from arrays of (conditioned theta, recovered
theta-hat) pairs. It never hard-codes or asserts any model result. The smoke
test at the bottom builds a *synthetic* generator with known behavior so you
can confirm the metric code itself behaves correctly before you ever run a
real model. Confirming the metrics on synthetic data is not a scientific
result about any video model.

Dependencies: numpy only (matplotlib optional, used only if you call plot_*).

Metrics implemented (see paper Section 4):
  - PRE(S)              : normalized Parameter Recovery Error on a set S
  - faithfulness_slope  : OLS slope of theta_hat on theta (ideal = 1)
  - extrapolation_gap   : PRE(out) - PRE(in)
  - prior_reversion_index (PRI) : 1 - alpha from theta_hat = a*theta + (1-a)*theta0
  - bootstrap_ci        : 95% CI for any of the above
  - plausibility_gap    : pairs mean plausibility with PRE on the out-of-range set

Physics fitters (closed form, label-free) for recovering theta from a tracked
observable:
  - fit_gravity_from_trajectory   : parabola curvature -> g
  - fit_omega_from_crossings      : zero-crossing period -> angular frequency
  - fit_restitution_from_bounces  : successive bounce-height ratio -> e
"""

from __future__ import annotations
import numpy as np

EPS = 1e-8


# ---------------------------------------------------------------------------
# Core metrics
# ---------------------------------------------------------------------------
def pre(theta: np.ndarray, theta_hat: np.ndarray, delta: float = 1.0) -> float:
    """Normalized Parameter Recovery Error. Lower is better; 0 is perfect.

    theta, theta_hat: 1D arrays of equal length (conditioned vs recovered).
    delta: stabilizer in the denominator (paper Eq. 1).
    """
    theta = np.asarray(theta, float)
    theta_hat = np.asarray(theta_hat, float)
    return float(np.mean(np.abs(theta_hat - theta) / (np.abs(theta) + delta)))


def faithfulness_slope(theta: np.ndarray, theta_hat: np.ndarray) -> float:
    """OLS slope of theta_hat regressed on theta. Faithful model -> ~1,
    a model ignoring the conditioning -> ~0."""
    theta = np.asarray(theta, float)
    theta_hat = np.asarray(theta_hat, float)
    A = np.vstack([theta, np.ones_like(theta)]).T
    slope, _ = np.linalg.lstsq(A, theta_hat, rcond=None)[0]
    return float(slope)


def extrapolation_gap(theta_in, hat_in, theta_out, hat_out, delta: float = 1.0) -> float:
    """EG = PRE(out-of-range) - PRE(in-range). >0 means worse extrapolation."""
    return pre(theta_out, hat_out, delta) - pre(theta_in, hat_in, delta)


def prior_reversion_index(theta, theta_hat, theta0=None):
    """PRI = 1 - alpha from the shrinkage model (H1)
        theta_hat = alpha*theta + (1-alpha)*theta0 + noise   (paper Eq. 5)

    If theta0 is given (physically typical default), alpha is the slope of
    (theta_hat - theta0) on (theta - theta0). If theta0 is None it is estimated
    jointly by ordinary least squares (intercept = (1-alpha)*theta0).

    Returns (PRI, alpha, theta0_used). PRI is clipped to [0, 1].
    """
    theta = np.asarray(theta, float)
    theta_hat = np.asarray(theta_hat, float)
    if theta0 is None:
        A = np.vstack([theta, np.ones_like(theta)]).T
        alpha, intercept = np.linalg.lstsq(A, theta_hat, rcond=None)[0]
        theta0_used = intercept / (1.0 - alpha) if abs(1.0 - alpha) > EPS else np.nan
    else:
        x = theta - theta0
        y = theta_hat - theta0
        denom = float(np.dot(x, x))
        alpha = float(np.dot(x, y) / denom) if denom > EPS else 0.0
        theta0_used = float(theta0)
    pri = float(np.clip(1.0 - alpha, 0.0, 1.0))
    return pri, float(alpha), theta0_used


def case_based_index(theta, theta_hat, theta_edge):
    """CBI for the clamp model (H2): theta_hat = min(theta, theta_edge).
    CBI = 1 - RSS_H2 / RSS_null, the variance explained by clamping at the
    range edge. Returns CBI clipped to [0, 1]."""
    theta = np.asarray(theta, float)
    theta_hat = np.asarray(theta_hat, float)
    pred = np.minimum(theta, theta_edge)
    rss = float(np.sum((theta_hat - pred) ** 2))
    rss_null = float(np.sum((theta_hat - np.mean(theta_hat)) ** 2)) + EPS
    return float(np.clip(1.0 - rss / rss_null, 0.0, 1.0))


def spearman_rho(theta, theta_hat):
    """Spearman rank correlation (monotonicity), numpy-only. Robust to a
    nonlinear-but-order-preserving response."""
    theta = np.asarray(theta, float)
    theta_hat = np.asarray(theta_hat, float)
    def _rank(a):
        order = np.argsort(a, kind="mergesort")
        ranks = np.empty_like(order, float)
        ranks[order] = np.arange(len(a), dtype=float)
        # average ties
        _, inv, counts = np.unique(a, return_inverse=True, return_counts=True)
        sums = np.zeros(len(counts)); np.add.at(sums, inv, ranks)
        avg = sums / counts
        return avg[inv]
    ra, rb = _rank(theta), _rank(theta_hat)
    ra -= ra.mean(); rb -= rb.mean()
    denom = np.sqrt(np.sum(ra ** 2) * np.sum(rb ** 2)) + EPS
    return float(np.sum(ra * rb) / denom)


def _aic(rss, n, k):
    return n * np.log(rss / n + EPS) + 2 * k


def select_mechanism(theta_out, hat_out, theta0=None, theta_edge=None):
    """Adjudicate H1 (shrinkage) vs H2 (clamp) on out-of-range data using AIC
    and leave-one-theta-out R^2. Returns a dict with PRI, CBI, the AIC values,
    the LOO-R^2 values, and the selected label ('H1', 'H2', or 'neither')."""
    theta_out = np.asarray(theta_out, float)
    hat_out = np.asarray(hat_out, float)
    n = len(theta_out)
    if theta_edge is None:
        theta_edge = float(np.min(theta_out))  # crude default; pass the true edge
    pri, alpha, th0 = prior_reversion_index(theta_out, hat_out, theta0)
    cbi = case_based_index(theta_out, hat_out, theta_edge)
    th0_eff = th0 if theta0 is None else theta0
    pred_h1 = alpha * theta_out + (1 - alpha) * th0_eff
    pred_h2 = np.minimum(theta_out, theta_edge)
    rss_h1 = float(np.sum((hat_out - pred_h1) ** 2)) + EPS
    rss_h2 = float(np.sum((hat_out - pred_h2) ** 2)) + EPS
    aic_h1, aic_h2 = _aic(rss_h1, n, 2), _aic(rss_h2, n, 1)
    # leave-one-out R^2 (refit H1 each time; H2 has no free params if edge fixed)
    def _loo_r2_h1():
        if n < 4:
            return float("nan")
        errs = []
        for i in range(n):
            mask = np.arange(n) != i
            a, b = theta_out[mask], hat_out[mask]
            A = np.vstack([a, np.ones_like(a)]).T
            sl, ic = np.linalg.lstsq(A, b, rcond=None)[0]
            errs.append((hat_out[i] - (sl * theta_out[i] + ic)) ** 2)
        ss_res = float(np.sum(errs))
        ss_tot = float(np.sum((hat_out - hat_out.mean()) ** 2)) + EPS
        return 1.0 - ss_res / ss_tot
    loo_h1 = _loo_r2_h1()
    if min(rss_h1, rss_h2) / (np.sum((hat_out - hat_out.mean()) ** 2) + EPS) > 0.5:
        selected = "neither"
    else:
        selected = "H1" if aic_h1 <= aic_h2 else "H2"
    return {"PRI": pri, "CBI": cbi, "alpha": alpha, "theta0": th0_eff,
            "theta_edge": theta_edge, "AIC_H1": aic_h1, "AIC_H2": aic_h2,
            "dAIC": aic_h1 - aic_h2, "LOO_R2_H1": loo_h1, "selected": selected}


def within_condition_dispersion(theta_grid, hat_by_condition):
    """Mean within-condition std of theta_hat across seeds (the noise axis,
    separate from bias). hat_by_condition: list of arrays, one per theta."""
    stds = [float(np.std(np.asarray(h, float))) for h in hat_by_condition if len(h) > 1]
    return float(np.mean(stds)) if stds else float("nan")


def plausibility_gap(theta_out, hat_out, plausibility_out, delta: float = 1.0):
    """Return (mean_plausibility, PRE_out). The headline contrast predicts a
    high mean plausibility paired with a high PRE on the out-of-range set."""
    return float(np.mean(plausibility_out)), pre(theta_out, hat_out, delta)


# ---------------------------------------------------------------------------
# Uncertainty: paired bootstrap over (theta, seed) units
# ---------------------------------------------------------------------------
def bootstrap_ci(stat_fn, *arrays, n_boot: int = 2000, alpha: float = 0.05,
                 rng: np.random.Generator | None = None):
    """Generic percentile bootstrap CI. stat_fn takes the resampled arrays
    (in the same order) and returns a scalar. Resampling is paired across all
    arrays (same indices), which is the correct unit when each row is one
    (theta_i, seed_j) measurement."""
    if rng is None:
        rng = np.random.default_rng(0)
    arrays = [np.asarray(a) for a in arrays]
    n = len(arrays[0])
    stats = np.empty(n_boot)
    for b in range(n_boot):
        idx = rng.integers(0, n, n)
        stats[b] = stat_fn(*[a[idx] for a in arrays])
    lo, hi = np.percentile(stats, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(stat_fn(*arrays)), float(lo), float(hi)


def paired_bootstrap_pre_difference(theta_in, hat_in, theta_out, hat_out,
                                    delta=1.0, n_boot=2000, rng=None):
    """Test PRE(out) > PRE(in). Returns (point_diff, ci_lo, ci_hi, p_one_sided)
    where p is the bootstrap fraction with diff <= 0."""
    if rng is None:
        rng = np.random.default_rng(1)
    theta_in, hat_in = np.asarray(theta_in), np.asarray(hat_in)
    theta_out, hat_out = np.asarray(theta_out), np.asarray(hat_out)
    n_in, n_out = len(theta_in), len(theta_out)
    diffs = np.empty(n_boot)
    for b in range(n_boot):
        i_in = rng.integers(0, n_in, n_in)
        i_out = rng.integers(0, n_out, n_out)
        diffs[b] = (pre(theta_out[i_out], hat_out[i_out], delta)
                    - pre(theta_in[i_in], hat_in[i_in], delta))
    point = pre(theta_out, hat_out, delta) - pre(theta_in, hat_in, delta)
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    p = float(np.mean(diffs <= 0.0))
    return point, float(lo), float(hi), p


# ---------------------------------------------------------------------------
# Physics fitters: recover theta from a tracked observable (label-free)
# Each returns (theta_hat, r2) where r2 gates non-physical generations.
# ---------------------------------------------------------------------------
def _r2(y, y_fit):
    ss_res = float(np.sum((y - y_fit) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2)) + EPS
    return 1.0 - ss_res / ss_tot


def fit_gravity_from_trajectory(t, y):
    """Vertical position y(t) = y0 + v0 t - 0.5 g t^2. Returns (g_hat, r2).
    Curvature of the parabola gives g (sign convention: y up, g>0)."""
    t = np.asarray(t, float); y = np.asarray(y, float)
    A = np.vstack([np.ones_like(t), t, t ** 2]).T
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    y_fit = A @ coef
    g_hat = -2.0 * coef[2]
    return float(g_hat), _r2(y, y_fit)


def fit_omega_from_crossings(t, x):
    """Angular frequency from mean spacing of upward zero crossings of a
    (roughly) oscillatory signal x(t). Returns (omega_hat, r2_of_sine_fit)."""
    t = np.asarray(t, float); x = np.asarray(x, float)
    xc = x - np.mean(x)
    crossings = []
    for i in range(1, len(xc)):
        if xc[i - 1] <= 0 < xc[i]:
            # linear interpolation of crossing time
            frac = -xc[i - 1] / (xc[i] - xc[i - 1] + EPS)
            crossings.append(t[i - 1] + frac * (t[i] - t[i - 1]))
    if len(crossings) < 2:
        return float("nan"), 0.0
    period = float(np.mean(np.diff(crossings)))
    omega = 2.0 * np.pi / (period + EPS)
    # goodness of fit against a fitted UNDAMPED sine at this omega. NOTE: for a
    # genuinely damped oscillator (paper's pendulum system) this R^2 degrades
    # with real decay even when omega itself is recovered accurately -- it is
    # a fit-quality diagnostic for this function's own undamped model, not a
    # general non-physical-generation gate. Use damped_sine_r2() below (with a
    # zeta estimate) as the fit-quality gate for damped-oscillator systems.
    A = np.vstack([np.sin(omega * t), np.cos(omega * t), np.ones_like(t)]).T
    coef, *_ = np.linalg.lstsq(A, x, rcond=None)
    return float(omega), _r2(x, A @ coef)


def damped_sine_r2(t, x, omega, zeta):
    """Fit-quality R^2 against a DAMPED sine model exp(-zeta*omega*t)*(a*sin+b*cos)
    + const, for use as the fit-quality gate on genuinely damped oscillators
    (e.g. the pendulum system) where fit_omega_from_crossings's own R^2
    (computed against an undamped sine) would under-report quality purely
    because of expected, real decay. omega and zeta are taken as already
    estimated (e.g. from fit_omega_from_crossings and fit_zeta_from_envelope)."""
    t = np.asarray(t, float); x = np.asarray(x, float)
    envelope = np.exp(-zeta * omega * t)
    A = np.vstack([envelope * np.sin(omega * t), envelope * np.cos(omega * t),
                  np.ones_like(t)]).T
    coef, *_ = np.linalg.lstsq(A, x, rcond=None)
    return _r2(x, A @ coef)


def fit_restitution_from_bounces(peak_heights):
    """Coefficient of restitution from successive bounce peak heights:
    e = sqrt(h_{k+1} / h_k), averaged. Returns (e_hat, r2_of_geometric_decay)."""
    h = np.asarray(peak_heights, float)
    if len(h) < 2 or np.any(h <= 0):
        return float("nan"), 0.0
    ratios = h[1:] / h[:-1]
    e = float(np.mean(np.sqrt(np.clip(ratios, 0, None))))
    k = np.arange(len(h))
    log_fit = np.polyfit(k, np.log(h + EPS), 1)
    h_fit = np.exp(np.polyval(log_fit, k))
    return e, _r2(h, h_fit)


def fit_zeta_from_envelope(t, x, omega):
    """Damping ratio from the exponential decay of the oscillation envelope:
    x(t) ~ A * exp(-zeta*omega*t) * cos(omega_d*t + phi). The envelope is
    traced through the local peak magnitudes of x (both signs), decay rate
    lambda = zeta*omega is fit by a log-linear regression on those peaks, so
    zeta = lambda / omega. Requires the driving omega (e.g. from
    fit_omega_from_crossings on the same signal) since decay rate alone does
    not separate zeta from omega. Returns (zeta_hat, r2_of_log_linear_fit)."""
    t = np.asarray(t, float); x = np.asarray(x, float)
    xc = x - np.mean(x)
    envelope_t, envelope_v = [], []
    for i in range(1, len(xc) - 1):
        if abs(xc[i]) > abs(xc[i - 1]) and abs(xc[i]) >= abs(xc[i + 1]):
            envelope_t.append(t[i])
            envelope_v.append(abs(xc[i]))
    if len(envelope_v) < 2 or omega <= 0:
        return float("nan"), 0.0
    envelope_t = np.asarray(envelope_t); envelope_v = np.asarray(envelope_v)
    log_fit = np.polyfit(envelope_t, np.log(envelope_v + EPS), 1)
    decay_rate = -float(log_fit[0])          # lambda = zeta*omega, envelope decays as exp(-lambda*t)
    zeta = float(np.clip(decay_rate / omega, 0.0, 1.0))
    v_fit = np.exp(np.polyval(log_fit, envelope_t))
    return zeta, _r2(envelope_v, v_fit)


def fit_friction_from_slide(t, s):
    """Friction coefficient mu from acceleration along an incline of known
    angle: s(t) = s0 + v0*t + 0.5*a*t^2 (distance along the slope), then
    mu = (g*sin(angle) - a) / (g*cos(angle)). Returns (a_hat, r2); convert to
    mu with `friction_from_acceleration` since g and angle are experiment
    constants, not part of the trajectory fit itself."""
    t = np.asarray(t, float); s = np.asarray(s, float)
    A = np.vstack([np.ones_like(t), t, t ** 2]).T
    coef, *_ = np.linalg.lstsq(A, s, rcond=None)
    s_fit = A @ coef
    a_hat = 2.0 * coef[2]
    return float(a_hat), _r2(s, s_fit)


def friction_from_acceleration(a_hat, incline_rad, g=9.81):
    """mu_hat from a measured along-slope acceleration a_hat (m/s^2), a known
    incline angle, and standard gravity. See fit_friction_from_slide."""
    denom = g * np.cos(incline_rad)
    if abs(denom) < EPS:
        return float("nan")
    return float((g * np.sin(incline_rad) - a_hat) / denom)


# ---------------------------------------------------------------------------
# Synthetic smoke test: exercises the METRICS, not any real model.
# ---------------------------------------------------------------------------
def _synthetic_generator(theta, theta0=9.81, range_edge=15.0, rng=None):
    """A toy stand-in for a generator that is faithful inside [.., range_edge]
    and reverts toward a default theta0 outside it. Used ONLY to check the
    metric code. Returns a recovered theta_hat with a little noise."""
    if rng is None:
        rng = np.random.default_rng(42)
    theta = np.asarray(theta, float)
    hat = np.where(theta <= range_edge,
                   theta,                                  # faithful in-range
                   0.5 * theta + 0.5 * theta0)             # shrink toward prior
    hat = hat + rng.normal(0, 0.2, size=theta.shape)
    return hat


def run_smoke_test():
    print("=" * 64)
    print("PhysWeep metrics smoke test (synthetic generator, NOT a real model)")
    print("=" * 64)
    rng = np.random.default_rng(0)

    # --- 1. physics fitters recover known parameters from clean trajectories
    t = np.linspace(0, 1.0, 30)
    g_true = 9.81
    y = 2.0 + 3.0 * t - 0.5 * g_true * t ** 2
    g_hat, r2g = fit_gravity_from_trajectory(t, y)
    print(f"[fitter] gravity: true={g_true:.3f}  recovered={g_hat:.3f}  R2={r2g:.4f}")

    om_true = 2 * np.pi * 1.5
    x = np.sin(om_true * t)
    om_hat, r2o = fit_omega_from_crossings(t, x)
    print(f"[fitter] omega:   true={om_true:.3f}  recovered={om_hat:.3f}  R2={r2o:.4f}")

    e_true = 0.8
    peaks = [1.0 * (e_true ** 2) ** k for k in range(5)]
    e_hat, r2e = fit_restitution_from_bounces(peaks)
    print(f"[fitter] restit.: true={e_true:.3f}  recovered={e_hat:.3f}  R2={r2e:.4f}")

    # --- 2. metric behavior on the synthetic faithful-then-reverting generator
    theta_in = np.repeat(np.linspace(5, 15, 6), 5)        # in-range sweep, 5 seeds
    theta_out = np.repeat(np.linspace(18, 30, 4), 5)      # out-of-range sweep
    hat_in = _synthetic_generator(theta_in, rng=rng)
    hat_out = _synthetic_generator(theta_out, rng=rng)

    slope = faithfulness_slope(theta_in, hat_in)
    pre_in = pre(theta_in, hat_in)
    pre_out = pre(theta_out, hat_out)
    eg = extrapolation_gap(theta_in, hat_in, theta_out, hat_out)
    pri, alpha, th0 = prior_reversion_index(
        np.concatenate([theta_in, theta_out]),
        np.concatenate([hat_in, hat_out]))
    rho = spearman_rho(np.concatenate([theta_in, theta_out]),
                       np.concatenate([hat_in, hat_out]))

    print(f"\n[metric] in-range slope beta      = {slope:.3f}  (expect ~1)")
    print(f"[metric] Spearman rho (full)      = {rho:.3f}  (expect high, monotone)")
    print(f"[metric] PRE(in)                  = {pre_in:.4f} (expect small)")
    print(f"[metric] PRE(out)                 = {pre_out:.4f} (expect > PRE(in))")
    print(f"[metric] Extrapolation Gap EG     = {eg:.4f} (expect > 0)")
    print(f"[metric] Prior-Reversion Index    = {pri:.3f} (alpha={alpha:.3f}, "
          f"theta0_est={th0:.2f})")

    # --- 2b. adjudicate H1 (shrinkage) vs H2 (clamp) on the synthetic data,
    # which was generated as H1 (shrinkage), so H1 should win.
    sel = select_mechanism(theta_out, hat_out, theta0=9.81, theta_edge=15.0)
    print(f"\n[adjud] CBI (H2 clamp)            = {sel['CBI']:.3f}")
    print(f"[adjud] dAIC (H1-H2)              = {sel['dAIC']:.2f} "
          f"(<0 favors H1)")
    print(f"[adjud] selected mechanism        = {sel['selected']}  "
          f"(synthetic truth = H1)")

    # within-condition dispersion across seeds
    grid = np.linspace(5, 15, 6)
    hat_by_cond = [_synthetic_generator(np.full(8, t), rng=np.random.default_rng(i))
                   for i, t in enumerate(grid)]
    disp = within_condition_dispersion(grid, hat_by_cond)
    print(f"[noise] mean within-condition std = {disp:.3f}")

    # --- 3. bootstrap CI and paired difference test
    point, lo, hi = bootstrap_ci(lambda a, b: faithfulness_slope(a, b),
                                 theta_in, hat_in, n_boot=1000)
    print(f"\n[boot]  slope 95% CI              = {point:.3f} [{lo:.3f}, {hi:.3f}]")
    d, dlo, dhi, p = paired_bootstrap_pre_difference(
        theta_in, hat_in, theta_out, hat_out, n_boot=1000)
    print(f"[boot]  PRE(out)-PRE(in)          = {d:.4f} [{dlo:.4f}, {dhi:.4f}], "
          f"one-sided p={p:.3f}")

    print("\nAll quantities above were COMPUTED from synthetic inputs to verify "
          "the metric code. They say nothing about any real video model.")
    print("=" * 64)


if __name__ == "__main__":
    run_smoke_test()
