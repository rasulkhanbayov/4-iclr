#!/usr/bin/env python3
"""
Step 10: figures from real generated frames (review items T1/M3: the v1 paper showed no frame; N3/K4: the
v1 figures were AI-drawn or unreadable). CPU only; needs matplotlib (envs/fig, see env/fig.pip-freeze.txt).

  teaser    (a) motion trails of real clips for a low, Earth and high requested g, one model, one seed pair;
            (b) median recovered g vs requested g, projectile, every model (valid clips).
  scenes    the conditioning scene of each system in the structured and shaded styles, plus the simulated
            motion (what the requested parameter does in the renderer).
  failures  one example per validity failure, with the blob track overlaid.
  trackers  clips on which the blob tracker and CoTracker3 disagree, both tracks overlaid.
  frame     frame-implied channel (run main_frame): real clips of the most faithful model, median g_hat in the
            frame vs text channel, pair-mode timing against the true and constant-speed motion, and the
            scene-duration window (needs results_v2/window_sensitivity_clips.jsonl).

Every clip shown is chosen by a fixed rule (stated in SELECTION below and in each caption), not by eye. The
chosen clip ids and every number printed on a figure are written to figures/figures_manifest.json, so the
captions can be checked against the data (and registered in reproduce_numbers.py).

Usage:  python experiments/v2_figures.py [teaser scenes failures trackers frame]   (default: all)
Writes: <REVISION>/figures/fig_<name>.pdf and .png, figures/figures_manifest.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CODE_DIR)

import imageio.v2 as iio
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

from physweep.conditioning import render_ground_truth
from physweep.fits import contact_index
from physweep.runio import load_latest, raw_files

REV = os.path.dirname(CODE_DIR)
FIGDIR = os.path.join(REV, "figures")
OUT_ROOT = os.environ.get("PHYSWEEP_OUT", os.path.join(REV, "runs"))
RUN = "main_text"
SIZE = 256                                       # analysis frames: centre square crop, 256 x 256 (generators.py)
FULL_W, COL_W = 7.0, 3.4                         # inches: two-column and one-column figure widths
MODEL_NAMES = {
    "cogvideox": "CogVideoX-5B", "cogvideox15_i2v": "CogVideoX1.5-5B", "cosmos2_2b": "Cosmos-Predict2-2B",
    "dynamicrafter": "DynamiCrafter", "hunyuan15_i2v": "HunyuanVideo-1.5", "ltx": "LTX-Video",
    "ltx2": "LTX-2", "wan22_i2v_a14b": "Wan2.2-I2V-A14B", "wan22_ti2v_5b": "Wan2.2-TI2V-5B"}
SYSTEM_NAMES = {"projectile": "projectile", "bouncing_ball": "bouncing ball", "inclined_slide": "inclined slide"}
SELECTION = {
    "teaser_model": "the model with the most valid projectile clips in main_text",
    "teaser_seeds": "the first (scene seed, noise seed), in seed order, at which g = 1.6, 9.8 and 25 are all valid",
    "multiple_objects": "invalid_shape with a multiple/missing-object failure: most components in a frame",
    "unstable_size": "invalid_shape with only a size failure: largest area ratio to frame 0",
    "camera": "invalid_camera: largest floor-line shift",
    "static": "invalid_static: smallest maximum displacement",
    "fit": "invalid_fit with a clean single object of stable size, tracked in >= 95% of frames: lowest R^2",
    "trackers": "all valid clips whose second tracker disagrees, ordered by relative difference of the two estimates",
}
plt.rcParams.update({"font.size": 8, "axes.titlesize": 8, "axes.labelsize": 8, "legend.fontsize": 7,
                     "xtick.labelsize": 7, "ytick.labelsize": 7, "pdf.fonttype": 42, "savefig.dpi": 300})


# --------------------------------------------------------------------------- data helpers

def records(model, run=RUN):
    mdir = os.path.join(OUT_ROOT, run, model)
    return list(load_latest(mdir, prefer_rescored=True).values()) if os.path.isdir(mdir) and raw_files(mdir) else []


def models(run=RUN):
    root = os.path.join(OUT_ROOT, run)
    return sorted(m for m in os.listdir(root) if os.path.isdir(os.path.join(root, m)) and raw_files(os.path.join(root, m)))


def is_valid(r):
    return "error" not in r and r.get("label") == "valid" and r.get("theta_hat") is not None


def track(r, key):
    v = r.get(key)
    return None if v is None else np.where(np.asarray(v, float) < 0, np.nan, np.asarray(v, float))


def frames_rgb(r, run=RUN):
    """The clip's frames in analysis coordinates: centre square crop resized to 256 x 256, RGB."""
    path = os.path.join(OUT_ROOT, run, r["model"], r["video"])
    out = []
    for f in iio.get_reader(path):
        f = np.asarray(f)[..., :3]
        h, w = f.shape[:2]
        s = min(h, w)
        y0, x0 = (h - s) // 2, (w - s) // 2
        out.append(np.asarray(Image.fromarray(f[y0:y0 + s, x0:x0 + s]).resize((SIZE, SIZE), Image.BILINEAR)))
    return np.stack(out)


