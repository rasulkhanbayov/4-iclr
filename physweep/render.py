#!/usr/bin/env python3
"""
physweep/render.py
===================
Deterministic 2D rendering engine for the PhysWeep systems (paper Section 5,
Appendix "System grids and rendering details").

Each system is a closed-form 2D simulator producing:
  - a sequence of frames (T=24 @ 24fps, 256x256, single high-contrast disk on
    a plain background with a fixed ground line), and
  - the ground-truth trajectory of the tracked observable (position, angle,
    or bounce heights) needed later by the physics fitters in
    physweep_metrics.py.

No external assets, no labels beyond the analytically known theta. Seeding is
explicit so every clip is reproducible from (system, theta, seed).

This module does NOT call any video generator. It produces the conditioning
frames given to a generator (C1 channel) and, for E6 (negative control), the
full ground-truth continuation used to validate the tracker + fitter pipeline
before any real model is touched.
"""

from __future__ import annotations
import numpy as np

WIDTH = 256
HEIGHT = 256
N_FRAMES = 24
FPS = 24
DISK_RADIUS = 8
GROUND_Y = HEIGHT - 24          # fixed ground line, px from top
BG_VALUE = 235                  # plain light background
DISK_VALUE = 20                 # high-contrast dark disk
GROUND_VALUE = 120

DT = 1.0 / FPS


def _blank_canvas() -> np.ndarray:
    frame = np.full((HEIGHT, WIDTH), BG_VALUE, dtype=np.uint8)
    frame[GROUND_Y:, :] = GROUND_VALUE
    return frame


def _draw_disk(frame: np.ndarray, cx: float, cy: float, radius: int = DISK_RADIUS) -> None:
    """Rasterize a filled disk at (cx, cy) in-place. Silently clips off-canvas."""
    x0, x1 = int(cx - radius) - 1, int(cx + radius) + 2
    y0, y1 = int(cy - radius) - 1, int(cy + radius) + 2
    x0c, x1c = max(x0, 0), min(x1, WIDTH)
    y0c, y1c = max(y0, 0), min(y1, HEIGHT)
    if x0c >= x1c or y0c >= y1c:
        return
    ys, xs = np.mgrid[y0c:y1c, x0c:x1c]
    mask = (xs - cx) ** 2 + (ys - cy) ** 2 <= radius ** 2
    frame[y0c:y1c, x0c:x1c][mask] = DISK_VALUE


def _render_positions(positions: np.ndarray) -> np.ndarray:
    """positions: (T, 2) array of (x_px, y_px) disk centers -> (T, H, W) uint8 frames."""
    frames = np.empty((len(positions), HEIGHT, WIDTH), dtype=np.uint8)
    for t, (x, y) in enumerate(positions):
        frame = _blank_canvas()
        _draw_disk(frame, x, y)
        frames[t] = frame
    return frames


# ---------------------------------------------------------------------------
# System 1: Projectile (theta = g, recovered via parabola curvature)
# ---------------------------------------------------------------------------
PX_PER_M = 40.0  # rendering scale: shared across systems that use metric theta


def simulate_projectile(g: float, seed: int, n_frames: int = N_FRAMES):
    """Launch a disk under gravity g (m/s^2) with an initial upward velocity
    chosen analytically so the full parabolic arc (launch to landing at the
    same height) spans the clip duration exactly, for every g in the grid.
    This keeps the arc fully visible and unclipped from g=1.6 to g=25 (image
    convention: y grows downward, so y(t) = y0 - v0*t + 0.5*g*t^2).
    Returns (frames [T,H,W] uint8, y_px [T] float, t [T] float)."""
    rng = np.random.default_rng(seed)
    t = np.arange(n_frames) * DT
    duration = t[-1]

    v0 = 0.5 * g * duration          # m/s: symmetric arc returns to y0 at t=duration
    y0 = GROUND_Y - DISK_RADIUS - rng.uniform(5, 15)   # start just above ground line
    x0 = rng.uniform(50, 80)
    vx = rng.uniform(60, 90)          # px/s, horizontal drift for visual clarity

    x = x0 + vx * t
    y = y0 - v0 * PX_PER_M * t + 0.5 * g * PX_PER_M * t ** 2
    x = np.clip(x, DISK_RADIUS, WIDTH - DISK_RADIUS)
    # no y-clipping: v0 is chosen so y never leaves [y0 - apex_offset, y0] by construction

    positions = np.stack([x, y], axis=1)
    frames = _render_positions(positions)
    return frames, y.astype(float), t


