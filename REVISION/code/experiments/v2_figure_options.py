#!/usr/bin/env python3
"""
Figure OPTIONS (prototypes) for the IVC paper: six options per figure type, each modeled on a figure in
figure_refs.pdf and built from our own data (generated clips, tracks, simulator scenes, result files).
Prototypes, not final figures: layout and data are real, styling is rough, and clip choices use simple rules
(first valid clip in seed order unless stated).

Usage (envs/fig):  python experiments/v2_figure_options.py [option ids ...]     (default: all)
Writes: <REVISION>/figures/options/<id>.png and figures/options/figure_options.pdf (one page per option)
"""

from __future__ import annotations

import collections
import functools
import json
import os
import sys
import textwrap

CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CODE_DIR)
sys.path.insert(0, os.path.join(CODE_DIR, "experiments"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch, Rectangle

import v2_figures as VF
from physweep import render as R
from physweep.conditioning import build_conditioning, render_ground_truth
from physweep.validity import centroid_track_above, object_mask, shape_stats

REV = os.path.dirname(CODE_DIR)
OUT = os.path.join(REV, "figures", "options")
RES = os.path.join(REV, "results_v2")
ORDER = ["ltx", "cogvideox", "dynamicrafter", "cogvideox15_i2v", "wan22_ti2v_5b", "wan22_i2v_a14b",
         "hunyuan15_i2v", "ltx2", "cosmos2_2b"]
SHORT = {"ltx": "LTX-Video", "cogvideox": "CogVideoX-5B", "dynamicrafter": "DynamiCrafter",
         "cogvideox15_i2v": "CogVideoX1.5", "wan22_ti2v_5b": "Wan2.2-5B", "wan22_i2v_a14b": "Wan2.2-A14B",
         "hunyuan15_i2v": "Hunyuan-1.5", "ltx2": "LTX-2", "cosmos2_2b": "Cosmos-2B"}
SHORT2 = {"ltx": "LTX-\nVideo", "cogvideox": "CogVideoX\n-5B", "dynamicrafter": "Dynami-\nCrafter",
          "cogvideox15_i2v": "CogVideoX\n1.5", "wan22_ti2v_5b": "Wan2.2\n-5B", "wan22_i2v_a14b": "Wan2.2\n-A14B",
          "hunyuan15_i2v": "Hunyuan\n-1.5", "ltx2": "LTX-2", "cosmos2_2b": "Cosmos\n-2B"}
SYS = ["projectile", "bouncing_ball", "inclined_slide"]
SYSN = {"projectile": "projectile", "bouncing_ball": "bouncing ball", "inclined_slide": "inclined slide"}
SYM = {"projectile": "g", "bouncing_ball": "e", "inclined_slide": "\\mu"}
GRID = {"projectile": [1.6, 5, 7, 9.8, 12, 15, 25], "bouncing_ball": [0.2, 0.6, 0.7, 0.8, 0.9, 0.97],
        "inclined_slide": [0.01, 0.1, 0.2, 0.3, 0.4, 1.0]}
INR = {"projectile": (5, 15), "bouncing_ball": (0.6, 0.9), "inclined_slide": (0.1, 0.4)}
CMAP = plt.get_cmap("tab10")
COL = {m: CMAP(i % 10) for i, m in enumerate(sorted(ORDER))}
RED, BLUE = "#d62728", "#1f77b4"
plt.rcParams.update({"font.size": 8, "axes.titlesize": 8, "axes.labelsize": 8, "legend.fontsize": 7,
                     "xtick.labelsize": 7, "ytick.labelsize": 7, "savefig.dpi": 160})


# --------------------------------------------------------------------------------------------- data helpers
@functools.lru_cache(None)
def recs(model, run="main_text"):
    return tuple(r for r in VF.records(model, run) if "error" not in r)


def pick(model, system, theta, run="main_text", valid=True, scene=None, noise=None, key=None):
    rs = [r for r in recs(model, run) if r["system"] == system and r["theta"] == theta
          and (not valid or VF.is_valid(r)) and (scene is None or r["scene_seed"] == scene)
          and (noise is None or r["noise_seed"] == noise)]
    rs.sort(key=key or (lambda r: (r["scene_seed"], r["noise_seed"])))
    return rs[0] if rs else None


@functools.lru_cache(maxsize=64)
def _frames(clip_id, model, run):
    r = next(x for x in recs(model, run) if x["clip_id"] == clip_id)
    return VF.frames_rgb(r, run)


def frames(r, run="main_text"):
    return _frames(r["clip_id"], r["model"], run)


@functools.lru_cache(None)
def sim(system, theta, seed=0, style="structured"):
    g = render_ground_truth(system, theta, seed, style)
    cx, cy = centroid_track_above(g, shape_stats(g)["ground_row0"])
    return np.repeat(g[..., None], 3, axis=3), cx, cy, shape_stats(g)["ground_row0"]


def window(r):
    a, b = VF.fitted_window(r)
    return a, max(a + 2, min(b, r["n_frames_out"]))


def strobe(fr, a, b, n=8):
    idx = np.unique(np.linspace(a, b - 1, n).round().astype(int))
    return fr[idx].min(axis=0)


def crop_box(rs, margin=36):
    """Square crop (analysis px) around where the ball moves in the given clips."""
    xs, ys = [], []
    for r in rs:
        if r is None:
            continue
        cx, cy = VF.track(r, "blob_cx"), VF.track(r, "blob_cy")
        xs += list(cx[np.isfinite(cx)]); ys += list(cy[np.isfinite(cy)])
    if not xs:
        return 0, 256, 0, 256
    x0, x1, y0, y1 = min(xs) - margin, max(xs) + margin, min(ys) - margin, max(ys) + margin
    side = min(max(x1 - x0, y1 - y0, 80), 256)
    cxm, cym = (x0 + x1) / 2, (y0 + y1) / 2
    x0, y0 = int(np.clip(cxm - side / 2, 0, 256 - side)), int(np.clip(cym - side / 2, 0, 256 - side))
    return x0, x0 + int(side), y0, y0 + int(side)


def off(ax):
    ax.set_xticks([]), ax.set_yticks([])


def blank(ax, text="no valid clip"):
    ax.set_facecolor("0.95"), off(ax)
    ax.text(0.5, 0.5, text, ha="center", va="center", fontsize=6, color="0.4", transform=ax.transAxes)


def show_clip(ax, r, run="main_text", n=8, title=None, track=True, full=False):
    if r is None:
        return blank(ax)
    fr = frames(r, run)
    a, b = (0, len(fr)) if full else window(r)
    ax.imshow(strobe(fr, a, b, n))
    if track:
        cx, cy = VF.track(r, "blob_cx"), VF.track(r, "blob_cy")
        ax.plot(cx[a:b], cy[a:b], color=RED, lw=0.8)
    off(ax)
    if title:
        ax.set_title(title, pad=2, fontsize=7)


def show_sim(ax, system, theta, seed=0, style="structured", n=8, title=None):
    fr, cx, cy, _ = sim(system, theta, seed, style)
    ax.imshow(strobe(fr, 0, len(fr), n))
    ax.plot(cx, cy, color=BLUE, lw=0.8)
    off(ax)
    if title:
        ax.set_title(title, pad=2, fontsize=7)


def height(r):
    cx, cy = VF.track(r, "blob_cx"), VF.track(r, "blob_cy")
    a, b = window(r)
    dt = r.get("dt") or 1.0 / r["fps"]
    h = VF.fit_coordinate(r["system"], cx, cy, r["ground_row0"])
    return np.arange(b - a) * dt, h[a:b]


def sim_height(system, theta, seed=0):
    fr, cx, cy, g = sim(system, theta, seed)
    return np.arange(len(cx)) * R.DT, VF.fit_coordinate(system, cx, cy, g)


@functools.lru_cache(None)
def ratings(model, rater="qwen3vl_30b_a3b"):
    p = os.path.join(VF.OUT_ROOT, "main_text", model, f"plausibility_{rater}.jsonl")
    out = {}
    for line in open(p):
        x = json.loads(line)
        if x.get("expected") is not None:
            out[x["clip_id"]] = x["expected"]
    return out


def J(name):
    return json.load(open(os.path.join(RES, name)))


def ghat(r):
    return f"$\\hat {SYM[r['system']]}$ = {r['theta_hat']:.2f}" if r and r.get("theta_hat") is not None else ""


def box(ax, xy, w, h=None, text=None, fc="#eef2f8", ec="#5b6b8c", fs=7, bold=False):
    if len(xy) == 4:                    # box(ax, (x, y, w, h), text)
        text, (x0, y0, w, h) = w, xy
        xy = (x0, y0)
    ax.add_patch(FancyBboxPatch(xy, w, h, boxstyle="round,pad=0.01,rounding_size=0.02", fc=fc, ec=ec, lw=0.8))
    ax.text(xy[0] + w / 2, xy[1] + h / 2, text, ha="center", va="center", fontsize=fs,
            fontweight="bold" if bold else "normal")


def arrow(ax, p, q, color="0.3"):
    ax.annotate("", xy=q, xytext=p, arrowprops=dict(arrowstyle="-|>", color=color, lw=0.9))


def inset_img(fig, rect, img, track=None, color=RED, title=None):
    ax = fig.add_axes(rect)
    ax.imshow(img)
    if track is not None:
        ax.plot(*track, color=color, lw=0.8)
    off(ax)
    if title:
        ax.set_title(title, fontsize=6.5, pad=1.5)
    return ax


# --------------------------------------------------------------------------------------------- TEASER
def T1(fig):
    """Same request (Moon gravity), simulator + nine generators, one stroboscopic composite each."""
    axs = fig.subplots(2, 5).flat
    axs = list(axs)
    show_sim(axs[0], "projectile", 1.6, title="simulator\n$g$ = 1.6")
    for ax, m in zip(axs[1:], ORDER):
        r = pick(m, "projectile", 1.6)
        show_clip(ax, r, title=f"{SHORT[m]}\n{ghat(r)}")
    fig.suptitle("Requested: Moon gravity ($g$ = 1.6 m s$^{-2}$). Blue: what it should look like; red: what each "
                 "generator did", fontsize=8, y=0.98)


def T2(fig):
    """Truth vs generated for three requests, with the VLM plausibility score under each generated clip."""
    axs = fig.subplots(2, 3)
    m = "wan22_i2v_a14b"
    for j, g in enumerate((1.6, 9.8, 25)):
        show_sim(axs[0, j], "projectile", g, seed=0, title=f"simulator, $g$ = {g:g}")
        r = pick(m, "projectile", g, scene=0, noise=1000) or pick(m, "projectile", g)
        s = ratings(m).get(r["clip_id"]) if r else None
        show_clip(axs[1, j], r, title=f"{SHORT[m]}: {ghat(r)}")
        if s is not None:
            axs[1, j].text(0.5, -0.08, f"VLM plausibility {s:.1f} / 5", transform=axs[1, j].transAxes, ha="center",
                           va="top", fontsize=7, color="darkgreen")
    axs[0, 0].set_ylabel("requested", fontsize=8), axs[1, 0].set_ylabel("generated", fontsize=8)
    fig.subplots_adjust(hspace=0.35, wspace=0.05)


def T4(fig):
    """Text channel vs frame channel for the same model (LTX-2): told the gravity vs shown it."""
    axs = fig.subplots(2, 3)
    gs = (1.6, 9.8, 25)
    for i, run in enumerate(("main_text", "main_frame")):
        ok = {(r["scene_seed"], r["noise_seed"], r["theta"]): r for r in recs("ltx2", run)
              if r["system"] == "projectile" and VF.is_valid(r)}
        seeds = next(((s, z) for s in range(4) for z in range(1000, 1004) if all((s, z, g) in ok for g in gs)), None)
        for j, g in enumerate(gs):
            r = ok.get((*seeds, g)) if seeds else None
            show_clip(axs[i, j], r, run=run, title=f"$g$ = {g:g}: {ghat(r)}")
            if run == "main_frame" and r is not None:
                fr = frames(r, run)
                cx, cy = VF.track(r, "blob_cx"), VF.track(r, "blob_cy")
                axs[i, j].plot(cx[:r["n_given"] + 1], cy[:r["n_given"] + 1], color=BLUE, lw=1.2)
    axs[0, 0].set_ylabel("told (text prompt)", fontsize=8)
    axs[1, 0].set_ylabel("shown (9 frames, blue)", fontsize=8)
    fig.suptitle("LTX-2: the same model ignores gravity it is told and follows gravity it is shown", fontsize=8)


def T5(fig):
    """Height-vs-time: true curves fan out with g, generated curves collapse (one model)."""
    ax = fig.subplots(1, 2, sharey=True)
    m = "wan22_i2v_a14b"
    cm = plt.get_cmap("viridis")
    for k, g in enumerate(GRID["projectile"]):
        c = cm(k / 6)
        t, h = sim_height("projectile", g)
        ax[0].plot(t, h, color=c, lw=1.2, label=f"$g$ = {g:g}")
        for r in [x for x in recs(m) if x["system"] == "projectile" and x["theta"] == g and VF.is_valid(x)][:4]:
            t2, h2 = height(r)
            ax[1].plot(t2, h2, color=c, lw=0.8, alpha=0.8)
    ax[0].set_title("simulator: what was requested"), ax[1].set_title(f"{SHORT[m]}: what was generated (valid clips)")
    for a in ax:
        a.set_xlabel("time (s)")
    ax[0].set_ylabel("height above floor (px)")
    ax[0].legend(fontsize=6, ncol=2, frameon=False)


def T6(fig):
    """Plausibility does not predict faithfulness: VLM score vs relative error, all valid projectile clips."""
    ax, ax2 = fig.subplots(1, 2, gridspec_kw=dict(width_ratios=[2.2, 1]))
    xs, ys = [], []
    for m in ORDER:
        rt = ratings(m)
        pts = [(rt[r["clip_id"]], abs(r["theta_hat"] - r["theta"]) / r["theta"]) for r in recs(m)
               if r["system"] == "projectile" and VF.is_valid(r) and r["clip_id"] in rt]
        if pts:
            x, y = np.array(pts).T
            ax.scatter(x + np.random.default_rng(0).uniform(-0.05, 0.05, len(x)), y, s=5, color=COL[m], alpha=0.6,
                       label=SHORT[m])
            xs += list(x); ys += list(y)
    from scipy.stats import spearmanr
    rho = spearmanr(xs, ys).correlation
    ax.set_yscale("log"), ax.set_xlabel("VLM plausibility (Qwen3-VL-30B, expected 1-5)")
    ax.set_ylabel("|relative error| of $\\hat g$"), ax.set_title(f"valid projectile clips, Spearman $\\rho$ = {rho:.2f}")
    ax.legend(fontsize=5.5, ncol=2, frameon=False)
    # most plausible clip with a large error
    best = max(((ratings(m).get(r["clip_id"], 0), r) for m in ORDER for r in recs(m)
                if r["system"] == "projectile" and VF.is_valid(r) and abs(r["theta_hat"] - r["theta"]) / r["theta"] > 0.9),
               key=lambda t: (t[0], t[1]["clip_id"]))
    show_clip(ax2, best[1], title=f"plausibility {best[0]:.1f}/5\nrequested $g$ = {best[1]['theta']:g}, {ghat(best[1])}")


def T3(fig):
    ax = fig.subplots()
    ax.imshow(plt.imread(os.path.join(REV, "figures", "fig_teaser.png"))), ax.axis("off")


# --------------------------------------------------------------------------------------------- PIPELINE
def P1(fig):
    """Stage bands left to right, every panel a real image or plot."""
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 1), ax.set_ylim(0, 1), ax.axis("off")
    stages = ["request", "renderer", "generator", "tracker", "validity", "fit", "metrics"]
    cols = ["#f4e6d4", "#e3eef9", "#efe3f6", "#e2f3e6", "#fbe4e4", "#fff6d5", "#e8e8e8"]
    w = 1 / 7
    for i, (s, c) in enumerate(zip(stages, cols)):
        ax.add_patch(Rectangle((i * w, 0.0), w, 1, color=c, lw=0))
        ax.text(i * w + w / 2, 0.04, s, ha="center", fontsize=8, fontweight="bold")
    box(ax, (0.012, 0.45), w - 0.024, 0.18, "$g$ = 1.6 m s$^{-2}$\n'Moon gravity'", fc="white")
    fr, cx, cy, _ = sim("projectile", 1.6)
    inset_img(fig, [w + 0.01, 0.3, w - 0.02, 0.45], fr[0])
    r = pick("wan22_i2v_a14b", "projectile", 1.6, scene=0, noise=1000)
    f = frames(r); a, b = window(r)
    inset_img(fig, [2 * w + 0.01, 0.3, w - 0.02, 0.45], strobe(f, a, b))
    inset_img(fig, [3 * w + 0.01, 0.3, w - 0.02, 0.45], strobe(f, a, b), track=(VF.track(r, "blob_cx")[a:b], VF.track(r, "blob_cy")[a:b]))
    for k, (t, ok) in enumerate([("one object", 1), ("stable size", 1), ("fixed camera", 1), ("moving", 1), ("R$^2$ ≥ 0.8", 1)]):
        ax.text(4 * w + 0.015, 0.72 - k * 0.08, ("✓ " if ok else "✗ ") + t, fontsize=7, color="darkgreen")
    axp = fig.add_axes([5 * w + 0.02, 0.32, w - 0.035, 0.4])
    t, h = height(r)
    axp.plot(t, h, "o", ms=2, color=RED); co = np.polyfit(t, h, 2); axp.plot(t, np.polyval(co, t), color="k", lw=0.8)
    axp.set_xticks([]), axp.set_yticks([]), axp.set_title("parabola fit", fontsize=6.5)
    box(ax, (6 * w + 0.01, 0.42, w - 0.02, 0.24), f"{ghat(r)}\nvs $g$ = 1.6\n$\\beta$, $\\rho$, PRE,\nshares", fc="white")
    for i in range(6):
        arrow(ax, ((i + 1) * w - 0.008, 0.85), ((i + 1) * w + 0.008, 0.85))


def P2(fig):
    """Two branches through the same instrument: simulator (positive control) vs generator."""
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 1), ax.set_ylim(0, 1), ax.axis("off")
    r = pick("wan22_i2v_a14b", "projectile", 25, scene=0, noise=1000)
    fr, cx, cy, _ = sim("projectile", 25)
    rows = [("simulator video", strobe(fr, 0, len(fr)), (cx, cy), sim_height("projectile", 25), "$\\hat g$ = 25.0 ✓"),
            ("generated video", None, None, height(r), f"{ghat(r)} ✗")]
    for k, (name, img, tr, (t, h), res) in enumerate(rows):
        y = 0.55 - k * 0.48
        ax.text(0.02, y + 0.385, name, fontsize=8, fontweight="bold")
        if img is None:
            f = frames(r); a, b = window(r); img = strobe(f, a, b); tr = (VF.track(r, "blob_cx")[a:b], VF.track(r, "blob_cy")[a:b])
        inset_img(fig, [0.02, y - 0.02, 0.2, 0.38], img, track=tr, color=BLUE if k == 0 else RED)
        box(ax, (0.3, y + 0.08, 0.16, 0.14), "same tracker\n+ validity checks", fc="white")
        axp = fig.add_axes([0.53, y, 0.2, 0.34]); axp.plot(t, h, color=BLUE if k == 0 else RED)
        axp.set_xticks([]), axp.set_yticks([]), axp.set_title("height vs time", fontsize=6.5)
        box(ax, (0.8, y + 0.08, 0.18, 0.14), f"requested $g$ = 25\n{res}", fc="white")
        for p, q in [((0.23, y + 0.15), (0.3, y + 0.15)), ((0.46, y + 0.15), (0.53, y + 0.15)), ((0.73, y + 0.15), (0.8, y + 0.15))]:
            arrow(ax, p, q)


