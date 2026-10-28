#!/usr/bin/env python3
"""
Artifact-injection test for physweep/validity.py (CPU only, no generator).

Takes ground-truth simulator clips and re-renders them with the artifacts
found in generated clips (REVISION/01_review_analysis.md, F3-F5):
  clean      unmodified ground truth (must be valid)
  still      object never moves (must be valid, flagged static)
  drip       object stays put while fragments drip downward from frame T/3
  duplicate  true moving object plus a second, static copy
  balloon    static object whose radius grows with its top edge fixed
  camera     clean motion, but the whole frame drifts up to 20 px vertically
             (added 2026-10-16 with amendment 2; a HunyuanVideo pilot clip did this)
  shadow     clean motion plus a dark contact shadow on the floor under the ball;
             must stay VALID and accurate (added 2026-10-17 with amendment 3)

For each clip it reports whether the old fit gate (R^2 >= 0.8) passes and
what validity label the new checks give. The point is to show that
artifacts can pass the fit gate yet are caught by the shape checks.

Usage:  python experiments/v2_validity_injection.py
Writes: results_v2/validity_injection.json
"""

from __future__ import annotations
import json
import os
import sys

CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CODE_DIR)
sys.path.insert(0, os.path.join(CODE_DIR, "experiments"))

import numpy as np
import yaml

from physweep import render as R
from physweep.track import centroid_track
from physweep.validity import shape_stats, classify, centroid_track_above
from e5a_cotracker_analysis import REFIT_FN

OUT_DIR = os.path.join(os.path.dirname(CODE_DIR), "results_v2")
CFG = yaml.safe_load(open(os.path.join(CODE_DIR, "physweep", "configs", "systems.yaml")))
SEEDS = range(5)
T = 24


def gt_positions(system: str, theta: float, seed: int) -> np.ndarray:
    if system == "projectile":
        frames = R.simulate_projectile(g=theta, seed=seed, n_frames=T, ground_clearance_px=100)[0]
    elif system == "bouncing_ball":
        frames = R.simulate_bouncing_ball(e=theta, seed=seed, n_frames=T)[0]
    else:
        frames = R.simulate_inclined_slide(mu=theta, seed=seed, n_frames=T)[0]
    cx, cy = centroid_track(frames)          # clean ground truth: positions only
    return np.stack([cx, cy], axis=1)


def draw(objs_per_frame) -> np.ndarray:
    """objs_per_frame: list over frames of [(x, y, radius), ...]."""
    out = np.empty((len(objs_per_frame), R.HEIGHT, R.WIDTH), dtype=np.uint8)
    for t, objs in enumerate(objs_per_frame):
        f = R._blank_canvas()
        for x, y, r in objs:
            R._draw_disk(f, x, y, radius=int(round(r)))
        out[t] = f
    return out


def make_clip(kind: str, pos: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    r0 = R.DISK_RADIUS
    x0, y0 = pos[0]
    k = T // 3
    if kind == "clean":
        return draw([[(x, y, r0)] for x, y in pos])
    if kind == "still":
        return draw([[(x0, y0, r0)] for _ in range(T)])
    if kind == "drip":
        n_drops = 5
        dx = rng.uniform(-6, 6, n_drops)
        accel = rng.uniform(0.25, 0.6, n_drops)        # px / frame^2
        frames = []
        for t in range(T):
            objs = [(x0, y0, r0)]
            if t >= k:
                s = t - k
                objs += [(x0 + dx[j] * s / 6, y0 + r0 + 0.5 * accel[j] * s ** 2, 4) for j in range(n_drops)]
            frames.append(objs)
        return draw(frames)
    if kind == "duplicate":
        return draw([[(x, y, r0), (x0 + 60, y0, r0)] for x, y in pos])
    if kind == "balloon":
        frames = []
        for t in range(T):
            r = r0 + 16 * (t / (T - 1)) ** 2
            frames.append([(x0, y0 - r0 + r, r)])      # top edge fixed, grows downward
        return draw(frames)
    if kind == "camera":
        clean = draw([[(x, y, r0)] for x, y in pos])
        out = np.empty_like(clean)
        for t in range(T):
            shift = int(round(20 * t / (T - 1)))
            out[t] = np.concatenate([clean[t, shift:], np.repeat(clean[t, -1:], shift, axis=0)])
        return out
    if kind == "shadow":
        clean = draw([[(x, y, r0)] for x, y in pos])
        for t in range(T):
            x = int(round(pos[t, 0]))
            clean[t, R.GROUND_Y + 2:R.GROUND_Y + 5, max(x - 10, 0):x + 10] = 15   # dark streak inside the floor
        return clean
    raise ValueError(kind)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    rng = np.random.default_rng(0)
    kinds = ["clean", "still", "drip", "duplicate", "balloon", "camera", "shadow"]
    rows = []
    for system in ["projectile", "bouncing_ball", "inclined_slide"]:
        grid = CFG["systems"][system]["in_range"]
        for theta in grid:
            for seed in SEEDS:
                pos = gt_positions(system, theta, seed)
                for kind in kinds:
                    frames = make_clip(kind, pos, rng)
                    st_ = shape_stats(frames)
                    cx, cy = centroid_track_above(frames, st_["ground_row0"])
                    hat, r2 = REFIT_FN[system](cx, cy)
                    lab = classify(system, shape_stats(frames), hat, r2)
                    rows.append(dict(system=system, theta=theta, seed=seed, kind=kind,
                                     theta_hat=None if not np.isfinite(hat) else float(hat),
                                     r2=float(r2), **lab))

    summary = {}
    print(f"{'system':<15}{'artifact':<11}{'n':>4}{'fit-gate pass':>15}{'valid':>8}{'static':>8}")
    for system in ["projectile", "bouncing_ball", "inclined_slide"]:
        for kind in kinds:
            sel = [r for r in rows if r["system"] == system and r["kind"] == kind]
            n = len(sel)
            fit = sum(r["fit_ok"] for r in sel)
            valid = sum(r["label"] == "valid" for r in sel)
            static = sum(r["static"] for r in sel if r["label"] == "valid")
            summary[f"{system}/{kind}"] = dict(n=n, fit_gate_pass=fit, valid=valid, valid_static=static)
            print(f"{system:<15}{kind:<11}{n:>4}{fit:>15}{valid:>8}{static:>8}")

    out = os.path.join(OUT_DIR, "validity_injection.json")
    with open(out, "w") as f:
        json.dump(dict(summary=summary, rows=rows), f, indent=1,
                  default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
