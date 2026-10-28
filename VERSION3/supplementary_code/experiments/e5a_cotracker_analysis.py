#!/usr/bin/env python3
"""
experiments/e5a_cotracker_analysis.py
=======================================
E5(a) -- tracker-swap robustness check (runbook Section "EXPERIMENTS").

`experiments/e3e5_extended.py --dual-track` already ran CoTracker3 on every
saved clip from the E3/E5(default) generation pass and stored the raw
trajectory (`cotracker_cx`/`cotracker_cy`) in each row of
`results/e3e5_default_{system}_{model}.json`, alongside the blob-centroid
tracker's own `theta_hat`/`r2` (computed at generation time from
`centroid_track`'s cx/cy). This script re-runs the SAME closed-form fitter
each system already uses on the blob-centroid trajectory, but on the
CoTracker3 trajectory instead, and compares the two trackers' recovered
theta_hat / fit-quality-gated slope / PRE side by side. This is pure
re-analysis of already-collected data -- no GPU, no new generation.

The question this answers: is the paper's headline finding (conditioning
not honored; two of three models converge to seed-fixed wrong defaults) an
artifact of the specific tracker used (naive blob centroiding), or does it
reproduce under a second, independent, learned tracker? If CoTracker3
recovers materially different theta_hat values or a materially different
fit-quality-gated pass rate than blob-centroiding on the SAME clips, that
would undercut the headline result's robustness; if the two trackers agree
closely, that is direct evidence the finding is about the generated video,
not the measurement.

Per-system fit recipes are mirrored EXACTLY from experiments/e3e5_extended.py's
run_*_variant functions (same fitter calls, same fixed parameters, same
frame-timestep reconstruction) so a difference in recovered theta_hat is
attributable only to the tracker, not to any change in fitting logic.
"""
from __future__ import annotations
import sys, os, json, glob, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import yaml

from physweep_metrics import (
    fit_gravity_from_trajectory, fit_omega_from_crossings, fit_zeta_from_envelope,
    fit_restitution_from_bounces, fit_friction_from_slide, friction_from_acceleration,
    pre, faithfulness_slope, bootstrap_ci,
)
from physweep.track import pixel_y_to_physics_y

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(REPO_ROOT, "results")
FPS = 24.0
DT = 1.0 / FPS
FIT_R2_GATE = 0.8

with open(os.path.join(REPO_ROOT, "physweep", "configs", "systems.yaml")) as f:
    CFG = yaml.safe_load(f)


def _t_gt(n):
    return np.arange(n) * DT


def refit_projectile(cx, cy):
    if np.any(np.isnan(cy)):
        return float("nan"), 0.0
    t = _t_gt(len(cy))
    y_phys = pixel_y_to_physics_y(np.asarray(cy, float))
    return fit_gravity_from_trajectory(t, y_phys)


def refit_pendulum_omega(cx, cy):
    if np.any(np.isnan(cx)):
        return float("nan"), 0.0
    t = _t_gt(len(cx))
    return fit_omega_from_crossings(t, np.asarray(cx, float))


def refit_pendulum_zeta(cx, cy):
    if np.any(np.isnan(cx)):
        return float("nan"), 0.0
    t = _t_gt(len(cx))
    om_hat, _ = fit_omega_from_crossings(t, np.asarray(cx, float))
    if np.isnan(om_hat):
        return float("nan"), 0.0
    return fit_zeta_from_envelope(t, np.asarray(cx, float), om_hat)


def refit_bouncing_ball(cx, cy):
    if np.any(np.isnan(cy)):
        return float("nan"), 0.0
    cy = np.asarray(cy, float)
    floor = float(np.max(cy))
    heights = floor - cy
    peaks = []
    rising, last_h = False, heights[0]
    for h in heights[1:]:
        if rising and h < last_h:
            peaks.append(last_h); rising = False
        elif h > last_h:
            rising = True
        last_h = h
    if len(peaks) >= 2:
        return fit_restitution_from_bounces(np.array(peaks))
    return float("nan"), 0.0


def refit_spring_mass(cx, cy):
    if np.any(np.isnan(cx)):
        return float("nan"), 0.0
    t = _t_gt(len(cx))
    mass = CFG["systems"]["spring_mass"]["mass_kg"]
    om_hat, r2 = fit_omega_from_crossings(t, np.asarray(cx, float))
    k_hat = om_hat ** 2 * mass if not np.isnan(om_hat) else float("nan")
    return k_hat, r2


def refit_inclined_slide(cx, cy):
    if np.any(np.isnan(cx)):
        return float("nan"), 0.0
    cx = np.asarray(cx, float); cy = np.asarray(cy, float)
    incline_deg = CFG["systems"]["inclined_slide"]["incline_deg"]
    incline_rad = np.deg2rad(incline_deg)
    g_internal = 300.0
    dxu, dyu = np.cos(incline_rad), np.sin(incline_rad)
    t = _t_gt(len(cx))
    s_px = (cx - cx[0]) * dxu + (cy - cy[0]) * dyu
    a_hat, r2 = fit_friction_from_slide(t, s_px)
    mu_hat = friction_from_acceleration(a_hat, incline_rad, g=g_internal)
    return mu_hat, r2


