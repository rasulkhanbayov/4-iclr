#!/usr/bin/env python3
"""
experiments/e0_pilot.py
========================
E0 — PILOT / DECISION GATE (runbook Section "EXPERIMENTS").

Objective: does LTX-Video honor the conditioned physical parameter AT ALL?
Projectile system only. 5 in-range + 3 out-of-range g values, 5 seeds each
(per physweep/configs/systems.yaml).

Conditioning channel: C2 (text-specified), using the plain, reliable
LTXImageToVideoPipeline with single first-frame conditioning + a text prompt
that explicitly names the gravity magnitude and a qualitative descriptor.
This required two pivots from the original plan, both recorded in full in
CLAUDE.md Section 5:
  1. A single first frame carries NO g signal at all (position at t=0 does
     not depend on gravity in this renderer), so a bare single-frame C1
     attempt produced degenerate, seed-only output.
  2. LTXConditionPipeline (needed for proper C1 first+last-frame
     conditioning) has a real diffusers==0.39.0 bug (missing `mu` for its
     dynamic-shifting scheduler) -- patched in physweep/ltx_patch.py -- but
     even after that fix, the pipeline produces pure noise by mid-clip
     REGARDLESS of resolution or conditioning content (confirmed with a real
     photographic image at LTX-Video's native 704x512 resolution, using the
     library's own documented example). The plain LTXImageToVideoPipeline
     produces clean, coherent output on the identical input. This isolates
     the defect to LTXConditionPipeline itself, not our resolution or scene
     content -- so C1 (which needs multi-frame conditioning) is not reliably
     testable with this diffusers version. C2 is used instead, which only
     needs the pipeline that actually works.

Decision gate (from physweep_runbook.txt / CLAUDE.md Section 4):
  beta 95% CI excludes 0  -> conditioning is honored; proceed to full study.
  beta 95% CI includes 0  -> reframe: "conditioning not honored."

Usage: python3 experiments/e0_pilot.py
Writes results/e0_pilot.json
"""
from __future__ import annotations
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Force the project-local HF cache regardless of any pre-set HF_HOME in the
# shell (the instance's default /workspace/.hf_home is root-owned and not
# writable by this user -- see CLAUDE.md Section 6).
os.environ["HF_HOME"] = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".hf_home")

import numpy as np
import torch
import yaml
from PIL import Image

from physweep.render import simulate_projectile, N_FRAMES, DISK_VALUE
from physweep.track import centroid_track, pixel_y_to_physics_y
from physweep_metrics import fit_gravity_from_trajectory, faithfulness_slope, bootstrap_ci, pre

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "physweep", "configs", "systems.yaml")
RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
FIT_R2_GATE = 0.8
GEN_RESOLUTION = 512   # LTX-Video is trained at ~512-1216px; 256px caused instability (see module docstring)

NEGATIVE_PROMPT = "blurry, distorted, artifacts, morphing, multiple balls, text, watermark"


