#!/usr/bin/env python3
"""
Analyze the step-7 plausibility ratings (v2_rate_plausibility.py) of a v2 run (CPU).

Per rater x model, on every rated clip:
  - score histogram (1..5) and mean expected score;
  - validity: AUROC of the expected score for valid vs. not valid (0.5 = no separation), with a bootstrap CI,
    and the mean expected score per validity label;
  - Spearman rho(expected score, fit R^2), the association v1 reported for Qwen2.5-VL-7B.
On VALID clips: Spearman rho(expected score, relative parameter error |theta_hat - theta| / theta), per
system and pooled over systems after ranking within each model x system (a negative rho would mean that
more plausible-looking clips realize the requested value more closely).
Across raters, on clips both rated: Spearman rho of the expected scores, exact agreement of the digits and
quadratic-weighted kappa.
Bootstrap CIs resample clips (2000 draws, seed 0); clips are not independent within a seed cluster.

Usage:  python experiments/v2_plausibility_analysis.py --run main_text
Writes: <REVISION>/results_v2/<run>_plausibility.json and <run>_plausibility.md
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys

CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CODE_DIR)

import numpy as np

from physweep.runio import load_latest, raw_files

RESULTS = os.path.join(os.path.dirname(CODE_DIR), "results_v2")
LABELS = ["valid", "invalid_fit", "invalid_shape", "invalid_camera", "invalid_static"]


def ranks(x):
    x = np.asarray(x, float)
    order = np.argsort(x, kind="mergesort")
    r = np.empty(len(x))
    r[order] = np.arange(len(x))
    for v in np.unique(x):                        # average ranks for ties
        m = x == v
        r[m] = r[m].mean()
    return r


def spearman(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 3 or np.ptp(x[ok]) == 0 or np.ptp(y[ok]) == 0:
        return None
    return float(np.corrcoef(ranks(x[ok]), ranks(y[ok]))[0, 1])


def auroc(score, positive):
    s, p = np.asarray(score, float), np.asarray(positive, bool)
    if p.all() or not p.any():
        return None
    r = ranks(s)
    n1, n0 = p.sum(), (~p).sum()
    return float((r[p].sum() - n1 * (n1 - 1) / 2) / (n1 * n0))


def boot_ci(fn, *cols, n=2000, seed=0):
    rng = np.random.default_rng(seed)
    cols = [np.asarray(c) for c in cols]
    vals = []
    for _ in range(n):
        i = rng.integers(0, len(cols[0]), len(cols[0]))
        v = fn(*(c[i] for c in cols))
        if v is not None and np.isfinite(v):
            vals.append(v)
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))] if len(vals) > n // 2 else None


def weighted_kappa(a, b, k=5):
    a, b = np.asarray(a, int) - 1, np.asarray(b, int) - 1
    obs = np.zeros((k, k))
    for i, j in zip(a, b):
        obs[i, j] += 1
    obs /= obs.sum()
    exp = np.outer(obs.sum(1), obs.sum(0))
    w = np.subtract.outer(np.arange(k), np.arange(k)) ** 2 / (k - 1) ** 2
    den = (w * exp).sum()
    return None if den == 0 else float(1 - (w * obs).sum() / den)


def load(root, model, rater):
    path = os.path.join(root, model, f"plausibility_{rater}.jsonl")
    if not os.path.exists(path):
        return []
    recs = load_latest(os.path.join(root, model), prefer_rescored=True)
    out = []
    for line in open(path):
        if not line.strip():
            continue
        p = json.loads(line)
        r = recs.get(p["clip_id"])
        if r is None or "error" in p or p.get("expected") is None:
            continue
        th, hat = r["theta"], r.get("theta_hat")
        rel = abs(hat - th) / abs(th) if hat is not None and th else None
        out.append(dict(clip_id=p["clip_id"], system=r["system"], label=r["label"], r2=r.get("r2"),
                        score=p["score"], expected=p["expected"], rel_err=rel))
    return out


def analyze(root, raters):
    models = sorted(m for m in os.listdir(root) if os.path.isdir(os.path.join(root, m)) and raw_files(os.path.join(root, m)))
    res = {"per_rater": {}, "agreement": {}}
    rated = {}
    for rater in raters:
        res["per_rater"][rater] = {}
        for model in models:
            rows = load(root, model, rater)
            if not rows:
                continue
            rated[(rater, model)] = {r["clip_id"]: r for r in rows}
            e = np.array([r["expected"] for r in rows])
            valid = np.array([r["label"] == "valid" for r in rows])
            r2 = np.array([r["r2"] if r["r2"] is not None else np.nan for r in rows], float)
            hist = collections.Counter(r["score"] for r in rows)
            per_label = {lab: float(np.mean([r["expected"] for r in rows if r["label"] == lab]))
                         for lab in LABELS if any(r["label"] == lab for r in rows)}
            faith, pooled_e, pooled_err = {}, [], []
            for system in sorted({r["system"] for r in rows}):
                v = [r for r in rows if r["system"] == system and r["label"] == "valid" and r["rel_err"] is not None]
                if len(v) >= 8:
                    x, y = [r["expected"] for r in v], [r["rel_err"] for r in v]
                    faith[system] = dict(n=len(v), rho=spearman(x, y), ci95=boot_ci(spearman, x, y))
                    pooled_e += list(ranks(x) / len(v))
                    pooled_err += list(ranks(y) / len(v))
            res["per_rater"][rater][model] = dict(
                n=len(rows), mean_expected=float(e.mean()), hist={k: hist.get(k, 0) for k in range(1, 6)},
                valid_rate=float(valid.mean()),
                auroc_valid=auroc(e, valid), auroc_ci95=boot_ci(auroc, e, valid),
                mean_expected_by_label=per_label,
                rho_r2=spearman(e, r2), rho_r2_ci95=boot_ci(spearman, e, r2),
                faithfulness=faith,
                rho_rel_err_pooled=spearman(pooled_e, pooled_err) if len(pooled_e) >= 8 else None,
                rho_rel_err_pooled_ci95=boot_ci(spearman, pooled_e, pooled_err) if len(pooled_e) >= 8 else None)
    if len(raters) == 2:
        a, b = raters
        for model in models:
            ra, rb = rated.get((a, model), {}), rated.get((b, model), {})
            both = sorted(set(ra) & set(rb))
            if len(both) < 8:
                continue
            ea, eb = [ra[c]["expected"] for c in both], [rb[c]["expected"] for c in both]
            sa, sb = [ra[c]["score"] for c in both], [rb[c]["score"] for c in both]
            res["agreement"][model] = dict(n=len(both), rho=spearman(ea, eb), ci95=boot_ci(spearman, ea, eb),
                                           exact=float(np.mean(np.array(sa) == np.array(sb))),
                                           kappa_quadratic=weighted_kappa(sa, sb))
    return res


def f(x, nd=2):
    return "–" if x is None else f"{x:.{nd}f}"


def fci(ci):
    return "" if not ci else f" [{ci[0]:.2f}, {ci[1]:.2f}]"


def to_md(run, res):
    out = [f"# Plausibility ratings, run `{run}` (step 7)", "",
           "Generated by `experiments/v2_plausibility_analysis.py`. AUROC: expected score, valid vs. not valid "
           "(0.5 = no separation). ρ(R²): Spearman with fit R². ρ(err): Spearman with relative parameter error on "
           "valid clips, ranked within model × system and pooled (negative = plausible clips are more faithful). "
           "CIs: 2000 bootstrap draws over clips.", ""]
    for rater, per in res["per_rater"].items():
        out += [f"## {rater}", "", "| model | n | valid | mean E[score] | 1 / 2 / 3 / 4 / 5 | AUROC valid | ρ(R²) | ρ(err), valid |",
                "|---|---|---|---|---|---|---|---|"]
        for model, d in per.items():
            h = " / ".join(str(d["hist"][k]) for k in range(1, 6))
            out.append(f"| {model} | {d['n']} | {d['valid_rate']:.2f} | {d['mean_expected']:.2f} | {h} | "
                       f"{f(d['auroc_valid'])}{fci(d['auroc_ci95'])} | {f(d['rho_r2'])}{fci(d['rho_r2_ci95'])} | "
                       f"{f(d['rho_rel_err_pooled'])}{fci(d['rho_rel_err_pooled_ci95'])} |")
        out.append("")
    if res["agreement"]:
        out += ["## Agreement between raters", "", "| model | n | ρ(expected) | exact digit agreement | weighted κ |",
                "|---|---|---|---|---|"]
        for model, d in res["agreement"].items():
            out.append(f"| {model} | {d['n']} | {f(d['rho'])}{fci(d['ci95'])} | {d['exact']:.2f} | {f(d['kappa_quadratic'])} |")
        out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-root", default=os.environ.get("PHYSWEEP_OUT", os.path.join(CODE_DIR, "..", "runs")))
    ap.add_argument("--run", default="main_text")
    ap.add_argument("--raters", nargs="+", default=["qwen3vl_30b_a3b", "qwen25vl_7b"])
    ap.add_argument("--results", default=RESULTS)
    a = ap.parse_args()
    res = analyze(os.path.join(a.out_root, a.run), a.raters)
    os.makedirs(a.results, exist_ok=True)
    with open(os.path.join(a.results, f"{a.run}_plausibility.json"), "w") as fh:
        json.dump(res, fh, indent=1)
    md = to_md(a.run, res)
    with open(os.path.join(a.results, f"{a.run}_plausibility.md"), "w") as fh:
        fh.write(md + "\n")
    print(md)


if __name__ == "__main__":
    main()
