#!/usr/bin/env python3
"""
Summarize pilot runs (CPU; run on a shared server after the pilot jobs).
Per model: clips done/errored, seconds per clip, peak VRAM, validity labels,
and the projected GPU-hours for the 304-clip main sweep.

Usage:  python experiments/v2_pilot_summary.py [--run pilot]
Writes: $PHYSWEEP_OUT/<run>/pilot_summary.json and prints a table.
"""

import argparse
import collections
import json
import os
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from physweep.runio import load_latest, raw_files

SWEEP_CLIPS = 304


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-root", default=os.environ.get("PHYSWEEP_OUT", "runs"))
    ap.add_argument("--run", default="pilot")
    a = ap.parse_args()
    root = os.path.join(a.out_root, a.run)
    summary = {}
    print(f"{'model':<18}{'done':>5}{'err':>5}{'s/clip':>8}{'VRAM GB':>9}{'valid':>7}{'shape✗':>8}{'fit✗':>6}"
          f"{'static✗':>8}{'cam✗':>5}{'2nd ok':>7}  sweep GPU-h")
    for model in sorted(os.listdir(root)):
        mdir = os.path.join(root, model)
        if not os.path.isdir(mdir) or not raw_files(mdir):
            continue
        recs = list(load_latest(mdir, prefer_rescored=True).values())
        ok = [r for r in recs if "error" not in r]
        err = [r for r in recs if "error" in r]
        lab = collections.Counter(r["label"] for r in ok)
        sec = st.median([r["gen_seconds"] for r in ok]) if ok else float("nan")
        vram = max((r["peak_vram_gb"] or 0) for r in ok) if ok else float("nan")
        conf = sum(r.get("second_tracker") == "confirmed" for r in ok)
        hours = sec * SWEEP_CLIPS / 3600
        summary[model] = dict(done=len(ok), errors=len(err), median_seconds=sec, peak_vram_gb=vram,
                              labels=dict(lab), confirmed=conf, projected_sweep_gpu_hours=hours,
                              first_error=err[0]["error"] if err else None)
        print(f"{model:<18}{len(ok):>5}{len(err):>5}{sec:>8.0f}{vram:>9.1f}{lab.get('valid', 0):>7}"
              f"{lab.get('invalid_shape', 0):>8}{lab.get('invalid_fit', 0):>6}{lab.get('invalid_static', 0):>8}{lab.get('invalid_camera', 0):>5}"
              f"{conf:>7}  {hours:6.1f}")
        if err:
            print(f"   first error: {err[0]['error'][:200]}")
    total = sum(v["projected_sweep_gpu_hours"] for v in summary.values() if v["done"])
    print(f"\nprojected main sweep (304 clips/model, text channel): {total:.0f} GPU-hours")
    with open(os.path.join(root, "pilot_summary.json"), "w") as f:
        json.dump(summary, f, indent=1)


if __name__ == "__main__":
    main()
