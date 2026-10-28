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


def _render_positions(positions: np.ndarray, style: str = "minimal", scene=None) -> np.ndarray:
    """positions: (T, 2) array of (x_px, y_px) disk centers -> (T, H, W) uint8 frames.

    style "minimal" reproduces the original renderer exactly (single disk on a
    plain background with a ground strip). "structured" and "shaded" also call
    scene(frame, t, x, y) to draw the system's physical structure before the
    disk; see _STYLE_NOTE.
    """
    if style not in STYLES:
        raise ValueError(f"unknown style {style!r}; expected one of {STYLES}")
    frames = np.empty((len(positions), HEIGHT, WIDTH), dtype=np.uint8)
    for t, (x, y) in enumerate(positions):
        if style == "minimal":
            frame = _blank_canvas()
            _draw_disk(frame, x, y)
        else:
            frame = _styled_canvas(style)
            if scene is not None:
                scene(frame, t, x, y)
            if style == "shaded":
                _draw_shaded_disk(frame, x, y)
            else:
                _draw_disk(frame, x, y)
        frames[t] = frame
    return frames


# ---------------------------------------------------------------------------
# Scene styles (added 2026-10-15 for the journal revision)
# ---------------------------------------------------------------------------
_STYLE_NOTE = """
Reviewers and our own check (REVISION/01_review_analysis.md, F2) found that the
original conditioning frames show only a dot above a ground strip: no slope, no
pendulum rod, no spring. "structured" draws that structure; "shaded" adds a
background gradient, a shaded ball and a drop shadow, to test sensitivity to
out-of-distribution minimalism. Every structure pixel is kept >= STRUCT_MIN so
it falls outside the tracker's disk mask (|v - DISK_VALUE| <= 30, i.e. <= 50):
the tracker and the validity checks still see only the ball.
"""
STYLES = ("minimal", "structured", "shaded")
STRUCT_VALUE = 150          # slope, mount, wall, table
STRUCT_EDGE = 105           # outlines, rod, spring coil
SHADOW_VALUE = 95
STRUCT_MIN = 90


def _styled_canvas(style: str) -> np.ndarray:
    if style == "structured":
        return _blank_canvas()
    rows = np.linspace(245, 212, HEIGHT)[:, None]
    frame = np.repeat(rows, WIDTH, axis=1).astype(np.uint8)
    frame[GROUND_Y:, :] = GROUND_VALUE
    frame[GROUND_Y:GROUND_Y + 2, :] = 150                       # lit floor edge
    stripes = (np.arange(WIDTH) // 16) % 2 == 0
    frame[GROUND_Y + 2:, stripes] = GROUND_VALUE - 10           # floor texture
    return frame


def _draw_shaded_disk(frame, cx, cy, radius=DISK_RADIUS):
    """Shaded ball: dark core, darker rim, small highlight. Body stays <= 50 so
    the tracker mask covers it; the 2-px highlight is excluded but moves with
    the ball, so it only shifts the centroid by a constant."""
    x0, x1 = max(int(cx - radius) - 1, 0), min(int(cx + radius) + 2, WIDTH)
    y0, y1 = max(int(cy - radius) - 1, 0), min(int(cy + radius) + 2, HEIGHT)
    if x0 >= x1 or y0 >= y1:
        return
    ys, xs = np.mgrid[y0:y1, x0:x1]
    d = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2) / radius
    inside = d <= 1.0
    shade = (40 - 25 * d).clip(15, 40)
    region = frame[y0:y1, x0:x1]
    region[inside] = shade[inside].astype(np.uint8)
    hl = ((xs - (cx - radius * 0.35)) ** 2 + (ys - (cy - radius * 0.35)) ** 2) <= 2 ** 2
    region[hl & inside] = 200


def _fill_mask(frame, mask_fn, value, bbox=None):
    x0, y0, x1, y1 = bbox if bbox else (0, 0, WIDTH, HEIGHT)
    x0, y0 = max(int(x0), 0), max(int(y0), 0)
    x1, y1 = min(int(np.ceil(x1)) + 1, WIDTH), min(int(np.ceil(y1)) + 1, HEIGHT)
    if x0 >= x1 or y0 >= y1:
        return
    ys, xs = np.mgrid[y0:y1, x0:x1]
    frame[y0:y1, x0:x1][mask_fn(xs, ys)] = value


