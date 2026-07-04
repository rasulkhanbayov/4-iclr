#!/usr/bin/env python3
"""
physweep/track.py
==================
Label-free tracking + pixel-to-physics conversion for PhysWeep.

Two responsibilities, kept separate on purpose (E5(a) swaps only the first):
  1. TRACKING: recover the disk's pixel position per frame from raw video
     frames. Default: color-blob centroiding (paper: "robust here" for
     high-contrast synthetic scenes). CoTracker3 is a drop-in alternative
     for the tracker-swap ablation (E5a) — not implemented in this MVP.
  2. UNIT CONVERSION: map tracked pixel coordinates to the physics-frame
     units the fitters in physweep_metrics.py expect. This matters more than
     it looks: physweep_metrics.fit_gravity_from_trajectory assumes a
     y-up, g>0 convention (y(t) = y0 + v0*t - 0.5*g*t^2), whereas image
     pixel coordinates grow DOWNWARD. Feeding raw pixel-y into the fitter
     silently flips the sign of every recovered g. This module is the one
     place that flip happens, so it can't be gotten wrong twice.
"""

from __future__ import annotations
import numpy as np

from physweep.render import DISK_VALUE, PX_PER_M, HEIGHT, WIDTH


def centroid_track(frames: np.ndarray, disk_value: int = DISK_VALUE, tol: int = 30):
    """Blob-centroid tracker: for each frame, find pixels close to the known
    disk intensity and return their centroid. frames: (T, H, W) uint8.
    Returns (cx [T] float, cy [T] float) in pixel coordinates (image
    convention: y grows downward). NaN for any frame with no matching blob.
    """
    T = frames.shape[0]
    cx = np.full(T, np.nan)
    cy = np.full(T, np.nan)
    for i in range(T):
        mask = np.abs(frames[i].astype(int) - disk_value) <= tol
        ys, xs = np.nonzero(mask)
        if len(xs) == 0:
            continue
        cx[i] = xs.mean()
        cy[i] = ys.mean()
    return cx, cy


def pixel_y_to_physics_y(y_px: np.ndarray) -> np.ndarray:
    """Convert image-convention pixel-y (grows downward) to physics-convention
    y in meters (grows upward), as required by fit_gravity_from_trajectory.
    The overall additive offset is irrelevant to the fitter (it fits a free
    intercept), only the sign and scale matter."""
    y_px = np.asarray(y_px, float)
    return -y_px / PX_PER_M


def pixel_x_to_meters(x_px: np.ndarray) -> np.ndarray:
    return np.asarray(x_px, float) / PX_PER_M


def px_to_m(v_px) -> np.ndarray:
    return np.asarray(v_px, float) / PX_PER_M


# ---------------------------------------------------------------------------
# Smoke test: track a rendered projectile clip and confirm the recovered
# trajectory, once unit-converted, matches the known g via the paper's fitter.
# ---------------------------------------------------------------------------
def _smoke_test():
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from physweep.render import simulate_projectile
    from physweep_metrics import fit_gravity_from_trajectory

    print("PhysWeep tracker smoke test (render -> track -> fit, ground truth path)")
    for g_true in [1.6, 5.0, 9.8, 15.0, 25.0]:
        frames, y_px_true, t = simulate_projectile(g=g_true, seed=0)
        cx, cy = centroid_track(frames)
        assert not np.any(np.isnan(cy)), "tracker lost the disk in some frame"
        # sanity: tracked pixel-y should match the renderer's ground truth closely
        px_err = np.max(np.abs(cy - y_px_true))
        y_phys = pixel_y_to_physics_y(cy)
        g_hat, r2 = fit_gravity_from_trajectory(t, y_phys)
        rel_err = abs(g_hat - g_true) / g_true
        print(f"g_true={g_true:6.2f}  g_hat={g_hat:7.3f}  rel_err={rel_err:.4f}  "
              f"R2={r2:.4f}  max_track_px_err={px_err:.2f}")
        assert rel_err < 0.05, f"gravity recovery off by {rel_err:.1%} at g={g_true}"
        assert r2 > 0.99, f"fit R2 too low at g={g_true}"
    print("PASS: tracker + unit conversion + fitter recover g correctly, all signs consistent.")


if __name__ == "__main__":
    _smoke_test()