def fitted_window(r):
    cy = track(r, "blob_cy")
    k0 = r.get("n_given") or 0
    if r["system"] in ("projectile", "inclined_slide") and cy is not None:
        return k0, max(k0 + 2, contact_index(cy, r["ground_row0"]))
    return k0, r["n_frames_out"]


def trail(frames, idx):
    """Stroboscopic image: per-pixel minimum over the chosen frames (the ball is the darkest object)."""
    return frames[idx].min(axis=0)


def label_name(m):
    return MODEL_NAMES.get(m, m)


# --------------------------------------------------------------------------- figures

def fig_teaser(manifest):
    per = {m: [r for r in records(m) if r["system"] == "projectile"] for m in models()}
    best = max(per, key=lambda m: (sum(is_valid(r) for r in per[m]), m))
    ok = {(r["scene_seed"], r["noise_seed"], r["theta"]): r for r in per[best] if is_valid(r)}
    gs = (1.6, 9.8, 25)
    seeds = next((s, z) for s in range(4) for z in range(1000, 1004) if all((s, z, g) in ok for g in gs))
    chosen = [ok[(seeds[0], seeds[1], g)] for g in gs]

    fig = plt.figure(figsize=(FULL_W, 2.3))
    gsp = fig.add_gridspec(1, 5, width_ratios=[1, 1, 1, 1.32, 1.0], wspace=0.08, left=0.01, right=0.995,
                           top=0.86, bottom=0.21)
    out = dict(model=best, scene_seed=seeds[0], noise_seed=seeds[1], clips=[])
    for i, r in enumerate(chosen):
        ax = fig.add_subplot(gsp[0, i])
        fr = frames_rgb(r)
        a, b = fitted_window(r)
        idx = np.unique(np.linspace(a, b - 1, 8).round().astype(int))
        ax.imshow(trail(fr, idx))
        cx, cy = track(r, "blob_cx"), track(r, "blob_cy")
        ax.plot(cx[a:b], cy[a:b], color="#d62728", lw=0.9)
        ax.set_xticks([]), ax.set_yticks([])
        ax.set_title(f"requested $g$ = {r['theta']:g}\nrecovered $\\hat g$ = {r['theta_hat']:.2f}", pad=2)
        out["clips"].append(dict(clip_id=r["clip_id"], theta=r["theta"], theta_hat=r["theta_hat"], r2=r["r2"],
                                 frames_shown=idx.tolist()))
    p0, p2 = fig.axes[0].get_position(), fig.axes[2].get_position()
    fig.text((p0.x0 + p2.x1) / 2, 0.035, f"(a) {label_name(best)}, scene seed {seeds[0]}, noise seed {seeds[1]}\n"
             "8 frames of each clip overlaid; blob track in red", ha="center", va="bottom", linespacing=1.3)

    ax = fig.add_subplot(gsp[0, 3])
    pos = ax.get_position()
    ax.set_position([pos.x0 + 0.05, pos.y0, pos.width - 0.05, pos.height])
    grid = sorted({r["theta"] for m in per for r in per[m]})
    ax.axvspan(5, 15, color="0.92", lw=0)
    ax.plot([0, 26], [0, 26], color="0.4", ls="--", lw=0.8, label="faithful ($\\hat g = g$)")
    cmap = plt.get_cmap("tab10")
    out["medians"] = {}
    for j, m in enumerate(sorted(per)):
        med = []
        for g in grid:
            v = [r["theta_hat"] for r in per[m] if is_valid(r) and r["theta"] == g]
            med.append(np.median(v) if len(v) >= 2 else np.nan)
        out["medians"][m] = dict(zip(map(str, grid), [None if not np.isfinite(x) else float(x) for x in med]))
        ax.plot(grid, med, marker="o", ms=2.5, lw=0.8, color=cmap(j % 10), label=label_name(m))
    ax.set_xlim(0, 26), ax.set_ylim(-3, 26)
    ax.set_xlabel("requested $g$ (m s$^{-2}$)"), ax.set_ylabel("median recovered $\\hat g$")
    ax.set_title("(b) all models, valid clips", pad=2)
    ax.text(10, 24.3, "in range", ha="center", fontsize=6.5, color="0.35")
    lax = fig.add_subplot(gsp[0, 4])
    lax.axis("off")
    lax.legend(*ax.get_legend_handles_labels(), loc="center left", frameon=False, handlelength=1.2,
               borderaxespad=0, fontsize=6.5)
    save(fig, "teaser")
    manifest["teaser"] = out


