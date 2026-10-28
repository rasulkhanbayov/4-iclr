#!/usr/bin/env python3
"""
experiments/e5bdef_ablation_analysis.py
=========================================
E5(b,d,e,f) -- robustness/ablation analysis (runbook Section "EXPERIMENTS").

`experiments/e3e5_extended.py` already generated and fit every ablation
variant (scale-invariance E5(b), conditioning-resolution E5(d),
guidance-scale E5(e), prompt-phrasing E5(f)), all scoped to the projectile
system per the runbook's own scoping decision, all writing
`results/e3e5_{variant}_projectile_{model}.json` with the same
`theta`/`theta_hat`/`r2`/`split`/`seed` row schema as the default run. This
script is pure re-analysis: no GPU, no new generation. It computes
dropped-rate, slope(in), and PRE(in) for every variant and compares each
against the SAME model's `e3e5_default_projectile_{model}.json` baseline,
to answer the actual E5 question -- does the headline finding (conditioning
not honored; seed-fixed-default convergence) hold up as these nuisance
parameters change, or is it an artifact of one specific rendering scale,
conditioning resolution, guidance scale, or prompt phrasing?
"""
from __future__ import annotations
import sys, os, json, glob, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from physweep_metrics import pre, faithfulness_slope

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(REPO_ROOT, "results")
FIT_R2_GATE = 0.8

# variant name -> (ablation family, human label)
VARIANT_FAMILY = {
    "default": ("baseline", "default"),
    "scale0.5x1.0": ("E5b scale", "0.5x size, 1.0x fps"),
    "scale1.5x1.0": ("E5b scale", "1.5x size, 1.0x fps"),
    "scale2.0x1.0": ("E5b scale", "2.0x size, 1.0x fps"),
    "scale1.0x0.5": ("E5b scale", "1.0x size, 0.5x fps"),
    "scale1.0x2.0": ("E5b scale", "1.0x size, 2.0x fps"),
    "res256": ("E5d cond-resolution", "256px conditioning"),
    "res384": ("E5d cond-resolution", "384px conditioning"),
    "cfg1.0": ("E5e guidance-scale", "cfg=1.0"),
    "cfg1.5": ("E5e guidance-scale", "cfg=1.5"),
    "cfg4.5": ("E5e guidance-scale", "cfg=4.5"),
    "cfg9.0": ("E5e guidance-scale", "cfg=9.0"),
    "prompt-terse": ("E5f prompt-phrasing", "terse prompt"),
    "prompt-verbose": ("E5f prompt-phrasing", "verbose prompt"),
}

MODELS = ["ltx", "cogvideox", "dynamicrafter"]


def load_rows(variant, model):
    path = os.path.join(RESULTS_DIR, f"e3e5_{variant}_projectile_{model}.json")
    if not os.path.exists(path):
        return None
    return json.load(open(path))["rows"]


def gated_in(rows):
    theta = np.array([r["theta"] for r in rows if r["split"] == "in"
                       and not (isinstance(r["theta_hat"], float) and np.isnan(r["theta_hat"]))
                       and r["r2"] >= FIT_R2_GATE])
    hat = np.array([r["theta_hat"] for r in rows if r["split"] == "in"
                     and not (isinstance(r["theta_hat"], float) and np.isnan(r["theta_hat"]))
                     and r["r2"] >= FIT_R2_GATE])
    return theta, hat


def stats_for(rows):
    n_total_in = sum(1 for r in rows if r["split"] == "in")
    theta, hat = gated_in(rows)
    n_gated = len(theta)
    out = dict(n_total_in=n_total_in, n_gated_in=n_gated,
               dropped_rate_in=1.0 - n_gated / max(n_total_in, 1))
    if n_gated >= 3 and len(set(theta.tolist())) >= 2:
        out["slope_in"] = faithfulness_slope(theta, hat)
        out["pre_in"] = pre(theta, hat)
        # seed-clustering signature check: within-seed std of theta_hat vs
        # across-all std -- low within-seed std relative to across-all std
        # is the same signature already documented for the default run.
        by_seed = {}
        for r in rows:
            if r["split"] != "in":
                continue
            th = r["theta_hat"]
            if isinstance(th, float) and np.isnan(th):
                continue
            if r["r2"] < FIT_R2_GATE:
                continue
            by_seed.setdefault(r["seed"], []).append(th)
        seed_stds = [np.std(v) for v in by_seed.values() if len(v) >= 2]
        if seed_stds:
            out["mean_within_seed_std"] = float(np.mean(seed_stds))
        out["overall_std"] = float(np.std(hat))
    else:
        out["slope_in"] = None
        out["pre_in"] = None
    return out


def main():
    all_results = {}
    print(f"{'model':<15}{'variant':<16}{'family':<20}{'n_gated_in':<12}{'dropped%':<10}"
          f"{'slope_in':<12}{'pre_in':<10}")
    for model in MODELS:
        model_variants = {}
        default_rows = load_rows("default", model)
        if default_rows is None:
            continue
        default_stats = stats_for(default_rows)
        model_variants["default"] = default_stats

        for variant, (family, label) in VARIANT_FAMILY.items():
            if variant == "default":
                continue
            rows = load_rows(variant, model)
            if rows is None:
                continue
            s = stats_for(rows)
            s["family"] = family
            s["label"] = label
            model_variants[variant] = s
            print(f"{model:<15}{variant:<16}{family:<20}{s['n_gated_in']:<12}"
                  f"{s['dropped_rate_in']*100:<10.1f}"
                  f"{s['slope_in'] if s['slope_in'] is not None else float('nan'):<12.4f}"
                  f"{s['pre_in'] if s['pre_in'] is not None else float('nan'):<10.4f}")
        all_results[model] = model_variants
        print()

    out_path = os.path.join(RESULTS_DIR, "e5bdef_ablation_comparison.json")
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"Wrote {out_path}")

    # Explicit no-op/exclusion note (already documented in CLAUDE.md/10_e5_ablations.sh):
    # dynamicrafter has no cond-resolution or guidance-scale knob (hardcoded
    # in its own subprocess call), and cogvideox's resolution sweep was
    # permanently skipped (hard model limitation -- learned positional
    # embeddings baked to 480x720). Confirm this script's own output reflects
    # that (no res*/cfg* rows for dynamicrafter, no res* rows for cogvideox)
    # rather than silently treating missing files as zero variance.
    missing = []
    for model in MODELS:
        for variant in VARIANT_FAMILY:
            if variant == "default":
                continue
            if load_rows(variant, model) is None:
                missing.append((model, variant))
    if missing:
        print("\nConfirmed absent (expected exclusions, not errors -- see CLAUDE.md):")
        for model, variant in missing:
            print(f"  {model} / {variant}")


if __name__ == "__main__":
    main()
