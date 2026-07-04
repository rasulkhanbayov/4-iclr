#!/usr/bin/env python3
"""
experiments/e6_negative_control.py
===================================
E6 — NEGATIVE CONTROL (runbook Section "EXPERIMENTS").

Feeds GROUND-TRUTH simulator continuations (not any generative model) through
the identical tracker + fitter pipeline that will later be used on real video
generators. This validates the MEASUREMENT, not any model.

Pass/fail (per physweep_runbook.txt):
  PRE  ~ 0    (near-perfect recovery)
  slope ~ 1   (faithfulness slope on the in-range set)
  fit R^2 ~ 1 (fitter explains the tracked trajectory well)

If this fails, the pipeline is broken and no generator should be run yet.

Usage: python3 experiments/e6_negative_control.py
Writes results/e6_negative_control.json
"""
from __future__ import annotations
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import yaml

from physweep.render import (
    simulate_projectile, simulate_damped_pendulum, simulate_bouncing_ball,
    simulate_spring_mass, simulate_inclined_slide,
)
from physweep.track import centroid_track, pixel_y_to_physics_y
from physweep_metrics import (
    fit_gravity_from_trajectory, fit_omega_from_crossings, fit_zeta_from_envelope,
    fit_restitution_from_bounces, fit_friction_from_slide, friction_from_acceleration,
    pre, faithfulness_slope, bootstrap_ci, damped_sine_r2,
)

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "physweep", "configs", "systems.yaml")
FIT_R2_GATE = 0.8   # per runbook: gate low-R^2 fits out of PRE, report the rate


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def run_projectile(cfg, n_seeds):
    sysc = cfg["systems"]["projectile"]
    theta_in = sysc["in_range"]; theta_out = sysc["out_of_range"]
    rows = []
    for theta_set, label in [(theta_in, "in"), (theta_out, "out")]:
        for g_true in theta_set:
            for seed in range(n_seeds):
                frames, y_px_true, t = simulate_projectile(g=g_true, seed=seed)
                cx, cy = centroid_track(frames)
                y_phys = pixel_y_to_physics_y(cy)
                g_hat, r2 = fit_gravity_from_trajectory(t, y_phys)
                rows.append(dict(system="projectile", theta=g_true, theta_hat=g_hat,
                                 r2=r2, split=label, seed=seed))
    return rows


def run_pendulum_omega(cfg, n_seeds):
    """Gate on damped_sine_r2, not fit_omega_from_crossings's own (undamped)
    R^2 -- the undamped model under-reports quality for a real damped signal
    even when omega itself is recovered accurately (verified directly; see
    CLAUDE.md Section 2 / commit history for the investigation)."""
    sysc = cfg["systems"]["damped_pendulum_omega"]
    n_frames = sysc.get("n_frames", 24)
    zeta = sysc["fixed_zeta"]
    rows = []
    for theta_set, label in [(sysc["in_range"], "in"), (sysc["out_of_range"], "out")]:
        for om_true in theta_set:
            for seed in range(n_seeds):
                frames, bx_true, t = simulate_damped_pendulum(
                    omega=om_true, zeta=zeta, seed=seed, n_frames=n_frames)
                cx, cy = centroid_track(frames)
                om_hat, _ = fit_omega_from_crossings(t, cx)
                if np.isnan(om_hat):
                    r2 = 0.0
                else:
                    zeta_hat, _ = fit_zeta_from_envelope(t, cx, om_hat)
                    zeta_for_r2 = zeta_hat if not np.isnan(zeta_hat) else zeta
                    r2 = damped_sine_r2(t, cx, om_hat, zeta_for_r2)
                rows.append(dict(system="pendulum_omega", theta=om_true, theta_hat=om_hat,
                                 r2=r2, split=label, seed=seed))
    return rows


def run_pendulum_zeta(cfg, n_seeds):
    sysc = cfg["systems"]["damped_pendulum_zeta"]
    n_frames = sysc.get("n_frames", 24)
    omega = sysc["fixed_omega"]
    rows = []
    for theta_set, label in [(sysc["in_range"], "in"), (sysc["out_of_range"], "out")]:
        for zeta_true in theta_set:
            for seed in range(n_seeds):
                frames, bx_true, t = simulate_damped_pendulum(
                    omega=omega, zeta=zeta_true, seed=seed, n_frames=n_frames)
                cx, cy = centroid_track(frames)
                om_hat, _ = fit_omega_from_crossings(t, cx)
                if np.isnan(om_hat):
                    zeta_hat, r2 = float("nan"), 0.0
                else:
                    zeta_hat, r2 = fit_zeta_from_envelope(t, cx, om_hat)
                rows.append(dict(system="pendulum_zeta", theta=zeta_true, theta_hat=zeta_hat,
                                 r2=r2, split=label, seed=seed))
    return rows


def run_bouncing_ball(cfg, n_seeds):
    sysc = cfg["systems"]["bouncing_ball"]
    rows = []
    for theta_set, label in [(sysc["in_range"], "in"), (sysc["out_of_range"], "out")]:
        for e_true in theta_set:
            for seed in range(n_seeds):
                frames, ys, t, peaks = simulate_bouncing_ball(e=e_true, seed=seed)
                if len(peaks) >= 2:
                    e_hat, r2 = fit_restitution_from_bounces(peaks)
                else:
                    e_hat, r2 = float("nan"), 0.0
                rows.append(dict(system="bouncing_ball", theta=e_true, theta_hat=e_hat,
                                 r2=r2, split=label, seed=seed))
    return rows


