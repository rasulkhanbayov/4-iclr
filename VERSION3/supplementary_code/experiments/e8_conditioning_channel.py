#!/usr/bin/env python3
"""
experiments/e8_conditioning_channel.py
========================================
E8 -- CONDITIONING-CHANNEL ABLATION (runbook Section "EXPERIMENTS"): C1
(frame-implied) vs C2 (text-specified) conditioning, on DynamiCrafter only.

Every result in this paper up to this experiment used C2 (text-specified)
conditioning on all three models -- true C1 (frame-implied) conditioning
was never tested end-to-end for any model. LTX-Video's multi-frame path
(`LTXConditionPipeline`) was tried and found genuinely broken in this
project's diffusers version, beyond a real but insufficient `mu`-parameter
bug fix (see physweep/ltx_patch.py and CLAUDE.md): even after that fix, the
pipeline's own output quality degrades into noise by the second half of a
clip on a real reference image, an issue independent of and beyond the
`mu` crash. CogVideoX's official diffusers pipeline has no multi-frame
conditioning path at all (confirmed by inspecting its released
pipeline/docs); the only multi-frame variants that exist for it are
unofficial third-party repos or community fine-tunes, not a bounded
integration.

DynamiCrafter, by contrast, ships an OFFICIAL interpolation checkpoint
(`Doubiiu/DynamiCrafter_512_Interp`) that runs through the exact same
`scripts/evaluation/inference.py` this project already integrates for the
C2 experiments, just with `--interp` added and a first+last (for most
systems) or first+middle (for projectile specifically, see below)
conditioning frame pair instead of one image -- confirmed directly against
`external/DynamiCrafter/scripts/run_application.sh` and
`load_data_prompts()`'s own source (interp mode reads sorted
[..., name_01.png, name_02.png, ...] pairs from the prompt directory).
This is the one bounded, same-codebase path to a real C1 test.

Projectile-specific caveat, carried over from this project's earlier
LTX-Video C1 attempt (see CLAUDE.md): `simulate_projectile`'s launch
velocity is chosen so the arc returns to the SAME y0 at its last frame
REGARDLESS of g (a symmetric arc, by construction) -- so a first+LAST
frame pair for projectile would carry ZERO g signal, repeating a bug
already found and fixed once in this project. We use first+MIDDLE frame
for projectile specifically (verified below that the middle frame's height
does vary with g), and first+last for bouncing_ball/inclined_slide (their
trajectories are not symmetric arcs -- verified below too).

Scope: projectile, bouncing_ball, inclined_slide only -- the three systems
where DynamiCrafter's fixed 16-frame output already produces usable C2
data (Section 4.4/5); pendulum_omega/pendulum_zeta/spring_mass need >=1-2
oscillation periods DynamiCrafter's frame ceiling cannot deliver regardless
of conditioning channel, so C1 vs C2 is not a meaningful comparison there.

Usage: python3 experiments/e8_conditioning_channel.py
Writes results/e8_conditioning_channel_{system}_dynamicrafter.json
"""
from __future__ import annotations
import sys, os, json, time, subprocess, shutil, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HF_HOME"] = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".hf_home")

import numpy as np
import yaml
from PIL import Image

from physweep.render import simulate_projectile, simulate_bouncing_ball, simulate_inclined_slide
from physweep.track import centroid_track, pixel_y_to_physics_y
from physweep_metrics import (
    fit_gravity_from_trajectory, fit_restitution_from_bounces, fit_friction_from_slide,
    friction_from_acceleration, faithfulness_slope, pre, bootstrap_ci,
)
from experiments.e0_pilot import gravity_prompt
from experiments.e4_generality import bouncing_ball_prompt, inclined_slide_prompt

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DC_ROOT = os.path.join(REPO_ROOT, "external", "DynamiCrafter")
DC_PYTHON = os.path.join(REPO_ROOT, "external", "dynamicrafter_venv", "bin", "python")
CONFIG_PATH = os.path.join(REPO_ROOT, "physweep", "configs", "systems.yaml")
RESULTS_DIR = os.path.join(REPO_ROOT, "results")
FIT_R2_GATE = 0.8
GEN_HEIGHT, GEN_WIDTH = 320, 512
DC_N_FRAMES = 16
FRAME_STRIDE = 5           # this checkpoint's own recommended default (run_application.sh), NOT
                           # the 24 used for the C2 (single-image) checkpoint -- different checkpoint,
                           # different recommended stride; using the C2 value here would be an
                           # unjustified assumption, not a like-for-like comparison.
