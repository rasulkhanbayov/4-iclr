"""
physweep/fits.py
================
Closed-form recovery of theta_hat from a tracked trajectory, with the frame
interval `dt` as an explicit argument.

Same fitting logic as experiments/e5a_cotracker_analysis.py (REFIT_FN), but
v1 hard-coded dt = 1/24 s. That is correct for the renderer and LTX-Video, but
not for every generator: CogVideoX-5B plays at 8 fps, so v1 recovered g_hat
values 9x too large in real time (REVISION/01_review_analysis.md, F8). v2
passes each model's declared playback rate. The trajectory must already be in
the renderer's 256-px coordinate frame (see generators.to_analysis_frames).
"""

from __future__ import annotations

import numpy as np

from physweep.design import CFG_KEY, load_cfg
from physweep.track import pixel_y_to_physics_y
from physweep_metrics import (damped_sine_r2, fit_friction_from_slide, fit_gravity_from_trajectory,
                              fit_omega_from_crossings, fit_restitution_from_bounces,
                              fit_zeta_from_envelope, friction_from_acceleration)

_CFG = load_cfg()
SLIDE_G_INTERNAL = 300.0   # must match render.simulate_inclined_slide


def _bad(*arrs):
    return any(a is None or np.any(~np.isfinite(np.asarray(a, float))) for a in arrs)


MIN_FIT_FRAMES = 6


def contact_index(cy, ground_row: float) -> int:
    """First frame where the ball's bottom is within 2 px of the floor line, or len(cy)."""
    from physweep.render import DISK_RADIUS
    hit = np.nonzero(ground_row - np.asarray(cy, float) <= DISK_RADIUS + 2)[0]
    return int(hit[0]) if len(hit) else len(cy)


def fit_theta(system: str, cx, cy, dt: float, ground_row: float | None = None):
    """Return (theta_hat, r2); (nan, 0.0) when the trajectory cannot be fitted.

    ground_row (added 2026-10-16 after the step 4 pilot): for projectile and
    inclined_slide the fit uses only frames BEFORE the ball reaches the floor.
    Generated clips are 2-6 s long; fitting through the landing and the rest
    on the floor bends the parabola the wrong way (a Wan2.2 pilot clip that
    fell at constant speed and then rested gave g_hat = -0.92). None keeps the
    v1 behaviour (fit every frame)."""
    nan = (float("nan"), 0.0)
    cx = None if cx is None else np.asarray(cx, float)
    cy = None if cy is None else np.asarray(cy, float)
    if _bad(cx, cy) or len(cx) < 4:
        return nan
    if ground_row is not None and system in ("projectile", "inclined_slide"):
        k = contact_index(cy, ground_row)
        if k < MIN_FIT_FRAMES:
            return nan
        cx, cy = cx[:k], cy[:k]
    t = np.arange(len(cx)) * dt

    if system == "projectile":
        return fit_gravity_from_trajectory(t, pixel_y_to_physics_y(cy))

    if system == "bouncing_ball":
        heights = float(np.max(cy)) - cy
        peaks, rising, last = [], False, heights[0]
        for h in heights[1:]:
            if rising and h < last:
                peaks.append(last)
                rising = False
            elif h > last:
                rising = True
            last = h
        return fit_restitution_from_bounces(np.array(peaks)) if len(peaks) >= 2 else nan

    if system == "inclined_slide":
        a = np.deg2rad(_CFG["systems"]["inclined_slide"]["incline_deg"])
        s = (cx - cx[0]) * np.cos(a) + (cy - cy[0]) * np.sin(a)
        acc, r2 = fit_friction_from_slide(t, s)
        return friction_from_acceleration(acc, a, g=SLIDE_G_INTERNAL), r2

    if system in ("pendulum_omega", "pendulum_zeta", "spring_mass"):
        om, r2 = fit_omega_from_crossings(t, cx)
        if not np.isfinite(om):
            return nan
        sc = _CFG["systems"][CFG_KEY.get(system, system)]
        if system == "spring_mass":
            return om ** 2 * sc["mass_kg"], r2
        z, zr2 = fit_zeta_from_envelope(t, cx, om)
        if system == "pendulum_zeta":
            return z, zr2
        return om, damped_sine_r2(t, cx, om, z if np.isfinite(z) else sc["fixed_zeta"])

    raise ValueError(system)