# ---------------------------------------------------------------------------
# System 2/3: Damped pendulum (theta = omega or zeta)
# ---------------------------------------------------------------------------
def simulate_damped_pendulum(omega: float, zeta: float, seed: int, n_frames: int = N_FRAMES):
    """Small-angle damped pendulum: theta(t) = A * exp(-zeta*omega*t) *
    cos(omega_d * t + phi), omega_d = omega*sqrt(1-zeta^2) (underdamped).
    Rendered as a disk (bob) swinging from a fixed pivot.
    Returns (frames, bob_x_px [T] float [the oscillatory observable], t [T])."""
    rng = np.random.default_rng(seed)
    pivot_x, pivot_y = WIDTH / 2, 40.0
    length_px = 90.0
    amp0 = rng.uniform(0.35, 0.55)     # initial angle, radians
    phi = rng.uniform(-0.1, 0.1)

    zeta = min(zeta, 0.999)
    omega_d = omega * np.sqrt(max(1.0 - zeta ** 2, 1e-6))

    t = np.arange(n_frames) * DT
    angle = amp0 * np.exp(-zeta * omega * t) * np.cos(omega_d * t + phi)

    bob_x = pivot_x + length_px * np.sin(angle)
    bob_y = pivot_y + length_px * np.cos(angle)

    positions = np.stack([bob_x, bob_y], axis=1)
    frames = _render_positions(positions)
    return frames, bob_x.astype(float), t


# ---------------------------------------------------------------------------
# System 4: Bouncing ball (theta = e, restitution)
# ---------------------------------------------------------------------------
def simulate_bouncing_ball(e: float, seed: int, n_frames: int = N_FRAMES, g: float = 800.0,
                           drop_height_px: float = 15.0):
    """Vertical bounce with coefficient of restitution e. g and drop_height_px
    are chosen (not physically literal) so that >= 3 bounces occur within the
    24-frame clip across the full e grid (0.2-0.97) — a real bounce needs
    enough sub-clip time to show >=2 peaks for fit_restitution_from_bounces.
    Integrated with small sub-steps per frame for bounce-timing accuracy.
    Returns (frames, y_px [T] float, t [T], peak_heights [np.ndarray of
    successive local-maximum heights above ground, one per completed bounce]).
    """
    rng = np.random.default_rng(seed)
    x = rng.uniform(WIDTH * 0.35, WIDTH * 0.65)
    floor = GROUND_Y - DISK_RADIUS
    y = floor - drop_height_px
    vy = 0.0

    substeps = 20
    sub_dt = DT / substeps
    t = np.arange(n_frames) * DT
    ys = np.empty(n_frames)
    heights = np.empty(n_frames)
    peak_heights = []
    rising = False
    last_height = floor - y

    for i in range(n_frames):
        ys[i] = y
        heights[i] = floor - y
        for _ in range(substeps):
            vy += g * sub_dt
            y += vy * sub_dt
            if y >= floor:
                y = floor
                vy = -vy * e
            h = floor - y
            if rising and h < last_height:
                peak_heights.append(last_height)   # local max just passed
                rising = False
            elif h > last_height:
                rising = True
            last_height = h

    positions = np.stack([np.full(n_frames, x), ys], axis=1)
    frames = _render_positions(positions)
    return frames, ys.astype(float), t, np.array(peak_heights, dtype=float)


