#!/usr/bin/env python3
"""
experiments/e3e5_extended.py
===============================
E3 (plausibility-measurement gap) + E5 (robustness/ablations b, d, e, f),
built as ONE consolidated harness so each clip is generated exactly ONCE
and every artifact needed by any of these experiments is extracted from
that single generation, rather than regenerating similar clips per
experiment. Reuses e4_generality.py's per-system runners and per-model
generate_fn factories unmodified (imported, not duplicated) -- this script
only WRAPS generate_fn to add video-saving and (optionally) a second
tracker pass, and provides parameter-variant closures for E5(b)/(d)/(e)/(f).

E5(a) (tracker swap, CoTracker3) and E5(c) (fit-gate sensitivity) are
handled elsewhere:
  - E5(c): experiments/e5c_fit_gate_sensitivity.py -- pure re-analysis of
    existing result JSONs, no GPU, no video needed.
  - E5(a): this script's --dual-track flag runs CoTracker3 (physweep/track.py
    cotracker_track()) alongside blob-centroiding on every saved clip, so a
    single --save-video run here ALSO produces E5(a)'s data -- see below.

WHY VIDEO NEEDS SAVING (real discovery this session, 2026-08-2x): every
prior experiment (E0/E1/E4) tracks the generated video in-process and
discards it immediately -- no .mp4 from any past run exists on disk. E3
(VLM plausibility scoring) and E5(a) (a second tracker on the SAME clip)
both need the actual pixels, not just the previously-saved centroid
trajectory, so this script must regenerate rather than reuse.

Usage:
  # Default run: same grid/seeds as E4's existing out-of-range data (so E3's
  # plausibility scores can be paired with PRE(out) from data we ALREADY
  # have adjudicated in results/e2_extrapolation.json), with video saving
  # (for E3) and dual-tracking (for E5a) both on:
  python3 experiments/e3e5_extended.py --model ltx --systems projectile \
      --save-video --dual-track

  # E5(e): guidance-scale sweep (only re-generates, no video/dual-track needed
  # unless you also want E3/E5a coverage at these guidance values):
  python3 experiments/e3e5_extended.py --model ltx --systems projectile \
      --guidance-scale 1.5

  # E5(f): alternate prompt template:
  python3 experiments/e3e5_extended.py --model ltx --systems projectile \
      --prompt-variant terse

  # E5(b): rescale the rendered object / clip fps before conditioning:
  python3 experiments/e3e5_extended.py --model ltx --systems projectile \
      --disk-scale 1.5 --fps-scale 2.0

  # E5(d): conditioning resolution / frame count override:
  python3 experiments/e3e5_extended.py --model ltx --systems projectile \
      --cond-resolution 256

Writes results/e3e5_{variant}_{system}_{model}.json (rows identical in
shape to e4_generality.py's, plus optional plausibility/cotracker fields),
and (if --save-video) saved clips under results/e3e5_videos/.
"""
from __future__ import annotations
import sys, os, json, time, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HF_HOME"] = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".hf_home")

import numpy as np
import torch
from PIL import Image
import imageio.v3 as iio