def P3(fig):
    """The crossed design: one request, 4 scene seeds x 4 noise seeds, plus the variance decomposition."""
    m, g = "wan22_i2v_a14b", 9.8
    gs = fig.add_gridspec(4, 6, width_ratios=[1, 1, 1, 1, 0.25, 1.6])
    for s in range(4):
        for z in range(4):
            ax = fig.add_subplot(gs[s, z])
            r = pick(m, "projectile", g, valid=False, scene=s, noise=1000 + z)
            if r is not None and VF.is_valid(r):
                show_clip(ax, r, n=6)
                ax.text(0.03, 0.03, f"{r['theta_hat']:.1f}", transform=ax.transAxes, fontsize=6, color="white",
                        bbox=dict(fc=RED, ec="none", pad=1))
            else:
                blank(ax, r["label"] if r else "--")
            if s == 0:
                ax.set_title(f"noise {1000 + z}", fontsize=6.5)
            if z == 0:
                ax.set_ylabel(f"scene {s}", fontsize=6.5)
    ax = fig.add_subplot(gs[:, 5])
    d = J("main_text_analysis.json")["results"]
    keys = [f"{m}/{s}" for s in SYS]
    shares = [d[k].get("decomposition", {}).get("corrected", {}) for k in keys]
    bottom = np.zeros(3)
    for f, c in (("request", "#8c564b"), ("scene", "#1f77b4"), ("noise", "#ff7f0e")):
        v = np.array([s.get(f, 0) for s in shares]); ax.bar(range(3), v, bottom=bottom, color=c, label=f); bottom += v
    ax.set_xticks(range(3)), ax.set_xticklabels([SYSN[s] for s in SYS], rotation=30, fontsize=6)
    ax.set_title(f"{SHORT[m]}: variance shares of $\\hat\\theta$"), ax.legend(fontsize=6, frameon=False)
    fig.suptitle(f"{SHORT[m]}, requested $g$ = {g}: rows = scene seed, columns = noise seed (number = $\\hat g$)", fontsize=8)