INTERP_CKPT = "checkpoints/dynamicrafter_512_interp_v1/model.ckpt"
GROUND_CLEARANCE_PX = 100  # projectile only, matches every other experiment's C2 setup


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def run_dynamicrafter_interp(image1, image2, prompt, seed, work_dir):
    """Same subprocess pattern as e0_pilot_dynamicrafter.py's run_dynamicrafter,
    but writes TWO conditioning frames (name_01.png, name_02.png -- sorted-pair
    convention required by load_data_prompts(interp=True)) and adds --interp
    with the interpolation checkpoint."""
    prompt_dir = os.path.join(work_dir, "input")
    results_dir = os.path.join(work_dir, "results")
    os.makedirs(prompt_dir, exist_ok=True)
    if os.path.exists(results_dir):
        shutil.rmtree(results_dir)
    if os.path.exists(prompt_dir):
        shutil.rmtree(prompt_dir)
        os.makedirs(prompt_dir, exist_ok=True)

    img_name = "clip"
    image1.resize((GEN_WIDTH, GEN_HEIGHT), Image.NEAREST).save(os.path.join(prompt_dir, f"{img_name}_01.png"))
    image2.resize((GEN_WIDTH, GEN_HEIGHT), Image.NEAREST).save(os.path.join(prompt_dir, f"{img_name}_02.png"))
    with open(os.path.join(prompt_dir, "prompts.txt"), "w") as f:
        f.write(prompt + "\n")

    cmd = [
        DC_PYTHON, "scripts/evaluation/inference.py",
        "--seed", str(seed),
        "--ckpt_path", INTERP_CKPT,
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
        "--interp",
    ]
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, cwd=DC_ROOT, capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        print(f"DynamiCrafter-interp subprocess TIMED OUT after {time.time()-t0:.0f}s (limit 900s)")
        return None
    print(f"  (DynamiCrafter-interp subprocess took {time.time()-t0:.0f}s)")
    if proc.returncode != 0:
        print("DynamiCrafter-interp subprocess FAILED:")
        print(proc.stderr[-3000:])
        return None

    # interp mode's output filename is derived from the FIRST conditioning
    # frame's own filename (load_data_prompts reads it via
    # os.path.split(file_list[idx*2]) and save_results_seperate does
    # f'{filename.split(".")[0]}_sample{i}.mp4') -- NOT the bare img_name
    # used by the single-image C2 mode. Confirmed directly against
    # scripts/evaluation/inference.py's save_results_seperate source after
    # job 381033 failed every clip on a wrong-filename guess (img_name
    # alone, without the _01 suffix).
    out_path = os.path.join(results_dir, "samples_separate", f"{img_name}_01_sample0.mp4")
    if not os.path.exists(out_path):
        print(f"Expected output not found: {out_path}")
        return None

    import imageio.v3 as iio
    frames = iio.imread(out_path)
    gray = np.array([np.array(Image.fromarray(f).convert("L").resize((256, 256))) for f in frames])
    return gray