# ---------------------------------------------------------------------------
# System 5: Spring-mass (theta = k, recovered via oscillation period)
# ---------------------------------------------------------------------------
def simulate_spring_mass(k: float, seed: int, n_frames: int = N_FRAMES, mass_kg: float = 1.0):
    """Undamped horizontal spring-mass: x(t) = A*cos(omega_n*t + phi),
    omega_n = sqrt(k/m). k in N/m with a px-per-meter scale for rendering.
    Returns (frames, x_px [T] float, t [T])."""
    rng = np.random.default_rng(seed)
    px_per_m = 60.0
    amp_m = rng.uniform(0.5, 0.9)
    phi = rng.uniform(-0.15, 0.15)
    cy = HEIGHT / 2
    cx0 = WIDTH / 2

    omega_n = np.sqrt(k / mass_kg)
    t = np.arange(n_frames) * DT
    x_m = amp_m * np.cos(omega_n * t + phi)
    x_px = cx0 + x_m * px_per_m
    x_px = np.clip(x_px, DISK_RADIUS, WIDTH - DISK_RADIUS)

    positions = np.stack([x_px, np.full(n_frames, cy)], axis=1)
    frames = _render_positions(positions)
    return frames, x_px.astype(float), t


# ---------------------------------------------------------------------------
# System 6: Inclined slide (theta = mu, recovered via acceleration along slope)
# ---------------------------------------------------------------------------
def simulate_inclined_slide(mu: float, seed: int, n_frames: int = N_FRAMES,
                            incline_deg: float = 60.0, g: float = 300.0):
    """Disk sliding down a frictional incline: a = g*(sin(a_rad) - mu*cos(a_rad))
    (px/s^2, clipped at 0 so it never slides back up). Returns (frames,
    s_px [T] float [distance traveled along the slope], t [T]).

    incline_deg defaults to 60 (not 30) so the object still slides at every
    grid value including mu=1.0: static friction stalls motion entirely once
    mu >= tan(incline_deg), and the paper's out-of-range grid goes up to
    mu=1.0. tan(60deg)=1.73 clears that with margin; tan(30deg)=0.577 would
    leave mu=0.7 and mu=1.0 stationary (zero signal). See CLAUDE.md Section 2.
    """
    rng = np.random.default_rng(seed)
    a_rad = np.deg2rad(incline_deg)
    accel = max(g * (np.sin(a_rad) - mu * np.cos(a_rad)), 0.0)

    s0 = rng.uniform(0, 10)
    t = np.arange(n_frames) * DT
    s = s0 + 0.5 * accel * t ** 2   # starts at rest

    # map slope-distance to (x, y) pixel coords along the incline
    x0, y0 = 30.0, GROUND_Y - 180.0
    dx, dy = np.cos(a_rad), np.sin(a_rad)
    x = x0 + s * dx
    y = y0 + s * dy
    x = np.clip(x, DISK_RADIUS, WIDTH - DISK_RADIUS)
    y = np.clip(y, DISK_RADIUS, GROUND_Y - DISK_RADIUS)

    positions = np.stack([x, y], axis=1)
    frames = _render_positions(positions)
    return frames, s.astype(float), t


# ---------------------------------------------------------------------------
# Smoke test: render one clip per system, sanity-check shapes.
# ---------------------------------------------------------------------------
def _smoke_test():
    print("PhysWeep renderer smoke test")
    frames, y, t = simulate_projectile(g=9.8, seed=0)
    print(f"projectile:        frames {frames.shape}, y range [{y.min():.1f}, {y.max():.1f}] px")

    frames, bx, t = simulate_damped_pendulum(omega=3.0, zeta=0.05, seed=0)
    print(f"pendulum (omega):  frames {frames.shape}, bob_x range [{bx.min():.1f}, {bx.max():.1f}] px")

    frames, ys, t, heights = simulate_bouncing_ball(e=0.8, seed=0)
    print(f"bouncing ball:     frames {frames.shape}, {len(heights[heights>1])} nonzero height samples")

    frames, xs, t = simulate_spring_mass(k=40.0, seed=0)
    print(f"spring-mass:       frames {frames.shape}, x range [{xs.min():.1f}, {xs.max():.1f}] px")

    frames, s, t = simulate_inclined_slide(mu=0.2, seed=0)
    print(f"inclined slide:    frames {frames.shape}, s range [{s.min():.1f}, {s.max():.1f}] px")

    assert frames.dtype == np.uint8 and frames.shape[1:] == (HEIGHT, WIDTH)
    print("All systems rendered successfully with expected shapes/dtypes.")


if __name__ == "__main__":
    _smoke_test()