def P4(fig):
    """The two channels with real inputs and outputs: text, frame pair, frame prefix."""
    rows = [("text channel: first frame + prompt", "ltx2", "main_text", "text"),
            ("frame channel, pair: first + middle key frame", "wan22_i2v_a14b", "main_frame", "pair"),
            ("frame channel, prefix: 9 given frames", "ltx2", "main_frame", "prefix")]
    gs = fig.add_gridspec(3, 7, width_ratios=[1.3, 1, 1, 0.2, 1, 1, 1])
    for i, (name, m, run, mode) in enumerate(rows):
        r = pick(m, "projectile", 9.8, run=run)
        cond = build_conditioning(dict(system="projectile", theta=9.8, scene_seed=r["scene_seed"], style="structured",
                                       channel="text" if mode == "text" else "frame"), mode if mode != "text" else "pair",
                                  k=9, model_fps=24)
        axt = fig.add_subplot(gs[i, 0]); axt.axis("off")
        axt.text(0, 0.5, textwrap.fill(name, 22) + "\n\n" + textwrap.fill('"' + cond["prompt"][:80] + '..."', 24),
                 fontsize=5.5, va="center")
        ins = cond["frames"][:2] if mode != "prefix" else [cond["frames"][0], cond["frames"][-1]]
        for j, f in enumerate(ins):
            ax = fig.add_subplot(gs[i, 1 + j]); ax.imshow(f, cmap="gray", vmin=0, vmax=255); off(ax)
            ax.set_title(["input", "input (2nd)" if mode == "pair" else ("input (9th)" if mode == "prefix" else "")][min(j, 1)] if j or mode else "input", fontsize=6)
        fr = frames(r, run)
        idx = np.linspace(r.get("n_given") or 0, len(fr) - 1, 3).round().astype(int)
        for j, t in enumerate(idx):
            ax = fig.add_subplot(gs[i, 4 + j]); ax.imshow(fr[t]); off(ax); ax.set_title(f"output frame {t}", fontsize=6)
    fig.suptitle("Requested $g$ = 9.8 in each channel (LTX-2, Wan2.2-A14B)", fontsize=8)


