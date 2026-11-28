#!/usr/bin/env python3
"""
Sensitivity analysis (CPU, EXPLORATORY, defined 2026-11-28 after the main_frame run was seen): score every
clip again with the registered rules, but only over the scene's own duration.

Why. The rendered scene lasts N_FRAMES / FPS = 1 s. Generated clips are 2-6 s long, and the registered
measurement fits from the first generated frame up to floor contact, and checks shape and camera over the
whole clip. Two things can therefore differ from a 1-s reading: (a) an early response to theta that the
model does not sustain can be diluted or ruled invalid by what happens later in the clip; (b) a text-channel
null could in principle be an artefact of long windows. This script measures both.

Window. Frames 0 .. E-1 with E = round(1 s / dt) for text and prefix clips (dt = 1 / model fps); pair clips
already span the key-frame interval, so their window is the whole clip. Prefix frames copied from the input
(n_given) are excluded from the fit, as in the registered measurement.

Rules (unchanged from the registered pipeline, applied to the window): blob track `centroid_track_above`,
`fits.fit_theta` with floor-contact truncation, `validity.shape_stats` and `validity.classify` (fit gate,
camera, single object, stable size, static), CoTracker3 second tracker from its stored track cut to the
window. Systems: projectile and inclined_slide only (the bouncing-ball fit reads bounce peaks over the whole
clip; a 1-s window removes most bounces, so it is not a like-for-like reading).

Usage:  python experiments/v2_window_sensitivity.py --runs main_text main_frame [--workers 12]
Writes: <REVISION>/results_v2/window_sensitivity.{json,md} and window_sensitivity_clips.jsonl
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CODE_DIR)
sys.path.insert(0, os.path.join(CODE_DIR, "experiments"))

import imageio.v2 as iio
import numpy as np

from physweep import render as R
from physweep.fits import fit_theta
from physweep.generators import to_analysis_frames
from physweep.runio import load_latest, raw_files
from physweep.validity import centroid_track_above, classify, shape_stats
from v2_analyze import seed_free

RESULTS = os.path.join(os.path.dirname(CODE_DIR), "results_v2")
SYSTEMS = ("projectile", "inclined_slide")
SCENE_SECONDS = R.N_FRAMES * R.DT          # 1.0 s


def finite(x):
    return x is not None and np.isfinite(x)


def track(rec, key):
    v = rec.get(key)
    return None if v is None else np.where(np.asarray(v, float) < 0, np.nan, np.asarray(v, float))


def window_end(rec, n_frames):
    if rec.get("frame_mode") == "pair":
        return n_frames
    dt = rec.get("dt") or 1.0 / rec["fps"]
    return min(n_frames, int(round(SCENE_SECONDS / dt)))


def score(args):
    root, rec = args
    frames = np.stack([np.asarray(f) for f in iio.get_reader(os.path.join(root, rec["video"]))])
    ana = to_analysis_frames(frames)
    end = window_end(rec, len(ana))
    w = ana[:end]
    stats = shape_stats(w)
    g = stats["ground_row0"]
    dt = rec.get("dt") or 1.0 / rec["fps"]
    k = rec.get("n_given") or 0
    bcx, bcy = centroid_track_above(w, g)
    hat, r2 = fit_theta(rec["system"], bcx[k:], bcy[k:], dt, ground_row=g)
    hat2 = r2b = None
    if rec.get("cot_cx") is not None:
        hat2, r2b = fit_theta(rec["system"], track(rec, "cot_cx")[k:end], track(rec, "cot_cy")[k:end], dt,
                              ground_row=g)
    lab = classify(rec["system"], stats, hat if finite(hat) else None, r2,
                   hat2 if finite(hat2) else None, r2b)
    return dict(clip_id=rec["clip_id"], model=rec["model"], system=rec["system"], theta=rec["theta"],
                split=rec["split"], scene_seed=rec["scene_seed"], noise_seed=rec["noise_seed"],
                window_frames=end, n_given=k, theta_hat=float(hat) if finite(hat) else None, r2=float(r2),
                label=lab["label"], second_tracker=lab["second_tracker"],
                registered_label=rec["label"], registered_theta_hat=rec.get("theta_hat"))


def medians(valid):
    by = collections.defaultdict(list)
    for r in valid:
        by[r["theta"]].append(r["theta_hat"])
    return {str(t): dict(median=float(np.median(v)), n=len(v)) for t, v in sorted(by.items())}


def is_valid(r):
    return r["label"] == "valid" and r["theta_hat"] is not None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-root", default=os.environ.get("PHYSWEEP_OUT", os.path.join(CODE_DIR, "..", "runs")))
    ap.add_argument("--runs", nargs="+", default=["main_text", "main_frame"])
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--results", default=RESULTS)
    a = ap.parse_args()

    summary, clips = {}, []
    with ProcessPoolExecutor(a.workers) as pool:
        for run in a.runs:
            for model in sorted(os.listdir(os.path.join(a.out_root, run))):
                mdir = os.path.join(a.out_root, run, model)
                if not os.path.isdir(mdir) or not raw_files(mdir):
                    continue
                recs = [r for r in load_latest(mdir, prefer_rescored=True).values()
                        if "error" not in r and r["system"] in SYSTEMS]
                out = list(pool.map(score, [(mdir, r) for r in recs], chunksize=4))
                for o in out:
                    o["run"] = run
                clips += out
                for system in SYSTEMS:
                    reg = [r for r in recs if r["system"] == system]
                    win = [o for o in out if o["system"] == system]
                    if not reg:
                        continue
                    rv = [r for r in reg if is_valid(r)]
                    wv = [o for o in win if is_valid(o)]
                    summary[f"{run}/{model}/{system}"] = dict(
                        window_frames=sorted({o["window_frames"] for o in win}),
                        registered=dict(seed_free(rv, len(reg)), medians=medians(rv)),
                        window=dict(seed_free(wv, len(win)), medians=medians(wv)),
                        labels_window=dict(collections.Counter(o["label"] for o in win)))
                print(f"{run}/{model}: {len(out)} clips scored", flush=True)

    os.makedirs(a.results, exist_ok=True)
    stem = os.path.join(a.results, "window_sensitivity")
    with open(stem + ".json", "w") as fh:
        json.dump(dict(scene_seconds=SCENE_SECONDS, runs=a.runs, summary=summary), fh, indent=1)
    with open(stem + "_clips.jsonl", "w") as fh:
        for c in clips:
            fh.write(json.dumps(c) + "\n")
    md = to_md(summary)
    with open(stem + ".md", "w") as fh:
        fh.write(md + "\n")
    print(md)


def ci(d):
    if "beta_in" not in d:
        return "–"
    c = d.get("beta_in_ci")
    return f"{d['beta_in']:.2f}" + (f" [{c[0]:.2f}, {c[1]:.2f}]" if c else "")


def rho(d):
    return "–" if d.get("spearman_rho") is None else f"{d['spearman_rho']:.2f}"


def to_md(summary):
    out = ["# Scene-duration window: sensitivity analysis (exploratory)", "",
           "Generated by `experiments/v2_window_sensitivity.py`. Defined after the `main_frame` run was seen; not "
           "the registered measurement. Same rules as the registered pipeline (fit gate, camera, shape, static, "
           "second tracker), applied only to the frames up to t = 1 s, the duration of the rendered scene "
           "(pair clips: the whole clip, which spans the key-frame interval). β: in-range slope on valid clips "
           "[95% bootstrap CI]; ρ: Spearman over the full grid.", "",
           "| run / model / system | window (frames) | valid registered | valid window | β registered | β window | "
           "ρ registered | ρ window |", "|---|---|---|---|---|---|---|---|"]
    for k, d in summary.items():
        r, w = d["registered"], d["window"]
        out.append(f"| {k} | {','.join(map(str, d['window_frames']))} | {r['n_valid']}/{r['n_clips']} | "
                   f"{w['n_valid']}/{w['n_clips']} | {ci(r)} | {ci(w)} | {rho(r)} | {rho(w)} |")
    out += ["", "## Median θ̂ per θ on valid clips (window)", "",
            "| run / model / system | θ: median θ̂ (n) |", "|---|---|"]
    for k, d in summary.items():
        m = d["window"]["medians"]
        out.append(f"| {k} | " + "; ".join(f"{t}: {v['median']:.2f} ({v['n']})" for t, v in m.items()) + " |")
    return "\n".join(out)


if __name__ == "__main__":
    main()