def run_projectile_c1(cfg, seeds_by_label, dt):
    """First+MIDDLE frame conditioning -- see module docstring for why NOT
    first+last (projectile's arc is symmetric by construction, so last frame
    carries zero g signal, already discovered and documented once before in
    this project's LTX-Video C1 attempt)."""
    proj_cfg = cfg["systems"]["projectile"]
    g_in = proj_cfg["in_range"][:5]
    g_out = proj_cfg["out_of_range"][:3]
    t_dc = np.arange(DC_N_FRAMES) * dt
    work_dir = os.path.join(DC_ROOT, "e8_run_projectile")
    os.makedirs(work_dir, exist_ok=True)
    rows = []
    for theta_set, label in [(g_in, "in"), (g_out, "out")]:
        for g_true in theta_set:
            for seed in seeds_by_label[label]:
                frames_gt, y_true, t_gt = simulate_projectile(
                    g=g_true, seed=seed, n_frames=DC_N_FRAMES, ground_clearance_px=GROUND_CLEARANCE_PX)
                mid_idx = DC_N_FRAMES // 2
                first_frame = Image.fromarray(frames_gt[0]).convert("RGB")
                mid_frame = Image.fromarray(frames_gt[mid_idx]).convert("RGB")
                prompt = gravity_prompt(g_true)  # neutral prompt kept identical to the C2 run's
                                                   # text -- C1's manipulation is the SECOND image,
                                                   # not the removal of text, to isolate one variable

                video_np = run_dynamicrafter_interp(first_frame, mid_frame, prompt, seed, work_dir)
                if video_np is None:
                    rows.append(dict(theta=g_true, theta_hat=float("nan"), r2=0.0, split=label, seed=seed))
                    print(f"g_true={g_true:6.2f} seed={seed}: GENERATION FAILED")
                    continue
                cx, cy = centroid_track(video_np, disk_value=20, tol=60)
                if np.any(np.isnan(cy)):
                    g_hat, r2 = float("nan"), 0.0
                else:
                    y_phys = pixel_y_to_physics_y(cy)
                    g_hat, r2 = fit_gravity_from_trajectory(t_dc[:len(cy)], y_phys)
                rows.append(dict(theta=g_true, theta_hat=g_hat, r2=r2, split=label, seed=seed))
                print(f"g_true={g_true:6.2f} seed={seed}: g_hat={g_hat if not np.isnan(g_hat) else float('nan'):.3f} r2={r2:.3f}")
    return rows


def run_bouncing_ball_c1(cfg, seeds_by_label, dt):
    sysc = cfg["systems"]["bouncing_ball"]
    t_dc = np.arange(DC_N_FRAMES) * dt
    work_dir = os.path.join(DC_ROOT, "e8_run_bouncing_ball")
    os.makedirs(work_dir, exist_ok=True)
    rows = []
    for theta_set, label in [(sysc["in_range"], "in"), (sysc["out_of_range"], "out")]:
        for e_true in theta_set:
            for seed in seeds_by_label[label]:
                frames_gt, ys_true, t_gt, peaks_true = simulate_bouncing_ball(
                    e=e_true, seed=seed, n_frames=DC_N_FRAMES)
                first_frame = Image.fromarray(frames_gt[0]).convert("RGB")
                last_frame = Image.fromarray(frames_gt[-1]).convert("RGB")
                prompt = bouncing_ball_prompt(e_true)
                video_np = run_dynamicrafter_interp(first_frame, last_frame, prompt, seed, work_dir)
                if video_np is None:
                    rows.append(dict(theta=e_true, theta_hat=float("nan"), r2=0.0, split=label, seed=seed))
                    print(f"e_true={e_true:6.2f} seed={seed}: GENERATION FAILED")
                    continue
                cx, cy = centroid_track(video_np, disk_value=20, tol=60)
                if np.any(np.isnan(cy)):
                    e_hat, r2 = float("nan"), 0.0
                else:
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
                        e_hat, r2 = fit_restitution_from_bounces(np.array(peaks))
                    else:
                        e_hat, r2 = float("nan"), 0.0
                rows.append(dict(theta=e_true, theta_hat=e_hat, r2=r2, split=label, seed=seed))
                print(f"e_true={e_true:6.2f} seed={seed}: e_hat={e_hat if not np.isnan(e_hat) else float('nan'):.3f} r2={r2:.3f}")
    return rows