SYM = {"projectile": "g", "bouncing_ball": "e", "inclined_slide": "\\mu"}
COORD_LABEL = {"projectile": "height (px)", "bouncing_ball": "height (px)", "inclined_slide": "along slope (px)"}


def fit_coordinate(system, cx, cy, ground_row):
    """The coordinate the fit reads theta from: height above the floor, or distance along the slope."""
    if system == "inclined_slide":
        from physweep.design import load_cfg
        a = np.deg2rad(load_cfg()["systems"]["inclined_slide"]["incline_deg"])
        return (cx - cx[0]) * np.cos(a) + (cy - cy[0]) * np.sin(a)
    return ground_row - cy


def fig_scenes(manifest):
    from physweep import render as R
    from physweep.validity import centroid_track_above, shape_stats
    systems = ("projectile", "bouncing_ball", "inclined_slide")
    thetas = {"projectile": (1.6, 9.8, 25), "bouncing_ball": (0.35, 0.6, 0.9), "inclined_slide": (0.1, 0.4, 1.0)}
    fig, axes = plt.subplots(len(systems), 3, figsize=(FULL_W * 0.75, 4.3),
                             gridspec_kw=dict(width_ratios=[1, 1, 1.3]))
    cmap = plt.get_cmap("viridis")
    for i, s in enumerate(systems):
        for j, style in enumerate(("structured", "shaded")):
            gt = render_ground_truth(s, thetas[s][1], 0, style)
            axes[i, j].imshow(gt[0], cmap="gray", vmin=0, vmax=255)
            axes[i, j].set_xticks([]), axes[i, j].set_yticks([])
            if i == 0:
                axes[i, j].set_title(f"first frame, {style} style", pad=3)
        ax = axes[i, 2]
        for k, th in enumerate(thetas[s]):
            gt = render_ground_truth(s, th, 0, "structured")
            g = shape_stats(gt)["ground_row0"]
            cx, cy = centroid_track_above(gt, g)
            u = fit_coordinate(s, cx, cy, g)
            ax.plot(np.arange(len(u)) * R.DT, u, color=cmap(0.15 + 0.35 * k), lw=1.1, label=f"${SYM[s]}$ = {th:g}")
        ax.set_ylabel(COORD_LABEL[s])
        ax.legend(frameon=False, fontsize=6.5, loc="best", handlelength=1.2)
        ax.tick_params(length=2)
        if i == 0:
            ax.set_title("simulated motion", pad=3)
        ax.set_xlim(0, 1)
        if i == len(systems) - 1:
            ax.set_xlabel("time (s)")
        else:
            ax.set_xticklabels([])
        axes[i, 0].set_ylabel(SYSTEM_NAMES[s])
    fig.subplots_adjust(left=0.05, right=0.985, top=0.94, bottom=0.08, wspace=0.08, hspace=0.12)
    for i in range(len(systems)):                       # room for the motion column's y label
        p = axes[i, 2].get_position()
        axes[i, 2].set_position([p.x0 + 0.075, p.y0, p.width - 0.075, p.height])
    save(fig, "scenes")
    manifest["scenes"] = dict(scene_seed=0, thetas=thetas, frame_rate=24,
                              note="right column: blob track of the simulator's own clip, 24 frames, 1 s")