def gravity_prompt(g: float) -> str:
    """C2 text-specified conditioning: name the gravity magnitude explicitly
    plus a qualitative anchor, so the model has an actual chance of mapping
    text to acceleration rather than a single ambiguous adjective."""
    if g <= 2.0:
        qual = "extremely weak gravity, like the Moon, very gentle slow-motion drifting fall"
    elif g <= 6.0:
        qual = "weak gravity, slow floaty fall"
    elif g <= 11.0:
        qual = "normal Earth-like gravity, natural falling speed"
    elif g <= 16.0:
        qual = "strong gravity, fast falling speed"
    else:
        qual = "extremely strong gravity, like Jupiter, violent rapid acceleration downward"
    return (f"a dark ball falling on a plain background with acceleration {g:.1f} meters "
           f"per second squared, {qual}, simple physics simulation")


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def main():
    cfg = load_config()
    proj_cfg = cfg["systems"]["projectile"]
    n_seeds = cfg["render"]["seeds_per_point"]
    g_in = proj_cfg["in_range"][:5]
    g_out = proj_cfg["out_of_range"][:3]

    from diffusers import LTXImageToVideoPipeline
    print("Loading LTX-Video (image2video pipeline)...")
    pipe = LTXImageToVideoPipeline.from_pretrained("Lightricks/LTX-Video", torch_dtype=torch.bfloat16)
    pipe.to("cuda")

    gen_num_frames = 25   # 8k+1 quantization; trim to N_FRAMES=24 for fitting
    rows = []
    t0_all = time.time()
    for theta_set, label in [(g_in, "in"), (g_out, "out")]:
        for g_true in theta_set:
            for seed in range(n_seeds):
                frames_gt, y_true, t_gt = simulate_projectile(g=g_true, seed=seed, n_frames=N_FRAMES)
                first_frame = Image.fromarray(frames_gt[0]).convert("RGB").resize(
                    (GEN_RESOLUTION, GEN_RESOLUTION), Image.NEAREST)
                prompt = gravity_prompt(g_true)

                gen = torch.Generator("cuda").manual_seed(seed)
                out = pipe(
                    image=first_frame, prompt=prompt, negative_prompt=NEGATIVE_PROMPT,
                    height=GEN_RESOLUTION, width=GEN_RESOLUTION, num_frames=gen_num_frames, frame_rate=24,
                    num_inference_steps=30, guidance_scale=3.0, generator=gen,
                )
                video = out.frames[0][:N_FRAMES]
                video_np = np.stack([np.array(f.convert("L").resize((256, 256))) for f in video])

                cx, cy = centroid_track(video_np, disk_value=DISK_VALUE, tol=60)
                if np.any(np.isnan(cy)):
                    g_hat, r2 = float("nan"), 0.0
                else:
                    y_phys = pixel_y_to_physics_y(cy)
                    g_hat, r2 = fit_gravity_from_trajectory(t_gt[:len(cy)], y_phys)

                rows.append(dict(g_true=g_true, g_hat=g_hat, r2=r2, split=label, seed=seed))
                print(f"g_true={g_true:6.2f} seed={seed}: g_hat={g_hat if not np.isnan(g_hat) else float('nan'):.3f} r2={r2:.3f}")

    print(f"\nTotal generation time: {time.time()-t0_all:.1f}s for {len(rows)} clips")

    gated = [r for r in rows if r["r2"] >= FIT_R2_GATE and not np.isnan(r["g_hat"])]
    dropped_rate = 1.0 - len(gated) / max(len(rows), 1)
    print(f"Fit-quality dropped rate: {dropped_rate:.2%} ({len(rows)-len(gated)}/{len(rows)})")

    theta_in = np.array([r["g_true"] for r in gated if r["split"] == "in"])
    hat_in = np.array([r["g_hat"] for r in gated if r["split"] == "in"])

    result = {"rows": rows, "n_gated_in": len(theta_in), "fit_quality_dropped_rate": dropped_rate,
              "conditioning_channel": "C2_text_specified", "n_inference_steps": 30, "guidance_scale": 3.0,
              "resolution": GEN_RESOLUTION}

    if len(theta_in) >= 4:
        slope, slope_lo, slope_hi = bootstrap_ci(faithfulness_slope, theta_in, hat_in, n_boot=2000)
        pre_in, pre_lo, pre_hi = bootstrap_ci(pre, theta_in, hat_in, n_boot=2000)
        result["slope_in"] = [slope, slope_lo, slope_hi]
        result["PRE_in"] = [pre_in, pre_lo, pre_hi]
        print(f"\nslope(in) = {slope:.4f}  95% CI [{slope_lo:.4f}, {slope_hi:.4f}]")
        print(f"PRE(in)   = {pre_in:.4f}  95% CI [{pre_lo:.4f}, {pre_hi:.4f}]")
        print("\n" + "=" * 60)
        if slope_lo > 0 or slope_hi < 0:
            print(f"E0 DECISION: beta CI excludes 0 -> conditioning IS honored.")
            print("Proceed to the full study (E1 onward).")
        else:
            print(f"E0 DECISION: beta CI includes 0 -> conditioning NOT detectably honored.")
            print("Reframe to 'open generators do not honor conditioned dynamics.'")
        print("=" * 60)
    else:
        print("\nNOT ENOUGH GATED IN-RANGE POINTS to compute a slope CI.")
        print("This itself is informative: too many generations failed the fit-quality")
        print("gate (R^2 < 0.8), meaning the tracker lost the object or the physics")
        print("fit was poor -- likely the generator did not produce a trackable,")
        print("physically fittable trajectory. Report this as a finding.")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, "e0_pilot.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, default=lambda o: None if isinstance(o, float) and np.isnan(o) else o)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
