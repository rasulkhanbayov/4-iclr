#!/usr/bin/env python3
"""
Analyze a finished v2 run (CPU). Uses the re-scored records when present.

Per model x system:
  - validity: counts per label and the valid rate (a result in its own right);
  - on VALID clips: in-range faithfulness slope beta with a 95% bootstrap CI,
    Spearman rho over the full grid, PRE(in), PRE(out), EG;
  - on VALID clips: the request / scene / noise variance decomposition
    (physweep/decomposition.py), with chance-corrected shares and p-values.
With --compare <api run>: the seed-free metrics (valid rate, beta, rho) of the
seeded run next to the same metrics from the API-mode run (fresh noise seed
per clip), to check that the seed-free tier does not depend on seed control.

Usage:  python experiments/v2_analyze.py --run main_text [--compare api_text]
Writes: <REVISION>/results_v2/<run>_analysis.json and <run>_analysis.md
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

from physweep.decomposition import variance_shares
from physweep.runio import load_latest, raw_files
from physweep_metrics import faithfulness_slope, pre, spearman_rho

RESULTS = os.path.join(os.path.dirname(CODE_DIR), "results_v2")
LABELS = ["valid", "invalid_fit", "invalid_shape", "invalid_camera", "invalid_static", "error"]


def boot(fn, x, y, n=2000, seed=0):
    """NaN-safe percentile bootstrap over clips; skips degenerate resamples."""
    rng = np.random.default_rng(seed)
    x, y = np.asarray(x, float), np.asarray(y, float)
    vals = []
    for _ in range(n):
        i = rng.integers(0, len(x), len(x))
        if len(np.unique(x[i])) < 2:
            continue
        v = fn(x[i], y[i])
        if np.isfinite(v):
            vals.append(v)
    if len(vals) < n // 2:
        return None
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


def seed_free(valid, total):
    out = dict(n_clips=total, n_valid=len(valid), valid_rate=len(valid) / total if total else None)
    inn = [r for r in valid if r["split"] == "in"]
    if len(inn) >= 3 and len({r["theta"] for r in inn}) >= 2:
        x = np.array([r["theta"] for r in inn], float)
        y = np.array([r["theta_hat"] for r in inn], float)
        out["beta_in"] = float(faithfulness_slope(x, y))
        out["beta_in_ci"] = boot(faithfulness_slope, x, y)
        out["pre_in"] = float(pre(x, y))
    outr = [r for r in valid if r["split"] == "out"]
    if outr:
        out["pre_out"] = float(pre([r["theta"] for r in outr], [r["theta_hat"] for r in outr]))
        if "pre_in" in out:
            out["eg"] = out["pre_out"] - out["pre_in"]
    if len(valid) >= 4 and len({r["theta"] for r in valid}) >= 2:
        out["spearman_rho"] = float(spearman_rho([r["theta"] for r in valid], [r["theta_hat"] for r in valid]))
    return out


def analyze_run(root, confirmed_only=False):
    res = {}
    for model in sorted(os.listdir(root)):
        mdir = os.path.join(root, model)
        if not os.path.isdir(mdir) or not raw_files(mdir):
            continue
        recs = list(load_latest(mdir, prefer_rescored=True).values())
        for system in sorted({r["system"] for r in recs}):
            rs = [r for r in recs if r["system"] == system]
            lab = collections.Counter("error" if "error" in r else r["label"] for r in rs)
            valid = [r for r in rs if "error" not in r and r["label"] == "valid" and r["theta_hat"] is not None
                     and (not confirmed_only or r.get("second_tracker") == "confirmed")]
            entry = dict(labels={k: lab.get(k, 0) for k in LABELS},
                         confirmed=sum(r.get("second_tracker") == "confirmed" for r in valid),
                         **seed_free(valid, len(rs)))
            if len(valid) >= 8 and len({r["noise_seed"] for r in valid}) >= 2:
                d = variance_shares([r["theta"] for r in valid], [r["scene_seed"] for r in valid],
                                    [r["noise_seed"] for r in valid], [r["theta_hat"] for r in valid],
                                    n_perm=500, n_boot=300)
                entry["decomposition"] = {k: d.get(k) for k in ("n", "shares", "corrected", "p_value", "ci95",
                                                                 "confounded", "total_variance")}
            res[f"{model}/{system}"] = entry
    return res


def fmt_ci(ci):
    return "—" if not ci else f"[{ci[0]:.2f}, {ci[1]:.2f}]"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-root", default=os.environ.get("PHYSWEEP_OUT", os.path.join(CODE_DIR, "..", "runs")))
    ap.add_argument("--run", required=True)
    ap.add_argument("--compare", default=None, help="API-mode run to compare seed-free metrics against")
    ap.add_argument("--results-dir", default=RESULTS)
    ap.add_argument("--confirmed-only", action="store_true",
                    help="robustness check: use only valid clips confirmed by the second tracker")
    a = ap.parse_args()

    main_res = analyze_run(os.path.join(a.out_root, a.run), a.confirmed_only)
    cmp_res = analyze_run(os.path.join(a.out_root, a.compare), a.confirmed_only) if a.compare else {}
    tag = a.run + ("_confirmed" if a.confirmed_only else "")
    os.makedirs(a.results_dir, exist_ok=True)
    with open(os.path.join(a.results_dir, f"{tag}_analysis.json"), "w") as f:
        json.dump(dict(run=a.run, compare=a.compare, results=main_res, compare_results=cmp_res), f, indent=1)

    lines = [f"# Analysis of run `{a.run}`" + (" (second-tracker-confirmed clips only)" if a.confirmed_only else ""), "",
             "Metrics on VALID clips only. β = in-range faithfulness slope (1 = faithful, 0 = ignores the request).",
             "Shares = chance-corrected variance shares of θ̂ (request / scene / noise); p-values from label permutation.", "",
             "| model / system | clips | valid | 2nd-tracker confirmed | β in-range [95% CI] | Spearman ρ | PRE in | PRE out | request share (p) | scene share (p) | noise share (p) |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, e in main_res.items():
        d = e.get("decomposition") or {}
        cor, pv = d.get("corrected") or {}, d.get("p_value") or {}
        sh = lambda f: f"{cor[f]:.2f} ({pv[f]:.3f})" if f in cor else "—"
        lines.append(f"| {k} | {e['n_clips']} | {e['n_valid']} | {e['confirmed']} | "
                     f"{e['beta_in']:.2f} {fmt_ci(e.get('beta_in_ci'))} | " if "beta_in" in e else
                     f"| {k} | {e['n_clips']} | {e['n_valid']} | {e['confirmed']} | — | ")
        lines[-1] += (f"{e['spearman_rho']:.2f} | " if "spearman_rho" in e else "— | ")
        lines[-1] += (f"{e['pre_in']:.2f} | " if "pre_in" in e else "— | ")
        lines[-1] += (f"{e['pre_out']:.2f} | " if "pre_out" in e else "— | ")
        lines[-1] += f"{sh('request')} | {sh('scene')} | {sh('noise')} |"
    if cmp_res:
        lines += ["", f"## Seed-free tier: `{a.run}` (seeded) vs `{a.compare}` (API mode, fresh seed per clip)", "",
                  "| model / system | valid rate seeded | valid rate API | β seeded [CI] | β API [CI] | ρ seeded | ρ API |",
                  "|---|---|---|---|---|---|---|"]
        for k in sorted(set(main_res) & set(cmp_res)):
            m, c = main_res[k], cmp_res[k]
            b = lambda e: f"{e['beta_in']:.2f} {fmt_ci(e.get('beta_in_ci'))}" if "beta_in" in e else "—"
            r = lambda e: f"{e['spearman_rho']:.2f}" if "spearman_rho" in e else "—"
            lines.append(f"| {k} | {m['valid_rate']:.2f} | {c['valid_rate']:.2f} | {b(m)} | {b(c)} | {r(m)} | {r(c)} |")
    with open(os.path.join(a.results_dir, f"{tag}_analysis.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
