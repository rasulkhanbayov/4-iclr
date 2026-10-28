#!/usr/bin/env python3
"""
physweep/track.py
==================
Label-free tracking + pixel-to-physics conversion for PhysWeep.

Two responsibilities, kept separate on purpose (E5(a) swaps only the first):
  1. TRACKING: recover the disk's pixel position per frame from raw video
     frames. Default: color-blob centroiding (paper: "robust here" for
     high-contrast synthetic scenes). CoTracker3 (cotracker_track(), below)
     is a drop-in alternative for the tracker-swap ablation (E5a).
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


_COTRACKER_MODEL = None  # lazy-loaded singleton, avoid re-downloading/re-loading per clip


def _get_cotracker_model():
    global _COTRACKER_MODEL
    if _COTRACKER_MODEL is None:
        import torch
        # "online" (chunked), not "offline": offline caps at 60 frames, but
        # this project's pendulum_omega/spring_mass clips run to 180 frames
        # (systems.yaml) -- online processes in windows internally so there
        # is no hard frame-count ceiling to work around per-system.
        _COTRACKER_MODEL = torch.hub.load("facebookresearch/co-tracker", "cotracker3_online")
        if torch.cuda.is_available():
            _COTRACKER_MODEL = _COTRACKER_MODEL.cuda()
    return _COTRACKER_MODEL


def cotracker_track(frames: np.ndarray, disk_value: int = DISK_VALUE, tol: int = 30):
    """E5(a) tracker-swap ablation: CoTracker3 (online variant) in place of
    blob-centroiding, same (cx[T], cy[T]) contract as centroid_track() so it
    is a drop-in for every downstream fitter. frames: (T, H, W) uint8
    grayscale.

    Seeds CoTracker with a SINGLE query point at the disk's frame-0 centroid
    (found via the same blob-centroid logic used elsewhere in this file --
    only for frame 0, not as the tracker under test) and lets CoTracker3
    track that one point across the clip; this is the natural analogue of
    "give it the known starting pixel," matching how centroid_track()
    implicitly starts from a known disk_value/tol rather than requiring
    open-set object discovery. Requires a GPU-capable torch + the
    facebookresearch/co-tracker hub entrypoint (auto-downloads weights on
    first call); see requirements.txt for the pin this was verified against.

    CHUNKING (real bug fixed 2026-08-2x after a first attempt crashed with
    "Online mode: video chunk must be <= window size."): the online model
    does NOT accept a whole clip in one call. It must be fed in a sliding-
    window loop of at most `model.step*2` (default 8*2=16) frames per call,
    triggered every `model.step` (default 8) new frames, exactly matching
    the reference loop in the upstream repo's online_demo.py (`_process_step`
    slicing `window_frames[-model.step*2:]`). The FIRST call
    (is_first_step=True) only initializes internal state and returns
    (None, None) -- it must still be issued, its return discarded. A final
    trailing call after the frame loop ends covers any leftover frames.
    """
    import torch

    T, H, W = frames.shape
    mask0 = np.abs(frames[0].astype(int) - disk_value) <= tol
    ys0, xs0 = np.nonzero(mask0)
    if len(xs0) == 0:
        # no seed point at all -- report as fully lost, same as centroid_track
        # would via its own per-frame NaN when no blob is found.
        return np.full(T, np.nan), np.full(T, np.nan)
    x0, y0 = float(xs0.mean()), float(ys0.mean())

    model = _get_cotracker_model()
    device = next(model.parameters()).device
    step = model.step  # default 8; window = 2*step = 16

    # (T,H,W) uint8 grayscale -> per-frame (3,H,W) float RGB tensors
    # (channel-replicated; CoTracker3 expects RGB, this project's scenes are
    # grayscale). Kept as a growing Python list (window_frames), sliced with
    # the EXACT same negative-index formulas as the upstream repo's
    # online_demo.py `_process_step`/main-loop pattern, rather than
    # reimplemented with absolute indices -- a first attempt at the latter
    # silently used the wrong trailing window whenever T is not a multiple
    # of `step` (verified directly: matches only for T in {16,24,32,40,...},
    # diverges for T in {17,20,30,97,180} -- and this project's pendulum_omega/
    # spring_mass systems use T=180, exactly a case that would have diverged).
    frames_t = [torch.from_numpy(frames[t]).float().unsqueeze(0).repeat(3, 1, 1).to(device)
               for t in range(T)]
    queries = torch.tensor([[[0.0, x0, y0]]], device=device)  # (1,1,3): (t=0, x, y)

    def _process_step(window_frames, is_first):
        chunk = torch.stack(window_frames[-step * 2:]).unsqueeze(0)  # (1, t<=16, 3, H, W)
        return model(video_chunk=chunk, is_first_step=is_first, queries=queries)

    pred_tracks, pred_visibility = None, None
    is_first_step = True
    window_frames = []
    i = 0
    for i in range(T):
        if i % step == 0 and i != 0:
            out = _process_step(window_frames, is_first_step)
            if not is_first_step:
                pred_tracks, pred_visibility = out
            is_first_step = False
        window_frames.append(frames_t[i])
    # trailing call for leftover frames, exact same slice formula as the
    # upstream reference (window_frames[-(i % step) - step - 1:]) -- do not
    # simplify this to "last step*2 frames," which only coincides with this
    # formula when T is a multiple of step.
    trailing = window_frames[-(i % step) - step - 1:]
    out = _process_step(trailing, is_first_step) if len(trailing) else (pred_tracks, pred_visibility)
    if not is_first_step:
        pred_tracks, pred_visibility = out

    if pred_tracks is None:
        # clip shorter than one full step (T < step) never triggered a real
        # prediction call -- report fully lost rather than guessing.
        return np.full(T, np.nan), np.full(T, np.nan)

    # IMPORTANT (verified directly against the model's internals, not
    # assumed from the demo script alone): the online predictor accumulates
    # state across calls (self.online_coords_predicted grows by `step` frames
    # every call) and each call's return already covers the FULL clip
    # processed so far, not just the current window -- so the trailing
    # call's pred_tracks already has one row per original frame 0..T-1, with
    # no stitching/offset needed. If this ever comes back a different length
    # than T (e.g. an upstream API change), fail loudly rather than silently
    # misaligning indices against what every fitter expects.
    tracks = pred_tracks[0, :, 0, :].detach().cpu().numpy()  # (T, 2) -> x, y
    vis = pred_visibility[0, :, 0].detach().cpu().numpy().astype(bool)
    if len(tracks) != T:
        raise RuntimeError(f"cotracker_track: expected {T} tracked frames, got {len(tracks)} -- "
                          f"CoTracker3's online-mode accumulation behavior may have changed upstream.")

    cx = np.where(vis, tracks[:, 0], np.nan)
    cy = np.where(vis, tracks[:, 1], np.nan)
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


def _smoke_test_cotracker():
    """Same validation as _smoke_test() but for the E5(a) tracker-swap
    ablation's CoTracker3 path -- run this on a GPU node with network
    to download weights on first call), NOT on a local machine without
    torch/CUDA. Confirms cotracker_track() is a correct drop-in for
    centroid_track() against ground truth BEFORE trusting it on any
    generated-model clip."""
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from physweep.render import simulate_projectile
    from physweep_metrics import fit_gravity_from_trajectory

    print("PhysWeep CoTracker3 smoke test (render -> cotracker_track -> fit, ground truth path)")
    for g_true in [1.6, 5.0, 9.8, 15.0, 25.0]:
        frames, y_px_true, t = simulate_projectile(g=g_true, seed=0)
        cx, cy = cotracker_track(frames)
        if np.any(np.isnan(cy)):
            print(f"g_true={g_true:6.2f}: CoTracker3 lost the point in some frame -- FAIL")
            continue
        px_err = np.max(np.abs(cy - y_px_true))
        y_phys = pixel_y_to_physics_y(cy)
        g_hat, r2 = fit_gravity_from_trajectory(t, y_phys)
        rel_err = abs(g_hat - g_true) / g_true
        print(f"g_true={g_true:6.2f}  g_hat={g_hat:7.3f}  rel_err={rel_err:.4f}  "
              f"R2={r2:.4f}  max_track_px_err={px_err:.2f}")
    print("Compare these rel_err/R2 numbers directly against _smoke_test()'s "
         "blob-centroid numbers above -- E5(a)'s claim is that they agree, "
         "not that either is perfect in isolation.")


if __name__ == "__main__":
    _smoke_test()
    print()
    try:
        _smoke_test_cotracker()
    except Exception as e:
        print(f"CoTracker3 smoke test skipped/failed ({e}) -- expected on a "
             f"machine without GPU/torch/network access; run this file on "
             f"a real GPU to actually validate the E5(a) tracker before use.")