from physweep.render import N_FRAMES, DISK_VALUE
from physweep.track import centroid_track, cotracker_track, pixel_y_to_physics_y, px_to_m
from physweep_metrics import (
    fit_omega_from_crossings, fit_zeta_from_envelope, fit_restitution_from_bounces,
    fit_friction_from_slide, friction_from_acceleration, faithfulness_slope,
    spearman_rho, pre, bootstrap_ci, damped_sine_r2, fit_gravity_from_trajectory,
)
from physweep.render import (
    simulate_projectile, simulate_damped_pendulum, simulate_bouncing_ball,
    simulate_spring_mass, simulate_inclined_slide,
)
from experiments.e0_pilot import gravity_prompt
from experiments.e4_generality import (
    load_config, make_dynamicrafter_generate_fn, NEGATIVE_PROMPT, MAX_GEN_FRAMES,
    pendulum_omega_prompt, pendulum_zeta_prompt, bouncing_ball_prompt,
    spring_mass_prompt, inclined_slide_prompt,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(REPO_ROOT, "results")
VIDEO_DIR = os.path.join(RESULTS_DIR, "e3e5_videos")
FIT_R2_GATE = 0.8

# ---------------------------------------------------------------------------
# E5(f): alternate prompt phrasing variants for the C2 (text-specified)
# channel. "default" reuses e4_generality.py's own prompt builders exactly
# (so the "default" variant of THIS script reproduces E4's numbers as a
# sanity check); "terse" and "verbose" are the two robustness alternatives.
# ---------------------------------------------------------------------------
PROMPT_BUILDERS_DEFAULT = {
    "projectile": gravity_prompt,
    "pendulum_omega": pendulum_omega_prompt,
    "pendulum_zeta": pendulum_zeta_prompt,
    "bouncing_ball": bouncing_ball_prompt,
    "spring_mass": spring_mass_prompt,
    "inclined_slide": inclined_slide_prompt,
}


def terse_prompt(system, theta):
    """E5(f) variant: name the number and nothing else -- no qualitative
    anchor phrase, no "simple physics simulation" framing. Tests whether the
    qualitative anchor phrases in the default prompts (e.g. "extremely weak
    gravity, like the Moon") are doing the conditioning work rather than the
    literal numeric value."""
    unit = {"projectile": "meters per second squared", "pendulum_omega": "radians per second",
           "pendulum_zeta": "", "bouncing_ball": "", "spring_mass": "newtons per meter",
           "inclined_slide": ""}[system]
    name = {"projectile": "acceleration", "pendulum_omega": "angular frequency",
           "pendulum_zeta": "damping ratio", "bouncing_ball": "coefficient of restitution",
           "spring_mass": "spring stiffness", "inclined_slide": "friction coefficient"}[system]
    return f"a dark ball, {name} {theta:.2f} {unit}".strip()


def verbose_prompt(system, theta):
    """E5(f) variant: the default prompt plus extra redundant physical
    framing, testing whether more emphatic text-conditioning moves PRI/CBI
    (a mechanistic link to the guidance/memorization literature per E5(e))."""
    base = PROMPT_BUILDERS_DEFAULT[system](theta)
    return (f"{base}, precise physically accurate simulation, exact numerical value, "
           f"photorealistic rendering, laboratory measurement setup")


PROMPT_VARIANTS = {"default": None, "terse": terse_prompt, "verbose": verbose_prompt}


def build_prompt(system, theta, variant):
    if variant == "default":
        return PROMPT_BUILDERS_DEFAULT[system](theta)
    return PROMPT_VARIANTS[variant](system, theta)


def rescale_disk_in_frame(first_frame, disk_scale):
    """E5(b): resize the disk WITHIN the conditioning frame by disk_scale,
    keeping canvas size and disk center fixed, so the generator sees a
    bigger/smaller object without changing the physics grid or timing at
    all. Operates on the PIL RGB conditioning image the runners already
    build (Image.fromarray(frames_gt[0]).convert('RGB')), not on
    physweep/render.py's simulator -- deliberately a rendering-side-only
    change, since modifying DISK_RADIUS in render.py would also perturb
    physweep_metrics.py's already-validated (E6) unit conversions."""
    if disk_scale == 1.0:
        return first_frame
    from physweep.render import DISK_VALUE, BG_VALUE, GROUND_VALUE
    import numpy as _np
    arr = _np.array(first_frame.convert("L"))
    disk_mask = _np.abs(arr.astype(int) - DISK_VALUE) <= 30
    ys, xs = _np.nonzero(disk_mask)
    if len(xs) == 0:
        return first_frame  # nothing to rescale, return unchanged rather than guessing
    cx, cy = xs.mean(), ys.mean()
    r0 = float(_np.sqrt(disk_mask.sum() / _np.pi))
    r_new = r0 * disk_scale
    out = arr.copy()
    out[disk_mask] = BG_VALUE if cy < arr.shape[0] * 0.85 else GROUND_VALUE  # erase old disk (bg vs ground line)
    yy, xx = _np.mgrid[0:arr.shape[0], 0:arr.shape[1]]
    new_mask = (xx - cx) ** 2 + (yy - cy) ** 2 <= r_new ** 2
    out[new_mask] = DISK_VALUE
    from PIL import Image as _Image
    return _Image.fromarray(out).convert("RGB")


# ---------------------------------------------------------------------------
# generate_fn wrapper: adds video saving (E3), dual-tracking (E5a), and
# disk-rescaling (E5b) on top of whatever base generate_fn a model factory
# produces, without touching e4_generality.py. The wrapped function still
# returns the SAME (T,H,W) grayscale numpy array run_{system} expects, so
# every existing runner in e4_generality.py works unmodified; the extra
# artifacts are stashed in `sidecar` (a plain dict keyed by (system, theta,
# seed)) for this script's own post-processing.
# ---------------------------------------------------------------------------
def wrap_generate_fn(base_fn, model_tag, system, save_video, dual_track, sidecar, disk_scale=1.0):
    def wrapped(first_frame, prompt, seed, n_frames):
        first_frame = rescale_disk_in_frame(first_frame, disk_scale)
        video_np = base_fn(first_frame, prompt, seed, n_frames)
        key = f"{system}_seed{seed}_{len(sidecar)}"
        entry = {}
        if save_video and not np.any(np.isnan(video_np)):
            os.makedirs(VIDEO_DIR, exist_ok=True)
            out_path = os.path.join(VIDEO_DIR, f"{model_tag}_{key}.mp4")
            # video_np is grayscale (T,H,W) uint8 -- imageio needs an explicit
            # uint8 cast (fitters upstream may have left it as float in some
            # NaN-padded failure paths) and RGB replication for a standard mp4.
            frames_u8 = np.clip(video_np, 0, 255).astype(np.uint8)
            rgb = np.stack([frames_u8] * 3, axis=-1)
            iio.imwrite(out_path, rgb, fps=24)
            entry["video_path"] = out_path
        if dual_track and not np.any(np.isnan(video_np)):
            try:
                cx2, cy2 = cotracker_track(video_np.astype(np.uint8))
                entry["cotracker_cx"] = cx2.tolist()
                entry["cotracker_cy"] = cy2.tolist()
            except Exception as e:
                entry["cotracker_error"] = str(e)
        sidecar[key] = entry
        return video_np
    return wrapped


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["ltx", "cogvideox", "dynamicrafter"], required=True)
    parser.add_argument("--systems", nargs="*",
                        default=["projectile", "pendulum_omega", "pendulum_zeta",
                                "bouncing_ball", "spring_mass", "inclined_slide"])
    parser.add_argument("--seeds-in", type=int, default=None)
    parser.add_argument("--seeds-out", type=int, default=None)
    parser.add_argument("--start-seed", type=int, default=0)
    parser.add_argument("--merge", action="store_true")

    # E3
    parser.add_argument("--save-video", action="store_true",
                        help="save generated clips to results/e3e5_videos/ for later VLM scoring (E3)")
    # E5(a)
    parser.add_argument("--dual-track", action="store_true",
                        help="also run CoTracker3 on every clip alongside blob-centroiding (E5a)")
    # E5(b)
    parser.add_argument("--disk-scale", type=float, default=1.0,
                        help="E5(b): rescale the rendered disk radius by this factor before conditioning")
    parser.add_argument("--fps-scale", type=float, default=1.0,
                        help="E5(b): rescale clip fps (affects dt passed to fitters) by this factor")
    # E5(d)
    parser.add_argument("--cond-resolution", type=int, default=None,
                        help="E5(d): override the conditioning image resolution (default: each model's own)")
    # E5(e)
    parser.add_argument("--guidance-scale", type=float, default=None,
                        help="E5(e): override the model's default classifier-free guidance scale")
    # E5(f)
    parser.add_argument("--prompt-variant", choices=list(PROMPT_VARIANTS.keys()), default="default",
                        help="E5(f): prompt phrasing variant for the C2 channel")

    args = parser.parse_args()

    variant_tag = "default"
    tags = []
    if args.disk_scale != 1.0 or args.fps_scale != 1.0:
        tags.append(f"scale{args.disk_scale}x{args.fps_scale}")
    if args.cond_resolution is not None:
        tags.append(f"res{args.cond_resolution}")
    if args.guidance_scale is not None:
        tags.append(f"cfg{args.guidance_scale}")
    if args.prompt_variant != "default":
        tags.append(f"prompt-{args.prompt_variant}")
    if tags:
        variant_tag = "_".join(tags)

    cfg = load_config()
    base_seeds = cfg["render"]["seeds_per_point"]
    seeds_in = args.seeds_in if args.seeds_in is not None else base_seeds
    seeds_out = args.seeds_out if args.seeds_out is not None else base_seeds
    n_seeds = {"in": list(range(args.start_seed, args.start_seed + seeds_in)),
              "out": list(range(args.start_seed, args.start_seed + seeds_out))}
    print(f"variant={variant_tag}  seeds: in={n_seeds['in']} out={n_seeds['out']}")

    pipe = None
    if args.model == "ltx":
        from diffusers import LTXImageToVideoPipeline
        print("Loading LTX-Video...")
        pipe = LTXImageToVideoPipeline.from_pretrained("Lightricks/LTX-Video", torch_dtype=torch.bfloat16)
        pipe.to("cuda")
        base_factory = lambda: make_ltx_generate_fn_variant(pipe, args)
        model_tag = "ltx"
    elif args.model == "cogvideox":
        from diffusers import CogVideoXImageToVideoPipeline
        print("Loading CogVideoX-5B-I2V...")
        pipe = CogVideoXImageToVideoPipeline.from_pretrained("zai-org/CogVideoX-5b-I2V", torch_dtype=torch.bfloat16)
        pipe.to("cuda")
        pipe.vae.enable_tiling()
        base_factory = lambda: make_cogvideox_generate_fn_variant(pipe, args)
        model_tag = "cogvideox"
    else:
        print("Using DynamiCrafter_512 (subprocess-driven, no in-process pipeline)...")
        base_factory = lambda: make_dynamicrafter_generate_fn()
        model_tag = "dynamicrafter"

    all_summaries = {}
    for system in args.systems:
        print(f"\n{'='*70}\n{system} ({model_tag}, variant={variant_tag})\n{'='*70}")
        sidecar = {}
        base_fn = base_factory()
        generate_fn = wrap_generate_fn(base_fn, model_tag, system, args.save_video, args.dual_track,
                                       sidecar, disk_scale=args.disk_scale)

        t0 = time.time()
        new_rows = SYSTEM_RUNNERS[system](generate_fn, cfg, n_seeds, args.prompt_variant, args.fps_scale)
        elapsed = time.time() - t0

        # attach sidecar (video path / cotracker trajectory) onto matching rows by
        # position -- rows and sidecar entries are produced in the same iteration
        # order per system, so zip is safe here (both built by the same loop).
        for row, (key, entry) in zip(new_rows, sidecar.items()):
            row.update(entry)

        out_path = os.path.join(RESULTS_DIR, f"e3e5_{variant_tag}_{system}_{model_tag}.json")
        if args.merge and os.path.exists(out_path):
            with open(out_path) as f:
                existing_rows = json.load(f)["rows"]
            by_key = {(r["theta"], r["split"], r["seed"]): r for r in existing_rows}
            for r in new_rows:
                by_key[(r["theta"], r["split"], r["seed"])] = r
            rows = list(by_key.values())
        else:
            rows = new_rows

        gated = [r for r in rows if r["r2"] is not None and r["r2"] >= FIT_R2_GATE and not np.isnan(r["theta_hat"])]
        dropped_rate = 1.0 - len(gated) / max(len(rows), 1)
        summary = {"n_total": len(rows), "n_gated": len(gated), "dropped_rate": dropped_rate,
                  "elapsed_seconds": elapsed, "variant": variant_tag}
        all_summaries[system] = summary
        print(f"{system}: n_gated={len(gated)}/{len(rows)} dropped_rate={dropped_rate:.2%} elapsed={elapsed:.0f}s")

        with open(out_path, "w") as f:
            json.dump({"rows": rows, "summary": summary}, f, indent=2,
                     default=lambda o: None if isinstance(o, float) and np.isnan(o) else o)
        print(f"Wrote {out_path}")

    combined_path = os.path.join(RESULTS_DIR, f"e3e5_{variant_tag}_{model_tag}_summary.json")
    with open(combined_path, "w") as f:
        json.dump(all_summaries, f, indent=2)
    print(f"\nWrote combined summary: {combined_path}")


