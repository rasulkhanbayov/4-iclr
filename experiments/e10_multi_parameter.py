#!/usr/bin/env python3
"""
experiments/e10_multi_parameter.py
=====================================
The multi-parameter experiment (E10, optional -- runbook Section
"EXPERIMENTS"): sweep two physical parameters JOINTLY on one system and
check whether faithfulness on one axis degrades when the OTHER is
out-of-range, connecting to combinatorial generalization
\citep{kang2025howfar}.

System chosen: the damped pendulum (`simulate_damped_pendulum`), whose
angular frequency omega and damping ratio zeta are ALREADY both real
parameters of the same simulator -- every prior experiment in this project
(the faithfulness-curve, generality, extrapolation, and mechanism-
adjudication experiments) sweeps only ONE of these while holding the other
fixed at systems.yaml's `fixed_zeta`/`fixed_omega`. This script instead
varies BOTH at once, using the SAME closed-form joint-recovery pipeline
those other experiments already validate independently
(`fit_omega_from_crossings` first, then `fit_zeta_from_envelope` using the
recovered omega on the SAME trajectory) -- no new fitter, no new simulator
code, only a joint grid and a joint prompt.

Joint grid (verified locally against GROUND TRUTH before writing this
experiment -- both the fitter's own zero-crossing/envelope logic AND its
fit-quality R^2 at every cell, not just a peak count -- see CLAUDE.md for
the full derivation): omega in {3, 5, 8} rad/s, zeta in {0.05, 0.2, 0.3}.
omega=3,5 are the existing single-axis in-range grid's values; omega=8 is
the existing single-axis out-of-range grid's smallest value. zeta=0.05 is
in-range; zeta=0.2 and 0.3 are out-of-range.

zeta=0.2 was chosen deliberately over the single-axis experiment's own
out-of-range value (0.6): on ground truth, zeta=0.6 makes
fit_omega_from_crossings return nan at EVERY omega (the pendulum decays
before completing even one full oscillation, 0 zero-crossings), which
would leave the omega-faithfulness-when-zeta-out-of-range comparison with
ZERO usable rows -- a real design flaw caught by testing the fitter
end-to-end on ground truth before writing the final grid, not just
checking envelope-peak counts (which looked fine at zeta=0.6 but did not
guarantee the OMEGA half of the joint fit would work). zeta=0.2 instead
clears the R^2>=0.8 fit-quality gate on ground truth at ALL THREE omega
values (0.83-0.99), so it is the point that actually carries the
cross-axis comparison. zeta=0.3 is kept as a second, harder out-of-range
point precisely because it partially degrades on ground truth itself at
higher omega (R^2 0.53-0.71 for omega=5,8) -- its own dropout rate is
itself part of what this experiment reports, not something to route
around.

This gives the design E10 needs: at least one out-of-range zeta value
(0.2) where every omega cell is independently fittable, letting us ask
specifically whether omega faithfulness degrades when zeta alone is
pushed out-of-range and whether zeta faithfulness degrades when omega
alone is pushed out-of-range, not just whether both together look worse.

Scope: LTX-Video and CogVideoX only. DynamiCrafter's fixed 16-frame output
makes this system's n_frames=180 requirement architecturally impossible on
that model (already an established, permanent exclusion for the pendulum
systems generally -- see the generality experiment's own writeup), so
running it here would only reproduce that same, already-documented
ceiling rather than test anything new about joint faithfulness.

Usage:
  python3 experiments/e10_multi_parameter.py --model ltx
  python3 experiments/e10_multi_parameter.py --model cogvideox
Writes results/e10_multi_parameter_{model}.json
"""
from __future__ import annotations
import sys, os, json, time, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HF_HOME"] = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".hf_home")

import numpy as np
import torch
from PIL import Image

