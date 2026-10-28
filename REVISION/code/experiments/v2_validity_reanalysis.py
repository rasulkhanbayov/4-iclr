#!/usr/bin/env python3
"""
Re-score every saved generated clip (results_v1/e3e5_videos, 630 clips) with
the validity checks in physweep/validity.py. CPU only.

Inputs per clip:
  - the saved .mp4 (shape checks; also re-tracked to confirm the stored row
    matches the video on disk),
  - the stored blob-tracker theta_hat / R^2 (results_v1/e3e5_default_*.json),
  - the CoTracker3 theta_hat / R^2 (results_v1/e5a_cotracker_comparison.json).

Usage:  python experiments/v2_validity_reanalysis.py
Writes: results_v2/validity_reanalysis.json
"""

from __future__ import annotations
import json
import math
import os
import sys

CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CODE_DIR)
sys.path.insert(0, os.path.join(CODE_DIR, "experiments"))

import imageio.v2 as iio
import numpy as np

from physweep.track import centroid_track
from physweep.validity import shape_stats, classify, FIT_R2_GATE
from physweep_metrics import faithfulness_slope, pre
from e5a_cotracker_analysis import REFIT_FN

REV_DIR = os.path.dirname(CODE_DIR)
V1 = os.path.join(REV_DIR, "results_v1")
OUT_DIR = os.path.join(REV_DIR, "results_v2")
SYSTEMS = ["projectile", "bouncing_ball", "inclined_slide", "pendulum_omega", "pendulum_zeta", "spring_mass"]
MODELS = ["ltx", "cogvideox", "dynamicrafter"]


def finite(x):
    return x is not None and isinstance(x, (int, float)) and math.isfinite(x)


def read_gray(path: str) -> np.ndarray:
    frames = [np.asarray(f) for f in iio.get_reader(path)]
    arr = np.stack(frames).astype(float)
    if arr.ndim == 4:
        arr = arr[..., :3].mean(axis=3)
    return np.clip(np.rint(arr), 0, 255).astype(np.uint8)


def slope_pre(rows, split="in"):
    sel = [r for r in rows if r["split"] == split]
    th = np.array([r["theta"] for r in sel], float)
    hat = np.array([r["theta_hat"] for r in sel], float)
    if len(sel) >= 3 and len(set(th.tolist())) >= 2:
        return dict(n=len(sel), slope=float(faithfulness_slope(th, hat)), pre=float(pre(th, hat)))
    return dict(n=len(sel))


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    cot = json.load(open(os.path.join(V1, "e5a_cotracker_comparison.json")))
    all_rows, summaries = [], {}
    for system in SYSTEMS:
        for model in MODELS:
            src = json.load(open(os.path.join(V1, f"e3e5_default_{system}_{model}.json")))
            cot_rows = {(float(r["theta"]), r["split"], r["seed"]): r
                        for r in cot.get(f"{system}_{model}", {}).get("rows", [])}
            pair_rows = []
            for r in src["rows"]:
                key = (float(r["theta"]), r["split"], r["seed"])
                vid = os.path.join(V1, "e3e5_videos", os.path.basename(r["video_path"]))
                frames = read_gray(vid)
                stats = shape_stats(frames)
                # re-track the saved video to check it matches the stored row
                cx, cy = centroid_track(frames)
                rehat, rer2 = REFIT_FN[system](cx, cy)
                c = cot_rows.get(key, {})
                lab = classify(system, stats, r["theta_hat"], r["r2"],
                               c.get("cotracker_theta_hat"), c.get("cotracker_r2"))
                row = dict(system=system, model=model, theta=r["theta"], split=r["split"], seed=r["seed"],
                           video=os.path.basename(vid), theta_hat=r["theta_hat"], r2=r["r2"],
                           cot_theta_hat=c.get("cotracker_theta_hat"), cot_r2=c.get("cotracker_r2"),
                           retracked_theta_hat=float(rehat) if finite(rehat) else None,
                           retracked_r2=float(rer2), **stats, **lab)
                pair_rows.append(row)
            all_rows += pair_rows

            fit = [r for r in pair_rows if r["fit_ok"]]
            valid = [r for r in pair_rows if r["label"] == "valid"]
            conf = [r for r in valid if r["second_tracker"] == "confirmed"]
            reasons = {}
            for r in pair_rows:
                if r["label"] == "invalid_shape":
                    for k in r["shape_fail_reasons"]:
                        reasons[k] = reasons.get(k, 0) + 1
            summaries[f"{system}/{model}"] = dict(
                n=len(pair_rows), n_fit_ok=len(fit), n_valid=len(valid),
                n_invalid_shape=sum(r["label"] == "invalid_shape" for r in pair_rows),
                n_invalid_static=sum(r["label"] == "invalid_static" for r in pair_rows),
                shape_fail_reasons=reasons,
                n_valid_static=sum(r["static"] for r in valid),
                second_tracker={k: sum(r["second_tracker"] == k for r in valid)
                                for k in ["confirmed", "disagree", "unconfirmed"]},
                in_range_old_gate=slope_pre(fit), in_range_valid=slope_pre(valid),
                in_range_valid_confirmed=slope_pre(conf),
            )

    # does re-tracking the saved mp4 reproduce the stored theta_hat?
    chk = [r for r in all_rows if r["fit_ok"] and finite(r["retracked_theta_hat"])]
    close = sum(abs(r["retracked_theta_hat"] - r["theta_hat"]) <= 0.05 * (abs(r["theta_hat"]) + 1) for r in chk)
    retrack = dict(n_fit_ok_rows=sum(r["fit_ok"] for r in all_rows), n_retracked=len(chk), n_close=close)

    tot = {k: sum(s[k] for s in summaries.values()) for k in ["n", "n_fit_ok", "n_valid", "n_invalid_shape", "n_invalid_static", "n_valid_static"]}
    tot["second_tracker"] = {k: sum(s["second_tracker"][k] for s in summaries.values())
                             for k in ["confirmed", "disagree", "unconfirmed"]}
    with open(os.path.join(OUT_DIR, "validity_reanalysis.json"), "w") as f:
        json.dump(dict(totals=tot, retrack_check=retrack, summaries=summaries, rows=all_rows), f, indent=1,
                  default=lambda o: o.item() if hasattr(o, "item") else (None if o != o else str(o)))

    print(f"{'pair':<30}{'n':>4}{'fit':>5}{'valid':>6}{'shape✗':>7}{'static':>7}{'conf':>5}{'disag':>6}{'unconf':>7}")
    for k, s in summaries.items():
        st = s["second_tracker"]
        print(f"{k:<30}{s['n']:>4}{s['n_fit_ok']:>5}{s['n_valid']:>6}{s['n_invalid_shape']:>7}"
              f"{s['n_valid_static']:>7}{st['confirmed']:>5}{st['disagree']:>6}{st['unconfirmed']:>7}")
    print("TOTAL", tot)
    print("re-track check:", retrack)


if __name__ == "__main__":
    main()