def P5(fig):
    """Validity decision tree with counts from the main sweep and a real example at each rejection."""
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 1), ax.set_ylim(0, 1), ax.axis("off")
    lab = J("main_text_analysis.json")["results"]
    tot = collections.Counter()
    for e in lab.values():
        tot.update(e["labels"])
    sel = VF.pick_failures()
    steps = [("fit gate\nR$^2$ ≥ 0.8, no lost frame", "invalid_fit", "fit"), ("camera fixed", "invalid_camera", "camera"),
             ("one object,\nstable size", "invalid_shape", "multiple_objects"), ("moving\n(bouncing ball)", "invalid_static", "static")]
    box(ax, (0.01, 0.8, 0.11, 0.12), f"{sum(tot.values()):,} clips", fc="white", bold=True)
    for i, (name, key, ex) in enumerate(steps):
        x = 0.16 + i * 0.18
        box(ax, (x, 0.8, 0.15, 0.12), name, fc="#e2f3e6")
        arrow(ax, (x - 0.04, 0.86), (x, 0.86))
        arrow(ax, (x + 0.075, 0.8), (x + 0.075, 0.68), color=RED)
        ax.text(x + 0.085, 0.72, f"{tot[key]:,} rejected", fontsize=7, color=RED)
        r = sel.get(ex)
        if r is not None:
            fr = frames(r); idx = np.linspace(0, len(fr) - 1, 4).round().astype(int)
            inset_img(fig, [x, 0.25, 0.15, 0.4], fr[idx[-1]], track=(VF.track(r, "blob_cx"), VF.track(r, "blob_cy")),
                      title=f"{SHORT[r['model']]}, {SYSN[r['system']]}")
    box(ax, (0.88, 0.8, 0.11, 0.12), f"valid\n{tot['valid']:,}", fc="#c9eac9", bold=True)
    arrow(ax, (0.85, 0.86), (0.88, 0.86))


def P6(fig):
    """One row per system: rendered clip with track -> fitted coordinate vs time -> closed-form estimate."""
    gs = fig.add_gridspec(3, 3, width_ratios=[1, 1.6, 1.2])
    est = {"projectile": "$\\hat g$ = 2 x curvature\nof height(t)",
           "bouncing_ball": "$\\hat e$ = $\\sqrt{h_{k+1}/h_k}$\nfrom bounce peaks",
           "inclined_slide": "$\\hat\\mu$ = tan $\\alpha$ $-$ $a$ / ($g$ cos $\\alpha$)\nfrom slope acceleration"}
    for i, (s, th) in enumerate((("projectile", 9.8), ("bouncing_ball", 0.8), ("inclined_slide", 0.2))):
        fr, cx, cy, g = sim(s, th)
        ax = fig.add_subplot(gs[i, 0]); ax.imshow(strobe(fr, 0, len(fr))); ax.plot(cx, cy, color=BLUE, lw=0.8); off(ax)
        ax.set_title(f"{SYSN[s]}, ${SYM[s]}$ = {th:g}", fontsize=7)
        ax = fig.add_subplot(gs[i, 1]); t, h = sim_height(s, th); ax.plot(t, h, "o", ms=2, color=BLUE)
        if s != "bouncing_ball":
            ax.plot(t, np.polyval(np.polyfit(t, h, 2), t), color="k", lw=0.8)
        ax.set_xlabel("time (s)", fontsize=6), ax.set_ylabel(VF.COORD_LABEL[s], fontsize=6)
        ax = fig.add_subplot(gs[i, 2]); ax.axis("off"); ax.text(0.05, 0.5, est[s], fontsize=8, va="center")
    fig.subplots_adjust(hspace=0.6)


# --------------------------------------------------------------------------------------------- QUALITATIVE
def Q1(fig):
    """Generators x time: filmstrips of the same request (g = 9.8), simulator on top."""
    n = 6
    axs = fig.subplots(10, n)
    fr, cx, cy, _ = sim("projectile", 9.8)
    for j, t in enumerate(np.linspace(0, len(fr) - 1, n).round().astype(int)):
        axs[0, j].imshow(fr[t]); off(axs[0, j])
    axs[0, 0].set_ylabel("simulator", fontsize=6, rotation=0, ha="right", va="center")
    for i, m in enumerate(ORDER, 1):
        r = pick(m, "projectile", 9.8)
        x0, x1, y0, y1 = crop_box([r])
        for j in range(n):
            if r is None:
                blank(axs[i, j], ""); continue
            f = frames(r); a, b = 0, len(f)
            t = int(round(np.linspace(a, b - 1, n)[j])); axs[i, j].imshow(f[t][y0:y1, x0:x1]); off(axs[i, j])
        axs[i, 0].set_ylabel(SHORT[m], fontsize=6, rotation=0, ha="right", va="center")
    fig.subplots_adjust(left=0.14, wspace=0.03, hspace=0.06)


def Q2(fig):
    """Requests x generators matrix of stroboscopic composites (g = 1.6, 9.8, 25)."""
    gs_ = (1.6, 9.8, 25)
    axs = fig.subplots(3, 10)
    for i, g in enumerate(gs_):
        show_sim(axs[i, 0], "projectile", g, n=6)
        for j, m in enumerate(ORDER, 1):
            r = pick(m, "projectile", g)
            show_clip(axs[i, j], r, n=6)
            if r:
                axs[i, j].text(0.03, 0.03, f"{r['theta_hat']:.1f}", transform=axs[i, j].transAxes, fontsize=5.5,
                               color="white", bbox=dict(fc=RED, ec="none", pad=0.8))
            if i == 0:
                axs[i, j].set_title(SHORT2[m], fontsize=6)
        axs[i, 0].set_ylabel(f"$g$ = {g:g}", fontsize=7)
    axs[0, 0].set_title("simulator", fontsize=6)
    fig.subplots_adjust(wspace=0.04, hspace=0.06)


def Q3(fig):
    """Same scene, same request, four noise seeds: the noise picks the physics."""
    models = ["ltx2", "wan22_i2v_a14b", "hunyuan15_i2v"]
    axs = fig.subplots(len(models), 4)
    for i, m in enumerate(models):
        for z in range(4):
            r = pick(m, "projectile", 9.8, valid=False, scene=0, noise=1000 + z)
            if r is not None and VF.is_valid(r):
                show_clip(axs[i, z], r, title=f"noise {1000 + z}: {ghat(r)}")
            else:
                blank(axs[i, z], r["label"] if r else "--")
        axs[i, 0].set_ylabel(SHORT[m], fontsize=7)
    fig.suptitle("Scene seed 0, requested $g$ = 9.8; only the generator's noise seed changes", fontsize=8)


def Q4(fig):
    """Text vs frame channel filmstrips, LTX-2, g = 25."""
    axs = fig.subplots(2, 7)
    for i, run in enumerate(("main_text", "main_frame")):
        r = pick("ltx2", "projectile", 25, run=run)
        f = frames(r, run)
        x0, x1, y0, y1 = crop_box([r])
        for j, t in enumerate(np.linspace(0, len(f) - 1, 7).round().astype(int)):
            axs[i, j].imshow(f[t][y0:y1, x0:x1]); off(axs[i, j]); axs[i, j].set_title(f"frame {t}", fontsize=6)
            if run == "main_frame" and t < r["n_given"]:
                for sp in axs[i, j].spines.values():
                    sp.set_edgecolor(BLUE); sp.set_linewidth(2)
        axs[i, 0].set_ylabel(("text: " if i == 0 else "frames: ") + ghat(r), fontsize=7)
    fig.suptitle("LTX-2, requested $g$ = 25; blue border: frames given as input", fontsize=8)


def Q5(fig):
    """Structured vs shaded twins (same scene, noise and request)."""
    models = ["ltx2", "wan22_i2v_a14b", "dynamicrafter", "cosmos2_2b"]
    axs = fig.subplots(2, len(models))
    for j, m in enumerate(models):
        base = pick(m, "projectile", 9.8, run="shaded_text", valid=False)
        twin = pick(m, "projectile", 9.8, valid=False, scene=base["scene_seed"], noise=base["noise_seed"]) if base else None
        for i, (r, run) in enumerate(((twin, "main_text"), (base, "shaded_text"))):
            show_clip(axs[i, j], r, run=run, title=(f"{SHORT[m]}\n{r['label']}" + (f", {ghat(r)}" if VF.is_valid(r) else "")) if r else "")
    axs[0, 0].set_ylabel("structured", fontsize=7), axs[1, 0].set_ylabel("shaded", fontsize=7)