from physweep.render import simulate_damped_pendulum
from physweep.track import centroid_track
from physweep_metrics import (
    fit_omega_from_crossings, fit_zeta_from_envelope, damped_sine_r2,
    faithfulness_slope, pre, bootstrap_ci,
)
from experiments.e4_generality import (
    make_ltx_generate_fn, make_cogvideox_generate_fn, DISK_VALUE,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(REPO_ROOT, "results")
FIT_R2_GATE = 0.8
N_FRAMES = 180          # matches the existing pendulum_omega/pendulum_zeta systems' override
SEEDS = [0, 1, 2, 3, 4]  # 5 seeds/cell, same per-point budget as every other experiment

OMEGA_GRID = [3.0, 5.0, 8.0]   # 3,5 in-range; 8 out-of-range (matches existing single-axis grids)
ZETA_GRID = [0.05, 0.2, 0.3]   # 0.05 in-range; 0.2 and 0.3 out-of-range.
                                # NOT 0.6 (the single-axis experiment's own out-of-range grid
                                # value): verified on ground truth that omega_hat is nan at
                                # EVERY omega when zeta=0.6 (decays before one full oscillation,
                                # 0 zero-crossings), which would leave the
                                # omega-faithfulness-when-zeta-out-of-range comparison with
                                # zero usable rows. 0.2 was chosen specifically because it
                                # clears the R^2>=0.8 fit-quality gate on ground truth at ALL
                                # THREE omega values (0.83-0.99) -- this is the point that
                                # carries the actual cross-axis comparison. 0.3 is kept as a
                                # third, harder out-of-range point (partial dropout at higher
                                # omega on ground truth itself, 0.53-0.71 R^2 there) -- its
                                # own dropout rate is informative, not hidden.
OMEGA_IN_RANGE = {3.0, 5.0}
ZETA_IN_RANGE = {0.05}


def joint_pendulum_prompt(omega: float, zeta: float) -> str:
    """Names BOTH parameters in one prompt, combining the qualitative anchor
    phrases the single-axis prompts already use (pendulum_omega_prompt /
    pendulum_zeta_prompt in experiments/e4_generality.py) rather than
    inventing new wording, so this experiment's C2 (text-specified)
    channel is directly comparable to the single-axis experiments'."""
    if omega <= 3: om_qual = "swinging slowly, low frequency oscillation"
    elif omega <= 6: om_qual = "swinging at a natural, moderate speed"
    else: om_qual = "swinging extremely fast, rapid high-frequency oscillation"
    if zeta <= 0.1: ze_qual = "with almost no damping, oscillating steadily for a long time"
    elif zeta <= 0.3: ze_qual = "with noticeable damping, the swings shrinking over time"
    else: ze_qual = "heavily damped, quickly settling to a stop"
    return (f"a dark ball on a pendulum swinging with angular frequency {omega:.1f} radians per "
           f"second and damping ratio {zeta:.2f}, {om_qual}, {ze_qual}, "
           f"simple physics simulation, plain background")


def run_joint_grid(generate_fn, n_frames=N_FRAMES):
    rows = []
    for omega_true in OMEGA_GRID:
        for zeta_true in ZETA_GRID:
            omega_split = "in" if omega_true in OMEGA_IN_RANGE else "out"
            zeta_split = "in" if zeta_true in ZETA_IN_RANGE else "out"
            for seed in SEEDS:
                frames_gt, bx_true, t_gt = simulate_damped_pendulum(
                    omega=omega_true, zeta=zeta_true, seed=seed, n_frames=n_frames)
                first_frame = Image.fromarray(frames_gt[0]).convert("RGB")
                prompt = joint_pendulum_prompt(omega_true, zeta_true)
                video_np = generate_fn(first_frame, prompt, seed, n_frames)
                cx, cy = centroid_track(video_np, disk_value=DISK_VALUE, tol=60)
                if np.any(np.isnan(cx)):
                    omega_hat, zeta_hat, r2 = float("nan"), float("nan"), 0.0
                else:
                    omega_hat, _ = fit_omega_from_crossings(t_gt[:len(cx)], cx)
                    if np.isnan(omega_hat):
                        zeta_hat, r2 = float("nan"), 0.0
                    else:
                        zeta_hat, _ = fit_zeta_from_envelope(t_gt[:len(cx)], cx, omega_hat)
                        r2 = damped_sine_r2(t_gt[:len(cx)], cx, omega_hat, zeta_hat) if not np.isnan(zeta_hat) else 0.0
                rows.append(dict(
                    omega_true=omega_true, zeta_true=zeta_true,
                    omega_hat=omega_hat, zeta_hat=zeta_hat, r2=r2,
                    omega_split=omega_split, zeta_split=zeta_split, seed=seed,
                ))
                print(f"  omega_true={omega_true:5.1f} ({omega_split}) zeta_true={zeta_true:5.2f} ({zeta_split}) "
                      f"seed={seed}: omega_hat={omega_hat if not (isinstance(omega_hat,float) and np.isnan(omega_hat)) else float('nan'):.3f} "
                      f"zeta_hat={zeta_hat if not (isinstance(zeta_hat,float) and np.isnan(zeta_hat)) else float('nan'):.3f} r2={r2:.3f}")
    return rows


def summarize(rows):
    """Cross-axis degradation check: for each parameter, compare its own
    faithfulness slope/PRE when the OTHER parameter is in-range vs.
    out-of-range. This is the actual E10 question -- not just "does the 2D
    faithfulness degrade" but "does axis A's faithfulness depend on whether
    axis B is out of range.\""""
    def gated(rows_subset, hat_key, true_key):
        g = [r for r in rows_subset if r["r2"] >= FIT_R2_GATE
             and not (isinstance(r[hat_key], float) and np.isnan(r[hat_key]))]
        theta = np.array([r[true_key] for r in g])
        hat = np.array([r[hat_key] for r in g])
        return theta, hat, len(g)

    out = {}
    for other_split, label in [("in", "other_in_range"), ("out", "other_out_of_range")]:
        # omega faithfulness when zeta is in/out of range
        subset = [r for r in rows if r["zeta_split"] == other_split]
        theta, hat, n = gated(subset, "omega_hat", "omega_true")
        entry = dict(n_gated=n, n_total=len(subset))
        if n >= 3 and len(set(theta.tolist())) >= 2:
            entry["slope"] = faithfulness_slope(theta, hat)
            entry["pre"] = pre(theta, hat)
        out[f"omega_faithfulness_when_zeta_{label}"] = entry

        # zeta faithfulness when omega is in/out of range
        subset = [r for r in rows if r["omega_split"] == other_split]
        theta, hat, n = gated(subset, "zeta_hat", "zeta_true")
        entry = dict(n_gated=n, n_total=len(subset))
        if n >= 3 and len(set(theta.tolist())) >= 2:
            entry["slope"] = faithfulness_slope(theta, hat)
            entry["pre"] = pre(theta, hat)
        out[f"zeta_faithfulness_when_omega_{label}"] = entry

    gated_all = [r for r in rows if r["r2"] >= FIT_R2_GATE
                 and not (isinstance(r["omega_hat"], float) and np.isnan(r["omega_hat"]))]
    out["overall_dropped_rate"] = 1.0 - len(gated_all) / max(len(rows), 1)
    out["n_total"] = len(rows)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["ltx", "cogvideox"], required=True)
    args = ap.parse_args()

    if args.model == "ltx":
        from diffusers import LTXImageToVideoPipeline
        print("Loading LTX-Video...")
        pipe = LTXImageToVideoPipeline.from_pretrained("Lightricks/LTX-Video", torch_dtype=torch.bfloat16)
        pipe.to("cuda")
        generate_fn = make_ltx_generate_fn(pipe)
    else:
        from diffusers import CogVideoXImageToVideoPipeline
        print("Loading CogVideoX-5B-I2V...")
        pipe = CogVideoXImageToVideoPipeline.from_pretrained("zai-org/CogVideoX-5b-I2V", torch_dtype=torch.bfloat16)
        pipe.to("cuda")
        pipe.vae.enable_tiling()
        generate_fn = make_cogvideox_generate_fn(pipe)

    t0 = time.time()
    rows = run_joint_grid(generate_fn)
    elapsed = time.time() - t0
    summary = summarize(rows)
    summary["elapsed_seconds"] = elapsed
    print(f"\nTotal time: {elapsed:.1f}s for {len(rows)} clips")
    print(json.dumps(summary, indent=2, default=str))

    out_path = os.path.join(RESULTS_DIR, f"e10_multi_parameter_{args.model}.json")
    with open(out_path, "w") as f:
        json.dump(dict(rows=rows, summary=summary), f, indent=2, default=str)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