def pick_failures():
    allr = [dict(r, model=m) for m in models() for r in records(m) if "error" not in r]
    sel = {}

    def best(cands, key):
        cands = [r for r in cands if np.isfinite(key(r))]
        return max(cands, key=lambda r: (key(r), r["clip_id"])) if cands else None

    shape = [r for r in allr if r["label"] == "invalid_shape"]
    sel["multiple_objects"] = best([r for r in shape if "multiple_or_missing_objects" in r["shape_fail_reasons"]],
                                   lambda r: r["max_components"])
    sel["unstable_size"] = best([r for r in shape if r["shape_fail_reasons"] == ["unstable_size"]],
                                lambda r: r["max_area_ratio"])
    sel["camera"] = best([r for r in allr if r["label"] == "invalid_camera"], lambda r: r["ground_row_shift"])
    sel["static"] = best([r for r in allr if r["label"] == "invalid_static"], lambda r: -r["max_displacement_px"])

    def clean(r):
        cy = track(r, "blob_cy")
        return (r["label"] == "invalid_fit" and r["single_object_ok"] and r["stable_size_ok"] and cy is not None
                and np.isfinite(cy).mean() >= 0.95 and r.get("r2") is not None)
    sel["fit"] = best([r for r in allr if clean(r)], lambda r: -r["r2"])
    return sel


def describe(kind, r):
    return {"multiple_objects": f"up to {r['max_components']} objects in a frame",
            "unstable_size": f"object area up to {r['max_area_ratio']:.1f}x frame 0",
            "camera": f"floor line moves {r['ground_row_shift']} px",
            "static": f"ball moves at most {r['max_displacement_px']:.1f} px",
            "fit": f"fit R$^2$ = {r['r2']:.2f}"}[kind]


FAIL_TITLE = {"multiple_objects": "invalid_shape (extra objects)", "unstable_size": "invalid_shape (object grows)",
              "camera": "invalid_camera", "static": "invalid_static", "fit": "invalid_fit"}


def frame_tag(ax, t):
    ax.text(0.03, 0.97, f"frame {t}", transform=ax.transAxes, va="top", ha="left", fontsize=6,
            bbox=dict(boxstyle="square,pad=0.15", fc="white", ec="none", alpha=0.8))


