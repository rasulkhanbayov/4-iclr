#!/usr/bin/env python3
"""
experiments/e0_pilot_cogvideox.py
===================================
E0 — PILOT / DECISION GATE, repeated on CogVideoX-5B-I2V (zai-org/CogVideoX-5b-I2V).

Rationale: E0 on LTX-Video (experiments/e0_pilot.py) returned a solid,
confound-checked null (slope(in) 95% CI includes 0 both with the ball near
the ground and clearly mid-air) under C2 (text-specified) conditioning. A
null on one model does not support a general claim about video generators
-- this script repeats the identical experiment design on a second, larger
model to see whether the null replicates or is LTX-Video-specific. See
CLAUDE.md Section 5 for the full LTX-Video E0 account.

Conditioning channel: C2 (text-specified), same as the final LTX-Video
approach -- CogVideoXImageToVideoPipeline also only supports single-image
conditioning (no first+last-frame parameter), so true C1 (frame-implied,
multi-frame) is not testable with this pipeline either. Consistent with the
LTX-Video experiment for a fair comparison.

Decision gate (from physweep_runbook.txt / CLAUDE.md Section 4):
  beta 95% CI excludes 0  -> conditioning is honored; proceed to full study.
  beta 95% CI includes 0  -> reframe: "conditioning not honored."

Usage: python3 experiments/e0_pilot_cogvideox.py
Writes results/e0_pilot_cogvideox.json
"""
from __future__ import annotations
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HF_HOME"] = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".hf_home")

import numpy as np
import torch
import yaml
from PIL import Image

from physweep.render import simulate_projectile, N_FRAMES, DISK_VALUE
from physweep.track import centroid_track, pixel_y_to_physics_y
from physweep_metrics import fit_gravity_from_trajectory, faithfulness_slope, bootstrap_ci, pre
from experiments.e0_pilot import gravity_prompt, NEGATIVE_PROMPT

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "physweep", "configs", "systems.yaml")
RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
FIT_R2_GATE = 0.8
GEN_HEIGHT, GEN_WIDTH = 480, 720   # CogVideoX-5b-I2V native training resolution
GROUND_CLEARANCE_PX = 100          # ball clearly mid-air; see LTX-Video E0 v3 confound check


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def main():
    cfg = load_config()
    proj_cfg = cfg["systems"]["projectile"]
    n_seeds = cfg["render"]["seeds_per_point"]
    g_in = proj_cfg["in_range"][:5]
    g_out = proj_cfg["out_of_range"][:3]

    from diffusers import CogVideoXImageToVideoPipeline
    print("Loading CogVideoX-5B-I2V pipeline...")
    pipe = CogVideoXImageToVideoPipeline.from_pretrained(
        "zai-org/CogVideoX-5b-I2V", torch_dtype=torch.bfloat16)
    pipe.to("cuda")
    pipe.vae.enable_tiling()   # 480x720 video VAE decode is memory-heavy on a single card

    rows = []
    t0_all = time.time()
    for theta_set, label in [(g_in, "in"), (g_out, "out")]:
        for g_true in theta_set:
            for seed in range(n_seeds):
                frames_gt, y_true, t_gt = simulate_projectile(
                    g=g_true, seed=seed, n_frames=N_FRAMES, ground_clearance_px=GROUND_CLEARANCE_PX)
                first_frame = Image.fromarray(frames_gt[0]).convert("RGB").resize(
                    (GEN_WIDTH, GEN_HEIGHT), Image.NEAREST)
                prompt = gravity_prompt(g_true)

                gen = torch.Generator("cuda").manual_seed(seed)
                out = pipe(
                    image=first_frame, prompt=prompt, negative_prompt=NEGATIVE_PROMPT,
                    height=GEN_HEIGHT, width=GEN_WIDTH, num_frames=49,
                    num_inference_steps=30, guidance_scale=6.0, generator=gen,
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
              "conditioning_channel": "C2_text_specified", "model": "zai-org/CogVideoX-5b-I2V",
              "n_inference_steps": 30, "guidance_scale": 6.0, "resolution": [GEN_HEIGHT, GEN_WIDTH],
              "ground_clearance_px": GROUND_CLEARANCE_PX}

    if len(theta_in) >= 4:
        slope, slope_lo, slope_hi = bootstrap_ci(faithfulness_slope, theta_in, hat_in, n_boot=2000)
        pre_in, pre_lo, pre_hi = bootstrap_ci(pre, theta_in, hat_in, n_boot=2000)
        result["slope_in"] = [slope, slope_lo, slope_hi]
        result["PRE_in"] = [pre_in, pre_lo, pre_hi]
        print(f"\nslope(in) = {slope:.4f}  95% CI [{slope_lo:.4f}, {slope_hi:.4f}]")
        print(f"PRE(in)   = {pre_in:.4f}  95% CI [{pre_lo:.4f}, {pre_hi:.4f}]")
        print("\n" + "=" * 60)
        if slope_lo > 0 or slope_hi < 0:
            print(f"E0 DECISION (CogVideoX): beta CI excludes 0 -> conditioning IS honored.")
        else:
            print(f"E0 DECISION (CogVideoX): beta CI includes 0 -> conditioning NOT detectably honored.")
        print("=" * 60)
    else:
        print("\nNOT ENOUGH GATED IN-RANGE POINTS to compute a slope CI.")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, "e0_pilot_cogvideox.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, default=lambda o: None if isinstance(o, float) and np.isnan(o) else o)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
