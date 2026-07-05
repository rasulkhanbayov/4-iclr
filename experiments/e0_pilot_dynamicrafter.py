#!/usr/bin/env python3
"""
experiments/e0_pilot_dynamicrafter.py
========================================
E0 — PILOT / DECISION GATE, repeated on DynamiCrafter (Doubiiu/DynamiCrafter_512).

Third model in the runbook's queue. Unlike LTX-Video/CogVideoX (diffusers
pipelines, called in-process), DynamiCrafter ships as a standalone research
codebase (not diffusers-compatible) with a file-based, subprocess-driven
interface: write a conditioning image + a single-line prompt.txt to a
directory, shell out to its scripts/evaluation/inference.py, read back the
.mp4 it writes. See CLAUDE.md Section 6 for the full integration account
(isolated venv, dependency version fixes: open_clip_torch pinned to 2.22.0
matching its original requirements.txt -- NOT the latest, which changed the
VisionTransformer API it depends on; and a source patch replacing
torchvision.io.write_video, removed in torchvision>=0.20, with imageio).

Conditioning channel: C2 (text-specified), consistent with the LTX-Video/
CogVideoX experiments -- DynamiCrafter's --text_input flag takes a prompt
per conditioning image, same style as gravity_prompt() used elsewhere.

Model specifics: generates exactly 16 frames (not configurable), frame_stride
acts as an FPS-like knob for the 512 checkpoint (smaller = more motion; we
use 24, matching our own render fps so the fitter's dt is exactly right).

Usage: python3 experiments/e0_pilot_dynamicrafter.py
Writes results/e0_pilot_dynamicrafter.json
"""
from __future__ import annotations
import sys, os, json, time, subprocess, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HF_HOME"] = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".hf_home")

import numpy as np
import yaml
from PIL import Image