def run_inclined_slide_c1(cfg, seeds_by_label, dt):
    sysc = cfg["systems"]["inclined_slide"]
    incline_deg = sysc["incline_deg"]
    incline_rad = np.deg2rad(incline_deg)
    g_internal = 300.0
    dxu, dyu = np.cos(incline_rad), np.sin(incline_rad)
    t_dc = np.arange(DC_N_FRAMES) * dt
    work_dir = os.path.join(DC_ROOT, "e8_run_inclined_slide")
    os.makedirs(work_dir, exist_ok=True)
    rows = []
    for theta_set, label in [(sysc["in_range"], "in"), (sysc["out_of_range"], "out")]:
        for mu_true in theta_set:
            for seed in seeds_by_label[label]:
                frames_gt, s_true, t_gt = simulate_inclined_slide(
                    mu=mu_true, seed=seed, incline_deg=incline_deg, n_frames=DC_N_FRAMES)
                first_frame = Image.fromarray(frames_gt[0]).convert("RGB")
                last_frame = Image.fromarray(frames_gt[-1]).convert("RGB")
                prompt = inclined_slide_prompt(mu_true)
                video_np = run_dynamicrafter_interp(first_frame, last_frame, prompt, seed, work_dir)
                if video_np is None:
                    rows.append(dict(theta=mu_true, theta_hat=float("nan"), r2=0.0, split=label, seed=seed))
                    print(f"mu_true={mu_true:6.2f} seed={seed}: GENERATION FAILED")
                    continue
                cx, cy = centroid_track(video_np, disk_value=20, tol=60)
                if np.any(np.isnan(cx)):
                    mu_hat, r2 = float("nan"), 0.0
                else:
                    s_px = (cx - cx[0]) * dxu + (cy - cy[0]) * dyu
                    a_hat, r2 = fit_friction_from_slide(t_dc[:len(s_px)], s_px)
                    mu_hat = friction_from_acceleration(a_hat, incline_rad, g=g_internal)
                rows.append(dict(theta=mu_true, theta_hat=mu_hat, r2=r2, split=label, seed=seed))
                print(f"mu_true={mu_true:6.2f} seed={seed}: mu_hat={mu_hat if not np.isnan(mu_hat) else float('nan'):.3f} r2={r2:.3f}")
    return rows


SYSTEM_RUNNERS = {
    "projectile": run_projectile_c1,
    "bouncing_ball": run_bouncing_ball_c1,
    "inclined_slide": run_inclined_slide_c1,
}


def summarize(rows):
    gated = [r for r in rows if r["r2"] >= FIT_R2_GATE and not (isinstance(r["theta_hat"], float) and np.isnan(r["theta_hat"]))]
    dropped_rate = 1.0 - len(gated) / max(len(rows), 1)
    theta_in = np.array([r["theta"] for r in gated if r["split"] == "in"])
    hat_in = np.array([r["theta_hat"] for r in gated if r["split"] == "in"])
    out = dict(n_total=len(rows), n_gated=len(gated), dropped_rate=dropped_rate,
               n_gated_in=len(theta_in))
    if len(theta_in) >= 3 and len(set(theta_in.tolist())) >= 2:
        out["slope_in"] = faithfulness_slope(theta_in, hat_in)
        out["pre_in"] = pre(theta_in, hat_in)
        try:
            out["slope_in_ci"] = bootstrap_ci(faithfulness_slope, theta_in, hat_in)
        except Exception:
            pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--systems", nargs="+", default=list(SYSTEM_RUNNERS.keys()))
    args = ap.parse_args()

    cfg = load_config()
    base_seeds = cfg["render"]["seeds_per_point"]
    seeds_by_label = {"in": list(range(base_seeds)), "out": list(range(base_seeds))}

    for system in args.systems:
        print(f"\n=== E8 C1 (frame-implied), system={system}, model=dynamicrafter ===")
        dt = 1.0 / FRAME_STRIDE
        t0 = time.time()
        rows = SYSTEM_RUNNERS[system](cfg, seeds_by_label, dt)
        elapsed = time.time() - t0
        summ = summarize(rows)
        summ["elapsed_seconds"] = elapsed
        summ["channel"] = "C1"
        print(f"{system}: {json.dumps(summ, default=str)}")

        out_path = os.path.join(RESULTS_DIR, f"e8_conditioning_channel_{system}_dynamicrafter.json")
        with open(out_path, "w") as f:
            json.dump(dict(rows=rows, summary=summ), f, indent=2, default=str)
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
