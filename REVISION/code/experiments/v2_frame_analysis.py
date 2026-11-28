#!/usr/bin/env python3
"""
Step 6 analysis specific to the frame-implied channel (CPU). The standard metrics (validity, beta, rho, PRE,
variance decomposition) come from `v2_analyze.py --run main_frame`; this script adds what only the frame
channel has:

1. Key-frame fidelity: ball-position error (px) between the output and the frames it was given
   (`key_frame_err_px`, recorded by v2_run.py), and how many clips miss a key frame by more than 2 px.
2. Frame vs. text channel, same model and system: valid rate, in-range beta (95% bootstrap CI), Spearman rho,
   PRE(in), from `main_frame` and `main_text` (v2_analyze.seed_free on valid clips).
3. Pair mode only (two key frames, endpoints fixed): the measured theta_hat then reflects how the model
   times the motion between the endpoints. Two references, both computed from the ground-truth scene:
     physics  the true trajectory between the key frames, resampled at the output's frame times;
     linear   constant-speed motion between the two key-frame positions (projectile: g_hat = 0;
              slide: zero acceleration, mu_hat = tan(incline)).
   Per valid clip, RMS distance (px) from each reference along the coordinate the fit uses (height for the
   projectile, distance along the slope for the slide), over the fitted frames (before floor contact), and
   which reference is closer.
4. Pair-mode projectile: clips whose ball touches the floor before the second key frame (the model meets the
   apex key frame by inserting a bounce). Counted over all clips with a track, not only valid ones.

Usage:  python experiments/v2_frame_analysis.py [--run main_frame --text-run main_text]
Writes: <REVISION>/results_v2/<run>_frame.json and .md
"""

from __future__ import annotations

import argparse
import json
import os
import sys

CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CODE_DIR)
sys.path.insert(0, os.path.join(CODE_DIR, "experiments"))

import numpy as np

from physweep import render as R
from physweep.conditioning import render_ground_truth
from physweep.design import load_cfg
from physweep.fits import contact_index
from physweep.runio import load_latest, raw_files
from physweep.validity import centroid_track_above, shape_stats
from v2_analyze import seed_free

RESULTS = os.path.join(os.path.dirname(CODE_DIR), "results_v2")
SYSTEMS = ("projectile", "inclined_slide", "bouncing_ball")
MISS_PX = 2.0
INCLINE_DEG = load_cfg()["systems"]["inclined_slide"]["incline_deg"]


def track(rec, key):
    v = rec.get(key)
    return None if v is None else np.where(np.asarray(v, float) < 0, np.nan, np.asarray(v, float))


def is_valid(r):
    return "error" not in r and r.get("label") == "valid" and r.get("theta_hat") is not None


def pair_references(rec):
    """Physics and linear reference paths at the output's frame times, in analysis-frame pixels."""
    gt = render_ground_truth(rec["system"], rec["theta"], rec["scene_seed"], rec["style"])
    gx, gy = centroid_track_above(gt, shape_stats(gt)["ground_row0"])
    second = len(gt) // 2 if rec["system"] == "projectile" else len(gt) - 1
    n = rec["n_frames_out"]
    t_out = np.arange(n) * rec["dt"]
    t_gt = np.arange(second + 1) * R.DT
    phys = np.interp(t_out, t_gt, gx[:second + 1]), np.interp(t_out, t_gt, gy[:second + 1])
    s = np.linspace(0, 1, n)
    lin = gx[0] + (gx[second] - gx[0]) * s, gy[0] + (gy[second] - gy[0]) * s
    return phys, lin


def fit_coordinate(system, cx, cy):
    """The coordinate the fit reads theta from: height for projectile and ball, distance along the slope
    for the slide (fits.fit_theta). The other coordinate carries no theta (e.g. the projectile's horizontal
    speed is constant), so it is left out of the comparison."""
    if system == "inclined_slide":
        a = np.deg2rad(INCLINE_DEG)
        return cx * np.cos(a) + cy * np.sin(a)
    return cy


def profile(rec):
    cx, cy = track(rec, "blob_cx"), track(rec, "blob_cy")
    if cx is None:
        return None
    k = contact_index(cy, rec["ground_row0"]) if rec["system"] in ("projectile", "inclined_slide") else len(cy)
    (px, py), (lx, ly) = pair_references(rec)
    u, up, ul = (fit_coordinate(rec["system"], x, y)[:k] for x, y in ((cx, cy), (px, py), (lx, ly)))
    m = np.isfinite(u)
    if m.sum() < 4:
        return None
    rms = lambda ref: float(np.sqrt(np.mean((u[m] - ref[m]) ** 2)))
    return dict(rms_physics=rms(up), rms_linear=rms(ul))


def inserted_bounce(rec):
    cy = track(rec, "blob_cy")
    if cy is None or not np.isfinite(cy).any():
        return None
    return bool(contact_index(cy, rec["ground_row0"]) < len(cy) - 1)


