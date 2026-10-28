#!/usr/bin/env python3
"""
experiments/e7_mechanism_adjudication.py
==========================================
E7 — FAILURE-MECHANISM ADJUDICATION (paper Section "Experimental Protocol").

Adjudicates H1 (global prior reversion to a fixed default theta0) vs H2
(case-based clamp to the nearest in-range edge) on out-of-range data, using
physweep_metrics.select_mechanism() (AIC + leave-one-out R^2), exactly per
the paper's method.

Motivation: E0/E4 found that CogVideoX's IN-RANGE recovered values cluster
tightly by seed, essentially independent of the true conditioned parameter
-- reproduced in 4 systems (projectile, spring-mass, bouncing ball, inclined
slide). That is suggestive of H1 but says nothing about out-of-range
behavior, which is what H1 actually claims (Section~\ref{sec:problem}) and
what this experiment tests. Reuses E0's projectile data for CogVideoX,
which already includes 3 out-of-range g values (1.6, 20, 25) x 5 seeds --
no new GPU time needed.

Usage: python3 experiments/e7_mechanism_adjudication.py
Writes results/e7_mechanism_adjudication.json
"""
from __future__ import annotations
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from physweep_metrics import select_mechanism, pre, bootstrap_ci, paired_bootstrap_pre_difference

RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
FIT_R2_GATE = 0.8

# The physically typical / "everyday" gravity value the paper's H1 hypothesis
# would predict reversion toward (Earth g), independent of what our fitters
# happen to output. We ALSO let select_mechanism estimate theta0 jointly
# (theta0=None path) so we're not assuming the conclusion.
EARTH_G = 9.81


def load_projectile(fname):
    path = os.path.join(RESULTS_DIR, fname)
    with open(path) as f:
        d = json.load(f)
    return d["rows"]


def analyze(rows, model_name):
    gated = [r for r in rows if r["r2"] is not None and r["r2"] >= FIT_R2_GATE
            and r["g_hat"] is not None]
    theta_out = np.array([r["g_true"] for r in gated if r["split"] == "out"])
    hat_out = np.array([r["g_hat"] for r in gated if r["split"] == "out"])
    theta_in = np.array([r["g_true"] for r in gated if r["split"] == "in"])
    hat_in = np.array([r["g_hat"] for r in gated if r["split"] == "in"])

    print(f"\n=== {model_name}: projectile out-of-range data ===")
    print(f"n_gated_out={len(theta_out)}, n_gated_in={len(theta_in)}")
    if len(theta_out) < 4:
        print("NOT ENOUGH gated out-of-range points for mechanism adjudication.")
        return {"n_gated_out": len(theta_out), "n_gated_in": len(theta_in),
               "status": "insufficient_data"}

    print(f"theta_out: {theta_out}")
    print(f"hat_out:   {np.round(hat_out, 3)}")

    # theta_edge = the in-range grid's max (g=15), the natural "edge of experience"
    theta_edge = 15.0
    result_theta0_free = select_mechanism(theta_out, hat_out, theta0=None, theta_edge=theta_edge)
    result_theta0_earth = select_mechanism(theta_out, hat_out, theta0=EARTH_G, theta_edge=theta_edge)

    print(f"\n[theta0 estimated jointly] {result_theta0_free}")
    print(f"[theta0 fixed = Earth g={EARTH_G}] {result_theta0_earth}")

    out = {"n_gated_out": len(theta_out), "n_gated_in": len(theta_in),
           "theta_out": theta_out.tolist(), "hat_out": hat_out.tolist(),
           "theta_edge": theta_edge,
           "select_mechanism_theta0_free": result_theta0_free,
           "select_mechanism_theta0_earth_g": result_theta0_earth}

    if len(theta_in) >= 2 and len(theta_out) >= 2:
        d, dlo, dhi, p = paired_bootstrap_pre_difference(theta_in, hat_in, theta_out, hat_out, n_boot=2000)
        out["paired_bootstrap_PRE_out_minus_in"] = [d, dlo, dhi, p]
        print(f"\nPRE(out)-PRE(in) = {d:.4f} [{dlo:.4f}, {dhi:.4f}], one-sided p={p:.4f}")

    return out


def main():
    result = {}
    cog_rows = load_projectile("e0_pilot_cogvideox.json")
    result["CogVideoX-5B-I2V"] = analyze(cog_rows, "CogVideoX-5B-I2V")

    ltx_rows = load_projectile("e0_pilot.json")
    result["LTX-Video"] = analyze(ltx_rows, "LTX-Video")

    out_path = os.path.join(RESULTS_DIR, "e7_mechanism_adjudication.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, default=lambda o: None if isinstance(o, float) and np.isnan(o) else o)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