def fig_failures(manifest):
    sel = pick_failures()
    kinds = [k for k in ("multiple_objects", "unstable_size", "camera", "static", "fit") if sel.get(k)]
    fig, axes = plt.subplots(len(kinds), 4, figsize=(FULL_W * 0.7, 1.36 * len(kinds)))
    out = {}
    for i, k in enumerate(kinds):
        r = sel[k]
        fr = frames_rgb(r)
        idx = np.linspace(0, len(fr) - 1, 4).round().astype(int)
        cx, cy = track(r, "blob_cx"), track(r, "blob_cy")
        for j, t in enumerate(idx):
            ax = axes[i, j]
            ax.imshow(fr[t])
            ax.plot(cx[:t + 1], cy[:t + 1], color="#d62728", lw=0.8)
            ax.set_xticks([]), ax.set_yticks([])
            frame_tag(ax, t)
        out[k] = dict(clip_id=r["clip_id"], model=r["model"], system=r["system"], theta=r["theta"],
                      label=r["label"], rule=SELECTION[k], shown=describe(k, r), frames_shown=idx.tolist())
    fig.subplots_adjust(left=0.01, right=0.99, top=0.965, bottom=0.005, wspace=0.03, hspace=0.24)
    for i, k in enumerate(kinds):
        r, pos = sel[k], axes[i, 0].get_position()
        fig.text(pos.x0, pos.y1 + 0.004, f"{FAIL_TITLE[k]}: {label_name(r['model'])}, {SYSTEM_NAMES[r['system']]}; "
                 f"{describe(k, r)}", fontsize=7, va="bottom")
    save(fig, "failures")
    manifest["failures"] = out


def same_window_estimates(r, ends, dt):
    """Both trackers fitted on the SAME frames (up to the earlier of the two contact frames), to separate a
    tracking difference from a difference in where each tracker detects floor contact."""
    from physweep.fits import fit_theta
    k = min(ends.values())
    est = {}
    for key, name in (("blob", "blob"), ("cot", "cotracker")):
        x, y = track(r, f"{key}_cx"), track(r, f"{key}_cy")
        if r["system"] in ("projectile", "inclined_slide"):
            hat, _ = fit_theta(r["system"], x[:k], y[:k], dt, ground_row=None)
        else:
            hat, _ = fit_theta(r["system"], x, y, dt, ground_row=r["ground_row0"])
        est[f"same_window_{name}"] = float(hat) if np.isfinite(hat) else None
    return est