def _draw_line(frame, xa, ya, xb, yb, width=2.0, value=STRUCT_EDGE):
    vx, vy = xb - xa, yb - ya
    L2 = max(vx * vx + vy * vy, 1e-9)

    def m(xs, ys):
        u = np.clip(((xs - xa) * vx + (ys - ya) * vy) / L2, 0, 1)
        return (xs - (xa + u * vx)) ** 2 + (ys - (ya + u * vy)) ** 2 <= (width / 2) ** 2

    pad = width + 1
    _fill_mask(frame, m, value, (min(xa, xb) - pad, min(ya, yb) - pad, max(xa, xb) + pad, max(ya, yb) + pad))


def _fill_polygon(frame, pts, value=STRUCT_VALUE):
    pts = np.asarray(pts, float)

    def m(xs, ys):
        inside = np.zeros(xs.shape, bool)
        n = len(pts)
        for i in range(n):
            (xa, ya), (xb, yb) = pts[i], pts[(i + 1) % n]
            cond = (ya > ys) != (yb > ys)
            xint = xa + (ys - ya) * (xb - xa) / np.where(yb == ya, 1e-9, yb - ya)
            inside ^= cond & (xs < xint)
        return inside

    _fill_mask(frame, m, value, (pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max()))
    for i in range(len(pts)):
        _draw_line(frame, *pts[i], *pts[(i + 1) % len(pts)], width=1.5)


def _drop_shadow(frame, x, y):
    """Soft ellipse on the floor under the ball; fainter as the ball rises."""
    h = max(GROUND_Y - (y + DISK_RADIUS), 0)
    w = DISK_RADIUS * (1.2 - min(h, 120) / 240)
    _fill_mask(frame, lambda xs, ys: ((xs - x) / w) ** 2 + ((ys - (GROUND_Y + 2)) / 2.5) ** 2 <= 1,
               SHADOW_VALUE, (x - w - 1, GROUND_Y - 1, x + w + 1, GROUND_Y + 5))


def _scene_with_shadow(style):
    return (lambda f, t, x, y: _drop_shadow(f, x, y)) if style == "shaded" else None


# ---------------------------------------------------------------------------
# System 1: Projectile (theta = g, recovered via parabola curvature)
# ---------------------------------------------------------------------------
PX_PER_M = 40.0  # rendering scale: shared across systems that use metric theta


def simulate_projectile(g: float, seed: int, n_frames: int = N_FRAMES,
                        ground_clearance_px: float | None = None, dt_scale: float = 1.0,
                        style: str = "minimal"):
    """Launch a disk under gravity g (m/s^2) with an initial upward velocity
    chosen analytically so the full parabolic arc (launch to landing at the
    same height) spans the clip duration exactly, for every g in the grid.
    This keeps the arc fully visible and unclipped from g=1.6 to g=25 (image
    convention: y grows downward, so y(t) = y0 - v0*t + 0.5*g*t^2).

    ground_clearance_px: distance from the ground line to y0 (the starting/
    ending height of the symmetric arc). Default (None) samples 5-15px --
    i.e. the ball starts almost touching the ground, which E6/E1/etc. were
    validated against and should NOT be changed casually. Pass an explicit
    larger value (e.g. 130) when the CONDITIONING FRAME must visually read
    as "clearly mid-air" rather than "at rest on the ground" -- this was
    added for E0 after finding the default confounded a generator's
    tendency to keep a ground-adjacent object stationary with a genuine
    gravity-conditioning failure (see CLAUDE.md Section 5). Max safe value
    is bounded by apex_offset (up to ~115px at g=25) plus frame height.

    dt_scale (E5b scale-invariance ablation, added 2026-08-2x): multiplies
    the per-frame timestep, so dt_scale=2.0 means each rendered frame
    represents TWICE the real elapsed time (equivalent to halving the
    effective clip fps while keeping n_frames fixed) -- the object covers
    more of its trajectory per frame. Default 1.0 reproduces the exact
    behavior every prior E0/E1/E4/E6/E7 call relied on; this parameter did
    not exist when those were validated, so leaving it at the default is
    required for reproducing those results, not just convenient.
    Returns (frames [T,H,W] uint8, y_px [T] float, t [T] float)."""
    rng = np.random.default_rng(seed)
    t = np.arange(n_frames) * DT * dt_scale
    duration = t[-1]

    v0 = 0.5 * g * duration          # m/s: symmetric arc returns to y0 at t=duration
    clearance = ground_clearance_px if ground_clearance_px is not None else rng.uniform(5, 15)
    y0 = GROUND_Y - DISK_RADIUS - clearance
    x0 = rng.uniform(50, 80)
    vx = rng.uniform(60, 90)          # px/s, horizontal drift for visual clarity

    x = x0 + vx * t
    y = y0 - v0 * PX_PER_M * t + 0.5 * g * PX_PER_M * t ** 2
    x = np.clip(x, DISK_RADIUS, WIDTH - DISK_RADIUS)
    # no y-clipping: v0 is chosen so y never leaves [y0 - apex_offset, y0] by construction

    positions = np.stack([x, y], axis=1)
    frames = _render_positions(positions, style, _scene_with_shadow(style))
    return frames, y.astype(float), t


