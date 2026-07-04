#!/usr/bin/env python3
"""
experiments/e1_faithfulness.py
================================
E1 — FAITHFULNESS CURVE (paper Section "Experimental Protocol").

Formalizes E0's already-collected projectile data (both models) into E1's
official statistics: theta-vs-theta_hat, faithfulness slope beta, Spearman
rho, PRE(in), with bootstrap CIs, per model. E0 and E1 use the identical
grid/seeds/conditioning for the projectile system (E0 IS a subset of what E1
needs), so this reuses experiments/e0_pilot.py's and
experiments/e0_pilot_cogvideox.py's already-generated results rather than
re-running GPU work -- see CLAUDE.md Section 5 for why E0's design already
satisfies E1 for this system.

Scope note: this covers the PROJECTILE system only, both models tested so
far (LTX-Video, CogVideoX-5B-I2V), under C2 (text-specified) conditioning.
The other 5 sweep axes and true C1 conditioning are E4's and future work's
job respectively -- see CLAUDE.md Section 5/6 for the open items.

Usage: python3 experiments/e1_faithfulness.py
Writes results/e1_faithfulness.json
"""
from __future__ import annotations
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from physweep_metrics import faithfulness_slope, spearman_rho, pre, bootstrap_ci

RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
FIT_R2_GATE = 0.8

MODELS = {
    "LTX-Video": "e0_pilot.json",
    "CogVideoX-5B-I2V": "e0_pilot_cogvideox.json",
}


def analyze_model(rows):
    gated = [r for r in rows if r["r2"] is not None and r["r2"] >= FIT_R2_GATE
            and r["g_hat"] is not None]
    dropped_rate = 1.0 - len(gated) / max(len(rows), 1)

    theta_in = np.array([r["g_true"] for r in gated if r["split"] == "in"])
    hat_in = np.array([r["g_hat"] for r in gated if r["split"] == "in"])
    theta_all = np.array([r["g_true"] for r in gated])
    hat_all = np.array([r["g_hat"] for r in gated])

    out = {"n_total": len(rows), "n_gated_in": len(theta_in),
           "fit_quality_dropped_rate": dropped_rate,
           "theta_vs_theta_hat_in": list(zip(theta_in.tolist(), hat_in.tolist()))}

    if len(theta_in) >= 4:
        slope, slope_lo, slope_hi = bootstrap_ci(faithfulness_slope, theta_in, hat_in, n_boot=2000)
        pre_in, pre_lo, pre_hi = bootstrap_ci(pre, theta_in, hat_in, n_boot=2000)
        out["slope_beta_in"] = [slope, slope_lo, slope_hi]
        out["PRE_in"] = [pre_in, pre_lo, pre_hi]
    if len(theta_all) >= 4:
        rho = spearman_rho(theta_all, hat_all)
        out["spearman_rho_full_grid"] = rho
    return out


def main():
    result = {}
    for model_name, fname in MODELS.items():
        path = os.path.join(RESULTS_DIR, fname)
        if not os.path.exists(path):
            print(f"SKIP {model_name}: {path} not found (run its E0 script first)")
            continue
        with open(path) as f:
            data = json.load(f)
        analysis = analyze_model(data["rows"])
        result[model_name] = analysis
        print(f"\n=== {model_name} (projectile, in-range g=5..15) ===")
        print(f"n_gated_in: {analysis['n_gated_in']} / {analysis['n_total']}")
        print(f"fit_quality_dropped_rate: {analysis['fit_quality_dropped_rate']:.2%}")
        if "slope_beta_in" in analysis:
            s, lo, hi = analysis["slope_beta_in"]
            print(f"faithfulness slope beta = {s:.4f}  95% CI [{lo:.4f}, {hi:.4f}]")
            p, plo, phi = analysis["PRE_in"]
            print(f"PRE(in) = {p:.4f}  95% CI [{plo:.4f}, {phi:.4f}]")
        if "spearman_rho_full_grid" in analysis:
            print(f"Spearman rho (full grid, in+out) = {analysis['spearman_rho_full_grid']:.4f}")

    print("\n" + "=" * 70)
    print("E1 SUMMARY TABLE (projectile system, C2 conditioning)")
    print("=" * 70)
    print(f"{'Model':<20} {'slope beta (in)':<22} {'PRE(in)':<10} {'Spearman rho':<12}")
    for model_name, a in result.items():
        s = a.get("slope_beta_in")
        s_str = f"{s[0]:.3f} [{s[1]:.3f},{s[2]:.3f}]" if s else "n/a"
        p = a.get("PRE_in")
        p_str = f"{p[0]:.3f}" if p else "n/a"
        rho = a.get("spearman_rho_full_grid")
        rho_str = f"{rho:.3f}" if rho is not None else "n/a"
        print(f"{model_name:<20} {s_str:<22} {p_str:<10} {rho_str:<12}")

    out_path = os.path.join(RESULTS_DIR, "e1_faithfulness.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