from physweep.render import simulate_projectile, N_FRAMES, DISK_VALUE
from physweep.track import centroid_track, pixel_y_to_physics_y
from physweep_metrics import fit_gravity_from_trajectory, faithfulness_slope, bootstrap_ci, pre
from experiments.e0_pilot import gravity_prompt

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DC_ROOT = os.path.join(REPO_ROOT, "external", "DynamiCrafter")
DC_PYTHON = os.path.join(REPO_ROOT, "external", "dynamicrafter_venv", "bin", "python")
CONFIG_PATH = os.path.join(REPO_ROOT, "physweep", "configs", "systems.yaml")
RESULTS_DIR = os.path.join(REPO_ROOT, "results")
FIT_R2_GATE = 0.8
GEN_HEIGHT, GEN_WIDTH = 320, 512   # DynamiCrafter_512's native resolution
DC_N_FRAMES = 16                   # fixed by the model; not configurable
FRAME_STRIDE = 24                  # FPS-like control for the 512 checkpoint
GROUND_CLEARANCE_PX = 100          # ball clearly mid-air; see LTX-Video E0 v3


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def run_dynamicrafter(image: Image.Image, prompt: str, seed: int, work_dir: str) -> np.ndarray:
    """Writes image+prompt, shells out to DynamiCrafter's inference script,
    reads back the generated video as a (T, H, W) grayscale numpy array."""
    prompt_dir = os.path.join(work_dir, "input")
    results_dir = os.path.join(work_dir, "results")
    os.makedirs(prompt_dir, exist_ok=True)
    if os.path.exists(results_dir):
        shutil.rmtree(results_dir)

    img_name = "clip"
    image.resize((GEN_WIDTH, GEN_HEIGHT), Image.NEAREST).save(os.path.join(prompt_dir, f"{img_name}.png"))
    with open(os.path.join(prompt_dir, "prompts.txt"), "w") as f:
        f.write(prompt + "\n")

    cmd = [
        DC_PYTHON, "scripts/evaluation/inference.py",
        "--seed", str(seed),
        "--ckpt_path", "checkpoints/dynamicrafter_512_v1/model.ckpt",
        "--config", "configs/inference_512_v1.0.yaml",
        "--savedir", results_dir,
        "--n_samples", "1",
        "--bs", "1", "--height", str(GEN_HEIGHT), "--width", str(GEN_WIDTH),
        "--unconditional_guidance_scale", "7.5",
        "--ddim_steps", "50",
        "--ddim_eta", "1.0",
        "--prompt_dir", prompt_dir,
        "--text_input",
        "--video_length", str(DC_N_FRAMES),
        "--frame_stride", str(FRAME_STRIDE),
        "--timestep_spacing", "uniform_trailing", "--guidance_rescale", "0.7", "--perframe_ae",
    ]
    proc = subprocess.run(cmd, cwd=DC_ROOT, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        print("DynamiCrafter subprocess FAILED:")
        print(proc.stderr[-3000:])
        return None

    out_path = os.path.join(results_dir, "samples_separate", f"{img_name}_sample0.mp4")
    if not os.path.exists(out_path):
        print(f"Expected output not found: {out_path}")
        return None

    import imageio.v3 as iio
    frames = iio.imread(out_path)  # (T, H, W, 3) uint8
    gray = np.array([np.array(Image.fromarray(f).convert("L").resize((256, 256))) for f in frames])
    return gray


def main():
    cfg = load_config()
    proj_cfg = cfg["systems"]["projectile"]
    n_seeds = cfg["render"]["seeds_per_point"]
    g_in = proj_cfg["in_range"][:5]
    g_out = proj_cfg["out_of_range"][:3]

    work_dir = os.path.join(DC_ROOT, "e0_run")
    os.makedirs(work_dir, exist_ok=True)

    # DynamiCrafter's dt is set by frame_stride (FPS-equivalent) at 16 frames;
    # ground truth must be rendered at the SAME implied dt/duration for the
    # fitter's t array to correspond to actual generated frame timing.
    dt = 1.0 / FRAME_STRIDE
    t_dc = np.arange(DC_N_FRAMES) * dt

    rows = []
    t0_all = time.time()
    for theta_set, label in [(g_in, "in"), (g_out, "out")]:
        for g_true in theta_set:
            for seed in range(n_seeds):
                # render ground truth at DC_N_FRAMES/FRAME_STRIDE so the first
                # conditioning frame and the timestamps match what DynamiCrafter
                # will actually produce
                frames_gt, y_true, t_gt = simulate_projectile(
                    g=g_true, seed=seed, n_frames=DC_N_FRAMES, ground_clearance_px=GROUND_CLEARANCE_PX)
                first_frame = Image.fromarray(frames_gt[0]).convert("RGB")
                prompt = gravity_prompt(g_true)

                video_np = run_dynamicrafter(first_frame, prompt, seed, work_dir)
                if video_np is None:
                    rows.append(dict(g_true=g_true, g_hat=float("nan"), r2=0.0, split=label, seed=seed))
                    print(f"g_true={g_true:6.2f} seed={seed}: GENERATION FAILED")
                    continue

                cx, cy = centroid_track(video_np, disk_value=DISK_VALUE, tol=60)
                if np.any(np.isnan(cy)):
                    g_hat, r2 = float("nan"), 0.0
                else:
                    y_phys = pixel_y_to_physics_y(cy)
                    g_hat, r2 = fit_gravity_from_trajectory(t_dc[:len(cy)], y_phys)

                rows.append(dict(g_true=g_true, g_hat=g_hat, r2=r2, split=label, seed=seed))
                print(f"g_true={g_true:6.2f} seed={seed}: g_hat={g_hat if not np.isnan(g_hat) else float('nan'):.3f} r2={r2:.3f}")

    print(f"\nTotal time: {time.time()-t0_all:.1f}s for {len(rows)} clips")

    gated = [r for r in rows if r["r2"] >= FIT_R2_GATE and not np.isnan(r["g_hat"])]
    dropped_rate = 1.0 - len(gated) / max(len(rows), 1)
    print(f"Fit-quality dropped rate: {dropped_rate:.2%} ({len(rows)-len(gated)}/{len(rows)})")

    theta_in = np.array([r["g_true"] for r in gated if r["split"] == "in"])
    hat_in = np.array([r["g_hat"] for r in gated if r["split"] == "in"])

    result = {"rows": rows, "n_gated_in": len(theta_in), "fit_quality_dropped_rate": dropped_rate,
              "conditioning_channel": "C2_text_specified", "model": "Doubiiu/DynamiCrafter_512",
              "resolution": [GEN_HEIGHT, GEN_WIDTH], "n_frames": DC_N_FRAMES,
              "frame_stride": FRAME_STRIDE, "ground_clearance_px": GROUND_CLEARANCE_PX}

    if len(theta_in) >= 4:
        slope, slope_lo, slope_hi = bootstrap_ci(faithfulness_slope, theta_in, hat_in, n_boot=2000)
        pre_in, pre_lo, pre_hi = bootstrap_ci(pre, theta_in, hat_in, n_boot=2000)
        result["slope_in"] = [slope, slope_lo, slope_hi]
        result["PRE_in"] = [pre_in, pre_lo, pre_hi]
        print(f"\nslope(in) = {slope:.4f}  95% CI [{slope_lo:.4f}, {slope_hi:.4f}]")
        print(f"PRE(in)   = {pre_in:.4f}  95% CI [{pre_lo:.4f}, {pre_hi:.4f}]")
        print("\n" + "=" * 60)
        if slope_lo > 0 or slope_hi < 0:
            print("E0 DECISION (DynamiCrafter): beta CI excludes 0 -> conditioning IS honored.")
        else:
            print("E0 DECISION (DynamiCrafter): beta CI includes 0 -> conditioning NOT detectably honored.")
        print("=" * 60)
    else:
        print("\nNOT ENOUGH GATED IN-RANGE POINTS to compute a slope CI.")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, "e0_pilot_dynamicrafter.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, default=lambda o: None if isinstance(o, float) and np.isnan(o) else o)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