def analyze(root, run, text_run):
    res = {}
    for model in sorted(os.listdir(os.path.join(root, run))):
        mdir = os.path.join(root, run, model)
        if not os.path.isdir(mdir) or not raw_files(mdir):
            continue
        recs = [r for r in load_latest(mdir, prefer_rescored=True).values()]
        tdir = os.path.join(root, text_run, model)
        trecs = list(load_latest(tdir, prefer_rescored=True).values()) if os.path.isdir(tdir) and raw_files(tdir) else []
        for system in SYSTEMS:
            rs = [r for r in recs if r["system"] == system]
            if not rs:
                continue
            ok = [r for r in rs if "error" not in r]
            kfe = [e for r in ok for e in (r.get("key_frame_err_px") or []) if e is not None]
            miss = sum(any(e is None or e > MISS_PX for e in (r.get("key_frame_err_px") or [None])) for r in ok)
            ts = [r for r in trecs if r["system"] == system]
            entry = dict(
                frame_mode=ok[0].get("frame_mode") if ok else None, n_clips=len(rs), n_errors=len(rs) - len(ok),
                key_frame_err_median=float(np.median(kfe)) if kfe else None,
                key_frame_err_max=float(np.max(kfe)) if kfe else None, clips_missing_a_key_frame=miss,
                frame=seed_free([r for r in rs if is_valid(r)], len(rs)),
                text=seed_free([r for r in ts if is_valid(r)], len(ts)) if ts else None)
            if entry["frame_mode"] == "pair":
                prof = [p for p in (profile(r) for r in rs if is_valid(r)) if p]
                if prof:
                    entry["pair_profile"] = dict(
                        n=len(prof), median_rms_physics=float(np.median([p["rms_physics"] for p in prof])),
                        median_rms_linear=float(np.median([p["rms_linear"] for p in prof])),
                        closer_to_physics=sum(p["rms_physics"] < p["rms_linear"] for p in prof))
                if system == "projectile":
                    b = [x for x in (inserted_bounce(r) for r in ok) if x is not None]
                    entry["inserted_bounce"] = dict(n_tracked=len(b), n=sum(b))
            res[f"{model}/{system}"] = entry
    return res


def f(x, nd=2):
    return "–" if x is None else f"{x:.{nd}f}"


def beta_str(d):
    if not d or "beta_in" not in d:
        return "–"
    ci = d.get("beta_in_ci")
    return f"{d['beta_in']:.2f}" + (f" [{ci[0]:.2f}, {ci[1]:.2f}]" if ci else "")


def to_md(run, text_run, res):
    out = [f"# Frame-implied channel, run `{run}` (step 6)", "",
           "Generated by `experiments/v2_frame_analysis.py`. Standard metrics and the variance decomposition: "
           f"`{run}_analysis.md` (v2_analyze.py).", "",
           "## Key-frame fidelity and frame vs. text channel", "",
           f"Key-frame error: ball position in the output vs. the given frame (px, analysis frames 256×256); "
           f"'miss' = clips with a key frame off by > {MISS_PX:.0f} px or untracked. Text channel: run `{text_run}`, "
           "same model and system. β: in-range slope on valid clips [95% bootstrap CI].", "",
           "| model / system | mode | clips | key-frame err median / max | miss | valid frame | valid text | β frame | β text | ρ frame | ρ text |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, d in res.items():
        fr, tx = d["frame"], d["text"] or {}
        out.append(f"| {k} | {d['frame_mode']} | {d['n_clips']} | {f(d['key_frame_err_median'])} / "
                   f"{f(d['key_frame_err_max'])} | {d['clips_missing_a_key_frame']} | "
                   f"{fr['n_valid']}/{fr['n_clips']} | {tx.get('n_valid', '–')}/{tx.get('n_clips', '–')} | "
                   f"{beta_str(fr)} | {beta_str(tx)} | {f(fr.get('spearman_rho'))} | {f(tx.get('spearman_rho'))} |")
    pair = {k: d for k, d in res.items() if d.get("pair_profile") or d.get("inserted_bounce")}
    if pair:
        out += ["", "## Pair mode: timing between fixed endpoints", "",
                "RMS distance (px), along the fitted coordinate (height; distance along the slope), of the tracked path "
                "from the true motion between the key frames ('physics') and from constant-speed motion between "
                "them ('linear'), on valid clips, over the fitted frames. "
                "Inserted bounce: projectile clips whose ball touches the floor before the second (apex) key frame.",
                "", "| model / system | valid clips | median RMS physics | median RMS linear | closer to physics | inserted bounce |",
                "|---|---|---|---|---|---|"]
        for k, d in pair.items():
            p, b = d.get("pair_profile") or {}, d.get("inserted_bounce")
            out.append(f"| {k} | {p.get('n', '–')} | {f(p.get('median_rms_physics'), 1)} | "
                       f"{f(p.get('median_rms_linear'), 1)} | {p.get('closer_to_physics', '–')}/{p.get('n', '–')} | "
                       f"{'–' if not b else str(b['n']) + '/' + str(b['n_tracked'])} |")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-root", default=os.environ.get("PHYSWEEP_OUT", os.path.join(CODE_DIR, "..", "runs")))
    ap.add_argument("--run", default="main_frame")
    ap.add_argument("--text-run", default="main_text")
    ap.add_argument("--results", default=RESULTS)
    a = ap.parse_args()
    res = analyze(a.out_root, a.run, a.text_run)
    os.makedirs(a.results, exist_ok=True)
    stem = os.path.join(a.results, f"{a.run}_frame")
    with open(stem + ".json", "w") as fh:
        json.dump(res, fh, indent=1)
    md = to_md(a.run, a.text_run, res)
    with open(stem + ".md", "w") as fh:
        fh.write(md + "\n")
    print(md)


if __name__ == "__main__":
    main()
