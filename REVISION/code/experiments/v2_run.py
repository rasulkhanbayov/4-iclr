#!/usr/bin/env python3
"""
v2 sweep runner: one model, one shard of the v2 design.

Per clip: build conditioning (scene seed only) -> generate (noise seed only)
-> save the raw video -> blob-track + CoTracker3 -> closed-form fit at the
model's own frame rate -> validity checks -> one JSON line per clip in this
shard's own file (clips_shard<i>of<n>.jsonl). Clips already recorded in ANY of
the model's files are skipped, so a resubmitted job resumes.

Examples
  python experiments/v2_run.py --model simulator --pilot --no-cotracker --out-root /tmp/x   # CPU dry run
  python experiments/v2_run.py --model wan22_ti2v_5b --pilot                                 # GPU pilot
  python experiments/v2_run.py --model ltx2 --shard-index 0 --shard-count 4                  # main sweep

Output: $PHYSWEEP_OUT/<run>/<model>/{clips_shard*.jsonl, videos/<clip_id>.mp4, run_meta_shard*.json}
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
import traceback

CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CODE_DIR)

import numpy as np

from physweep.conditioning import build_conditioning
from physweep.design import DEFAULT_SYSTEMS, build_design, shard
from physweep.fits import fit_theta
from physweep.generators import MODEL_SPECS, REVISIONS, load_generator, to_analysis_frames
from physweep.runio import load_latest, shard_path
from physweep.validity import centroid_track_above, classify, shape_stats


def pilot_rows(rows):
    """Pilot subset: per system, the lowest and highest in-range theta, scene seeds 0-1, one noise seed."""
    keep = []
    for system in sorted({r["system"] for r in rows}):
        sys_rows = [r for r in rows if r["system"] == system and r["split"] == "in"]
        lo, hi = min(r["theta"] for r in sys_rows), max(r["theta"] for r in sys_rows)
        noise0 = min(r["noise_seed"] for r in sys_rows)
        keep += [r for r in sys_rows if r["theta"] in (lo, hi) and r["scene_seed"] in (0, 1)
                 and r["noise_seed"] == noise0]
    return keep


def finite(x):
    return x is not None and np.isfinite(x)


def key_frame_errors(ana, cond, ground):
    """Ball-position error (px) between the output and the conditioning frames it should reproduce:
    first and last output frame for "pair", the first k output frames for "prefix", frame 0 for text."""
    given = np.stack(cond["frames"])
    gx, gy = centroid_track_above(given, ground)
    ox, oy = centroid_track_above(ana, ground)
    if cond["frame_mode"] == "pair":
        pairs = [(0, 0), (len(ana) - 1, 1)]
    else:
        pairs = [(i, i) for i in range(min(len(given), len(ana)))]
    return [None if not (np.isfinite(ox[o]) and np.isfinite(gx[g])) else
            round(float(np.hypot(ox[o] - gx[g], oy[o] - gy[g])), 2) for o, g in pairs]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=list(MODEL_SPECS))
    ap.add_argument("--run", default=None, help="run name (default: pilot or sweep)")
    ap.add_argument("--out-root", default=os.environ.get("PHYSWEEP_OUT", os.path.join(CODE_DIR, "..", "runs")))
    ap.add_argument("--systems", nargs="+", default=list(DEFAULT_SYSTEMS))
    ap.add_argument("--mode", choices=["crossed", "api"], default="crossed")
    ap.add_argument("--n-scene", type=int, default=4)
    ap.add_argument("--n-noise", type=int, default=4)
    ap.add_argument("--style", default="structured", choices=["minimal", "structured", "shaded"])
    ap.add_argument("--channel", default="text", choices=["text", "frame"])
    ap.add_argument("--frame-mode", default=None, choices=["pair", "prefix"],
                    help="frame channel only; default: the model's own frame_mode in MODEL_SPECS")
    ap.add_argument("--prompt-variant", default="default", choices=["default", "terse", "verbose"])
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--shard-index", type=int, default=0)
    ap.add_argument("--shard-count", type=int, default=1)
    ap.add_argument("--no-cotracker", action="store_true")
    ap.add_argument("--offload", action="store_true", help="enable_model_cpu_offload (slower, less VRAM)")
    args = ap.parse_args()

    rows = build_design(args.systems, args.n_scene, args.n_noise, args.style, args.channel,
                        args.prompt_variant, args.mode)
    if args.pilot:
        rows = pilot_rows(rows)
    rows = shard(rows, args.shard_index, args.shard_count) if not args.pilot else rows
    if args.limit:
        rows = rows[:args.limit]

    run = args.run or ("pilot" if args.pilot else f"sweep_{args.mode}_{args.style}_{args.channel}")
    out_dir = os.path.join(args.out_root, run, args.model)
    os.makedirs(os.path.join(out_dir, "videos"), exist_ok=True)
    shard_count = 1 if args.pilot else args.shard_count
    out_path = shard_path(out_dir, args.shard_index, shard_count)
    # clips recorded by any shard are skipped; errored clips are retried
    done = {cid for cid, r in load_latest(out_dir).items() if "error" not in r}
    todo = [r for r in rows if r["clip_id"] not in done]
    print(f"[{args.model}] run={run} shard {args.shard_index}/{args.shard_count}: "
          f"{len(rows)} clips in shard, {len(done)} already done, {len(todo)} to do", flush=True)
    if not todo:
        return

    torch = None
    if args.model != "simulator":
        import torch
    t_load = time.time()
    gen = load_generator(args.model, offload=args.offload, channel=args.channel)
    load_s = time.time() - t_load
    print(f"[{args.model}] loaded in {load_s:.0f}s", flush=True)

    cot = None
    if not args.no_cotracker:
        from physweep.track import cotracker_track as cot

    meta = dict(model=args.model, spec=MODEL_SPECS[args.model], revision=REVISIONS.get(MODEL_SPECS[args.model]["repo"]),
                args=vars(args), load_seconds=load_s,
                host=platform.node(), slurm_job=os.environ.get("SLURM_JOB_ID"),
                gpu=torch.cuda.get_device_name(0) if torch is not None and torch.cuda.is_available() else None)
    with open(os.path.join(out_dir, f"run_meta_shard{args.shard_index}.json"), "w") as f:
        json.dump(meta, f, indent=1, default=str)

    import imageio.v2 as iio
    for i, row in enumerate(todo):
        rec = dict(row, model=args.model)
        try:
            spec = MODEL_SPECS[args.model]
            fmode = args.frame_mode or spec.get("frame_mode")
            if row["channel"] == "frame" and fmode is None:
                raise ValueError(f"{args.model} has no frame-channel mode")
            cond = build_conditioning(row, frame_mode=fmode or "pair", k=spec.get("frame_k", 5),
                                      model_fps=spec["fps"])
            if torch is not None:
                torch.cuda.reset_peak_memory_stats()
            t0 = time.time()
            out = gen.generate(cond["frames"], cond["prompt"], row["noise_seed"], row)
            rec["gen_seconds"] = time.time() - t0
            rec["peak_vram_gb"] = (torch.cuda.max_memory_allocated() / 1e9) if torch is not None else None
            frames, fps = out["frames"], out["fps"]
            rec.update(prompt=cond["prompt"], fps=fps, n_frames_out=int(frames.shape[0]),
                       out_hw=list(frames.shape[1:3]))
            vid = os.path.join(out_dir, "videos", f"{row['clip_id']}.mp4")
            iio.mimwrite(vid, list(frames), fps=fps, quality=9, macro_block_size=1)
            rec["video"] = os.path.relpath(vid, out_dir)

            ana = to_analysis_frames(frames)
            stats = shape_stats(ana)
            ground = stats["ground_row0"]
            # frame interval: pair mode spans key frame 1 -> key frame 2; otherwise the model's frame rate
            if cond["frame_mode"] == "pair":
                dt = (cond["key_times"][1] - cond["key_times"][0]) / (frames.shape[0] - 1)
            else:
                dt = 1.0 / fps
            n_given = cond["n_given"]          # prefix frames copied from the input are not fitted
            rec.update(frame_mode=cond["frame_mode"], key_times=cond["key_times"], n_given=n_given, dt=dt,
                       key_frame_err_px=key_frame_errors(ana, cond, ground))
            cx, cy = centroid_track_above(ana, ground)
            hat, r2 = fit_theta(row["system"], cx[n_given:], cy[n_given:], dt, ground_row=ground)
            rec.update(theta_hat=float(hat) if finite(hat) else None, r2=float(r2),
                       blob_cx=np.nan_to_num(cx, nan=-1).round(2).tolist(),
                       blob_cy=np.nan_to_num(cy, nan=-1).round(2).tolist())
            hat2 = r2b = None
            if cot is not None:
                cx2, cy2 = cot(ana)
                hat2, r2b = fit_theta(row["system"], cx2[n_given:], cy2[n_given:], dt, ground_row=ground)
                rec.update(cot_theta_hat=float(hat2) if finite(hat2) else None, cot_r2=float(r2b),
                           cot_cx=np.nan_to_num(cx2, nan=-1).round(2).tolist(),
                           cot_cy=np.nan_to_num(cy2, nan=-1).round(2).tolist())
            rec.update(stats)
            rec.update(classify(row["system"], stats, rec["theta_hat"], r2,
                                rec.get("cot_theta_hat"), rec.get("cot_r2")))
        except Exception as e:  # one bad clip must not kill the shard
            rec.update(error=f"{type(e).__name__}: {e}", traceback=traceback.format_exc()[-3000:])
            if torch is not None and "out of memory" in str(e).lower():
                torch.cuda.empty_cache()
        with open(out_path, "a") as f:
            f.write(json.dumps(rec, default=lambda o: o.item() if hasattr(o, "item") else str(o)) + "\n")
        print(f"[{args.model}] {i + 1}/{len(todo)} {row['system']} θ={row['theta']} s={row['scene_seed']} "
              f"z={row['noise_seed']}: " + (f"ERROR {rec['error'][:120]}" if "error" in rec else
              f"θ̂={rec['theta_hat']} R²={rec['r2']:.3f} {rec['label']}/{rec.get('second_tracker')} "
              f"{rec['gen_seconds']:.0f}s"), flush=True)


if __name__ == "__main__":
    main()
