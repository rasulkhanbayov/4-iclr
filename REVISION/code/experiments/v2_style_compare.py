#!/usr/bin/env python3
"""
Shaded-style ablation (plan step 2, review T3: are the findings an artefact of out-of-distribution flat scenes?).

The shaded run (`shaded_text`: text channel, style "shaded", 4 scene x 2 noise seeds) and the main run
(`main_text`: style "structured", 4 scene x 4 noise seeds) share the design factors, so every shaded clip has
a twin in main_text with the same system, theta, scene seed and noise seed (noise 1000 and 1001); only the
drawing style differs. Per model x system, on the matched pairs:
  - valid rate in each style, and an exact McNemar test on the discordant pairs;
  - in-range faithfulness slope beta on the valid clips of each style (95% bootstrap CI);
  - on pairs valid in BOTH styles: Spearman rho(theta_hat structured, theta_hat shaded), and the median
    relative change |theta_hat_shaded - theta_hat_structured| / theta.
Both runs are read through load_latest(prefer_rescored=True), i.e. scored by the current rules.

Usage:  python experiments/v2_style_compare.py [--run shaded_text --base main_text]
Writes: <REVISION>/results_v2/<run>_vs_<base>.json and .md
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CODE_DIR)

import numpy as np

from physweep.runio import load_latest, raw_files
from physweep_metrics import faithfulness_slope

RESULTS = os.path.join(os.path.dirname(CODE_DIR), "results_v2")
KEY = ("system", "theta", "scene_seed", "noise_seed")


def is_valid(r):
    return "error" not in r and r.get("label") == "valid" and r.get("theta_hat") is not None


def mcnemar_exact(b, c):
    """Two-sided exact McNemar p-value for b pairs valid only in A and c pairs valid only in B."""
    n = b + c
    if n == 0:
        return None
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def spearman(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 3 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return None
    rx = np.argsort(np.argsort(x, kind="mergesort"), kind="mergesort").astype(float)
    ry = np.argsort(np.argsort(y, kind="mergesort"), kind="mergesort").astype(float)
    for r, v in ((rx, x), (ry, y)):                     # average ranks for ties
        for u in np.unique(v):
            m = v == u
            r[m] = r[m].mean()
    return float(np.corrcoef(rx, ry)[0, 1])


def beta_ci(x, y, n=2000, seed=0):
    rng = np.random.default_rng(seed)
    x, y = np.asarray(x, float), np.asarray(y, float)
    vals = []
    for _ in range(n):
        i = rng.integers(0, len(x), len(x))
        if len(np.unique(x[i])) >= 2:
            vals.append(faithfulness_slope(x[i], y[i]))
    vals = [v for v in vals if np.isfinite(v)]
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))] if len(vals) > n // 2 else None


def beta(rows):
    inn = [r for r in rows if r["split"] == "in"]
    if len(inn) < 3 or len({r["theta"] for r in inn}) < 2:
        return None, None
    x, y = [r["theta"] for r in inn], [r["theta_hat"] for r in inn]
    return float(faithfulness_slope(np.array(x, float), np.array(y, float))), beta_ci(x, y)


def compare(root, run, base):
    res = {}
    for model in sorted(os.listdir(os.path.join(root, run))):
        mdir, bdir = os.path.join(root, run, model), os.path.join(root, base, model)
        if not (os.path.isdir(mdir) and raw_files(mdir) and os.path.isdir(bdir) and raw_files(bdir)):
            continue
        new = {tuple(r[k] for k in KEY): r for r in load_latest(mdir, prefer_rescored=True).values()}
        old = {tuple(r[k] for k in KEY): r for r in load_latest(bdir, prefer_rescored=True).values()}
        for system in sorted({k[0] for k in new}):
            keys = sorted(k for k in new if k[0] == system and k in old)
            pairs = [(old[k], new[k]) for k in keys]
            vo = [is_valid(o) for o, _ in pairs]
            vn = [is_valid(n) for _, n in pairs]
            b = sum(o and not n for o, n in zip(vo, vn))      # valid structured only
            c = sum(n and not o for o, n in zip(vo, vn))      # valid shaded only
            both = [(o, n) for (o, n), a, d in zip(pairs, vo, vn) if a and d]
            rel = [abs(n["theta_hat"] - o["theta_hat"]) / abs(o["theta"]) for o, n in both if o["theta"]]
            b_old, ci_old = beta([o for (o, _), a in zip(pairs, vo) if a])
            b_new, ci_new = beta([n for (_, n), d in zip(pairs, vn) if d])
            res[f"{model}/{system}"] = dict(
                n_pairs=len(pairs), unmatched=sum(k[0] == system for k in new) - len(pairs),
                valid_structured=sum(vo), valid_shaded=sum(vn), valid_both=len(both),
                only_structured=b, only_shaded=c, mcnemar_p=mcnemar_exact(b, c),
                beta_in_structured=b_old, beta_in_structured_ci=ci_old,
                beta_in_shaded=b_new, beta_in_shaded_ci=ci_new,
                rho_theta_hat=spearman([o["theta_hat"] for o, _ in both], [n["theta_hat"] for _, n in both]),
                median_rel_change=float(np.median(rel)) if rel else None)
    return res


def f(x, nd=2):
    return "–" if x is None else f"{x:.{nd}f}"


def fci(ci):
    return "" if not ci else f" [{ci[0]:.2f}, {ci[1]:.2f}]"


def to_md(run, base, res):
    out = [f"# Style ablation: `{run}` (shaded) vs `{base}` (structured)", "",
           "Generated by `experiments/v2_style_compare.py`. Pairs share system, θ, scene seed and noise seed; only "
           "the drawing style differs. McNemar: exact two-sided test on pairs valid in one style only. β: in-range "
           "faithfulness slope on valid clips (95% bootstrap CI). ρ(θ̂) and median |Δθ̂|/θ: on pairs valid in both "
           "styles.", "",
           "| model / system | pairs | valid struct. | valid shaded | McNemar p | β struct. | β shaded | both valid | ρ(θ̂) | median \\|Δθ̂\\|/θ |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for k, d in res.items():
        out.append(f"| {k} | {d['n_pairs']} | {d['valid_structured']} | {d['valid_shaded']} | {f(d['mcnemar_p'], 3)} | "
                   f"{f(d['beta_in_structured'])}{fci(d['beta_in_structured_ci'])} | "
                   f"{f(d['beta_in_shaded'])}{fci(d['beta_in_shaded_ci'])} | {d['valid_both']} | "
                   f"{f(d['rho_theta_hat'])} | {f(d['median_rel_change'])} |")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-root", default=os.environ.get("PHYSWEEP_OUT", os.path.join(CODE_DIR, "..", "runs")))
    ap.add_argument("--run", default="shaded_text")
    ap.add_argument("--base", default="main_text")
    ap.add_argument("--results", default=RESULTS)
    a = ap.parse_args()
    res = compare(a.out_root, a.run, a.base)
    os.makedirs(a.results, exist_ok=True)
    stem = os.path.join(a.results, f"{a.run}_vs_{a.base}")
    with open(stem + ".json", "w") as fh:
        json.dump(res, fh, indent=1)
    md = to_md(a.run, a.base, res)
    with open(stem + ".md", "w") as fh:
        fh.write(md + "\n")
    print(md)


if __name__ == "__main__":
    main()
