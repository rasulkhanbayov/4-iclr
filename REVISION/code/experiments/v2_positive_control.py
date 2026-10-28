#!/usr/bin/env python3
"""
Positive control for the revised scenes (CPU only, no generator).

Ground-truth simulator video in each scene style ("minimal", "structured",
"shaded") goes through the blob tracker, the closed-form fit and the validity
checks. Unlike the original E6, the bouncing ball is also recovered from the
TRACKED trajectory (the original used the simulator's own peak heights), so
every axis now tests the tracker.

Pass criterion (same as E6): pooled in-range PRE < 0.05 and |slope - 1| < 0.1,
and every clip that passes the fit gate is labelled valid.

Usage:  python experiments/v2_positive_control.py
Writes: results_v2/positive_control.json
"""

from __future__ import annotations
import json
import os
import sys

CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CODE_DIR)
sys.path.insert(0, os.path.join(CODE_DIR, "experiments"))

import numpy as np
import yaml

from physweep import render as R
from physweep.track import centroid_track
from physweep.validity import shape_stats, classify, centroid_track_above, FIT_R2_GATE
from physweep_metrics import (fit_omega_from_crossings, fit_zeta_from_envelope, damped_sine_r2,
                              pre, faithfulness_slope, bootstrap_ci)
from e5a_cotracker_analysis import REFIT_FN

OUT_DIR = os.path.join(os.path.dirname(CODE_DIR), "results_v2")
CFG = yaml.safe_load(open(os.path.join(CODE_DIR, "physweep", "configs", "systems.yaml")))
N_SEEDS = CFG["render"]["seeds_per_point"]
CFG_KEY = {"pendulum_omega": "damped_pendulum_omega", "pendulum_zeta": "damped_pendulum_zeta"}


def simulate(system, theta, seed, style):
    sc = CFG["systems"][CFG_KEY.get(system, system)]
    n = sc.get("n_frames", R.N_FRAMES)
    if system == "projectile":
        return R.simulate_projectile(g=theta, seed=seed, n_frames=n, ground_clearance_px=100, style=style)[0]
    if system == "pendulum_omega":
        return R.simulate_damped_pendulum(omega=theta, zeta=sc["fixed_zeta"], seed=seed, n_frames=n, style=style)[0]
    if system == "pendulum_zeta":
        return R.simulate_damped_pendulum(omega=sc["fixed_omega"], zeta=theta, seed=seed, n_frames=n, style=style)[0]
    if system == "bouncing_ball":
        return R.simulate_bouncing_ball(e=theta, seed=seed, n_frames=n, style=style)[0]
    if system == "spring_mass":
        return R.simulate_spring_mass(k=theta, seed=seed, n_frames=n, mass_kg=sc["mass_kg"], style=style)[0]
    return R.simulate_inclined_slide(mu=theta, seed=seed, n_frames=n, incline_deg=sc["incline_deg"], style=style)[0]


def fit(system, cx, cy):
    hat, r2 = REFIT_FN[system](cx, cy)
    if system == "pendulum_omega" and np.isfinite(hat):
        # gate on the damped-sine R^2, as in the original E6 (the undamped
        # R^2 from fit_omega_from_crossings under-reports real damped fits)
        t = np.arange(len(cx)) * R.DT
        z, _ = fit_zeta_from_envelope(t, np.asarray(cx, float), hat)
        r2 = damped_sine_r2(t, np.asarray(cx, float), hat, z if np.isfinite(z) else CFG["systems"]["damped_pendulum_omega"]["fixed_zeta"])
    return hat, r2


def summarize(rows):
    fit_ok = [r for r in rows if r["fit_ok"]]
    inn = [r for r in fit_ok if r["split"] == "in"]
    out = dict(n=len(rows), n_fit_ok=len(fit_ok),
               n_valid=sum(r["label"] == "valid" for r in rows),
               fit_ok_but_not_valid=sum(r["fit_ok"] and r["label"] != "valid" for r in rows))
    if len(inn) >= 3:
        th = np.array([r["theta"] for r in inn]); hat = np.array([r["theta_hat"] for r in inn])
        out["PRE_in"] = list(bootstrap_ci(pre, th, hat, n_boot=1000))
        out["slope_in"] = list(bootstrap_ci(faithfulness_slope, th, hat, n_boot=1000))
    return out


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    systems = ["projectile", "pendulum_omega", "pendulum_zeta", "bouncing_ball", "spring_mass", "inclined_slide"]
    results, rows_all = {}, []
    for style in R.STYLES:
        style_rows = []
        for system in systems:
            sc = CFG["systems"][CFG_KEY.get(system, system)]
            for split, grid in [("in", sc["in_range"]), ("out", sc["out_of_range"])]:
                for theta in grid:
                    for seed in range(N_SEEDS):
                        frames = simulate(system, theta, seed, style)
                        st_ = shape_stats(frames)
                        cx, cy = centroid_track_above(frames, st_["ground_row0"])
                        hat, r2 = fit(system, cx, cy)
                        lab = classify(system, shape_stats(frames), hat if np.isfinite(hat) else None, r2)
                        style_rows.append(dict(style=style, system=system, theta=theta, split=split, seed=seed,
                                               theta_hat=float(hat) if np.isfinite(hat) else None,
                                               r2=float(r2), **lab))
        results[style] = dict(pooled=summarize(style_rows),
                              per_system={s: summarize([r for r in style_rows if r["system"] == s]) for s in systems})
        rows_all += style_rows

    print(f"{'style':<11}{'system':<16}{'n':>4}{'fit':>5}{'valid':>6}{'fit∧¬valid':>11}   PRE_in            slope_in")
    for style, res in results.items():
        for s, v in list(res["per_system"].items()) + [("POOLED", res["pooled"])]:
            p = v.get("PRE_in"); b = v.get("slope_in")
            fmt = lambda x: f"{x[0]:.4f} [{x[1]:.4f},{x[2]:.4f}]" if x else "—"
            print(f"{style:<11}{s:<16}{v['n']:>4}{v['n_fit_ok']:>5}{v['n_valid']:>6}{v['fit_ok_but_not_valid']:>11}   {fmt(p):<18}{fmt(b)}")
        p, b = res["pooled"].get("PRE_in"), res["pooled"].get("slope_in")
        verdict = "PASS" if p and b and p[0] < 0.05 and abs(b[0] - 1) < 0.1 and res["pooled"]["fit_ok_but_not_valid"] == 0 else "CHECK"
        print(f"  -> {style}: {verdict}\n")

    with open(os.path.join(OUT_DIR, "positive_control.json"), "w") as f:
        json.dump(dict(results=results, rows=rows_all), f, indent=1,
                  default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print(f"Wrote {os.path.join(OUT_DIR, 'positive_control.json')}")


if __name__ == "__main__":
    main()