# ---------------------------------------------------------------------------
# System 2/3: Damped pendulum (theta = omega or zeta)
# ---------------------------------------------------------------------------
def simulate_damped_pendulum(omega: float, zeta: float, seed: int, n_frames: int = N_FRAMES,
                             dt_scale: float = 1.0, style: str = "minimal"):
    """Small-angle damped pendulum: theta(t) = A * exp(-zeta*omega*t) *
    cos(omega_d * t + phi), omega_d = omega*sqrt(1-zeta^2) (underdamped).
    Rendered as a disk (bob) swinging from a fixed pivot.
    dt_scale: see simulate_projectile's docstring (E5b ablation); default 1.0
    reproduces every prior call's exact behavior.
    Returns (frames, bob_x_px [T] float [the oscillatory observable], t [T])."""
    rng = np.random.default_rng(seed)
    pivot_x, pivot_y = WIDTH / 2, 40.0
    length_px = 90.0
    amp0 = rng.uniform(0.35, 0.55)     # initial angle, radians
    phi = rng.uniform(-0.1, 0.1)

    zeta = min(zeta, 0.999)
    omega_d = omega * np.sqrt(max(1.0 - zeta ** 2, 1e-6))

    t = np.arange(n_frames) * DT * dt_scale
    angle = amp0 * np.exp(-zeta * omega * t) * np.cos(omega_d * t + phi)

    bob_x = pivot_x + length_px * np.sin(angle)
    bob_y = pivot_y + length_px * np.cos(angle)

    positions = np.stack([bob_x, bob_y], axis=1)

    def scene(f, i, x, y):
        _fill_polygon(f, [(pivot_x - 24, pivot_y - 8), (pivot_x + 24, pivot_y - 8),
                          (pivot_x + 24, pivot_y - 3), (pivot_x - 24, pivot_y - 3)])   # ceiling mount
        _draw_line(f, pivot_x, pivot_y - 3, x, y, width=2.0)                          # rod
        _fill_mask(f, lambda xs, ys: (xs - pivot_x) ** 2 + (ys - pivot_y) ** 2 <= 9, STRUCT_EDGE,
                   (pivot_x - 4, pivot_y - 4, pivot_x + 4, pivot_y + 4))               # pivot

    frames = _render_positions(positions, style, scene)
    return frames, bob_x.astype(float), t


# ---------------------------------------------------------------------------
# System 4: Bouncing ball (theta = e, restitution)
# ---------------------------------------------------------------------------
def simulate_bouncing_ball(e: float, seed: int, n_frames: int = N_FRAMES, g: float = 800.0,
                           drop_height_px: float = 15.0, dt_scale: float = 1.0, style: str = "minimal"):
    """Vertical bounce with coefficient of restitution e. g and drop_height_px
    are chosen (not physically literal) so that >= 3 bounces occur within the
    24-frame clip across the full e grid (0.2-0.97) — a real bounce needs
    enough sub-clip time to show >=2 peaks for fit_restitution_from_bounces.
    Integrated with small sub-steps per frame for bounce-timing accuracy.
    dt_scale: see simulate_projectile's docstring (E5b ablation); scales
    BOTH the reported frame timestamps and the physics substep integration
    (sub_dt), so the simulated bounce dynamics themselves run at the scaled
    rate, not just their reported labels. Default 1.0 reproduces every
    prior call's exact behavior.
    Returns (frames, y_px [T] float, t [T], peak_heights [np.ndarray of
    successive local-maximum heights above ground, one per completed bounce]).
    """
    rng = np.random.default_rng(seed)
    x = rng.uniform(WIDTH * 0.35, WIDTH * 0.65)
    floor = GROUND_Y - DISK_RADIUS
    y = floor - drop_height_px
    vy = 0.0

    substeps = 20
    sub_dt = DT * dt_scale / substeps
    t = np.arange(n_frames) * DT * dt_scale
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
    frames = _render_positions(positions, style, _scene_with_shadow(style))
    return frames, ys.astype(float), t, np.array(peak_heights, dtype=float)