REFIT_FN = {
    "projectile": refit_projectile,
    "pendulum_omega": refit_pendulum_omega,
    "pendulum_zeta": refit_pendulum_zeta,
    "bouncing_ball": refit_bouncing_ball,
    "spring_mass": refit_spring_mass,
    "inclined_slide": refit_inclined_slide,
}

SYSTEMS = list(REFIT_FN.keys())
MODELS = ["ltx", "cogvideox", "dynamicrafter"]


def analyze_pair(system, model):
    path = os.path.join(RESULTS_DIR, f"e3e5_default_{system}_{model}.json")
    if not os.path.exists(path):
        return None
    d = json.load(open(path))
    rows = d["rows"]
    refit = REFIT_FN[system]

    out = dict(system=system, model=model, n_rows=len(rows), rows=[])
    for r in rows:
        cx2 = r.get("cotracker_cx")
        cy2 = r.get("cotracker_cy")
        if cx2 is None or cy2 is None:
            continue
        cx2 = np.array(cx2, float)
        cy2 = np.array(cy2, float)
        ct_hat, ct_r2 = refit(cx2, cy2)
        out["rows"].append(dict(
            theta=r["theta"], split=r["split"], seed=r["seed"],
            blob_theta_hat=r["theta_hat"], blob_r2=r["r2"],
            cotracker_theta_hat=ct_hat, cotracker_r2=ct_r2,
        ))
    return out


def summarize(pair_result):
    rows = pair_result["rows"]
    if not rows:
        return dict(n=0)

    def gated(key_hat, key_r2, split):
        theta = np.array([r["theta"] for r in rows if r["split"] == split
                           and not (isinstance(r[key_hat], float) and np.isnan(r[key_hat]))
                           and r[key_r2] >= FIT_R2_GATE])
        hat = np.array([r[key_hat] for r in rows if r["split"] == split
                         and not (isinstance(r[key_hat], float) and np.isnan(r[key_hat]))
                         and r[key_r2] >= FIT_R2_GATE])
        return theta, hat

    n_total_in = sum(1 for r in rows if r["split"] == "in")
    summary = dict(n_total_in=n_total_in)

    for tracker, (kh, kr2) in [("blob", ("blob_theta_hat", "blob_r2")),
                                ("cotracker", ("cotracker_theta_hat", "cotracker_r2"))]:
        theta_in, hat_in = gated(kh, kr2, "in")
        n_gated_in = len(theta_in)
        entry = dict(n_gated_in=n_gated_in, dropped_rate_in=1.0 - n_gated_in / max(n_total_in, 1))
        if n_gated_in >= 3 and len(set(theta_in.tolist())) >= 2:
            entry["slope_in"] = faithfulness_slope(theta_in, hat_in)
            entry["pre_in"] = pre(theta_in, hat_in)
        summary[tracker] = entry

    # agreement between the two trackers' theta_hat on rows BOTH gate through
    both_theta, both_blob, both_ct = [], [], []
    for r in rows:
        if (not (isinstance(r["blob_theta_hat"], float) and np.isnan(r["blob_theta_hat"]))
                and r["blob_r2"] >= FIT_R2_GATE
                and not (isinstance(r["cotracker_theta_hat"], float) and np.isnan(r["cotracker_theta_hat"]))
                and r["cotracker_r2"] >= FIT_R2_GATE):
            both_theta.append(r["theta"]); both_blob.append(r["blob_theta_hat"]); both_ct.append(r["cotracker_theta_hat"])
    summary["n_both_gated"] = len(both_theta)
    if len(both_theta) >= 2:
        both_blob = np.array(both_blob); both_ct = np.array(both_ct)
        rel_diff = np.abs(both_blob - both_ct) / (np.abs(both_blob) + 1.0)
        summary["mean_rel_diff_theta_hat"] = float(np.mean(rel_diff))
        summary["corr_blob_cotracker_theta_hat"] = float(np.corrcoef(both_blob, both_ct)[0, 1]) if len(both_theta) >= 3 else None

    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(RESULTS_DIR, "e5a_cotracker_comparison.json"))
    args = ap.parse_args()

    all_results = {}
    print(f"{'system':<16}{'model':<15}{'n_gated_in(blob)':<18}{'n_gated_in(cot)':<17}"
          f"{'slope(blob)':<13}{'slope(cot)':<13}{'n_both':<8}{'mean_rel_diff':<15}{'corr':<8}")
    for system in SYSTEMS:
        for model in MODELS:
            pair = analyze_pair(system, model)
            if pair is None:
                continue
            summ = summarize(pair)
            key = f"{system}_{model}"
            all_results[key] = dict(summary=summ, rows=pair["rows"])
            b = summ.get("blob", {})
            c = summ.get("cotracker", {})
            print(f"{system:<16}{model:<15}"
                  f"{b.get('n_gated_in','-'):<18}{c.get('n_gated_in','-'):<17}"
                  f"{b.get('slope_in', float('nan')):<13.4f}"
                  f"{c.get('slope_in', float('nan')):<13.4f}"
                  f"{summ.get('n_both_gated', 0):<8}"
                  f"{summ.get('mean_rel_diff_theta_hat', float('nan')):<15.4f}"
                  f"{str(summ.get('corr_blob_cotracker_theta_hat')):<8}")

    with open(args.out, "w") as f:
        json.dump(all_results, f, indent=2, default=lambda x: None if isinstance(x, float) and np.isnan(x) else x)
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
