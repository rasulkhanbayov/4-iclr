#!/usr/bin/env python3
"""
Self-test for the v2 design, conditioning and decomposition (CPU only).

1. Design: the crossed design is the expected size, ids are unique, scene and
   noise seeds are disjoint, and api mode never reuses a noise seed.
2. Conditioning: the conditioning frames depend on scene_seed only (identical
   across noise seeds); for the frame channel they also vary with theta.
3. Decomposition, on synthetic theta_hat with 40% of clips dropped at random
   (to mimic invalid clips): each generating mechanism must be attributed to
   the right factor, and the v1 coupled design (one seed for scene and noise)
   must be flagged as confounded.

Usage:  python experiments/v2_design_selftest.py
Writes: results_v2/design_selftest.json
"""

from __future__ import annotations
import json
import os
import sys

CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CODE_DIR)

import numpy as np

from physweep.design import build_design, theta_grid, DEFAULT_SYSTEMS, NOISE_BASE
from physweep.conditioning import build_conditioning
from physweep.decomposition import variance_shares

OUT_DIR = os.path.join(os.path.dirname(CODE_DIR), "results_v2")


def check_design():
    d = build_design()
    api = build_design(mode="api")
    res = dict(n_crossed=len(d), expected=sum(len(theta_grid(s)) for s in DEFAULT_SYSTEMS) * 4 * 4,
               scene_noise_disjoint=max(r["scene_seed"] for r in d) < NOISE_BASE <= min(r["noise_seed"] for r in d),
               api_noise_unique=len({r["noise_seed"] for r in api}) == len(api))
    assert res["n_crossed"] == res["expected"] and res["scene_noise_disjoint"] and res["api_noise_unique"]
    return res


def check_conditioning():
    base = dict(system="projectile", theta=9.8, split="in", scene_seed=2, style="structured", prompt_variant="default")
    a = build_conditioning({**base, "noise_seed": 1000, "channel": "text"})["frames"][0]
    b = build_conditioning({**base, "noise_seed": 1003, "channel": "text"})["frames"][0]
    c = build_conditioning({**base, "noise_seed": 1000, "scene_seed": 3, "channel": "text"})["frames"][0]
    f1 = build_conditioning({**base, "noise_seed": 1000, "channel": "frame"})["frames"]
    f2 = build_conditioning({**base, "noise_seed": 1000, "channel": "frame", "theta": 20})["frames"]
    res = dict(text_same_across_noise=bool(np.array_equal(a, b)),
               text_differs_across_scene=bool(not np.array_equal(a, c)),
               frame_channel_varies_with_theta=bool(not np.array_equal(f1[1], f2[1])))
    assert all(res.values()), res
    return res


def synth(kind, rng, coupled=False, drop=0.4):
    """Synthetic theta_hat plus each factor's true generating component, so the
    test can compare estimated shares with the realized true shares."""
    thetas = [5, 7, 9.8, 12, 15, 1.6, 25]
    c_scene = rng.normal(0, 4, 4)
    c_noise = rng.normal(0, 4, 4)
    use = {"faithful": ("request",), "noise_locked": ("noise",), "scene_locked": ("scene",),
           "mixed_scene_noise": ("scene", "noise"), "pure_noise": (), "global_default": ()}[kind]
    rows = []
    for th in thetas:
        for s in range(4):
            for z in range(4):
                if coupled and z != s:
                    continue
                comp = {"request": th if "request" in use else 0.0,
                        "scene": c_scene[s] if "scene" in use else 0.0,
                        "noise": c_noise[z] if "noise" in use else 0.0}
                spread = rng.normal(0, 4) if kind == "pure_noise" else rng.normal(0, 0.3)
                base = 9.8 if kind == "global_default" else 8.0
                y = (0.0 if "request" in use else base) + sum(comp.values()) + spread
                rows.append((th, s, z, y, comp))
    keep = rows if coupled else [r for r in rows if rng.random() > drop]
    th, s, z, y = (np.array([r[i] for r in keep]) for i in range(4))
    vy = np.var(y)
    true = {f: float(np.var([r[4][f] for r in keep]) / vy) for f in ("request", "scene", "noise")}
    return th, s, z, y, true


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    rng = np.random.default_rng(42)
    out = dict(design=check_design(), conditioning=check_conditioning(), decomposition={})
    print("design:", out["design"])
    print("conditioning:", out["conditioning"])

    # Pass criteria (revised 2026-10-15 after the first run; see LOG.md):
    #  - structured scenarios: every factor's corrected share within 0.10 of
    #    its realized true share (true share = variance of that factor's
    #    generating component / variance of theta_hat, on the kept clips);
    #  - no-structure scenarios (pure_noise, global_default): no factor
    #    significant at permutation p < 0.01.
    print(f"\n{'scenario':<20}{'n':>4}  {'corrected req/scene/noise':<28}{'true req/scene/noise':<24}{'p req/scene/noise':<22}verdict")
    all_ok = True
    for kind in ["faithful", "noise_locked", "scene_locked", "mixed_scene_noise", "pure_noise", "global_default"]:
        th, s, z, y, true = synth(kind, rng)
        r = variance_shares(th, s, z, y, n_perm=200, n_boot=200)
        cor, pv = r["corrected"], r["p_value"]
        if kind in ("pure_noise", "global_default"):
            ok = min(pv.values()) >= 0.01
        else:
            ok = all(abs(cor[f] - true[f]) <= 0.10 for f in cor)
        all_ok &= ok
        out["decomposition"][kind] = dict(shares=r["shares"], corrected=cor, true=true, p_value=pv, ok=ok)
        f3 = lambda d: "/".join(f"{d[k]:.3f}" for k in ("request", "scene", "noise"))
        print(f"{kind:<20}{r['n']:>4}  {f3(cor):<28}{f3(true):<24}{f3(pv):<22}{'OK' if ok else 'FAIL'}")

    th, s, z, y, _ = synth("noise_locked", rng, coupled=True)
    rc = variance_shares(th, s, z, y, n_perm=200, n_boot=200)
    out["coupled_v1_design"] = dict(confounded=rc["confounded"], shares=rc["shares"])
    print(f"\nv1 coupled design (scene seed == noise seed), noise-locked data: confounded={rc['confounded']}, "
          f"scene={rc['shares']['scene']:.3f}, noise={rc['shares']['noise']:.3f} (split equally: not identifiable)")
    all_ok &= rc["confounded"]
    out["all_ok"] = bool(all_ok)
    with open(os.path.join(OUT_DIR, "design_selftest.json"), "w") as f:
        json.dump(out, f, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print("\nALL CHECKS PASSED" if all_ok else "\nSOME CHECKS FAILED")


if __name__ == "__main__":
    main()