def Q6(fig):
    """Pair mode: key frames fixed; what happens in between (DynamiCrafter vs Wan2.2 inserted bounce)."""
    from v2_frame_analysis import pair_references
    rows = [("dynamicrafter", pick("dynamicrafter", "projectile", 15, run="main_frame")),
            ("wan22_i2v_a14b", pick("wan22_i2v_a14b", "projectile", 5, run="main_frame"))]
    gs = fig.add_gridspec(2, 6, width_ratios=[1, 1, 1, 1, 0.2, 1.8])
    for i, (m, r) in enumerate(rows):
        f = frames(r, "main_frame")
        for j, t in enumerate(np.linspace(0, len(f) - 1, 4).round().astype(int)):
            ax = fig.add_subplot(gs[i, j]); ax.imshow(f[t]); off(ax)
            if t in (0, len(f) - 1):
                for sp in ax.spines.values():
                    sp.set_edgecolor(BLUE); sp.set_linewidth(2)
            ax.set_title(f"frame {t}", fontsize=6)
        ax = fig.add_subplot(gs[i, 5])
        t, h = np.arange(len(f)) * r["dt"], VF.fit_coordinate("projectile", VF.track(r, "blob_cx"), VF.track(r, "blob_cy"), r["ground_row0"])
        (px, py), (lx, ly) = pair_references(r)
        ax.plot(t, h, color=RED, label="generated"), ax.plot(t, VF.fit_coordinate("projectile", px, py, r["ground_row0"]), "k", label="true")
        ax.plot(t, VF.fit_coordinate("projectile", lx, ly, r["ground_row0"]), "k--", label="constant speed")
        ax.set_title(f"{SHORT[m]}, $g$ = {r['theta']:g}", fontsize=7), ax.legend(fontsize=5.5, frameon=False)
    fig.suptitle("Pair mode: blue = key frames given; the model fills in the motion between them", fontsize=8)
    fig.subplots_adjust(hspace=0.55)


# --------------------------------------------------------------------------------------------- FAILURES
def _failures():
    return VF.pick_failures()


def F1(fig):
    """Morpheus-style: failure types as column headers, frame 0 above the worst frame."""
    sel = _failures()
    kinds = ["multiple_objects", "unstable_size", "camera", "static", "fit"]
    axs = fig.subplots(2, len(kinds))
    for j, k in enumerate(kinds):
        r = sel[k]; f = frames(r)
        worst = len(f) - 1
        axs[0, j].imshow(f[0]); axs[1, j].imshow(f[worst]); off(axs[0, j]); off(axs[1, j])
        axs[0, j].set_title(VF.FAIL_TITLE[k].replace("invalid_", "").replace("(", "\n("), fontsize=7)
        axs[1, j].set_xlabel(textwrap.fill(VF.describe(k, r), 18), fontsize=6.5, color=RED)
    axs[0, 0].set_ylabel("frame 0", fontsize=7), axs[1, 0].set_ylabel("last frame", fontsize=7)


