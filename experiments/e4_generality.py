#!/usr/bin/env python3
"""
experiments/e4_generality.py
==============================
E4 — GENERALITY ACROSS SYSTEMS (paper Section "Experimental Protocol").

Repeats E0/E1's design (C2 text-specified conditioning, mid-air/clearly-
readable starting configuration, single first-frame conditioning) across
the remaining 5 sweep axes not yet tested: pendulum omega, pendulum zeta,
bouncing ball restitution, spring-mass stiffness, inclined slide friction.
Projectile (gravity) was already covered by E0/E1.

Usage:
  python3 experiments/e4_generality.py --model ltx
  python3 experiments/e4_generality.py --model cogvideox

Writes results/e4_{system}_{model}.json per system, plus a combined
results/e4_generality_{model}.json summary.
"""
from __future__ import annotations
import sys, os, json, time, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HF_HOME"] = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".hf_home")

import numpy as np
import torch
import yaml
from PIL import Image

from physweep.render import (
    simulate_damped_pendulum, simulate_bouncing_ball, simulate_spring_mass,
    simulate_inclined_slide, N_FRAMES, DISK_VALUE,
)
from physweep.track import centroid_track, pixel_y_to_physics_y, px_to_m
from physweep_metrics import (
    fit_omega_from_crossings, fit_zeta_from_envelope, fit_restitution_from_bounces,
    fit_friction_from_slide, friction_from_acceleration, faithfulness_slope,
    spearman_rho, pre, bootstrap_ci, damped_sine_r2,
)

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "physweep", "configs", "systems.yaml")
RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
FIT_R2_GATE = 0.8
NEGATIVE_PROMPT = "blurry, distorted, artifacts, morphing, multiple objects, text, watermark"


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Per-system prompt builders (C2: name the physical regime explicitly)
# ---------------------------------------------------------------------------
def pendulum_omega_prompt(omega: float) -> str:
    if omega <= 3: qual = "swinging slowly, low frequency oscillation"
    elif omega <= 6: qual = "swinging at a natural, moderate speed"
    else: qual = "swinging extremely fast, rapid high-frequency oscillation"
    return (f"a dark ball on a pendulum swinging with angular frequency {omega:.1f} radians per "
           f"second, {qual}, simple physics simulation, plain background")


def pendulum_zeta_prompt(zeta: float) -> str:
    if zeta <= 0.1: qual = "swinging with almost no damping, oscillating steadily for a long time"
    elif zeta <= 0.3: qual = "swinging with noticeable damping, the swings shrinking over time"
    else: qual = "heavily damped, quickly settling to a stop, barely swinging at all"
    return (f"a dark ball on a pendulum with damping ratio {zeta:.2f}, {qual}, "
           f"simple physics simulation, plain background")


def bouncing_ball_prompt(e: float) -> str:
    if e <= 0.4: qual = "a dead, unbouncy ball that barely bounces at all and quickly stops"
    elif e <= 0.9: qual = "a normal bouncy ball bouncing with decreasing height each time"
    else: qual = "an extremely bouncy, superball-like ball that keeps bouncing almost as high each time"
    return (f"a dark ball bouncing on the ground with coefficient of restitution {e:.2f}, "
           f"{qual}, simple physics simulation, plain background")


def spring_mass_prompt(k: float) -> str:
    if k <= 15: qual = "a very soft, loose spring oscillating slowly"
    elif k <= 100: qual = "a normal spring oscillating at a moderate rate"
    else: qual = "an extremely stiff, rigid spring oscillating very rapidly"
    return (f"a dark ball attached to a spring with stiffness {k:.1f} newtons per meter, "
           f"{qual}, simple physics simulation, plain background")


def inclined_slide_prompt(mu: float) -> str:
    if mu <= 0.05: qual = "an almost frictionless surface, the ball sliding very fast with little resistance"
    elif mu <= 0.4: qual = "a normal surface with moderate friction, sliding steadily"
    else: qual = "an extremely high-friction, sticky surface, the ball barely sliding at all"
    return (f"a dark ball sliding down an incline with friction coefficient {mu:.2f}, "
           f"{qual}, simple physics simulation, plain background")


