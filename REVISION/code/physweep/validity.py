"""
physweep/validity.py
====================
Measurement-validity checks for a tracked clip, beyond the fit-quality gate.

Why: the R^2 >= 0.8 gate only says the tracked centroid follows the fitted
law. It does not say the centroid belongs to ONE intact object. Frame
inspection of saved clips found high-R^2 fits produced by an object breaking
into fragments, a second object appearing, and an object ballooning in size
(REVISION/01_review_analysis.md, F3-F5). The blob tracker averages every
dark pixel, so all three yield a smooth, well-fitting centroid path.

Checks (thresholds fixed here, 2026-10-15, before any aggregate re-analysis):
  single_object  >= 90% of frames contain exactly one significant dark
                 component (area >= max(4 px, 10% of the frame-0 object area)).
  stable_size    >= 90% of frames have total object area within [0.5, 2.0] x
                 the frame-0 area.
  static         flag, not a failure: max centroid displacement from frame 0
                 is below one disk radius. A still object is a valid
                 measurement of "no motion" (e.g. g_hat ~ 0).
  trackers_agree blob and CoTracker3 both pass the fit gate and
                 |a - b| <= ABS_TOL[system] + 0.15 * (|a| + |b|) / 2.

Labels:
  invalid_fit    fit gate failed (or no track): same as the old pipeline.
  invalid_shape  fit gate passed but single_object or stable_size failed.
  invalid_static (amendment 1) object static on a system where a static
                 object cannot identify the parameter.
  valid          fit gate and both shape checks passed. Sub-status from the
                 second tracker: confirmed / disagree / unconfirmed.

Amendment 1 (2026-10-15, added AFTER the first re-analysis, reported as such):
the first pass found bouncing-ball clips with e_hat ~ 1.0 whose object moved
< 1 px, i.e. restitution "measured" from sub-pixel jitter. For systems whose
parameter is defined only by motion (bouncing_ball, pendulum_omega,
pendulum_zeta, spring_mass) a static object is now invalid. For projectile and
inclined_slide a static object stays a valid measurement of "no acceleration"
(g_hat ~ 0, mu_hat ~ tan(incline)).

Amendment 2 (2026-10-16, added AFTER the step 4 pilot, reported as such): a
HunyuanVideo-1.5 pilot clip moved its camera (the floor line drifted 25 px), so
pixel motion was not object motion. New label invalid_camera: the floor line,
located per frame near its rendered row, must stay within CAMERA_MAX_SHIFT_PX
of its frame-0 position.

Amendment 3 (2026-10-17, added AFTER the option-B re-pilot, reported as such):
HunyuanVideo-1.5 draws a dark contact shadow on the floor under the ball, which
counted as a second object (and pulled the blob centroid down). The object is
now searched for only above the floor line (rows < frame-0 floor row), in both
the shape checks and the v2 blob tracker (`centroid_track_above`). The camera
check guarantees the floor row is stable, so one row per clip suffices.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage

from physweep.render import DISK_VALUE, DISK_RADIUS, GROUND_Y

MASK_TOL = 30                  # identical to track.centroid_track's default
MIN_AREA_ABS = 4
MIN_AREA_FRAC = 0.10
SINGLE_OBJECT_FRAC = 0.90
SIZE_RANGE = (0.5, 2.0)
STABLE_SIZE_FRAC = 0.90
FIT_R2_GATE = 0.8
AGREE_REL = 0.15
ABS_TOL = {                    # in each parameter's own units
    "projectile": 0.5,         # m/s^2
    "bouncing_ball": 0.05,     # restitution
    "inclined_slide": 0.10,    # friction coefficient
    "pendulum_omega": 0.3,     # rad/s
    "pendulum_zeta": 0.02,
    "spring_mass": 2.0,        # N/m
}
CAMERA_MAX_SHIFT_PX = 3                                                     # amendment 2
GROUND_SEARCH = (GROUND_Y - 40, GROUND_Y + 20)
STATIC_UNIDENTIFIABLE = {"bouncing_ball", "pendulum_omega", "pendulum_zeta", "spring_mass"}  # amendment 1


def object_mask(frame: np.ndarray, ground_row: int | None = None) -> np.ndarray:
    """Same pixel rule as the blob tracker: intensity within MASK_TOL of the disk.
    With ground_row (amendment 3), rows at or below the floor line are ignored."""
    m = np.abs(frame.astype(int) - DISK_VALUE) <= MASK_TOL
    if ground_row is not None:
        m[int(ground_row):, :] = False
    return m


def centroid_track_above(frames: np.ndarray, ground_row: int):
    """v2 blob tracker: centroid of disk-like pixels above the floor line (amendment 3)."""
    T = frames.shape[0]
    cx, cy = np.full(T, np.nan), np.full(T, np.nan)
    for i in range(T):
        ys, xs = np.nonzero(object_mask(frames[i], ground_row))
        if len(xs):
            cx[i], cy[i] = xs.mean(), ys.mean()
    return cx, cy


def ground_rows(frames: np.ndarray) -> np.ndarray:
    """Per frame, the row of the strongest bright-to-dark step in the row-mean
    profile near the rendered floor line (amendment 2)."""
    lo, hi = max(GROUND_SEARCH[0], 1), min(GROUND_SEARCH[1], frames.shape[1] - 1)
    prof = frames.astype(float).mean(axis=2)                # (T, H)
    step = prof[:, lo:hi] - prof[:, lo - 1:hi - 1]
    return np.argmin(step, axis=1) + lo


def shape_stats(frames: np.ndarray) -> dict:
    """Per-clip shape statistics. frames: (T, H, W) uint8 grayscale."""
    T = frames.shape[0]
    g = ground_rows(frames)
    masks = [object_mask(f, int(g[0])) for f in frames]
    area = np.array([m.sum() for m in masks], dtype=float)
    a0 = area[0]
    if a0 <= 0:
        g = ground_rows(frames)
        return dict(n_frames=T, area0=0.0, ground_row0=int(g[0]), ground_row_shift=int(np.max(np.abs(g - g[0]))),
                    single_object_frac=0.0, stable_size_frac=0.0,
                    max_components=0, max_area_ratio=float("nan"), min_area_ratio=float("nan"),
                    max_displacement_px=float("nan"))
    min_area = max(MIN_AREA_ABS, MIN_AREA_FRAC * a0)
    n_comp = np.zeros(T, dtype=int)
    cx = np.full(T, np.nan)
    cy = np.full(T, np.nan)
    for i, m in enumerate(masks):
        lab, n = ndimage.label(m)
        if n:
            sizes = ndimage.sum(m, lab, index=np.arange(1, n + 1))
            n_comp[i] = int((sizes >= min_area).sum())
        if m.any():
            ys, xs = np.nonzero(m)
            cx[i], cy[i] = xs.mean(), ys.mean()
    ratio = area / a0
    disp = np.hypot(cx - cx[0], cy - cy[0])
    return dict(
        ground_row0=int(g[0]),
        ground_row_shift=int(np.max(np.abs(g - g[0]))),
        n_frames=T,
        area0=float(a0),
        single_object_frac=float(np.mean(n_comp == 1)),
        stable_size_frac=float(np.mean((ratio >= SIZE_RANGE[0]) & (ratio <= SIZE_RANGE[1]))),
        max_components=int(n_comp.max()),
        max_area_ratio=float(np.nanmax(ratio)),
        min_area_ratio=float(np.nanmin(ratio)),
        max_displacement_px=float(np.nanmax(disp)) if np.any(np.isfinite(disp)) else float("nan"),
    )


def _finite(x) -> bool:
    return x is not None and np.isfinite(x)


def trackers_agree(system: str, a, b) -> bool:
    return abs(a - b) <= ABS_TOL[system] + AGREE_REL * (abs(a) + abs(b)) / 2


def classify(system: str, stats: dict, theta_hat, r2, theta_hat_2=None, r2_2=None) -> dict:
    """Combine the fit gate, shape checks and the optional second tracker into labels."""
    single_ok = stats["single_object_frac"] >= SINGLE_OBJECT_FRAC
    size_ok = stats["stable_size_frac"] >= STABLE_SIZE_FRAC
    static = _finite(stats.get("max_displacement_px")) and stats["max_displacement_px"] < DISK_RADIUS
    fit_ok = _finite(theta_hat) and r2 is not None and r2 >= FIT_R2_GATE
    camera_ok = stats.get("ground_row_shift", 0) <= CAMERA_MAX_SHIFT_PX

    if not fit_ok:
        label = "invalid_fit"
    elif not camera_ok:
        label = "invalid_camera"
    elif not (single_ok and size_ok):
        label = "invalid_shape"
    elif static and system in STATIC_UNIDENTIFIABLE:
        label = "invalid_static"
    else:
        label = "valid"

    second = None
    if label == "valid":
        if _finite(theta_hat_2) and r2_2 is not None and r2_2 >= FIT_R2_GATE:
            second = "confirmed" if trackers_agree(system, theta_hat, theta_hat_2) else "disagree"
        else:
            second = "unconfirmed"

    reasons = []
    if not single_ok:
        reasons.append("multiple_or_missing_objects")
    if not size_ok:
        reasons.append("unstable_size")
    return dict(label=label, second_tracker=second, fit_ok=fit_ok, camera_ok=camera_ok, single_object_ok=single_ok,
                stable_size_ok=size_ok, static=bool(static), shape_fail_reasons=reasons)