def F3(fig):
    """VideoPhy-style: initial / middle / last frame + a red callout naming the failure and its size."""
    sel = _failures()
    kinds = ["multiple_objects", "unstable_size", "camera", "static", "fit"]
    gs = fig.add_gridspec(len(kinds), 4, width_ratios=[1, 1, 1, 1.6])
    for i, k in enumerate(kinds):
        r = sel[k]; f = frames(r)
        for j, t in enumerate((0, len(f) // 2, len(f) - 1)):
            ax = fig.add_subplot(gs[i, j]); ax.imshow(f[t]); off(ax)
        ax = fig.add_subplot(gs[i, 3]); ax.axis("off")
        ax.text(0.02, 0.5, f"{SHORT[r['model']]}, {SYSN[r['system']]}\n{VF.FAIL_TITLE[k]}\n{VF.describe(k, r)}",
                fontsize=6.5, va="center", bbox=dict(fc="#fde4e4", ec=RED, boxstyle="round,pad=0.4"))
    fig.subplots_adjust(hspace=0.08, wspace=0.04)


def F4(fig):
    """Physion-Eval-style strips: frames that break a check get a red border."""
    from scipy import ndimage
    sel = _failures()
    kinds = ["multiple_objects", "unstable_size", "static"]
    axs = fig.subplots(len(kinds), 8)
    for i, k in enumerate(kinds):
        r = sel[k]; f = frames(r)
        gray = f.mean(axis=3).astype(np.uint8)
        a0 = object_mask(gray[0], r["ground_row0"]).sum()
        for j, t in enumerate(np.linspace(0, len(f) - 1, 8).round().astype(int)):
            m = object_mask(gray[t], r["ground_row0"])
            lab, n = ndimage.label(m)
            sizes = ndimage.sum(m, lab, index=np.arange(1, n + 1)) if n else []
            ncomp = int(sum(s >= max(4, 0.1 * a0) for s in sizes))
            bad = (k == "multiple_objects" and ncomp != 1) or (k == "unstable_size" and not 0.5 <= m.sum() / max(a0, 1) <= 2)
            axs[i, j].imshow(f[t]); off(axs[i, j]); axs[i, j].set_title(f"{t}", fontsize=5.5)
            if bad or (k == "static" and j > 0):
                for sp in axs[i, j].spines.values():
                    sp.set_edgecolor(RED); sp.set_linewidth(2)
        axs[i, 0].set_ylabel(VF.FAIL_TITLE[k].split("(")[-1].rstrip(")"), fontsize=6.5)


def F5(fig):
    """Artifact injection on simulator clips: the fit is perfect, the estimate is wrong, the checks reject it."""
    from v2_validity_injection import gt_positions, make_clip
    from physweep.fits import fit_theta
    from physweep.validity import classify
    kinds = ["clean", "drip", "duplicate", "balloon", "camera"]
    axs = fig.subplots(1, len(kinds))
    pos = gt_positions("projectile", 9.8, 0)
    for ax, k in zip(axs, kinds):
        clip = make_clip(k, pos, np.random.default_rng(0))
        st_ = shape_stats(clip); cx, cy = centroid_track_above(clip, st_["ground_row0"])
        h, r2 = fit_theta("projectile", cx, cy, R.DT, ground_row=st_["ground_row0"])
        lab = classify("projectile", st_, h if np.isfinite(h) else None, r2)["label"]
        ax.imshow(np.repeat(clip.min(axis=0)[..., None], 3, axis=2)); ax.plot(cx, cy, color=RED, lw=0.8); off(ax)
        ax.set_title(f"{k}\nR$^2$ = {r2:.3f}, $\\hat g$ = {h:.1f}", fontsize=6.5)
        ax.set_xlabel(lab, fontsize=7, color="darkgreen" if lab == "valid" else RED)
    fig.suptitle("Injected artifacts, true $g$ = 9.8: a near-perfect fit is not a measurement", fontsize=8)


def F6(fig):
    """Valid but physically impossible: what passes every check and still breaks physics."""
    allv = [r for m in ORDER for r in recs(m) if VF.is_valid(r)]
    ball = max([r for r in allv if r["system"] == "bouncing_ball"], key=lambda r: (r["theta_hat"], r["clip_id"]))
    neg = min([r for r in allv if r["system"] == "projectile"], key=lambda r: (r["theta_hat"], r["clip_id"]))
    slide = min([r for r in allv if r["system"] == "inclined_slide"], key=lambda r: (r["theta_hat"], r["clip_id"]))
    axs = fig.subplots(1, 3)
    for ax, r, what in zip(axs, (ball, neg, slide), ("bounces higher each time", "decelerates while falling",
                                                        "faster than a frictionless slide")):
        show_clip(ax, r, full=r["system"] == "bouncing_ball", title=f"{SHORT[r['model']]}, {SYSN[r['system']]}\n{ghat(r)}\n{what}")


def F2(fig):
    ax = fig.subplots()
    ax.imshow(plt.imread(os.path.join(REV, "figures", "fig_failures.png"))), ax.axis("off")


# --------------------------------------------------------------------------------------------- RESULTS
def R1(fig):
    """Small multiples (Objects-Slower Fig. 4): g_hat vs g per generator, identity line, beta in the title."""
    d = J("main_text_analysis.json")["results"]
    axs = fig.subplots(3, 3, sharex=True)
    for ax, m in zip(axs.flat, ORDER):
        v = [r for r in recs(m) if r["system"] == "projectile" and VF.is_valid(r)]
        x = np.array([r["theta"] for r in v]) * np.exp(np.random.default_rng(0).normal(0, 0.03, len(v)))
        ax.scatter(x, [r["theta_hat"] for r in v], s=4, color=COL[m], alpha=0.7)
        ax.plot([0, 26], [0, 26], "k--", lw=0.6), ax.axvspan(5, 15, color="0.93", lw=0)
        e = d.get(f"{m}/projectile", {})
        b = f"$\\beta$ = {e['beta_in']:.2f} [{e['beta_in_ci'][0]:.2f}, {e['beta_in_ci'][1]:.2f}]" if "beta_in" in e else ""
        ax.set_title(f"{SHORT[m]} ({len(v)})\n{b}", fontsize=6.5), ax.set_ylim(-8, 28)
    fig.supxlabel("requested $g$"), fig.supylabel("recovered $\\hat g$ (valid clips)")
    fig.subplots_adjust(hspace=0.55)


def R2(fig):
    """Forest plot: in-range slope with CI for every pair, text channel (and frame channel)."""
    d = J("main_text_analysis.json")["results"]
    fr = J("main_frame_frame.json")
    rows = []
    for s in SYS:
        for m in ORDER:
            e = d.get(f"{m}/{s}", {})
            if "beta_in" in e:
                rows.append((f"{SHORT[m]} / {SYSN[s]}", e["beta_in"], e["beta_in_ci"], "text"))
        for k, f in fr.items():
            if k.endswith(s) and "beta_in" in f["frame"]:
                rows.append((f"{SHORT[k.split('/')[0]]} / {SYSN[s]} (frames)", f["frame"]["beta_in"], f["frame"]["beta_in_ci"], "frame"))
    ax = fig.subplots()
    for i, (name, b, ci, ch) in enumerate(rows):
        c = BLUE if ch == "frame" else "0.2"
        ax.plot(ci, [i, i], color=c, lw=1), ax.plot(b, i, "o", color=c, ms=3)
    ax.axvline(0, color="k", lw=0.6), ax.axvline(1, color="green", lw=0.6, ls="--")
    ax.set_yticks(range(len(rows))), ax.set_yticklabels([r[0] for r in rows], fontsize=5.5), ax.invert_yaxis()
    ax.set_xlim(-3, 4), ax.set_xlabel("in-range slope $\\beta$ [95% CI] (clipped to $-3$..4); blue: frame channel")


def R3(fig):
    """Variance shares stacked per generator and system."""
    d = J("main_text_analysis.json")["results"]
    axs = fig.subplots(1, 3, sharey=True)
    for ax, s in zip(axs, SYS):
        for i, m in enumerate(ORDER):
            dec = d.get(f"{m}/{s}", {}).get("decomposition")
            if not dec:
                ax.text(i, 0.02, "--", ha="center", fontsize=6); continue
            b = 0
            for f, c in (("request", "#8c564b"), ("scene", BLUE), ("noise", "#ff7f0e")):
                v = dec["corrected"][f]; ax.bar(i, v, bottom=b, color=c, label=f if i == 0 else None,
                                                 hatch="" if dec["p_value"][f] < 0.01 else "///", edgecolor="white", lw=0)
                b += v
        ax.set_xticks(range(len(ORDER))), ax.set_xticklabels([SHORT[m] for m in ORDER], rotation=60, fontsize=6)
        ax.set_title(SYSN[s]), ax.set_ylim(0, 1)
    from matplotlib.patches import Patch
    axs[0].set_ylabel("share of variance of $\\hat\\theta$ (hatched: p ≥ 0.01)")
    axs[0].legend(handles=[Patch(color=c, label=l) for l, c in (("request", "#8c564b"), ("scene", BLUE), ("noise", "#ff7f0e"))],
                  fontsize=6, frameon=False)


def R4(fig):
    """Validity breakdown per generator (stacked to 100%)."""
    d = J("main_text_analysis.json")["results"]
    labs = [("valid", "#2ca02c"), ("invalid_fit", "#bbbbbb"), ("invalid_shape", RED), ("invalid_static", "#9467bd"),
            ("invalid_camera", "#e377c2")]
    ax = fig.subplots()
    for i, m in enumerate(ORDER):
        c = collections.Counter()
        for s in SYS:
            c.update(d.get(f"{m}/{s}", {}).get("labels", {}))
        n = sum(c.values()); b = 0
        for l, col in labs:
            v = c[l] / n; ax.bar(i, v, bottom=b, color=col, label=l if i == 0 else None); b += v
        ax.text(i, 1.01, f"{c['valid']}", ha="center", fontsize=6)
    ax.set_xticks(range(len(ORDER))), ax.set_xticklabels([SHORT[m] for m in ORDER], rotation=45, fontsize=6.5)
    ax.set_ylabel("fraction of 304 clips"), ax.legend(fontsize=6, frameon=False, ncol=5, loc="upper center", bbox_to_anchor=(0.5, 1.13))


def R5(fig):
    """Rater small multiples (CRONOS Fig. 3 style): plausibility vs relative error, one panel per generator."""
    p = J("main_text_plausibility.json")["per_rater"]["qwen3vl_30b_a3b"]
    axs = fig.subplots(3, 3, sharex=True, sharey=True)
    for ax, m in zip(axs.flat, ORDER):
        rt = ratings(m)
        pts = [(rt[r["clip_id"]], abs(r["theta_hat"] - r["theta"]) / abs(r["theta"])) for r in recs(m)
               if VF.is_valid(r) and r["clip_id"] in rt and r["theta"]]
        if pts:
            x, y = np.array(pts).T; ax.scatter(x, y, s=3, color=COL[m], alpha=0.6)
        e = p[m]; rho = e.get("rho_rel_err_pooled")
        ax.set_title(f"{SHORT[m]}: $\\rho$ = {rho:.2f}, AUROC {e['auroc_valid']:.2f}" if rho is not None else SHORT[m], fontsize=6)
        ax.set_yscale("log")
    fig.supxlabel("plausibility (Qwen3-VL-30B)"), fig.supylabel("relative error (valid clips)")


def R6(fig):
    """Robustness: seeded vs seed-free slope, and structured vs shaded slope."""
    d = J("main_text_analysis.json")
    main, api = d["results"], d.get("compare_results") or {}
    ax1, ax2 = fig.subplots(1, 2)
    for k, e in main.items():
        a = api.get(k, {})
        if "beta_in" in e and "beta_in" in a:
            ax1.errorbar(e["beta_in"], a["beta_in"], xerr=[[e["beta_in"] - e["beta_in_ci"][0]], [e["beta_in_ci"][1] - e["beta_in"]]],
                         yerr=[[a["beta_in"] - a["beta_in_ci"][0]], [a["beta_in_ci"][1] - a["beta_in"]]], fmt="o", ms=3,
                         color=COL[k.split("/")[0]], lw=0.6)
    ax1.axhline(0, color="k", lw=0.5), ax1.axvline(0, color="k", lw=0.5)
    ax1.set_xlabel("$\\beta$ seeded"), ax1.set_ylabel("$\\beta$ seed-free (API mode)"), ax1.set_xlim(-2.5, 3), ax1.set_ylim(-2.5, 3.5)
    for k, e in J("shaded_text_vs_main_text.json").items():
        bs, bh, cs, ch = (e.get("beta_in_structured"), e.get("beta_in_shaded"), e.get("beta_in_structured_ci"),
                          e.get("beta_in_shaded_ci"))
        if bs is not None and bh is not None:
            ax2.errorbar(bs, bh, xerr=[[bs - cs[0]], [cs[1] - bs]], yerr=[[bh - ch[0]], [ch[1] - bh]], fmt="o", ms=3,
                         lw=0.6, color=COL.get(k.split("/")[0], "k"))
    ax2.set_xlim(-3.5, 3.5), ax2.set_ylim(-2, 2)
    ax2.axhline(0, color="k", lw=0.5), ax2.axvline(0, color="k", lw=0.5)
    ax2.set_xlabel("$\\beta$ structured"), ax2.set_ylabel("$\\beta$ shaded"), ax2.set_title("scene style", fontsize=7)
    ax1.set_title("seed control", fontsize=7)


# --------------------------------------------------------------------------------------------- DATASET
def D1(fig):
    """Kang Fig. 2 style: systems as columns, simulated frames top to bottom with a time arrow."""
    axs = fig.subplots(5, 3)
    for j, (s, th) in enumerate((("projectile", 9.8), ("bouncing_ball", 0.8), ("inclined_slide", 0.2))):
        fr, *_ = sim(s, th)
        for i, t in enumerate(np.linspace(0, len(fr) - 1, 5).round().astype(int)):
            axs[i, j].imshow(fr[t]); off(axs[i, j])
        axs[0, j].set_title(f"{SYSN[s]} (${SYM[s]}$ = {th:g})", fontsize=7)
    fig.text(0.04, 0.5, "time →", rotation=-90, va="center", fontsize=8)
    fig.subplots_adjust(wspace=0.05, hspace=0.05)


def D2(fig):
    """Every grid value of every system as a stroboscopic composite; out-of-range columns marked."""
    axs = fig.subplots(3, 7)
    for i, s in enumerate(SYS):
        for j in range(7):
            if j >= len(GRID[s]):
                axs[i, j].axis("off"); continue
            th = GRID[s][j]
            show_sim(axs[i, j], s, th, n=8, title=f"${SYM[s]}$ = {th:g}")
            lo, hi = INR[s]
            if not lo <= th <= hi:
                for sp in axs[i, j].spines.values():
                    sp.set_edgecolor("#ff7f0e"); sp.set_linewidth(2)
        axs[i, 0].set_ylabel(SYSN[s], fontsize=7)
    fig.suptitle("Parameter grids (orange border: out-of-range values)", fontsize=8)


def D3(fig):
    """EvalCrafter Fig. 3 style: headline numbers, then clips per run and valid clips per generator."""
    gs = fig.add_gridspec(2, 2, height_ratios=[0.6, 1.4], wspace=0.55)
    ax = fig.add_subplot(gs[0, :]); ax.axis("off")
    for k, (v, l) in enumerate((("5,432", "generated clips"), ("9", "open generators"), ("3", "physical systems"),
                                ("2", "conditioning channels"), ("2", "VLM raters"))):
        ax.text(0.1 + k * 0.2, 0.6, v, fontsize=20, fontweight="bold", ha="center", color="#3b5b92")
        ax.text(0.1 + k * 0.2, 0.15, l, fontsize=7, ha="center")
    ax = fig.add_subplot(gs[1, 0])
    runs = [("main text", 2736), ("seed-free", 1064), ("shaded", 608), ("frame", 1024)]
    ax.barh([r[0] for r in runs], [r[1] for r in runs], color="#8fb1d9"), ax.set_xlabel("clips"), ax.invert_yaxis()
    ax = fig.add_subplot(gs[1, 1])
    d = J("main_text_analysis.json")["results"]
    v = [sum(d.get(f"{m}/{s}", {}).get("labels", {}).get("valid", 0) for s in SYS) for m in ORDER]
    ax.barh([SHORT[m] for m in ORDER], v, color="#2ca02c"), ax.set_xlabel("valid clips (of 304), text channel"), ax.invert_yaxis()


def D4(fig):
    ax = fig.subplots()
    ax.imshow(plt.imread(os.path.join(REV, "figures", "fig_scenes.png"))), ax.axis("off")


def D5(fig):
    """Model zoo mosaic: one generated frame per generator and system (middle of a valid clip)."""
    axs = fig.subplots(3, 9)
    for j, m in enumerate(ORDER):
        for i, s in enumerate(SYS):
            r = pick(m, s, GRID[s][3]) or pick(m, s, GRID[s][3], valid=False)
            if r is None:
                blank(axs[i, j], ""); continue
            f = frames(r); axs[i, j].imshow(f[len(f) // 2]); off(axs[i, j])
            if not VF.is_valid(r):
                for sp in axs[i, j].spines.values():
                    sp.set_edgecolor(RED); sp.set_linewidth(1.5)
        axs[0, j].set_title(SHORT2[m], fontsize=6)
    for i, s in enumerate(SYS):
        axs[i, 0].set_ylabel(SYSN[s], fontsize=7)
    fig.suptitle("One generated frame per generator and system (red border: clip not valid)", fontsize=8, y=1.06)
    fig.subplots_adjust(wspace=0.04, hspace=0.04)


def D6(fig):
    """What the scene seed changes: the four conditioning frames per system, with the simulated motion."""
    axs = fig.subplots(3, 4)
    for i, (s, th) in enumerate((("projectile", 9.8), ("bouncing_ball", 0.8), ("inclined_slide", 0.2))):
        for j in range(4):
            show_sim(axs[i, j], s, th, seed=j, n=8, title=f"scene seed {j}" if i == 0 else None)
        axs[i, 0].set_ylabel(SYSN[s], fontsize=7)
    fig.suptitle("Scene seeds: the same request rendered from four initial states", fontsize=8)


# --------------------------------------------------------------------------------------------- catalogue
OPTIONS = [
    # id, section, size (w, h in), title, modeled on (figure_refs), what it argues / notes
    ("T1", "Teaser", (6, 3.4), T1, "One request, ten answers", "Objects-Slower Fig. 1 (stroboscopic falls, true gravity first)",
     "The Moon-gravity request: the simulator's slow arc first, then each generator's valid clip. Every generator falls at its own rate."),
    ("T2", "Teaser", (6, 4.4), T2, "Looks fine, wrong physics", "WorldModelBench Fig. 1; WorldScore Fig. 1 (benchmark says A ≈ B, physics says otherwise)",
     "Requested (simulator) above generated (Wan2.2-A14B) for three gravities, with the VLM plausibility score printed under each generated clip: plausible, but not the requested value."),
    ("T3", "Teaser", (7, 2.3), T3, "Current teaser (fig_teaser)", "Objects-Slower Fig. 1 + our median curves",
     "Existing figure: three Wan2.2 clips for g = 1.6, 9.8, 25 and median ĝ vs g for all nine generators."),
    ("T4", "Teaser", (6, 4.2), T4, "Told vs shown", "PhysGen Fig. 1 (input column, then generation); Kang Fig. 7",
     "The same model (LTX-2) given the gravity in text (top) and in nine frames (bottom, blue): the strongest single contrast in the paper."),
    ("T5", "Teaser", (7, 2.8), T5, "Curves that should fan out", "Objects-Slower Fig. 2 (height vs time per model, true curve dashed)",
     "Height vs time: the simulator's curves spread with g; the generator's curves for the same requests collapse together."),
    ("T6", "Teaser", (7, 2.8), T6, "Plausibility is not faithfulness", "CRONOS Fig. 3; WorldModelBench Fig. 9 (score vs score scatter)",
     "Every valid projectile clip: VLM plausibility against parameter error, no relation; next to it, the most plausible clip with a large error."),
    ("P1", "Pipeline / method", (7, 2.2), P1, "Stage bands with real images", "Pattern Recognition survey Fig. 3 (coloured stage bands); Morpheus Fig. 2",
     "Request → renderer → generator → tracker → validity → fit → metrics, each stage a real frame or plot. A data-driven alternative or input for Figure 2."),
    ("P2", "Pipeline / method", (7, 3.4), P2, "Same instrument, two inputs", "Morpheus Fig. 2 (real and generated videos through one pipeline)",
     "Positive control and generator side by side through the same tracker, checks and fit: the simulator returns g = 25, the generator does not."),
    ("P3", "Pipeline / method", (7, 3.6), P3, "The crossed design, filled with clips", "Inferring Fig. 1 (rows × splits); our decomposition",
     "One request on a 4 × 4 grid of scene and noise seeds (each tile a real clip with its ĝ), next to the variance shares it produces. Explains Section 3.3 at a glance."),
    ("P4", "Pipeline / method", (7, 3.6), P4, "Two channels, three input modes", "Physics-IQ Fig. 2 (conditioning frames → continuation)",
     "Text (first frame + prompt), pair (first + middle key frame), prefix (nine frames): the actual inputs and outputs for g = 9.8."),
    ("P5", "Pipeline / method", (7, 3.0), P5, "Validity layer as a decision tree", "Morpheus Fig. 2 (discard branch with Yes/No)",
     "The four checks in order, with how many of the 2,736 clips each rejects and a real example under each."),
    ("P6", "Pipeline / method", (6, 4.5), P6, "How θ̂ is read, per system", "Inferring Fig. 2 (segmentation → trajectory → fit, plots inline)",
     "One row per system: rendered clip with track, the fitted coordinate over time with its fit, and the closed-form estimator."),
    ("Q1", "Qualitative frames", (5, 7), Q1, "Generators × time filmstrips", "PISA Fig. 6; T2VPhysBench Fig. 2 (models as rows, frames as columns)",
     "The same request (g = 9.8) for the simulator and all nine generators, six frames each."),
    ("Q2", "Qualitative frames", (7.5, 2.6), Q2, "Requests × generators composites", "Objects-Slower Figs. 3 and 7 (composites in columns, truth first)",
     "Three requests as rows, simulator + nine generators as columns, ĝ in each tile: the whole text-channel result in one panel."),
    ("Q3", "Qualitative frames", (6, 4.4), Q3, "The noise picks the physics", "WorldScore Fig. 6 (examples with their score)",
     "Same scene, same request, four noise seeds per row, three generators: the realized gravity changes with the seed alone."),
    ("Q4", "Qualitative frames", (7, 2.2), Q4, "Told vs shown, as filmstrips", "PhysGen Fig. 4 (input column marked, generation to the right)",
     "LTX-2 at g = 25: text-channel clip vs frame-channel clip, given frames outlined in blue."),
    ("Q5", "Qualitative frames", (6, 3.2), Q5, "Structured vs shaded twins", "VBench-2.0 Figs. 7–8 (two strips per condition)",
     "The same scene, noise and request in both drawing styles for the four ablation models, with labels and ĝ."),
    ("Q6", "Qualitative frames", (7, 3.4), Q6, "What fills the gap between key frames", "Kang Fig. 10 (ground truth vs generated, minimal frames)",
     "Pair mode: key frames outlined, generated in-between frames, and the height profile against the true and constant-speed motion."),
    ("F1", "Failure gallery", (7, 3.0), F1, "Failure types as columns", "Morpheus Fig. 5 (disappearance / duplicates / stillness, frame 0 vs N)",
     "One column per validity failure, first frame above last frame, the measured quantity underneath."),
    ("F2", "Failure gallery", (5, 6.5), F2, "Current failure figure (fig_failures)", "VideoPhy Fig. 2",
     "Existing figure: one row per failure, four frames with the track."),
    ("F3", "Failure gallery", (6, 5.5), F3, "Frames with a red callout", "VideoPhy Fig. 2 (initial/middle/last + violation box)",
     "Initial, middle and last frame per failure, with a red box naming the check that failed and by how much."),
    ("F4", "Failure gallery", (7, 2.8), F4, "When the failure happens", "Physion-Eval Fig. 2 (strips with the glitch window marked)",
     "Eight frames per clip; frames that break the check (extra objects, area out of range) get a red border, computed per frame."),
    ("F5", "Failure gallery", (7, 2.0), F5, "Perfect fit, wrong answer", "Morpheus Fig. 5; our injection test",
     "Simulator clips with injected artifacts: fit R² and ĝ above each, the validity label below. Makes the case for the validity layer visually."),
    ("F6", "Failure gallery", (6, 2.6), F6, "Valid but impossible", "PhyGround Figs. 20–21 (qualitative violation examples)",
     "Clips that pass every check yet break physics: the most extreme valid estimates per system (e.g. an energy-gaining bounce)."),
    ("R1", "Results plot", (6, 5.2), R1, "One panel per generator", "Objects-Slower Fig. 4 (small multiples, identity line, slope in title)",
     "ĝ against g for every valid projectile clip, per generator, in-range band shaded, β [CI] in each title. Could replace or join Table 4."),
    ("R2", "Results plot", (5, 6.2), R2, "Forest plot of all slopes", "CRONOS Fig. 4; VBench Fig. 5 (per-dimension alignment)",
     "Every model × system slope with its interval, text channel in black and frame channel in blue, lines at 0 and 1."),
    ("R3", "Results plot", (7, 2.8), R3, "Variance shares as stacked bars", "Morpheus Fig. 6 (bars by category per model)",
     "Request, scene and noise shares per generator and system; hatched when not significant. A visual Table 5."),
    ("R4", "Results plot", (6, 2.8), R4, "Validity breakdown per generator", "Physion-Eval Fig. 6 (100% stacked bars of failure categories)",
     "How each generator's 304 clips split into valid and the four failure labels."),
    ("R5", "Results plot", (6, 5.2), R5, "Rater per generator", "CRONOS Fig. 3 (small multiples with r and p)",
     "Plausibility against relative error for each generator, ρ and AUROC in each title. A visual Table 7."),
    ("R6", "Results plot", (6, 2.8), R6, "Robustness at a glance", "WorldModelBench Fig. 9 (score vs score scatter)",
     "Slope with seed control vs without, and structured vs shaded scenes: points stay near zero on both axes."),
    ("D1", "Dataset / scene overview", (4.5, 5.5), D1, "Systems as columns, time downward", "Kang Fig. 2 (uniform motion / collision / parabola)",
     "The three systems' rendered frames over time, minimal and clean."),
    ("D2", "Dataset / scene overview", (7, 3.2), D2, "Every parameter value", "Inferring Fig. 1 (rows per property, columns per split)",
     "Each system's full grid as composites; out-of-range values outlined. Shows what the generators were asked to produce."),
    ("D3", "Dataset / scene overview", (7, 3.4), D3, "Headline numbers + counts", "EvalCrafter Fig. 3 (key numbers above the breakdown)",
     "5,432 clips, 9 generators, 3 systems, 2 channels, 2 raters; clips per run and valid clips per generator."),
    ("D4", "Dataset / scene overview", (7, 3.4), D4, "Current scene figure (fig_scenes)", "Physics-IQ Fig. 3",
     "Existing figure: structured and shaded conditioning frames plus the simulated motion."),
    ("D5", "Dataset / scene overview", (7, 2.6), D5, "Model zoo mosaic", "WorldScore Fig. 3; Physics-IQ Fig. 3 (labelled tiles)",
     "One generated frame per generator and system, invalid clips outlined in red: what the dataset looks like."),
    ("D6", "Dataset / scene overview", (6, 4.4), D6, "What the scene seed changes", "Inferring Fig. 1",
     "The same request rendered from the four scene seeds, per system: the controlled variation behind the scene share."),
]


def main():
    want = set(sys.argv[1:])
    os.makedirs(OUT, exist_ok=True)
    done, failed = [], []
    for oid, section, size, fn, title, ref, note in OPTIONS:
        if want and oid not in want:
            continue
        fig = plt.figure(figsize=size)
        try:
            fn(fig)
            fig.savefig(os.path.join(OUT, f"{oid}.png"), bbox_inches="tight")
            done.append(oid)
        except Exception as e:  # noqa: BLE001 - keep going, report at the end
            failed.append((oid, f"{type(e).__name__}: {e}"))
        plt.close(fig)
        print(oid, "ok" if done and done[-1] == oid else "FAILED", flush=True)
    # catalogue PDF: one page per option that exists
    with PdfPages(os.path.join(OUT, "figure_options.pdf")) as pdf:
        cur = None
        for oid, section, size, fn, title, ref, note in OPTIONS:
            png = os.path.join(OUT, f"{oid}.png")
            if not os.path.exists(png):
                continue
            if section != cur:
                cur = section
                fig = plt.figure(figsize=(8.27, 11.69)); fig.text(0.5, 0.55, section, ha="center", fontsize=28, weight="bold")
                fig.text(0.5, 0.48, "six options, built from our data; modeled on figures in figure_refs.pdf", ha="center", fontsize=11)
                pdf.savefig(fig); plt.close(fig)
            fig = plt.figure(figsize=(8.27, 11.69))
            fig.text(0.06, 0.95, f"{oid}  {title}", fontsize=15, weight="bold")
            fig.text(0.06, 0.92, "Modeled on: " + ref, fontsize=9, color="#3b5b92")
            fig.text(0.06, 0.86, textwrap.fill(note, 100), fontsize=9.5, va="top")
            img = plt.imread(png)
            h, w = img.shape[:2]
            aw, ah = 0.88, 0.74
            scale = min(aw / w, ah * 11.69 / 8.27 / h)
            iw, ih = w * scale, h * scale * 8.27 / 11.69
            ax = fig.add_axes([0.06 + (aw - iw) / 2, 0.08 + (ah - ih), iw, ih]); ax.imshow(img); ax.axis("off")
            pdf.savefig(fig); plt.close(fig)
    print(f"{len(done)} built; failed: {failed}")


if __name__ == "__main__":
    main()