# ---------------------------------------------------------------------------
# Per-system runners: render -> generate -> track -> fit
# ---------------------------------------------------------------------------
def run_pendulum_omega(pipe, generate_fn, cfg, n_seeds):
    sysc = cfg["systems"]["damped_pendulum_omega"]
    n_frames = sysc.get("n_frames", N_FRAMES)
    zeta = sysc["fixed_zeta"]
    rows = []
    for theta_set, label in [(sysc["in_range"], "in"), (sysc["out_of_range"], "out")]:
        for om_true in theta_set:
            for seed in range(n_seeds):
                frames_gt, bx_true, t_gt = simulate_damped_pendulum(
                    omega=om_true, zeta=zeta, seed=seed, n_frames=n_frames)
                first_frame = Image.fromarray(frames_gt[0]).convert("RGB")
                prompt = pendulum_omega_prompt(om_true)
                video_np = generate_fn(first_frame, prompt, seed, n_frames)
                cx, cy = centroid_track(video_np, disk_value=DISK_VALUE, tol=60)
                if np.any(np.isnan(cx)):
                    om_hat, r2 = float("nan"), 0.0
                else:
                    om_hat, r2 = fit_omega_from_crossings(t_gt[:len(cx)], cx)
                rows.append(dict(theta=om_true, theta_hat=om_hat, r2=r2, split=label, seed=seed))
                print(f"  omega_true={om_true:6.2f} seed={seed}: omega_hat={om_hat if not np.isnan(om_hat) else float('nan'):.3f} r2={r2:.3f}")
    return rows


def run_pendulum_zeta(pipe, generate_fn, cfg, n_seeds):
    sysc = cfg["systems"]["damped_pendulum_zeta"]
    n_frames = sysc.get("n_frames", N_FRAMES)
    omega = sysc["fixed_omega"]
    rows = []
    for theta_set, label in [(sysc["in_range"], "in"), (sysc["out_of_range"], "out")]:
        for zeta_true in theta_set:
            for seed in range(n_seeds):
                frames_gt, bx_true, t_gt = simulate_damped_pendulum(
                    omega=omega, zeta=zeta_true, seed=seed, n_frames=n_frames)
                first_frame = Image.fromarray(frames_gt[0]).convert("RGB")
                prompt = pendulum_zeta_prompt(zeta_true)
                video_np = generate_fn(first_frame, prompt, seed, n_frames)
                cx, cy = centroid_track(video_np, disk_value=DISK_VALUE, tol=60)
                if np.any(np.isnan(cx)):
                    zeta_hat, r2 = float("nan"), 0.0
                else:
                    om_hat, _ = fit_omega_from_crossings(t_gt[:len(cx)], cx)
                    if np.isnan(om_hat):
                        zeta_hat, r2 = float("nan"), 0.0
                    else:
                        zeta_hat, r2 = fit_zeta_from_envelope(t_gt[:len(cx)], cx, om_hat)
                rows.append(dict(theta=zeta_true, theta_hat=zeta_hat, r2=r2, split=label, seed=seed))
                print(f"  zeta_true={zeta_true:6.2f} seed={seed}: zeta_hat={zeta_hat if not np.isnan(zeta_hat) else float('nan'):.3f} r2={r2:.3f}")
    return rows


def run_bouncing_ball(pipe, generate_fn, cfg, n_seeds):
    sysc = cfg["systems"]["bouncing_ball"]
    n_frames = N_FRAMES
    rows = []
    for theta_set, label in [(sysc["in_range"], "in"), (sysc["out_of_range"], "out")]:
        for e_true in theta_set:
            for seed in range(n_seeds):
                frames_gt, ys_true, t_gt, peaks_true = simulate_bouncing_ball(e=e_true, seed=seed, n_frames=n_frames)
                first_frame = Image.fromarray(frames_gt[0]).convert("RGB")
                prompt = bouncing_ball_prompt(e_true)
                video_np = generate_fn(first_frame, prompt, seed, n_frames)
                cx, cy = centroid_track(video_np, disk_value=DISK_VALUE, tol=60)
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
                print(f"  e_true={e_true:6.2f} seed={seed}: e_hat={e_hat if not np.isnan(e_hat) else float('nan'):.3f} r2={r2:.3f}")
    return rows