def run_spring_mass(cfg, n_seeds):
    sysc = cfg["systems"]["spring_mass"]
    n_frames = sysc.get("n_frames", 24)
    mass = sysc["mass_kg"]
    rows = []
    for theta_set, label in [(sysc["in_range"], "in"), (sysc["out_of_range"], "out")]:
        for k_true in theta_set:
            for seed in range(n_seeds):
                frames, xs, t = simulate_spring_mass(k=k_true, seed=seed, n_frames=n_frames, mass_kg=mass)
                cx, cy = centroid_track(frames)
                om_hat, r2 = fit_omega_from_crossings(t, cx)
                k_hat = om_hat ** 2 * mass if not np.isnan(om_hat) else float("nan")
                rows.append(dict(system="spring_mass", theta=k_true, theta_hat=k_hat,
                                 r2=r2, split=label, seed=seed))
    return rows


def run_inclined_slide(cfg, n_seeds):
    sysc = cfg["systems"]["inclined_slide"]
    incline_deg = sysc["incline_deg"]
    incline_rad = np.deg2rad(incline_deg)
    g_internal = 300.0  # must match render.py's simulate_inclined_slide default
    dx, dy = np.cos(incline_rad), np.sin(incline_rad)
    rows = []
    for theta_set, label in [(sysc["in_range"], "in"), (sysc["out_of_range"], "out")]:
        for mu_true in theta_set:
            for seed in range(n_seeds):
                frames, s_true, t = simulate_inclined_slide(mu=mu_true, seed=seed, incline_deg=incline_deg)
                cx, cy = centroid_track(frames)
                s_px = (cx - cx[0]) * dx + (cy - cy[0]) * dy
                a_hat, r2 = fit_friction_from_slide(t, s_px)
                mu_hat = friction_from_acceleration(a_hat, incline_rad, g=g_internal)
                rows.append(dict(system="inclined_slide", theta=mu_true, theta_hat=mu_hat,
                                 r2=r2, split=label, seed=seed))
    return rows


def summarize(rows, gate=FIT_R2_GATE):
    rows = [r for r in rows if not np.isnan(r["theta_hat"])]
    n_total_incl_nan = len(rows)
    gated = [r for r in rows if r["r2"] >= gate]
    dropped_rate = 1.0 - len(gated) / max(len(rows), 1)

    theta_in = np.array([r["theta"] for r in gated if r["split"] == "in"])
    hat_in = np.array([r["theta_hat"] for r in gated if r["split"] == "in"])
    theta_out = np.array([r["theta"] for r in gated if r["split"] == "out"])
    hat_out = np.array([r["theta_hat"] for r in gated if r["split"] == "out"])

    out = {"n_rows": len(rows), "n_gated_in": len(theta_in), "n_gated_out": len(theta_out),
           "fit_quality_dropped_rate": dropped_rate}

    if len(theta_in) >= 2:
        pre_in, pre_in_lo, pre_in_hi = bootstrap_ci(pre, theta_in, hat_in, n_boot=1000)
        slope, slope_lo, slope_hi = bootstrap_ci(faithfulness_slope, theta_in, hat_in, n_boot=1000)
        out["PRE_in"] = [pre_in, pre_in_lo, pre_in_hi]
        out["slope_in"] = [slope, slope_lo, slope_hi]
    if len(theta_out) >= 2:
        pre_out, pre_out_lo, pre_out_hi = bootstrap_ci(pre, theta_out, hat_out, n_boot=1000)
        out["PRE_out"] = [pre_out, pre_out_lo, pre_out_hi]
    out["mean_fit_r2"] = float(np.mean([r["r2"] for r in rows])) if rows else float("nan")
    return out


def main():
    cfg = load_config()
    n_seeds = cfg["render"]["seeds_per_point"]

    print(f"E6 negative control: n_seeds={n_seeds} per grid point, per system")
    all_rows = []
    runners = [
        ("projectile", run_projectile),
        ("pendulum_omega", run_pendulum_omega),
        ("pendulum_zeta", run_pendulum_zeta),
        ("bouncing_ball", run_bouncing_ball),
        ("spring_mass", run_spring_mass),
        ("inclined_slide", run_inclined_slide),
    ]
    per_system = {}
    for name, fn in runners:
        rows = fn(cfg, n_seeds)
        all_rows.extend(rows)
        summ = summarize(rows)
        per_system[name] = summ
        print(f"\n--- {name} ---")
        for k, v in summ.items():
            print(f"  {k}: {v}")

    overall = summarize(all_rows)
    print("\n=== OVERALL (all systems pooled) ===")
    for k, v in overall.items():
        print(f"  {k}: {v}")

    result = {"per_system": per_system, "overall": overall, "n_seeds": n_seeds,
              "fit_r2_gate": FIT_R2_GATE}
    out_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "results", "e6_negative_control.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nWrote {out_path}")

    # pass/fail per runbook
    pre_in = overall.get("PRE_in", [float("nan")])[0]
    slope_in = overall.get("slope_in", [float("nan")])[0]
    print("\n" + "=" * 60)
    if pre_in < 0.05 and abs(slope_in - 1.0) < 0.1:
        print(f"E6 PASS: PRE(in)={pre_in:.4f} (~0), slope(in)={slope_in:.4f} (~1)")
    else:
        print(f"E6 FAIL or MARGINAL: PRE(in)={pre_in:.4f}, slope(in)={slope_in:.4f}")
        print("Per the runbook: fix the pipeline before running any generator.")
    print("=" * 60)


if __name__ == "__main__":
    main()