# ---------------------------------------------------------------------------
# System 5: Spring-mass (theta = k, recovered via oscillation period)
# ---------------------------------------------------------------------------
def simulate_spring_mass(k: float, seed: int, n_frames: int = N_FRAMES, mass_kg: float = 1.0,
                         dt_scale: float = 1.0, style: str = "minimal"):
    """Undamped horizontal spring-mass: x(t) = A*cos(omega_n*t + phi),
    omega_n = sqrt(k/m). k in N/m with a px-per-meter scale for rendering.
    dt_scale: see simulate_projectile's docstring (E5b ablation); default
    1.0 reproduces every prior call's exact behavior.
    Returns (frames, x_px [T] float, t [T])."""
    rng = np.random.default_rng(seed)
    px_per_m = 60.0
    amp_m = rng.uniform(0.5, 0.9)
    phi = rng.uniform(-0.15, 0.15)
    cy = HEIGHT / 2
    cx0 = WIDTH / 2

    omega_n = np.sqrt(k / mass_kg)
    t = np.arange(n_frames) * DT * dt_scale
    x_m = amp_m * np.cos(omega_n * t + phi)
    x_px = cx0 + x_m * px_per_m
    x_px = np.clip(x_px, DISK_RADIUS, WIDTH - DISK_RADIUS)

    positions = np.stack([x_px, np.full(n_frames, cy)], axis=1)
    wall_x = 14.0

    def scene(f, i, x, y):
        _fill_polygon(f, [(4, cy - 30), (wall_x, cy - 30), (wall_x, cy + 30), (4, cy + 30)])   # wall
        _fill_polygon(f, [(4, cy + DISK_RADIUS + 1), (WIDTH - 4, cy + DISK_RADIUS + 1),
                          (WIDTH - 4, cy + DISK_RADIUS + 5), (4, cy + DISK_RADIUS + 5)])       # table
        end = x - DISK_RADIUS
        n_coils = 10
        xs_ = np.linspace(wall_x, end, 2 * n_coils + 1)
        ys_ = [cy] + [cy + (6 if j % 2 else -6) for j in range(1, 2 * n_coils)] + [cy]
        for j in range(len(xs_) - 1):
            _draw_line(f, xs_[j], ys_[j], xs_[j + 1], ys_[j + 1], width=1.5)

    frames = _render_positions(positions, style, scene)
    return frames, x_px.astype(float), t


# ---------------------------------------------------------------------------
# System 6: Inclined slide (theta = mu, recovered via acceleration along slope)
# ---------------------------------------------------------------------------
def simulate_inclined_slide(mu: float, seed: int, n_frames: int = N_FRAMES,
                            incline_deg: float = 60.0, g: float = 300.0, dt_scale: float = 1.0,
                            style: str = "minimal"):
    """Disk sliding down a frictional incline: a = g*(sin(a_rad) - mu*cos(a_rad))
    (px/s^2, clipped at 0 so it never slides back up). Returns (frames,
    s_px [T] float [distance traveled along the slope], t [T]).

    incline_deg defaults to 60 (not 30) so the object still slides at every
    grid value including mu=1.0: static friction stalls motion entirely once
    mu >= tan(incline_deg), and the paper's out-of-range grid goes up to
    mu=1.0. tan(60deg)=1.73 clears that with margin; tan(30deg)=0.577 would
    leave mu=0.7 and mu=1.0 stationary (zero signal). See CLAUDE.md Section 2.

    dt_scale: see simulate_projectile's docstring (E5b ablation); default
    1.0 reproduces every prior call's exact behavior.
    """
    rng = np.random.default_rng(seed)
    a_rad = np.deg2rad(incline_deg)
    accel = max(g * (np.sin(a_rad) - mu * np.cos(a_rad)), 0.0)

    s0 = rng.uniform(0, 10)
    t = np.arange(n_frames) * DT * dt_scale
    s = s0 + 0.5 * accel * t ** 2   # starts at rest

    # map slope-distance to (x, y) pixel coords along the incline
    x0, y0 = 30.0, GROUND_Y - 180.0
    dx, dy = np.cos(a_rad), np.sin(a_rad)
    x = x0 + s * dx
    y = y0 + s * dy
    x = np.clip(x, DISK_RADIUS, WIDTH - DISK_RADIUS)
    y = np.clip(y, DISK_RADIUS, GROUND_Y - DISK_RADIUS)

    positions = np.stack([x, y], axis=1)
    # slope surface: the ball's path offset by (radius + 1) toward the solid side (down-left)
    nx, ny = -np.sin(a_rad), np.cos(a_rad)
    off = DISK_RADIUS + 1
    top = (x0 - 12 * dx + off * nx, y0 - 12 * dy + off * ny)
    s_ground = (GROUND_Y - top[1]) / dy
    bottom = (top[0] + s_ground * dx, GROUND_Y)

    def scene(f, i, px, py):
        _fill_polygon(f, [top, bottom, (top[0], GROUND_Y)])

    frames = _render_positions(positions, style, scene)
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