def run_spring_mass(pipe, generate_fn, cfg, n_seeds):
    sysc = cfg["systems"]["spring_mass"]
    n_frames = sysc.get("n_frames", N_FRAMES)
    mass = sysc["mass_kg"]
    rows = []
    for theta_set, label in [(sysc["in_range"], "in"), (sysc["out_of_range"], "out")]:
        for k_true in theta_set:
            for seed in range(n_seeds):
                frames_gt, xs_true, t_gt = simulate_spring_mass(k=k_true, seed=seed, n_frames=n_frames, mass_kg=mass)
                first_frame = Image.fromarray(frames_gt[0]).convert("RGB")
                prompt = spring_mass_prompt(k_true)
                video_np = generate_fn(first_frame, prompt, seed, n_frames)
                cx, cy = centroid_track(video_np, disk_value=DISK_VALUE, tol=60)
                if np.any(np.isnan(cx)):
                    k_hat, r2 = float("nan"), 0.0
                else:
                    om_hat, r2 = fit_omega_from_crossings(t_gt[:len(cx)], cx)
                    k_hat = om_hat ** 2 * mass if not np.isnan(om_hat) else float("nan")
                rows.append(dict(theta=k_true, theta_hat=k_hat, r2=r2, split=label, seed=seed))
                print(f"  k_true={k_true:6.1f} seed={seed}: k_hat={k_hat if not np.isnan(k_hat) else float('nan'):.3f} r2={r2:.3f}")
    return rows


def run_inclined_slide(pipe, generate_fn, cfg, n_seeds):
    sysc = cfg["systems"]["inclined_slide"]
    incline_deg = sysc["incline_deg"]
    incline_rad = np.deg2rad(incline_deg)
    g_internal = 300.0
    dx, dy = np.cos(incline_rad), np.sin(incline_rad)
    rows = []
    for theta_set, label in [(sysc["in_range"], "in"), (sysc["out_of_range"], "out")]:
        for mu_true in theta_set:
            for seed in range(n_seeds):
                frames_gt, s_true, t_gt = simulate_inclined_slide(mu=mu_true, seed=seed, incline_deg=incline_deg)
                first_frame = Image.fromarray(frames_gt[0]).convert("RGB")
                prompt = inclined_slide_prompt(mu_true)
                video_np = generate_fn(first_frame, prompt, seed, N_FRAMES)
                cx, cy = centroid_track(video_np, disk_value=DISK_VALUE, tol=60)
                if np.any(np.isnan(cx)):
                    mu_hat, r2 = float("nan"), 0.0
                else:
                    s_px = (cx - cx[0]) * dx + (cy - cy[0]) * dy
                    a_hat, r2 = fit_friction_from_slide(t_gt[:len(s_px)], s_px)
                    mu_hat = friction_from_acceleration(a_hat, incline_rad, g=g_internal)
                rows.append(dict(theta=mu_true, theta_hat=mu_hat, r2=r2, split=label, seed=seed))
                print(f"  mu_true={mu_true:6.2f} seed={seed}: mu_hat={mu_hat if not np.isnan(mu_hat) else float('nan'):.3f} r2={r2:.3f}")
    return rows


SYSTEMS = {
    "pendulum_omega": run_pendulum_omega,
    "pendulum_zeta": run_pendulum_zeta,
    "bouncing_ball": run_bouncing_ball,
    "spring_mass": run_spring_mass,
    "inclined_slide": run_inclined_slide,
}


def summarize(rows):
    gated = [r for r in rows if r["r2"] is not None and r["r2"] >= FIT_R2_GATE and not np.isnan(r["theta_hat"])]
    dropped_rate = 1.0 - len(gated) / max(len(rows), 1)
    theta_in = np.array([r["theta"] for r in gated if r["split"] == "in"])
    hat_in = np.array([r["theta_hat"] for r in gated if r["split"] == "in"])
    out = {"n_total": len(rows), "n_gated_in": len(theta_in), "fit_quality_dropped_rate": dropped_rate}
    if len(theta_in) >= 4:
        slope, slo, shi = bootstrap_ci(faithfulness_slope, theta_in, hat_in, n_boot=2000)
        p, plo, phi = bootstrap_ci(pre, theta_in, hat_in, n_boot=2000)
        out["slope_beta_in"] = [slope, slo, shi]
        out["PRE_in"] = [p, plo, phi]
    return out


MAX_GEN_FRAMES = 97   # generator-practicality cap; ground truth may use more
                      # frames (e.g. 180 for pendulum_omega/spring_mass) but
                      # neither model was validated for clips that long and
                      # the cost is prohibitive (measured: CogVideoX takes
                      # ~5.9min for 97 frames vs ~2.3min for 49). Capping
                      # here means low-omega/low-k points may still fail the
                      # fitter's period requirement on GENERATED video even
                      # though they pass on ground truth (E6) -- that's a
                      # real, informative distinction between measurement
                      # validity and generator practicality, not a bug.