def fig_trackers(manifest, n_show=6):
    rows, n_valid = [], 0
    for m in models():
        for r in records(m):
            n_valid += is_valid(r)
            if is_valid(r) and r.get("second_tracker") == "disagree" and r.get("cot_theta_hat") is not None:
                a, b = r["theta_hat"], r["cot_theta_hat"]
                rows.append((abs(a - b) / max(1e-9, (abs(a) + abs(b)) / 2), dict(r, model=m)))
    rows = [r for _, r in sorted(rows, key=lambda t: (-t[0], t[1]["clip_id"]))]
    n_all = len(rows)
    rows = rows[:n_show]
    if not rows:
        return
    fig, axes = plt.subplots(2, len(rows), figsize=(FULL_W, 3.1), gridspec_kw=dict(height_ratios=[1, 0.75]))
    axes = axes.reshape(2, -1)
    out = dict(n_disagree=n_all, n_valid=n_valid, shown=[])
    cols = (("blob", "#d62728", "blob centroid"), ("cot", "#1f77b4", "CoTracker3"))
    for j, r in enumerate(rows):
        fr = frames_rgb(r)
        n = len(fr)
        dt = r.get("dt") or 1.0 / r["fps"]
        ends = {}
        for key, _, _ in cols:
            cy = track(r, f"{key}_cy")
            ends[key] = contact_index(cy, r["ground_row0"]) if r["system"] in ("projectile", "inclined_slide") else n
        idx = np.unique(np.linspace(0, max(ends.values()) - 1, 8).round().astype(int))
        ax = axes[0, j]
        ax.imshow(trail(fr, idx))
        for key, col, name in cols:
            ax.plot(track(r, f"{key}_cx")[:ends[key]], track(r, f"{key}_cy")[:ends[key]], color=col, lw=0.9)
        ax.set_xticks([]), ax.set_yticks([])
        ax.set_title(f"{label_name(r['model'])}\n{SYSTEM_NAMES[r['system']]}, ${SYM[r['system']]}$ = {r['theta']:g}\n"
                     f"blob {r['theta_hat']:.2f}, CoTr. {r['cot_theta_hat']:.2f}", pad=2, fontsize=6.3)
        ax = axes[1, j]
        for key, col, name in cols:
            u = fit_coordinate(r["system"], track(r, f"{key}_cx"), track(r, f"{key}_cy"), r["ground_row0"])
            ax.plot(np.arange(n) * dt, u, color=col, lw=0.8, marker="o", ms=1.2, label=name)
            if ends[key] < n:
                ax.axvline((ends[key] - 0.5) * dt, color=col, ls="--", lw=0.7)
        ax.set_xlabel("time (s)", labelpad=1, fontsize=6.5)
        ax.set_ylabel(COORD_LABEL[r["system"]], labelpad=1, fontsize=6.5)
        ax.tick_params(length=2, labelsize=5.5)
        out["shown"].append(dict(clip_id=r["clip_id"], model=r["model"], system=r["system"], theta=r["theta"],
                                 theta_hat_blob=r["theta_hat"], theta_hat_cotracker=r["cot_theta_hat"],
                                 fit_end_frame_blob=int(ends["blob"]), fit_end_frame_cotracker=int(ends["cot"]),
                                 n_frames=int(n), **same_window_estimates(r, ends, dt)))
    axes[1, 0].legend(fontsize=5.5, frameon=False, loc="best")
    fig.subplots_adjust(left=0.045, right=0.995, top=0.85, bottom=0.11, wspace=0.55, hspace=0.12)
    save(fig, "trackers")
    manifest["trackers"] = out


FRAME_RUN = "main_frame"
FRAME_MODELS = ("ltx2", "cosmos2_2b", "dynamicrafter", "wan22_i2v_a14b")
FRAME_MODE = {"ltx2": "prefix", "cosmos2_2b": "prefix", "dynamicrafter": "pair", "wan22_i2v_a14b": "pair"}
SELECTION.update({
    "frame_model": "frame channel: the model with the largest in-range slope on valid projectile clips",
    "frame_seeds": "as for the teaser: first (scene seed, noise seed) at which g = 1.6, 9.8 and 25 are all valid",
    "frame_pair": "pair mode: every valid projectile clip at g = 15 (highest in-range g), scene seed 0",
})


