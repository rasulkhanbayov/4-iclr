#!/usr/bin/env python3
"""
experiments/e5c_fit_gate_sensitivity.py
==========================================
E5(c) -- FIT-QUALITY GATE SENSITIVITY (runbook Section E5, sub-ablation c).

Objective: show the paper's headline conclusions (near-total fit-quality
dropped rates; faithfulness slope ~0; the seed-conditional-default finding)
are not an artifact of the specific R^2>=0.8 threshold chosen everywhere
else in this project. Re-computes dropped rate and in-range faithfulness
slope at several alternative gate thresholds against EVERY existing result
file, with ZERO new GPU time -- this is pure re-analysis of rows already
on disk (every row already carries its own r2, regardless of what gate
was applied when it was first summarized).

Usage: python3 experiments/e5c_fit_gate_sensitivity.py
Writes results/e5c_fit_gate_sensitivity.json
"""
from __future__ import annotations
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from physweep_metrics import faithfulness_slope, bootstrap_ci

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(REPO_ROOT, "results")

# The threshold used everywhere else in this project (E0/E1/E4/E6/E7/E2).
DEFAULT_GATE = 0.8
# Alternative thresholds to test sensitivity against, spanning well below
# and above the default.
ALT_GATES = [0.5, 0.6, 0.7, 0.8, 0.9, 0.95]

MODELS = ["ltx", "cogvideox", "dynamicrafter"]
E4_SYSTEMS = ["pendulum_omega", "pendulum_zeta", "bouncing_ball", "spring_mass", "inclined_slide"]
PROJECTILE_FILES = {"ltx": "e0_pilot.json", "cogvideox": "e0_pilot_cogvideox.json",
                    "dynamicrafter": "e0_pilot_dynamicrafter.json"}


def _normalize_rows(rows):
    out = []
    for r in rows:
        if "g_true" in r:
            out.append(dict(theta=r["g_true"], theta_hat=r["g_hat"], r2=r["r2"],
                            split=r["split"], seed=r["seed"]))
        else:
            out.append(r)
    return out


def load_rows(model, system):
    if system == "projectile":
        path = os.path.join(RESULTS_DIR, PROJECTILE_FILES[model])
    else:
        path = os.path.join(RESULTS_DIR, f"e4_{system}_{model}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        d = json.load(f)
    return _normalize_rows(d["rows"])


def summarize_at_gate(rows, gate):
    valid = [r for r in rows if r["theta_hat"] is not None
            and not (isinstance(r["theta_hat"], float) and np.isnan(r["theta_hat"]))]
    n_total = len(rows)
    gated = [r for r in valid if r["r2"] is not None and r["r2"] >= gate]
    dropped_rate = 1.0 - len(gated) / max(n_total, 1)

    theta_in = np.array([r["theta"] for r in gated if r["split"] == "in"])
    hat_in = np.array([r["theta_hat"] for r in gated if r["split"] == "in"])
    n_gated_out = sum(1 for r in gated if r["split"] == "out")

    out = {"n_total": n_total, "n_gated_in": len(theta_in), "n_gated_out": n_gated_out,
           "dropped_rate": dropped_rate}
    if len(theta_in) >= 4:
        slope, slo, shi = bootstrap_ci(faithfulness_slope, theta_in, hat_in, n_boot=1000)
        out["slope_in"] = [slope, slo, shi]
    return out


def main():
    systems = ["projectile"] + E4_SYSTEMS
    results = {}

    for model in MODELS:
        results[model] = {}
        for system in systems:
            rows = load_rows(model, system)
            if rows is None:
                continue
            per_gate = {str(g): summarize_at_gate(rows, g) for g in ALT_GATES}
            results[model][system] = per_gate

            # print a compact line: how does dropped rate / slope shift across gates?
            rates = [per_gate[str(g)]["dropped_rate"] for g in ALT_GATES]
            slopes = [per_gate[str(g)].get("slope_in") for g in ALT_GATES]
            rate_str = " ".join(f"{r:.2f}" for r in rates)
            print(f"{model:14s} {system:16s}  dropped_rate@[0.5,0.6,0.7,0.8,0.9,0.95]=[{rate_str}]")
            for g, s in zip(ALT_GATES, slopes):
                if s is not None:
                    print(f"    gate={g}: slope_in={s[0]:.3f} [{s[1]:.3f},{s[2]:.3f}]  n_gated_in={per_gate[str(g)]['n_gated_in']}")

    out_path = os.path.join(RESULTS_DIR, "e5c_fit_gate_sensitivity.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2,
                 default=lambda o: None if isinstance(o, float) and np.isnan(o) else o)
    print(f"\nWrote {out_path}")

    # Headline check: does the "no conditioning effect" conclusion (slope CI
    # including 0) hold across EVERY gate for EVERY model-system pair that
    # has enough gated in-range points to compute a slope at all?
    print("\n=== Headline robustness check ===")
    any_flip = False
    for model, systems in results.items():
        for system, per_gate in systems.items():
            slopes_with_ci = [(g, per_gate[str(g)]["slope_in"]) for g in ALT_GATES
                              if per_gate[str(g)].get("slope_in") is not None]
            if len(slopes_with_ci) < 2:
                continue
            cis_excl_zero = [(g, s) for g, s in slopes_with_ci if s[1] > 0 or s[2] < 0]
            if cis_excl_zero:
                any_flip = True
                print(f"  FLIP at {model}/{system}: gate(s) {[g for g,_ in cis_excl_zero]} "
                     f"give a slope CI excluding zero -- conclusion is gate-sensitive here.")
    if not any_flip:
        print("  No model-system pair with a computable slope flips from "
             "'CI includes zero' at any tested gate in [0.5, 0.95]. The "
             "in-range null-slope conclusion is NOT sensitive to the exact "
             "fit-quality threshold within this range.")


if __name__ == "__main__":
    main()