def make_ltx_generate_fn(pipe):
    def generate_fn(first_frame, prompt, seed, n_frames):
        n_frames = min(n_frames, MAX_GEN_FRAMES)
        img = first_frame.resize((512, 512), Image.NEAREST)
        gen = torch.Generator("cuda").manual_seed(seed)
        gen_frames = ((n_frames - 1) // 8 + 1) * 8 + 1  # 8k+1 quantization
        out = pipe(image=img, prompt=prompt, negative_prompt=NEGATIVE_PROMPT,
                  height=512, width=512, num_frames=gen_frames, frame_rate=24,
                  num_inference_steps=30, guidance_scale=3.0, generator=gen)
        video = out.frames[0][:n_frames]
        return np.stack([np.array(f.convert("L").resize((256, 256))) for f in video])
    return generate_fn


def make_cogvideox_generate_fn(pipe):
    def generate_fn(first_frame, prompt, seed, n_frames):
        n_frames = min(n_frames, MAX_GEN_FRAMES)
        img = first_frame.resize((720, 480), Image.NEAREST)
        gen = torch.Generator("cuda").manual_seed(seed)
        gen_frames = ((n_frames - 1) // 4 + 1) * 4 + 1  # 4k+1 quantization
        out = pipe(image=img, prompt=prompt, negative_prompt=NEGATIVE_PROMPT,
                  height=480, width=720, num_frames=gen_frames,
                  num_inference_steps=30, guidance_scale=6.0, generator=gen)
        video = out.frames[0][:n_frames]
        return np.stack([np.array(f.convert("L").resize((256, 256))) for f in video])
    return generate_fn


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["ltx", "cogvideox"], required=True)
    parser.add_argument("--systems", nargs="*", default=list(SYSTEMS.keys()))
    args = parser.parse_args()

    cfg = load_config()
    n_seeds = cfg["render"]["seeds_per_point"]

    if args.model == "ltx":
        from diffusers import LTXImageToVideoPipeline
        print("Loading LTX-Video...")
        pipe = LTXImageToVideoPipeline.from_pretrained("Lightricks/LTX-Video", torch_dtype=torch.bfloat16)
        pipe.to("cuda")
        generate_fn = make_ltx_generate_fn(pipe)
        model_tag = "ltx"
    else:
        from diffusers import CogVideoXImageToVideoPipeline
        print("Loading CogVideoX-5B-I2V...")
        pipe = CogVideoXImageToVideoPipeline.from_pretrained("zai-org/CogVideoX-5b-I2V", torch_dtype=torch.bfloat16)
        pipe.to("cuda")
        pipe.vae.enable_tiling()
        generate_fn = make_cogvideox_generate_fn(pipe)
        model_tag = "cogvideox"

    all_summaries = {}
    for sys_name in args.systems:
        print(f"\n{'='*70}\n{sys_name} ({model_tag})\n{'='*70}")
        t0 = time.time()
        rows = SYSTEMS[sys_name](pipe, generate_fn, cfg, n_seeds)
        elapsed = time.time() - t0
        summary = summarize(rows)
        summary["elapsed_seconds"] = elapsed
        all_summaries[sys_name] = summary
        print(f"\n{sys_name}: n_gated_in={summary['n_gated_in']}/{summary['n_total']} "
             f"dropped_rate={summary['fit_quality_dropped_rate']:.2%} elapsed={elapsed:.0f}s")
        if "slope_beta_in" in summary:
            s = summary["slope_beta_in"]
            print(f"  slope beta (in) = {s[0]:.4f}  95% CI [{s[1]:.4f}, {s[2]:.4f}]")

        out_path = os.path.join(RESULTS_DIR, f"e4_{sys_name}_{model_tag}.json")
        with open(out_path, "w") as f:
            json.dump({"rows": rows, "summary": summary}, f, indent=2,
                     default=lambda o: None if isinstance(o, float) and np.isnan(o) else o)
        print(f"Wrote {out_path}")

    combined_path = os.path.join(RESULTS_DIR, f"e4_generality_{model_tag}.json")
    with open(combined_path, "w") as f:
        json.dump(all_summaries, f, indent=2)
    print(f"\nWrote combined summary: {combined_path}")

    print(f"\n{'='*70}\nE4 SUMMARY ({model_tag})\n{'='*70}")
    print(f"{'System':<20} {'slope (in)':<24} {'dropped_rate':<14}")
    for name, s in all_summaries.items():
        sl = s.get("slope_beta_in")
        sl_str = f"{sl[0]:.3f} [{sl[1]:.3f},{sl[2]:.3f}]" if sl else "n/a"
        print(f"{name:<20} {sl_str:<24} {s['fit_quality_dropped_rate']:<14.2%}")


if __name__ == "__main__":
    main()