def fig_frame(manifest):
    """Frame-implied channel. (a) real clips of the model whose in-range slope is largest; (b) median g_hat vs g,
    registered measurement, frame vs text channel; (c, d) pair mode: tracked height between the two key frames vs
    the true motion and constant-speed motion; (e) the scene-duration window (exploratory)."""
    sys.path.insert(0, os.path.join(CODE_DIR, "experiments"))
    from physweep_metrics import faithfulness_slope
    from v2_frame_analysis import pair_references

    per = {m: [r for r in records(m, FRAME_RUN) if r["system"] == "projectile" and "error" not in r]
           for m in FRAME_MODELS}
    txt = {m: [r for r in records(m) if r["system"] == "projectile"] for m in FRAME_MODELS}

    def beta(rs):
        v = [r for r in rs if is_valid(r) and r["split"] == "in"]
        return faithfulness_slope([r["theta"] for r in v], [r["theta_hat"] for r in v]) if len(v) >= 3 else -np.inf

    best = max(FRAME_MODELS, key=lambda m: beta(per[m]))
    ok = {(r["scene_seed"], r["noise_seed"], r["theta"]): r for r in per[best] if is_valid(r)}
    gs = (1.6, 9.8, 25)
    seeds = next((s, z) for s in range(4) for z in range(1000, 1004) if all((s, z, g) in ok for g in gs))
    out = dict(model=best, beta_in=float(beta(per[best])), scene_seed=seeds[0], noise_seed=seeds[1], clips=[])

    short = {"cosmos2_2b": "Cosmos-2B", "wan22_i2v_a14b": "Wan2.2-A14B", "ltx2": "LTX-2", "dynamicrafter": "DynamiCrafter"}
    fig = plt.figure(figsize=(FULL_W, 4.7))
    top = fig.add_gridspec(1, 5, width_ratios=[1, 1, 1, 1.32, 0.95], wspace=0.08, left=0.01, right=0.995,
                           top=0.86, bottom=0.57)
    bot = fig.add_gridspec(1, 3, wspace=0.38, left=0.075, right=0.985, top=0.40, bottom=0.085)
    for i, g in enumerate(gs):
        r = ok[(seeds[0], seeds[1], g)]
        ax = fig.add_subplot(top[0, i])
        fr = frames_rgb(r, FRAME_RUN)
        a, b = fitted_window(r)
        idx = np.unique(np.linspace(0, b - 1, 8).round().astype(int))
        ax.imshow(trail(fr, idx))
        cx, cy = track(r, "blob_cx"), track(r, "blob_cy")
        ax.plot(cx[:a + 1], cy[:a + 1], color="#1f77b4", lw=1.1)
        ax.plot(cx[a:b], cy[a:b], color="#d62728", lw=0.9)
        ax.set_xticks([]), ax.set_yticks([])
        ax.set_title(f"requested $g$ = {g:g}\nrecovered $\\hat g$ = {r['theta_hat']:.2f}", pad=2)
        out["clips"].append(dict(clip_id=r["clip_id"], theta=g, theta_hat=r["theta_hat"], r2=r["r2"],
                                 n_given=a, fit_end=b, frames_shown=idx.tolist()))
    p0, p2 = fig.axes[0].get_position(), fig.axes[2].get_position()
    fig.text(p0.x0 + 0.005, 0.99, f"(a) {label_name(best)}, frame channel: {out['clips'][0]['n_given']} given frames "
             f"(track in blue), generated continuation (red)\nscene seed {seeds[0]}, noise seed {seeds[1]}",
             ha="left", va="top", linespacing=1.3)

    ax = fig.add_subplot(top[0, 3])
    pos = ax.get_position()
    ax.set_position([pos.x0 + 0.05, pos.y0, pos.width - 0.05, pos.height])
    grid = sorted({r["theta"] for m in per for r in per[m]})
    ax.axvspan(5, 15, color="0.92", lw=0)
    ax.plot([0, 26], [0, 26], color="0.4", ls="--", lw=0.8, label="faithful")
    cmap = plt.get_cmap("tab10")
    out["medians_frame"], out["medians_text"] = {}, {}

    def med(rs):
        m = []
        for g in grid:
            v = [r["theta_hat"] for r in rs if is_valid(r) and r["theta"] == g]
            m.append(np.median(v) if len(v) >= 2 else np.nan)
        return m

    for j, m in enumerate(FRAME_MODELS):
        mf, mt = med(per[m]), med(txt[m])
        out["medians_frame"][m] = dict(zip(map(str, grid), [None if not np.isfinite(x) else float(x) for x in mf]))
        out["medians_text"][m] = dict(zip(map(str, grid), [None if not np.isfinite(x) else float(x) for x in mt]))
        c = cmap(list(MODEL_NAMES).index(m) % 10)
        ax.plot(grid, mf, marker="o", ms=2.5, lw=0.9, color=c, label=f"{short[m]} ({FRAME_MODE[m]})")
        ax.plot(grid, mt, ls=":", lw=0.8, color=c)
    ax.plot([], [], ls=":", color="0.3", lw=0.8, label="text channel")
    ax.set_xlim(0, 26), ax.set_ylim(-6, 26)
    ax.set_xlabel("requested $g$ (m s$^{-2}$)"), ax.set_ylabel("median recovered $\\hat g$")
    ax.set_title("(b) frame vs text channel", pad=2)
    lax = fig.add_subplot(top[0, 4])
    lax.axis("off")
    lax.legend(*ax.get_legend_handles_labels(), loc="center left", frameon=False, handlelength=1.4,
               borderaxespad=0, fontsize=6.2)

    out["pair"] = {}
    for j, m in enumerate(("dynamicrafter", "wan22_i2v_a14b")):
        ax = fig.add_subplot(bot[0, j])
        rs = [r for r in per[m] if is_valid(r) and r["theta"] == 15 and r["scene_seed"] == 0]
        out["pair"][m] = []
        for r in sorted(rs, key=lambda r: r["noise_seed"]):
            cx, cy = track(r, "blob_cx"), track(r, "blob_cy")
            t = np.arange(len(cy)) * r["dt"]
            (px, py), (lx, ly) = pair_references(r)
            g0 = r["ground_row0"]
            ax.plot(t, fit_coordinate("projectile", cx, cy, g0), color=cmap(list(MODEL_NAMES).index(m) % 10), lw=0.8,
                    alpha=0.8)
            out["pair"][m].append(dict(clip_id=r["clip_id"], theta_hat=r["theta_hat"], noise_seed=r["noise_seed"]))
        if rs:
            ax.plot(t, fit_coordinate("projectile", px, py, g0), color="k", lw=1.2, label="true motion")
            ax.plot(t, fit_coordinate("projectile", lx, ly, g0), color="k", lw=1.0, ls="--", label="constant speed")
        ax.set_xlabel("time (s)"), ax.set_ylabel("height (px)")
        ax.set_title(f"({'cd'[j]}) {short[m]}, pair mode\n$g$ = 15, scene 0, {len(rs)} clips", pad=2)
        if j == 0:
            ax.legend(frameon=False, fontsize=6, loc="lower right")

    ax = fig.add_subplot(bot[0, 2])
    path = os.path.join(REV, "results_v2", "window_sensitivity_clips.jsonl")
    wc = [json.loads(l) for l in open(path)] if os.path.exists(path) else []
    wc = [c for c in wc if c.get("run") == FRAME_RUN and c["system"] == "projectile"]
    ax.axvspan(5, 15, color="0.92", lw=0)
    ax.plot([0, 26], [0, 26], color="0.4", ls="--", lw=0.8)
    out["medians_window"] = {}
    for m in FRAME_MODELS:
        mw = med([c for c in wc if c["model"] == m])
        out["medians_window"][m] = dict(zip(map(str, grid), [None if not np.isfinite(x) else float(x) for x in mw]))
        ax.plot(grid, mw, marker="o", ms=2.5, lw=0.9, color=cmap(list(MODEL_NAMES).index(m) % 10))
    ax.set_xlim(0, 26), ax.set_ylim(-6, 26)
    ax.set_xlabel("requested $g$ (m s$^{-2}$)"), ax.set_ylabel("median recovered $\\hat g$")
    ax.set_title("(e) first second only\n(exploratory, same rules)", pad=2)
    save(fig, "frame")
    manifest["frame"] = out


def save(fig, name):
    os.makedirs(FIGDIR, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(FIGDIR, f"fig_{name}.{ext}"))
    plt.close(fig)
    print(f"wrote figures/fig_{name}.pdf")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("figures", nargs="*", default=["teaser", "scenes", "failures", "trackers", "frame"])
    a = ap.parse_args()
    path = os.path.join(FIGDIR, "figures_manifest.json")
    manifest = json.load(open(path)) if os.path.exists(path) else {}
    manifest["selection_rules"] = SELECTION
    for name in a.figures:
        globals()[f"fig_{name}"](manifest)
    with open(path, "w") as f:
        json.dump(manifest, f, indent=1, default=float)


if __name__ == "__main__":
    main()