def make_ltx_generate_fn_variant(pipe, args):
    """Same as e4_generality.make_ltx_generate_fn but with E5(b)/(d)/(e)
    overrides threaded through. Duplicated (not wrapped) because the base
    factory's resolution/guidance_scale are baked into its closure body, not
    exposed as parameters -- see e4_generality.py:284-295 for the original
    this is derived from; keep the two in sync if the base pipeline call
    signature changes."""
    def generate_fn(first_frame, prompt, seed, n_frames):
        n_frames = min(n_frames, MAX_GEN_FRAMES)
        res = args.cond_resolution or 512
        img = first_frame.resize((res, res), Image.NEAREST)
        gen = torch.Generator("cuda").manual_seed(seed)
        gen_frames = ((n_frames - 1) // 8 + 1) * 8 + 1
        gs = args.guidance_scale if args.guidance_scale is not None else 3.0
        out = pipe(image=img, prompt=prompt, negative_prompt=NEGATIVE_PROMPT,
                  height=res, width=res, num_frames=gen_frames, frame_rate=24,
                  num_inference_steps=30, guidance_scale=gs, generator=gen)
        video = out.frames[0][:n_frames]
        return np.stack([np.array(f.convert("L").resize((256, 256))) for f in video])
    return generate_fn


def make_cogvideox_generate_fn_variant(pipe, args):
    def generate_fn(first_frame, prompt, seed, n_frames):
        n_frames = min(n_frames, MAX_GEN_FRAMES)
        w, h = (args.cond_resolution, args.cond_resolution) if args.cond_resolution else (720, 480)
        img = first_frame.resize((w, h), Image.NEAREST)
        gen = torch.Generator("cuda").manual_seed(seed)
        gen_frames = ((n_frames - 1) // 4 + 1) * 4 + 1
        gs = args.guidance_scale if args.guidance_scale is not None else 6.0
        out = pipe(image=img, prompt=prompt, negative_prompt=NEGATIVE_PROMPT,
                  height=h, width=w, num_frames=gen_frames,
                  num_inference_steps=30, guidance_scale=gs, generator=gen)
        video = out.frames[0][:n_frames]
        return np.stack([np.array(f.convert("L").resize((256, 256))) for f in video])
    return generate_fn


def run_projectile_variant(generate_fn, cfg, n_seeds, prompt_variant, dt_scale=1.0):
    """projectile lives in e0_pilot.py's family, not e4_generality.py's
    SYSTEMS dict -- reimplemented here (not imported) since e0_pilot.py's
    main() is a monolithic function, not a reusable run_projectile(...). Kept
    deliberately parallel in structure to e4_generality.py's other run_*
    functions so this script's own logic (sidecar zip, --merge, etc.)
    treats every system uniformly. dt_scale: E5(b) ablation, see
    physweep/render.py's simulate_projectile docstring."""
    proj_cfg = cfg["systems"]["projectile"]
    g_in = proj_cfg["in_range"][:5]
    g_out = proj_cfg["out_of_range"][:3]
    GROUND_CLEARANCE_PX = 100
    rows = []
    for theta_set, label in [(g_in, "in"), (g_out, "out")]:
        for g_true in theta_set:
            for seed in n_seeds[label]:
                frames_gt, y_true, t_gt = simulate_projectile(
                    g=g_true, seed=seed, n_frames=N_FRAMES, ground_clearance_px=GROUND_CLEARANCE_PX,
                    dt_scale=dt_scale)
                first_frame = Image.fromarray(frames_gt[0]).convert("RGB")
                prompt = build_prompt("projectile", g_true, prompt_variant)
                video_np = generate_fn(first_frame, prompt, seed, N_FRAMES)
                cx, cy = centroid_track(video_np, disk_value=DISK_VALUE, tol=60)
                if np.any(np.isnan(cy)):
                    g_hat, r2 = float("nan"), 0.0
                else:
                    y_phys = pixel_y_to_physics_y(cy)
                    g_hat, r2 = fit_gravity_from_trajectory(t_gt[:len(cy)], y_phys)
                rows.append(dict(theta=g_true, theta_hat=g_hat, r2=r2, split=label, seed=seed))
                print(f"  g_true={g_true:6.2f} seed={seed}: g_hat={g_hat if not np.isnan(g_hat) else float('nan'):.3f} r2={r2:.3f}")
    return rows


def run_pendulum_omega_variant(generate_fn, cfg, n_seeds, prompt_variant, dt_scale=1.0):
    sysc = cfg["systems"]["damped_pendulum_omega"]
    n_frames = sysc.get("n_frames", N_FRAMES)
    zeta = sysc["fixed_zeta"]
    rows = []
    for theta_set, label in [(sysc["in_range"], "in"), (sysc["out_of_range"], "out")]:
        for om_true in theta_set:
            for seed in n_seeds[label]:
                frames_gt, bx_true, t_gt = simulate_damped_pendulum(
                    omega=om_true, zeta=zeta, seed=seed, n_frames=n_frames, dt_scale=dt_scale)
                first_frame = Image.fromarray(frames_gt[0]).convert("RGB")
                prompt = build_prompt("pendulum_omega", om_true, prompt_variant)
                video_np = generate_fn(first_frame, prompt, seed, n_frames)
                cx, cy = centroid_track(video_np, disk_value=DISK_VALUE, tol=60)
                if np.any(np.isnan(cx)):
                    om_hat, r2 = float("nan"), 0.0
                else:
                    om_hat, r2 = fit_omega_from_crossings(t_gt[:len(cx)], cx)
                rows.append(dict(theta=om_true, theta_hat=om_hat, r2=r2, split=label, seed=seed))
                print(f"  omega_true={om_true:6.2f} seed={seed}: omega_hat={om_hat if not np.isnan(om_hat) else float('nan'):.3f} r2={r2:.3f}")
    return rows


def run_pendulum_zeta_variant(generate_fn, cfg, n_seeds, prompt_variant, dt_scale=1.0):
    sysc = cfg["systems"]["damped_pendulum_zeta"]
    n_frames = sysc.get("n_frames", N_FRAMES)
    omega = sysc["fixed_omega"]
    rows = []
    for theta_set, label in [(sysc["in_range"], "in"), (sysc["out_of_range"], "out")]:
        for zeta_true in theta_set:
            for seed in n_seeds[label]:
                frames_gt, bx_true, t_gt = simulate_damped_pendulum(
                    omega=omega, zeta=zeta_true, seed=seed, n_frames=n_frames, dt_scale=dt_scale)
                first_frame = Image.fromarray(frames_gt[0]).convert("RGB")
                prompt = build_prompt("pendulum_zeta", zeta_true, prompt_variant)
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


def run_bouncing_ball_variant(generate_fn, cfg, n_seeds, prompt_variant, dt_scale=1.0):
    sysc = cfg["systems"]["bouncing_ball"]
    n_frames = N_FRAMES
    rows = []
    for theta_set, label in [(sysc["in_range"], "in"), (sysc["out_of_range"], "out")]:
        for e_true in theta_set:
            for seed in n_seeds[label]:
                frames_gt, ys_true, t_gt, peaks_true = simulate_bouncing_ball(
                    e=e_true, seed=seed, n_frames=n_frames, dt_scale=dt_scale)
                first_frame = Image.fromarray(frames_gt[0]).convert("RGB")
                prompt = build_prompt("bouncing_ball", e_true, prompt_variant)
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


def run_spring_mass_variant(generate_fn, cfg, n_seeds, prompt_variant, dt_scale=1.0):
    sysc = cfg["systems"]["spring_mass"]
    n_frames = sysc.get("n_frames", N_FRAMES)
    mass = sysc["mass_kg"]
    rows = []
    for theta_set, label in [(sysc["in_range"], "in"), (sysc["out_of_range"], "out")]:
        for k_true in theta_set:
            for seed in n_seeds[label]:
                frames_gt, xs_true, t_gt = simulate_spring_mass(
                    k=k_true, seed=seed, n_frames=n_frames, mass_kg=mass, dt_scale=dt_scale)
                first_frame = Image.fromarray(frames_gt[0]).convert("RGB")
                prompt = build_prompt("spring_mass", k_true, prompt_variant)
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


def run_inclined_slide_variant(generate_fn, cfg, n_seeds, prompt_variant, dt_scale=1.0):
    sysc = cfg["systems"]["inclined_slide"]
    incline_deg = sysc["incline_deg"]
    incline_rad = np.deg2rad(incline_deg)
    g_internal = 300.0
    dx, dy = np.cos(incline_rad), np.sin(incline_rad)
    rows = []
    for theta_set, label in [(sysc["in_range"], "in"), (sysc["out_of_range"], "out")]:
        for mu_true in theta_set:
            for seed in n_seeds[label]:
                frames_gt, s_true, t_gt = simulate_inclined_slide(
                    mu=mu_true, seed=seed, incline_deg=incline_deg, dt_scale=dt_scale)
                first_frame = Image.fromarray(frames_gt[0]).convert("RGB")
                prompt = build_prompt("inclined_slide", mu_true, prompt_variant)
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


SYSTEM_RUNNERS = {
    "projectile": run_projectile_variant,
    "pendulum_omega": run_pendulum_omega_variant,
    "pendulum_zeta": run_pendulum_zeta_variant,
    "bouncing_ball": run_bouncing_ball_variant,
    "spring_mass": run_spring_mass_variant,
    "inclined_slide": run_inclined_slide_variant,
}


if __name__ == "__main__":
    main()
