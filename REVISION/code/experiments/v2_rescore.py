#!/usr/bin/env python3
"""
Re-score a finished run without the GPU: re-read each saved video, recompute
the shape and camera statistics, re-fit both trackers' stored trajectories with
the current fitting rules, and re-apply the validity checks. Writes
clips_rescored.jsonl (all shards merged) next to the raw shard files, which are
never modified.

Use it whenever fits.py or validity.py change, so every run is scored by the
same, current rules.

Usage:  python experiments/v2_rescore.py --run pilot [--models a b ...]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CODE_DIR)

import imageio.v2 as iio
import numpy as np

from physweep.fits import fit_theta
from physweep.generators import to_analysis_frames
from physweep.runio import load_latest, raw_files
from physweep.validity import centroid_track_above, classify, shape_stats


def finite(x):
    return x is not None and np.isfinite(x)


def track(rec, key):
    v = rec.get(key)
    return None if v is None else np.where(np.asarray(v, float) < 0, np.nan, np.asarray(v, float))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-root", default=os.environ.get("PHYSWEEP_OUT", os.path.join(CODE_DIR, "..", "runs")))
    ap.add_argument("--run", required=True)
    ap.add_argument("--models", nargs="*")
    a = ap.parse_args()
    root = os.path.join(a.out_root, a.run)
    for model in sorted(a.models or os.listdir(root)):
        mdir = os.path.join(root, model)
        if not os.path.isdir(mdir) or not raw_files(mdir):
            continue
        latest = load_latest(mdir)
        out = []
        for rec in latest.values():
            if "error" in rec:
                out.append(rec)
                continue
            frames = np.stack([np.asarray(f) for f in iio.get_reader(os.path.join(root, model, rec["video"]))])
            ana = to_analysis_frames(frames)
            stats = shape_stats(ana)
            g = stats["ground_row0"]
            dt = rec.get("dt") or 1.0 / rec["fps"]         # frame channel records its own interval
            k = rec.get("n_given") or 0                    # prefix frames copied from the input are not fitted
            bcx, bcy = centroid_track_above(ana, g)          # blob track recomputed with the current tracker
            hat, r2 = fit_theta(rec["system"], bcx[k:], bcy[k:], dt, ground_row=g)
            hat2 = r2b = None
            if rec.get("cot_cx") is not None:
                hat2, r2b = fit_theta(rec["system"], track(rec, "cot_cx")[k:], track(rec, "cot_cy")[k:], dt,
                                      ground_row=g)
            new = dict(rec, **stats)
            new.update(blob_cx=np.nan_to_num(bcx, nan=-1).round(2).tolist(),
                       blob_cy=np.nan_to_num(bcy, nan=-1).round(2).tolist())
            new.update(theta_hat=float(hat) if finite(hat) else None, r2=float(r2),
                       cot_theta_hat=float(hat2) if finite(hat2) else None,
                       cot_r2=None if r2b is None else float(r2b),
                       original_theta_hat=rec.get("theta_hat"), original_label=rec.get("label"))
            new.update(classify(rec["system"], stats, new["theta_hat"], r2, new["cot_theta_hat"], new["cot_r2"]))
            out.append(new)
        with open(os.path.join(root, model, "clips_rescored.jsonl"), "w") as f:
            for r in out:
                f.write(json.dumps(r, default=lambda o: o.item() if hasattr(o, "item") else str(o)) + "\n")
        changed = sum(r.get("original_label") != r.get("label") for r in out if "error" not in r)
        print(f"{model:<18} rescored {len(out)} clips; label changed on {changed}")


if __name__ == "__main__":
    main()
