#!/usr/bin/env python3
"""
Recompute every number in the paper and the step reports from the archived data.

Each number has one registry entry: the document and an anchor string that
locates its line, the value as printed, a function that recomputes it from the
archived files, and a short description of the source. The check recomputes
the value, rounds it to the printed precision, and compares. PROVENANCE.md is
generated from the same registry (--write-md), so the ledger and the check
cannot drift apart.

Usage (from REVISION/code, any env with numpy, pyyaml, pillow):
  python experiments/reproduce_numbers.py                # check everything
  python experiments/reproduce_numbers.py --write-md     # also regenerate ../PROVENANCE.md
  python experiments/reproduce_numbers.py --recompute    # also re-run v2_analyze.py into a temp dir, diff
  python experiments/reproduce_numbers.py --show ID      # one entry in full
  python experiments/reproduce_numbers.py --find 0.033   # entries whose printed value contains a string
Point at a restored copy with --v1 --v2 --runs --logs-v1 --logs-v2.

Status per number
  match        recomputed value rounds to the printed value
  MISMATCH     it does not (the paper or report is wrong, or the data drifted)
  superseded   an earlier table in a report that a later table in the same report replaces
  qualitative  a wording claim: the underlying values are shown, no pass/fail
  unarchived   comes from a source never saved as data (the note says which)
  external     quoted from another paper
  missing      an input file is not present (e.g. runs/ not restored)
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import functools
import glob
import hashlib
import importlib.util
import io
import json
import math
import os
import re
import statistics as st
import subprocess
import sys
import tempfile
from dataclasses import dataclass

CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REV = os.path.dirname(CODE_DIR)
ROOT = os.path.dirname(REV)
sys.path.insert(0, CODE_DIR)
sys.path.insert(0, os.path.join(CODE_DIR, "experiments"))

import numpy as np

DATA = dict(
    v1=os.path.join(REV, "results_v1"),
    v2=os.path.join(REV, "results_v2"),
    runs=os.environ.get("PHYSWEEP_OUT", "/export/hbku-research/rakh90100/physweep_revision/runs"),
    logs_v1=os.path.join(ROOT, "slurm_jobs"),
    logs_v2=os.path.join(REV, "slurm", "v2"),
    prov=os.path.join(REV, "provenance"),
    code=CODE_DIR,
    rev=REV,
)
CODE_FILES = ["physweep_metrics.py", "physweep/metrics_v3.py", "physweep/decomposition.py", "physweep/validity.py",
              "physweep/fits.py", "physweep/runio.py", "physweep/render.py", "physweep/generators.py",
              "physweep/configs/systems.yaml", "experiments/e2_extrapolation.py", "experiments/v2_analyze.py",
              "experiments/reproduce_numbers.py"]

_USED: dict[str, set] = collections.defaultdict(set)    # entry id -> input files
_CLIPS: dict[str, list] = collections.defaultdict(list)  # entry id -> clip keys aggregated
_CUR = [None]


class Missing(Exception):
    pass


def F(area: str, rel: str) -> str:
    """Path of an input file, recorded as used by the current entry."""
    p = os.path.join(DATA[area], rel)
    if not os.path.exists(p):
        raise Missing(f"{area}:{rel}")
    if _CUR[0]:
        _USED[_CUR[0]].add((area, rel))
    return p


def clips(keys):
    if _CUR[0]:
        _CLIPS[_CUR[0]].extend(keys)


@functools.lru_cache(None)
def _json(area, rel):
    with open(os.path.join(DATA[area], rel)) as f:
        return json.load(f)


def J(area, rel):
    F(area, rel)
    return _json(area, rel)


@functools.lru_cache(None)
def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def pm():          # v1 metrics (the submitted paper's numbers were computed with this)
    return module(os.path.join(CODE_DIR, "physweep_metrics.py"), "physweep_metrics")


def m3():          # VERSION3 metrics (SDI, Holm, margin rule)
    import physweep.metrics_v3 as m
    return m


def r(x, d):
    return None if x is None or not np.isfinite(x) else round(float(x), d)


# =============================================================================
# v1 data (results_v1/, the submitted WACV paper)
# =============================================================================
MODELS_V1 = ["ltx", "cogvideox", "dynamicrafter"]
SYSTEMS_V1 = ["projectile", "pendulum_omega", "pendulum_zeta", "bouncing_ball", "spring_mass", "inclined_slide"]
PF = {"ltx": "e0_pilot.json", "cogvideox": "e0_pilot_cogvideox.json", "dynamicrafter": "e0_pilot_dynamicrafter.json"}
FRAME_BOUND = ["pendulum_omega", "pendulum_zeta", "spring_mass"]
SHORT = ["projectile", "inclined_slide", "bouncing_ball"]


def v1file(model, system):
    return PF[model] if system == "projectile" else f"e4_{system}_{model}.json"


def v1rows(model, system):
    f = v1file(model, system)
    out = []
    for x in J("v1", f)["rows"]:
        if "g_true" in x:
            x = dict(theta=x["g_true"], theta_hat=x["g_hat"], r2=x["r2"], split=x["split"], seed=x["seed"])
        out.append(dict(x, _key=f"{f}:{x['theta']}:{x['split']}:{x['seed']}"))
    return out


def ok(x, gate=0.8):
    return x["r2"] is not None and x["r2"] >= gate and x["theta_hat"] is not None and np.isfinite(x["theta_hat"])


def gated(rows, split=None):
    g = [x for x in rows if ok(x) and (split is None or x["split"] == split)]
    clips([x["_key"] for x in g])
    return g


def arr(rows, k):
    return np.array([x[k] for x in rows], float)


def coverage(model, system):
    rows = v1rows(model, system)
    ins = [x for x in rows if x["split"] == "in"]
    return 100.0 * len(gated(ins)) / len(ins)


def slope_ci(model, system):
    g = gated(v1rows(model, system), "in")
    return pm().bootstrap_ci(pm().faithfulness_slope, arr(g, "theta"), arr(g, "theta_hat"))


def pre_in(model, system):
    g = gated(v1rows(model, system), "in")
    return pm().pre(arr(g, "theta"), arr(g, "theta_hat"))


SLOPE_CELLS = [("ltx", "projectile"), ("ltx", "inclined_slide"), ("cogvideox", "projectile"),
               ("dynamicrafter", "projectile"), ("dynamicrafter", "inclined_slide")]
E2_PAIRS = [("ltx", "projectile"), ("ltx", "bouncing_ball"), ("ltx", "inclined_slide"), ("cogvideox", "projectile"),
            ("cogvideox", "bouncing_ball"), ("dynamicrafter", "projectile"), ("dynamicrafter", "bouncing_ball"),
            ("dynamicrafter", "inclined_slide")]


def slope_estimable(model, system):
    """The paper's rule for a slope cell (CLAUDE.md 0zf): >= 5 gated in-range clips and, for the
    bouncing ball, no fitter-degenerate e_hat > 1.5 (DynamiCrafter's 10.28 at e=0.9, seed 1)."""
    g = gated(v1rows(model, system), "in")
    return len(g) >= 5 and not (system == "bouncing_ball" and any(x["theta_hat"] > 1.5 for x in g))


@functools.lru_cache(None)
def e2_recomputed(model, system):
    e2 = module(os.path.join(CODE_DIR, "experiments", "e2_extrapolation.py"), "e2_extrapolation")
    rows = [{k: v for k, v in x.items() if k != "_key"} for x in v1rows(model, system)]
    return e2.analyze_pair(model, system, rows, e2.theta_edge_for(system, e2.load_config()))


def e2(model, system):
    v1rows(model, system)            # records the input file
    gated(v1rows(model, system), "out")
    return e2_recomputed(model, system)


def sdi(model, system):
    g = gated(v1rows(model, system), "out")
    return m3().seed_determination_index(arr(g, "seed"), arr(g, "theta_hat"))


def bootstrap_pairs():
    out = []
    for m in MODELS_V1:
        for s in SYSTEMS_V1:
            if s in FRAME_BOUND and m == "dynamicrafter":
                pass
            res = e2(m, s) if os.path.exists(os.path.join(DATA["v1"], v1file(m, s))) else {}
            if res.get("paired_bootstrap_PRE_out_minus_in"):
                out.append(((m, s), res["paired_bootstrap_PRE_out_minus_in"]))
    return out


def holm():
    pb = bootstrap_pairs()
    adj = m3().holm_adjust([b[3] for _, b in pb])
    return {k: a for (k, _), a in zip(pb, adj)}


def perm_p(model, system, n=10000, seed=0):
    """Label-permutation null for beta (recreated; VERSION3's own script was never saved).
    Two-sided p = share of |beta_perm| >= |beta_obs|. rng seed 0 reproduces the 2026-08-26 values."""
    g = gated(v1rows(model, system), "in")
    th, h = arr(g, "theta"), arr(g, "theta_hat")
    b = pm().faithfulness_slope(th, h)
    rng = np.random.default_rng(seed)
    bs = np.array([pm().faithfulness_slope(rng.permutation(th), h) for _ in range(n)])
    return float(np.mean(np.abs(bs) >= abs(b)))


def tost_p(model, system, eps=0.2):
    """TOST of beta against +-eps, SE backed out of the 95% bootstrap CI (normal approx.)."""
    b, lo, hi = slope_ci(model, system)
    se = (hi - lo) / (2 * 1.959963985)
    phi = lambda z: 0.5 * (1 + math.erf(z / math.sqrt(2)))
    return max(1 - phi((b + eps) / se), 1 - phi((eps - b) / se))


def seed_stats(model, system, seed, split, gate=True, ddof=0):
    """Mean and std of one seed's theta_hat. The paper is not consistent: the CogVideoX seed
    clusters (+-0.03, +-0.2) match the sample std (ddof=1); the DynamiCrafter slide clusters
    (0.04, 0.13) match the population std (ddof=0)."""
    rows = [x for x in v1rows(model, system) if x["seed"] == seed and x["split"] == split]
    rows = gated(rows) if gate else rows
    if not gate:
        clips([x["_key"] for x in rows])
    v = arr(rows, "theta_hat")
    return float(np.mean(v)), float(np.std(v, ddof=ddof)), rows


def e3_rows(model):
    out = []
    for s in SYSTEMS_V1:
        f = f"e3_plausibility_default_{s}_{model}.json"
        for x in J("v1", f)["rows"]:
            if x.get("plausibility") is not None:
                out.append(x)
                clips([f"{f}:{os.path.basename(x['video_path'])}"])
    return out


def e3_corr(model):
    rows = e3_rows(model)
    return float(np.corrcoef(arr(rows, "r2"), arr(rows, "plausibility"))[0, 1])


def e3_clip(basename):
    for m in MODELS_V1:
        for x in e3_rows(m):
            if os.path.basename(x["video_path"]) == basename:
                return x
    raise KeyError(basename)


def e5b_slopes(model):
    b = J("v1", "e5bdef_ablation_comparison.json")[model]
    return [v["slope_in"] for k, v in b.items() if k != "default" and v.get("slope_in") is not None]


def v1_timed():
    """The 69 result files that log their own elapsed_seconds, with clip counts."""
    out = []
    for f in sorted(glob.glob(os.path.join(DATA["v1"], "*.json"))):
        d = _json("v1", os.path.basename(f))
        if not isinstance(d, dict) or "rows" not in d:
            continue
        s = d.get("summary") if isinstance(d.get("summary"), dict) else {}
        e = s.get("elapsed_seconds", d.get("elapsed_seconds"))
        if isinstance(e, (int, float)):
            F("v1", os.path.basename(f))
            out.append((os.path.basename(f), float(e), len(d["rows"])))
    return out


def v1_rate(model):
    t = [(e, n) for f, e, n in v1_timed() if model in f.replace("e4_generality", "")
         and (model != "ltx" or True) and _model_of(f) == model]
    return sum(e for e, _ in t) / sum(n for _, n in t)


def _model_of(f):
    for m in ["dynamicrafter", "cogvideox", "ltx"]:
        if m in f:
            return m


def v1_untimed_hours():
    tot = 0.0
    for m in ["cogvideox", "dynamicrafter"]:
        tot += len(J("v1", PF[m])["rows"]) * v1_rate(m)
    return tot / 3600


def vlm_hours():
    """VLM scoring window: first to last e3_plausibility_* write, frozen to provenance/ because
    file times do not survive an archive round trip."""
    t = J("prov", "v1_file_times.json")["e3_plausibility_default"]
    return (t["last_write_epoch"] - t["first_write_epoch"]) / 3600


def v1_gpu_hours():
    return sum(e for _, e, _ in v1_timed()) / 3600 + v1_untimed_hours() + vlm_hours()


def per_file_rate_range(model):
    v = [e / n for f, e, n in v1_timed() if _model_of(f) == model]
    return min(v), max(v)


# =============================================================================
# v2 data (results_v2/, runs/)
# =============================================================================
def recs(run, model, rescored=True):
    from physweep.runio import load_latest, raw_files
    d = os.path.join(DATA["runs"], run, model)
    if not os.path.isdir(d):
        raise Missing(f"runs:{run}/{model}")
    files = ["clips_rescored.jsonl"] if rescored and os.path.exists(os.path.join(d, "clips_rescored.jsonl")) \
        else [os.path.basename(p) for p in raw_files(d)]
    for f in files:
        F("runs", f"{run}/{model}/{f}")
    out = list(load_latest(d, prefer_rescored=rescored).values())
    clips([f"{run}/{model}/{x['clip_id']}" for x in out])
    return out


def run_models(run):
    d = os.path.join(DATA["runs"], run)
    if not os.path.isdir(d):
        raise Missing(f"runs:{run}")
    return sorted(m for m in os.listdir(d) if os.path.isdir(os.path.join(d, m)))


def valid(rs, **kw):
    return [x for x in rs if "error" not in x and x.get("label") == "valid"
            and all(x.get(k) == v for k, v in kw.items())]


def analysis(confirmed=False):
    return J("v2", "main_text_confirmed_analysis.json" if confirmed else "main_text_analysis.json")


def est_pairs(confirmed=False):
    return {k: v for k, v in analysis(confirmed)["results"].items() if v.get("beta_in_ci")}


def dec_pairs(confirmed=False):
    return {k: v["decomposition"] for k, v in analysis(confirmed)["results"].items() if v.get("decomposition")}


def n_sig(factor, confirmed=False, alpha=0.01):
    d = dec_pairs(confirmed)
    return sum(v["p_value"][factor] < alpha for v in d.values()), len(d)


def median_by_theta(run, model, system):
    v = valid(recs(run, model), system=system)
    by = collections.defaultdict(list)
    for x in v:
        if x.get("theta_hat") is not None:
            by[x["theta"]].append(x["theta_hat"])
    return {t: float(np.median(h)) for t, h in sorted(by.items())}


def fisher_two_sided(a, b, c, d):
    """Two-sided Fisher exact test for [[a, b], [c, d]] (sum of tables no more likely than observed)."""
    n1, n2, k = a + b, c + d, a + c
    lg = lambda n, r_: math.lgamma(n + 1) - math.lgamma(r_ + 1) - math.lgamma(n - r_ + 1)
    p = lambda x: math.exp(lg(n1, x) + lg(n2, k - x) - lg(n1 + n2, k))
    obs = p(a)
    return min(1.0, sum(p(x) for x in range(max(0, k - n2), min(k, n1) + 1) if p(x) <= obs * (1 + 1e-9)))


def api_valid_rate_tests():
    """Seeded vs API-mode valid rate per model x system, Fisher exact (recreated: the original
    test was not saved). Returns {pair: p}."""
    out = {}
    for m in run_models("api_text"):
        seeded, api = recs("main_text", m), recs("api_text", m)
        for s in SHORT:
            a = len(valid(seeded, system=s)); n = sum(1 for x in seeded if x.get("system") == s)
            c = len(valid(api, system=s)); n2 = sum(1 for x in api if x.get("system") == s)
            out[f"{m}/{s}"] = fisher_two_sided(a, n - a, c, n2 - c)
    return out


def ci_overlap_count():
    cmp_ = analysis()["compare_results"]
    main = analysis()["results"]
    pairs = [k for k in cmp_ if cmp_[k].get("beta_in_ci") and main.get(k, {}).get("beta_in_ci")]
    ov = sum(1 for k in pairs if not (main[k]["beta_in_ci"][1] < cmp_[k]["beta_in_ci"][0]
                                      or cmp_[k]["beta_in_ci"][1] < main[k]["beta_in_ci"][0]))
    return ov, len(pairs)


def gpu_hours_v2(run):
    gen = load = 0.0
    for m in run_models(run):
        for x in recs(run, m, rescored=False):
            gen += x.get("gen_seconds", 0) if "error" not in x else 0
        for f in glob.glob(os.path.join(DATA["runs"], run, m, "run_meta_shard*.json")):
            load += _json("runs", os.path.relpath(f, DATA["runs"])).get("load_seconds", 0)
            F("runs", os.path.relpath(f, DATA["runs"]))
    return (gen + load) / 3600


def label_changes(run):
    out = {}
    for m in run_models(run):
        rs = recs(run, m)
        out[m] = sum(1 for x in rs if "error" not in x and x.get("original_label") != x.get("label"))
    return out


def pilot_row(run, model):
    rs = [x for x in recs(run, model) if "error" not in x]
    lab = collections.Counter(x["label"] for x in rs)
    sec = st.median([x["gen_seconds"] for x in rs]) if rs else float("nan")
    return dict(done=len(rs), sec=sec, vram=max((x["peak_vram_gb"] or 0) for x in rs) if rs else float("nan"),
                lab=lab, conf=sum(x.get("second_tracker") == "confirmed" for x in rs), hours=sec * 304 / 3600)


def specs():
    from physweep.generators import MODEL_SPECS
    F("code", "physweep/generators.py")
    return MODEL_SPECS


def inj(kind, systems=("projectile", "bouncing_ball", "inclined_slide")):
    d = J("v2", "validity_injection.json")
    rows = [x for x in d["rows"] if x["kind"] == kind and x["system"] in systems]
    return rows


def inj_sum(kind, field, systems=("projectile", "bouncing_ball", "inclined_slide")):
    s = J("v2", "validity_injection.json")["summary"]
    return sum(s[f"{sy}/{kind}"][field] for sy in systems if f"{sy}/{kind}" in s)


def inj_median(kind, system, what):
    rows = [x for x in inj(kind, (system,)) if x["fit_ok"] and x["theta_hat"] is not None and np.isfinite(x["theta_hat"])]
    if what == "r2":
        return float(np.median([x["r2"] for x in rows]))
    return float(np.median([abs(x["theta_hat"] - x["theta"]) / abs(x["theta"]) for x in rows]))


def va(key):
    return J("v2", "validity_reanalysis.json")["summaries"][key]


def va_rows(**kw):
    return [x for x in J("v2", "validity_reanalysis.json")["rows"] if all(x.get(k) == v for k, v in kw.items())]


def pc(style, system=None):
    d = J("v2", "positive_control.json")["results"][style]
    return d["pooled"] if system is None else d["per_system"][system]


def dry(rel):
    from physweep.runio import load_latest
    d = os.path.join(DATA["v2"], "dryruns", rel)
    if not os.path.isdir(d):
        raise Missing(f"v2:dryruns/{rel}")
    for f in os.listdir(d):
        if f.endswith(".jsonl"):
            F("v2", f"dryruns/{rel}/{f}")
    return [x for x in load_latest(d).values() if "error" not in x]


def rel_errs(rows):
    return [abs(x["theta_hat"] - x["theta"]) / abs(x["theta"]) for x in rows if x.get("theta_hat") is not None]


def log_text(area, rel):
    with open(F(area, rel)) as f:
        return f.read()


def sdi_smoke():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        m3().smoke_test(verbose=True)
    F("code", "physweep/metrics_v3.py")
    vals = {}
    for line in buf.getvalue().splitlines():
        mm = re.search(r"SDI (?:~ 0 on a faithful|~ 1 on a seed-locked|stays low on pure noise|stays low on a single).*SDI=([0-9.]+)", line)
        if mm:
            key = ("faithful" if "faithful" in line else "seedlock" if "seed-locked" in line
                   else "noise" if "noise" in line else "default")
            vals[key] = float(mm.group(1))
    return vals


def cfg():
    import yaml
    with open(F("code", "physweep/configs/systems.yaml")) as f:
        return yaml.safe_load(f)


def grid(key):
    s = cfg()["systems"][key]
    return (sorted(float(x) for x in s["in_range"]), sorted(float(x) for x in s["out_of_range"]))


def render_bit_identical():
    """minimal style of REVISION's renderer == the original 4-ICLR/physweep/render.py, all five simulators."""
    new = module(os.path.join(CODE_DIR, "physweep", "render.py"), "render_new")
    old = module(F("rev", "../physweep/render.py"), "render_old")
    calls = [("simulate_projectile", dict(g=9.8)), ("simulate_damped_pendulum", dict(omega=3, zeta=0.05)),
             ("simulate_bouncing_ball", dict(e=0.8)), ("simulate_spring_mass", dict(k=40)),
             ("simulate_inclined_slide", dict(mu=0.2))]
    for name, kw in calls:
        for seed in range(3):
            a = getattr(new, name)(seed=seed, style="minimal", **kw)[0]
            b = getattr(old, name)(seed=seed, **kw)[0]
            if not np.array_equal(a, b):
                return False
    return True


# =============================================================================
# Registry
# =============================================================================
@dataclass
class Num:
    id: str
    doc: str
    anchor: str
    printed: object
    fn: object
    src: str
    how: str
    kind: str = "num"     # num | int | frac | claim | set | ge | le | lt | approx | qual | unarchived | external
    note: str = ""
    tol: float | None = None


REG: list[Num] = []
WORDS = dict(one=1, two=2, three=3, four=4, five=5, six=6, seven=7, eight=8, nine=9, ten=10, eighteen=18)


def add(doc, anchor, printed, fn, src, how, kind="num", note="", tol=None, id=None):
    i = id or f"{os.path.splitext(os.path.basename(doc))[0]}:{len([x for x in REG if x.doc == doc]) + 1:03d}"
    REG.append(Num(i, doc, anchor, printed, fn, src, how, kind, note, tol))


MAIN, APPX = "paper/main.tex", "paper/appendix.tex"
S = {i: f"results_v2/STEP{i}_REPORT.md" for i in range(1, 7)}
NAME = {"ltx": "LTX-Video", "cogvideox": "CogVideoX", "dynamicrafter": "DynamiCrafter"}
SYS = {"projectile": "projectile", "bouncing_ball": "bouncing ball", "inclined_slide": "inclined slide"}
E6 = lambda: J("v1", "e6_negative_control.json")["overall"]
E6SRC = "results_v1/e6_negative_control.json:overall (203 simulator clips, 6 axes, in+out)"
E6HOW = "experiments/e6_negative_control.py (stored field)"
V1HOW = "recomputed from rows: physweep_metrics.bootstrap_ci(faithfulness_slope) on gated (R2>=0.8) in-range clips"


def build_main():
    # ---- Figure 1 ---------------------------------------------------------
    add(MAIN, r"(simulator video) $\beta{=}1.0001$", "1.0001", lambda: E6()["slope_in"][0], E6SRC, E6HOW)
    add(MAIN, r"seed A: $11.4\pm0.03$", "11.4", lambda: abs(seed_stats("cogvideox", "projectile", 0, "in")[0]),
        "results_v1/e0_pilot_cogvideox.json rows, seed 0, in-range, gated", "|mean g_hat|")
    add(MAIN, r"seed A: $11.4\pm0.03$", "0.03", lambda: seed_stats("cogvideox", "projectile", 0, "in", ddof=1)[1],
        "same clips", "sample std (ddof=1)")
    add(MAIN, r"seed B: $7.1\pm0.2$", "7.1", lambda: abs(seed_stats("cogvideox", "projectile", 4, "in")[0]),
        "results_v1/e0_pilot_cogvideox.json rows, seed 4, in-range, gated", "|mean g_hat|")
    add(MAIN, r"seed B: $7.1\pm0.2$", "0.2", lambda: seed_stats("cogvideox", "projectile", 4, "in", ddof=1)[1],
        "same clips", "sample std (ddof=1) = 0.198")
    add(MAIN, r"{$80\%$ of clips trackable", "80", lambda: coverage("cogvideox", "projectile"),
        "results_v1/e0_pilot_cogvideox.json, in-range rows", "100 x gated / all in-range (20/25)")
    add(MAIN, r"in $[0.97,1.00]$};", "[0.97,1.00]",
        lambda: all(0.965 <= x["theta_hat"] < 1.005 for x in gated(v1rows("dynamicrafter", "bouncing_ball"), "in")
                    if x["theta_hat"] < 1.5),
        "results_v1/e4_bouncing_ball_dynamicrafter.json, gated in-range, excluding the e_hat=10.28 outlier",
        "all values round into [0.97, 1.00]", kind="claim")
    add(MAIN, r"{$25.0\%$ trackable, clip fit $R^2{=}1.000$", "25.0", lambda: coverage("dynamicrafter", "bouncing_ball"),
        "results_v1/e4_bouncing_ball_dynamicrafter.json, in-range rows", "100 x 5/20")
    add(MAIN, r"{$25.0\%$ trackable, clip fit $R^2{=}1.000$", "1.000",
        lambda: min(x["r2"] for x in gated(v1rows("dynamicrafter", "bouncing_ball"), "in") if x["theta_hat"] < 1.5),
        "same file, the 4 plotted clips (seed 4)", "min R2 of the plotted clips")
    add(MAIN, r"slope $1.0001$. Each point", "1.0001", lambda: E6()["slope_in"][0], E6SRC, E6HOW)
    add(MAIN, r"$g$ ($80\%$ trackable in-range)", "80", lambda: coverage("cogvideox", "projectile"),
        "results_v1/e0_pilot_cogvideox.json", "100 x 20/25")
    add(MAIN, r"quality that rules out a tracking artifact ($25.0\%$", "25.0",
        lambda: coverage("dynamicrafter", "bouncing_ball"), "results_v1/e4_bouncing_ball_dynamicrafter.json", "100 x 5/20")
    add(MAIN, r"one fitter-degenerate outlier, $\hat e>1$", "one",
        lambda: sum(x["theta_hat"] > 1.5 for x in gated(v1rows("dynamicrafter", "bouncing_ball"), "in")),
        "same file", "count of gated in-range e_hat > 1.5 (10.28, seed 1, e=0.9)", kind="int",
        note="Two other plotted values (1.002) are also slightly above 1; only the degenerate one is excluded.")
    # ---- Section 4 --------------------------------------------------------
    add(MAIN, r"(our rule uses $\tau=0.1$;", "0.1",
        lambda: __import__("inspect").signature(m3().select_mechanism).parameters["min_loo_r2"].default,
        "code/physweep/metrics_v3.py select_mechanism(min_loo_r2=0.1)", "code default",
        note="Table 3's labels were computed with v1 physweep_metrics.select_mechanism, which has no margin; "
             "all 8 pairs are 'neither' under both rules (see entry 'tau-relabel').")
    add(MAIN, r"(our rule uses $\tau=0.1$;", "all 8 neither under tau=0.1",
        lambda: all(m3().select_mechanism(np.array(e2(m, s)["theta_out"]), np.array(e2(m, s)["hat_out"]),
                                          e2(m, s)["theta_edge"]).label == "neither" for m, s in E2_PAIRS),
        "the 8 adjudicated pairs' out-of-range data", "metrics_v3.select_mechanism on each", kind="claim", id="tau-relabel")
    sm = lambda k: (lambda: sdi_smoke()[k])
    add(MAIN, r"returns $\mathrm{SDI}=0.999$ for a seed-locked", "0.999", sm("seedlock"),
        "code/physweep/metrics_v3.py smoke_test() synthetic data", "smoke_test(verbose=True), parsed")
    add(MAIN, r"returns $\mathrm{SDI}=0.999$ for a seed-locked", "0.000", sm("faithful"), "same", "faithful generator")
    add(MAIN, r"faithful, $0.000$ pure noise and $0.060$ single", "0.000", sm("noise"), "same", "pure noise")
    add(MAIN, r"faithful, $0.000$ pure noise and $0.060$ single", "0.060", sm("default"), "same", "single global default")
    # ---- Table 1 grids ----------------------------------------------------
    for anchor, key, printed in [
        (r"Projectile      & $g$", "projectile", ([5, 7, 9.8, 12, 15], [1.6, 3, 20, 25])),
        (r"Damped pendulum & $\omega$", "damped_pendulum_omega", ([2, 3, 4, 5], [8, 12])),
        (r"& $\zeta$  & envelope decay", "damped_pendulum_zeta", ([.02, .05, .1], [.3, .6, .9])),
        (r"Bouncing ball   & $e$", "bouncing_ball", ([.6, .7, .8, .9], [.2, .35, .97])),
        (r"Spring--mass    & $k$", "spring_mass", ([20, 40, 60, 80], [5, 10, 200, 400])),
        (r"Inclined slide  & $\mu$", "inclined_slide", ([.1, .2, .3, .4], [.01, .7, 1.0]))]:
        add(MAIN, anchor, (sorted(map(float, printed[0])), sorted(map(float, printed[1]))), (lambda k=key: grid(k)),
            f"code/physweep/configs/systems.yaml:{key}", "in-range / out-of-range lists", kind="set")
    # ---- Pipeline / compute -----------------------------------------------
    add(MAIN, r"inference-only, run on a shared NVIDIA A100-SXM4 (40\,GB)", "40", None,
        "CLAUDE.md §6 (Vast.ai A100-SXM4-40GB, Jul 2026 runs E0/E1/E4/E6/E7)", "hardware record", kind="unarchived",
        note="Only partly true: the Aug 2026 v1 runs (E2 gap-fill, E3/E5, E8, E10) ran on Panther, whose gpu-A100 "
             "nodes are 'NVIDIA A100 80GB PCIe' (from v2 run_meta). v1 jobs did not log the GPU.")
    add(MAIN, r"consumer GPU (CogVideoX's $25.3$\,GB peak", "25.3", None,
        "CLAUDE.md §5, E0 CogVideoX entry (2026-07-04, Vast.ai)", "torch.cuda.max_memory_allocated, not logged to a file",
        kind="unarchived")
    add(MAIN, r"budget), for an estimated $\sim\!57$ total GPU-hours", "57", v1_gpu_hours,
        "the 69 results_v1 files with elapsed_seconds + E0 pilot row counts + provenance/v1_file_times.json",
        "54.4 h logged + 2.6 h (95 untimed clips x per-model s/clip) + VLM window", kind="approx", tol=0.5)
    # ---- Table 2 (coverage) -----------------------------------------------
    for anchor, model, cells in [(r"LTX-Video      & \tkb{20}", "ltx", ["20", "35", "5"]),
                                 (r"CogVideoX      & \tkb{80}", "cogvideox", ["80", r"\tzero", "5"]),
                                 (r"DynamiCrafter  & \tkb{64}", "dynamicrafter", ["64", "80", "25"])]:
        for s, p in zip(SHORT, cells):
            add(MAIN, anchor, "0" if p == r"\tzero" else p, (lambda m=model, s=s: coverage(m, s)),
                f"results_v1/{v1file(model, s)}, in-range rows", "100 x gated(R2>=0.8) / in-range clips",
                note="printed as \\tzero (gray)" if p == r"\tzero" else "")
    add(MAIN, r"inclined slide), and \textbf{bold} marks the five cells", "five",
        lambda: sum(slope_estimable(m, s) for m in MODELS_V1 for s in SHORT),
        "the 9 coverage cells", "count of cells with >=5 gated in-range clips and no degenerate e_hat", kind="int")
    # ---- Results ------------------------------------------------------------
    add(MAIN, r"tracker and fitter, pooled across all six axes and both splits ($203$", "203",
        lambda: E6()["n_rows"], E6SRC, E6HOW, kind="int")
    for p, k, i in [("0.0031", "PRE_in", 0), ("0.0019", "PRE_in", 1), ("0.0045", "PRE_in", 2)]:
        add(MAIN, r"measurements), give $\PRE(S_\text{in}) = 0.0031$", p, (lambda k=k, i=i: E6()[k][i]), E6SRC, E6HOW)
    for p, k, i in [("1.0001", "slope_in", 0), ("1.00008", "slope_in", 1), ("1.00023", "slope_in", 2)]:
        add(MAIN, r"slope $\beta = 1.0001$ (CI $[1.00008, 1.00023]$)", p, (lambda k=k, i=i: E6()[k][i]), E6SRC, E6HOW)
    add(MAIN, r"slope $\beta = 1.0001$ (CI $[1.00008, 1.00023]$)", "0.986", lambda: E6()["mean_fit_r2"], E6SRC, E6HOW)
    add(MAIN, r"all; trackability never exceeds $80\%$ there", "80",
        lambda: max(coverage(m, s) for m in MODELS_V1 for s in SHORT), "the 9 coverage cells", "max")
    add(MAIN, r"all; trackability never exceeds $80\%$ there", "nine",
        lambda: sum(coverage(m, s) == 0 for m in MODELS_V1 for s in FRAME_BOUND), "9 frame-bound cells",
        "count of 0% cells", kind="int")
    add(MAIN, r"architectural $0\%$ (Section~\ref{sec:limitations}), so ten of all", "ten",
        lambda: sum(coverage(m, s) == 0 for m in MODELS_V1 for s in SYSTEMS_V1), "all 18 model-axis pairs",
        "count of 0% in-range trackability", kind="int")
    add(MAIN, r"Only five cells support a slope estimate", "five",
        lambda: sum(slope_estimable(m, s) for m in MODELS_V1 for s in SHORT), "the 9 coverage cells",
        "slope-estimable rule", kind="int")
    slope_lines = {("ltx", "projectile"): (r"$-0.015$ [$-0.090$, $0.039$] and inclined slide", ["-0.015", "-0.090", "0.039"]),
                   ("ltx", "inclined_slide"): (None, ["-0.464", "-1.751", "1.097"]),
                   ("cogvideox", "projectile"): (r"CogVideoX projectile $0.070$ [$-0.168$, $0.305$];", ["0.070", "-0.168", "0.305"]),
                   ("dynamicrafter", "projectile"): (r"DynamiCrafter projectile $-0.025$ [$-0.466$, $0.480$]", ["-0.025", "-0.466", "0.480"]),
                   ("dynamicrafter", "inclined_slide"): (r"$0.521$ [$-6.185$, $6.850$]$^{\dagger}$", ["0.521", "-6.185", "6.850"])}
    for (m, s), (anchor, vals) in slope_lines.items():
        for i, p in enumerate(vals):
            a = anchor
            if (m, s) == ("ltx", "inclined_slide"):
                a = r"$-0.015$ [$-0.090$, $0.039$] and inclined slide" if i < 2 else r"$1.097$]$^{\dagger}$; CogVideoX"
            add(MAIN, a, p, (lambda m=m, s=s, i=i: slope_ci(m, s)[i]), f"results_v1/{v1file(m, s)}, gated in-range",
                V1HOW, note="also stored in e1_faithfulness.json / summary.slope_*")
    add(MAIN, r"contain $\beta=1$, showing lack of power", "the two dagger CIs contain 1",
        lambda: all(slope_ci(m, s)[1] <= 1 <= slope_ci(m, s)[2] for m, s in [("ltx", "inclined_slide"),
                                                                              ("dynamicrafter", "inclined_slide")]),
        "the two inclined-slide cells", "CI contains 1", kind="claim")
    add(MAIN, r"count them as evidence for the null; the remaining three are inconsistent", "three CIs exclude 1",
        lambda: all(not (slope_ci(m, s)[1] <= 1 <= slope_ci(m, s)[2]) for m, s in SLOPE_CELLS if s == "projectile"),
        "the three projectile cells", "CI excludes 1", kind="claim")
    for m, p in [("ltx", "0.853"), ("cogvideox", "2.016"), ("dynamicrafter", "0.781")]:
        add(MAIN, r"the projectile cells ($\PRE(S_\text{in})=0.853$, $2.016$, $0.781$ for", p,
            (lambda m=m: pre_in(m, "projectile")), f"results_v1/{PF[m]}, gated in-range",
            "physweep_metrics.pre (delta=0.05) recomputed from rows")
    add(MAIN, r"against $0.0031$ for the positive", "0.0031", lambda: E6()["PRE_in"][0], E6SRC, E6HOW)
    for m, k, p in [("ltx", "LTX-Video", "-0.268"), ("cogvideox", "CogVideoX-5B-I2V", "0.046")]:
        add(MAIN, r"projectile sweep is $-0.268$ (LTX-Video) and $0.046$ (CogVideoX)", p,
            (lambda k=k: J("v1", "e1_faithfulness.json")[k]["spearman_rho_full_grid"]),
            "results_v1/e1_faithfulness.json:<model>.spearman_rho_full_grid", "experiments/e1_faithfulness.py (stored)",
            note="Computed when e0_pilot.json had 40 rows; it now has 55 (out-of-range gap-fill), see 'rho-now'.")
    add(MAIN, r"projectile sweep is $-0.268$ (LTX-Video) and $0.046$ (CogVideoX)", "-0.268",
        lambda: pm().spearman_rho(arr(gated(v1rows("ltx", "projectile")), "theta"), arr(gated(v1rows("ltx", "projectile")), "theta_hat")),
        "results_v1/e0_pilot.json, all gated rows NOW (55-row file)", "physweep_metrics.spearman_rho on gated in+out",
        id="rho-now", kind="qual",
        note="Drift indicator: the file gained 15 out-of-range rows after E1 was computed, so today's value differs.")
    add(MAIN, r"on CogVideoX one seed gives $\hat g \approx -11.4 \pm 0.03$", "-11.4",
        lambda: seed_stats("cogvideox", "projectile", 0, "in")[0], "e0_pilot_cogvideox.json seed 0 in-range gated", "mean")
    add(MAIN, r"on CogVideoX one seed gives $\hat g \approx -11.4 \pm 0.03$", "0.03",
        lambda: seed_stats("cogvideox", "projectile", 0, "in", ddof=1)[1], "same", "sample std")
    add(MAIN, r"and another gives $-7.1\pm0.2$", "-7.1", lambda: seed_stats("cogvideox", "projectile", 4, "in")[0],
        "seed 4", "mean")
    add(MAIN, r"and another gives $-7.1\pm0.2$", "0.2", lambda: seed_stats("cogvideox", "projectile", 4, "in", ddof=1)[1],
        "seed 4", "sample std")
    add(MAIN, r"(\autoref{fig:teaser}), reproducing out-of-range on the same seeds", "reproducing out-of-range",
        lambda: "; ".join(f"seed {z}: in {seed_stats('cogvideox', 'projectile', z, 'in')[0]:.2f}, out "
                          + ", ".join(f"{x['theta_hat']:.2f}" for x in seed_stats('cogvideox', 'projectile', z, 'out')[2])
                          for z in (0, 4)),
        "e0_pilot_cogvideox.json seeds 0 and 4, gated", "per-seed values", kind="qual")
    disp = lambda: [seed_stats("cogvideox", "projectile", 0, "in", ddof=1)[1], seed_stats("cogvideox", "projectile", 4, "in", ddof=1)[1],
                    seed_stats("dynamicrafter", "inclined_slide", 0, "in")[1],
                    seed_stats("dynamicrafter", "inclined_slide", 0, "out", gate=False)[1],
                    seed_stats("dynamicrafter", "inclined_slide", 3, "in")[1]]
    add(MAIN, r"not tight. They are not (within-seed dispersion $0.03$--$0.13$,", "0.03", lambda: min(disp()),
        "the clusters the paper names: CogVideoX proj seeds 0, 4; DynamiCrafter slide seed 0 (in, out) and 3",
        "min within-seed std")
    add(MAIN, r"not tight. They are not (within-seed dispersion $0.03$--$0.13$,", "0.13", lambda: max(disp()),
        "same clusters", "max within-seed std",
        note="The paper's own seed B (CogVideoX seed 4) has sample std 0.198, reported as 7.1 +- 0.2 two paragraphs up.")
    add(MAIN, r"individual-clip fit $R^2$ up to $1.000$", "1.000",
        lambda: max(x["r2"] for m, s in [("cogvideox", "projectile"), ("dynamicrafter", "inclined_slide"),
                                         ("dynamicrafter", "bouncing_ball")] for x in gated(v1rows(m, s))),
        "gated clips of the seed-locked pairs", "max R2")
    add(MAIN, r"failure generalizes, with four of its five remaining axes below $6\%$", "four",
        lambda: sum(coverage("ltx", s) < 6 for s in SYSTEMS_V1 if s != "projectile"), "LTX-Video, 5 non-projectile axes",
        "count with in-range trackability < 6%", kind="int")
    add(MAIN, r"restitution in $[0.97,1.00]$ regardless of the request", "[0.97,1.00]",
        lambda: all(0.965 <= x["theta_hat"] < 1.005 for x in gated(v1rows("cogvideox", "bouncing_ball"))),
        "results_v1/e4_bouncing_ball_cogvideox.json, all gated clips (1 in, 9 out)", "all in range", kind="claim")
    add(MAIN, r"($\hat e = 0.99$--$1.00$ across the full grid, individual-clip", "0.99",
        lambda: min(x["theta_hat"] for x in gated(v1rows("dynamicrafter", "bouncing_ball"), "in") if x["theta_hat"] < 1.5),
        "e4_bouncing_ball_dynamicrafter.json gated in-range (seed 4, outlier excluded)", "min")
    add(MAIN, r"($\hat e = 0.99$--$1.00$ across the full grid, individual-clip", "1.00",
        lambda: max(x["theta_hat"] for x in gated(v1rows("dynamicrafter", "bouncing_ball"), "in") if x["theta_hat"] < 1.5),
        "same", "max")
    add(MAIN, r"$R^2=1.000$): two architectures landing", "1.000",
        lambda: min(x["r2"] for x in gated(v1rows("dynamicrafter", "bouncing_ball"), "in") if x["theta_hat"] < 1.5),
        "same 4 clips", "min R2")
    add(MAIN, r"behavior. Three of DynamiCrafter's axes", "Three",
        lambda: sum(coverage("dynamicrafter", s) == 0 for s in FRAME_BOUND), "DynamiCrafter frame-bound axes", "count 0%",
        kind="int")
    add(MAIN, r"are separately bounded by its fixed $16$-frame output", "16",
        lambda: J("v1", "e0_pilot_dynamicrafter.json")["n_frames"], "results_v1/e0_pilot_dynamicrafter.json:n_frames",
        "stored config", kind="int")
    add(MAIN, r"$\hat\mu\approx1.80$ across the whole grid", "1.80",
        lambda: float(np.mean([x["theta_hat"] for x in v1rows("dynamicrafter", "inclined_slide") if x["seed"] == 3])),
        "e4_inclined_slide_dynamicrafter.json, seed 3, all 7 grid values", "mean over the whole grid", kind="approx", tol=0.05,
        note="In-range mean is 1.80; out-of-range values are 1.52, 1.60, 1.68, so 'across the whole grid' overstates it.")
    add(MAIN, r"clusters, $\hat\mu\approx4.7$ ($\mathrm{std}=0.04$) in-range", "4.7",
        lambda: seed_stats("dynamicrafter", "inclined_slide", 0, "in")[0], "seed 0 in-range gated", "mean")
    add(MAIN, r"clusters, $\hat\mu\approx4.7$ ($\mathrm{std}=0.04$) in-range", "0.04",
        lambda: seed_stats("dynamicrafter", "inclined_slide", 0, "in")[1], "same", "std")
    add(MAIN, r"clusters, $\hat\mu\approx4.7$ ($\mathrm{std}=0.04$) in-range", "7.6",
        lambda: seed_stats("dynamicrafter", "inclined_slide", 0, "out", gate=False)[0], "seed 0 out-of-range, UNGATED",
        "mean", note="These 3 clips have R2 0.786-0.797, i.e. below the paper's own 0.8 gate.")
    add(MAIN, r"($\mathrm{std}=0.13$) out-of-range", "0.13",
        lambda: seed_stats("dynamicrafter", "inclined_slide", 0, "out", gate=False)[1], "same", "std")
    add(MAIN, r"points, yielding \textbf{8 of 18} pairs", "8",
        lambda: sum(e2(m, s).get("status") == "adjudicated" for m in MODELS_V1 for s in SYSTEMS_V1),
        "all 18 pairs", "experiments/e2_extrapolation.analyze_pair recomputed", kind="int")
    add(MAIN, r"$\mathrm{SDI}$ says so. The paired-bootstrap test is computable for six", "six",
        lambda: len(bootstrap_pairs()), "adjudicated pairs with >=2 gated in-range clips", "count", kind="int")
    add(MAIN, r"pairs and exactly two intervals exclude zero", "two",
        lambda: sum(not (b[1] <= 0 <= b[2]) for _, b in bootstrap_pairs()), "the six bootstrap CIs", "count", kind="int")
    add(MAIN, r"(adjusted $p=0.033$; every", "0.033", lambda: holm()[("cogvideox", "projectile")],
        "the six one-sided paired-bootstrap p-values", "metrics_v3.holm_adjust")
    add(MAIN, r"other pair's adjusted $p\ge0.53$", "0.53",
        lambda: min(v for k, v in holm().items() if k != ("cogvideox", "projectile")), "same", "min of the other five",
        kind="ge")
    add(MAIN, r"other pair's adjusted $p\ge0.53$). Ten pairs", "Ten",
        lambda: sum(e2(m, s).get("status") != "adjudicated" for m in MODELS_V1 for s in SYSTEMS_V1), "all 18 pairs",
        "count", kind="int")
    add(MAIN, r"other pair's adjusted $p\ge0.53$). Ten pairs stay unadjudicated: three hit", "three",
        lambda: sum(e2("dynamicrafter", s).get("status") != "adjudicated" for s in FRAME_BOUND), "DynamiCrafter frame-bound",
        "count", kind="int")
    add(MAIN, r"the other seven a near-zero gated yield", "seven",
        lambda: sum(e2(m, s).get("status") != "adjudicated" for m in ["ltx", "cogvideox"] for s in SYSTEMS_V1),
        "LTX-Video and CogVideoX unadjudicated", "count", kind="int")
    # ---- Table 3 ------------------------------------------------------------
    t3 = {("ltx", "projectile"): (r"LTX-Video     & projectile     & $7$", ["7", "0.985", "-0.33", "2.73", "1.000", "-4.0", "0.995"]),
          ("ltx", "bouncing_ball"): (r"LTX-Video     & bouncing ball  & $4$", ["4", None, None, None, "1.000", "-9.8", "0.985"]),
          ("ltx", "inclined_slide"): (r"LTX-Video     & inclined slide & $4$", ["4", "0.264", "-0.51", "1.00", "0.514", "-11.3", "0.511"]),
          ("cogvideox", "projectile"): (r"CogVideoX     & projectile     & $12$", ["12", "1.068", "0.27", "1.89", "0.974", "-47.9", "0.919"]),
          ("cogvideox", "bouncing_ball"): (r"CogVideoX     & bouncing ball  & $9$", ["9", None, None, None, "0.999", "-100.4", "0.997"]),
          ("dynamicrafter", "projectile"): (r"DynamiCrafter & projectile     & $17$", ["17", "0.050", "-0.22", "0.34", "0.988", "-22.2", "0.343"]),
          ("dynamicrafter", "bouncing_ball"): (r"DynamiCrafter & bouncing ball  & $6$", ["6", "-0.761", "-2.74", "0.34", "0.223", "-0.6", "0.997"]),
          ("dynamicrafter", "inclined_slide"): (r"DynamiCrafter & inclined slide & $20$", ["20", "-0.939", "-1.57", "-0.35", "1.000", "-16.0", "0.176"])}
    cols = [("n_out", lambda m, s: e2(m, s)["n_gated_out"], "int"),
            ("EG", lambda m, s: e2(m, s)["extrapolation_gap"], "num"),
            ("EG CI lo", lambda m, s: e2(m, s)["paired_bootstrap_PRE_out_minus_in"][1], "num"),
            ("EG CI hi", lambda m, s: e2(m, s)["paired_bootstrap_PRE_out_minus_in"][2], "num"),
            ("PRI", lambda m, s: e2(m, s)["select_mechanism_theta0_free"]["PRI"], "num"),
            ("dAIC", lambda m, s: e2(m, s)["select_mechanism_theta0_free"]["dAIC"], "num"),
            ("SDI", lambda m, s: sdi(m, s), "num")]
    for (m, s), (anchor, vals) in t3.items():
        for (cname, fn, kind), p in zip(cols, vals):
            if p is None:
                continue
            add(MAIN, anchor, p, (lambda fn=fn, m=m, s=s: fn(m, s)),
                f"results_v1/{v1file(m, s)}, gated (R2>=0.8)",
                "metrics_v3.seed_determination_index on gated out-of-range clips (recreated Tier-0)" if cname == "SDI"
                else f"experiments/e2_extrapolation.analyze_pair recomputed from rows ({cname}); stored in e2_extrapolation.json",
                kind=kind)
        add(MAIN, anchor, "neither", (lambda m=m, s=s: e2(m, s)["select_mechanism_theta0_free"]["selected"] == "neither"),
            f"results_v1/{v1file(m, s)}", "v1 select_mechanism label", kind="claim")
    add(MAIN, r"$^{*}$Excludes zero in the hypothesized direction ($p=0.0055$)", "0.0055",
        lambda: e2("cogvideox", "projectile")["paired_bootstrap_PRE_out_minus_in"][3], "CogVideoX projectile",
        "one-sided paired-bootstrap p (2000 draws)")
    # ---- Plausibility rater ----------------------------------------------
    add(MAIN, r"rated all $630$ saved generality clips", "630", lambda: sum(len(e3_rows(m)) for m in MODELS_V1),
        "results_v1/e3_plausibility_default_*_*.json (18 files)", "rows with a plausibility score", kind="int")
    add(MAIN, r"Pooled mean $P$ is low for every model (LTX-Video $2.20$,", "2.20",
        lambda: float(np.mean(arr(e3_rows("ltx"), "plausibility"))), "6 LTX-Video files, 210 rows", "mean")
    add(MAIN, r"DynamiCrafter $1.76$, CogVideoX $1.26$), which looks", "1.76",
        lambda: float(np.mean(arr(e3_rows("dynamicrafter"), "plausibility"))), "210 rows", "mean")
    add(MAIN, r"DynamiCrafter $1.76$, CogVideoX $1.26$), which looks", "1.26",
        lambda: float(np.mean(arr(e3_rows("cogvideox"), "plausibility"))), "210 rows", "mean")
    add(MAIN, r"it never assigned a $4$", "no score of 4",
        lambda: all(x["plausibility"] != 4 for m in MODELS_V1 for x in e3_rows(m)), "all 630 rows", "no 4", kind="claim")
    add(MAIN, r"are bimodal ($1$ or $5$, never $2$--$4$)", "CogVideoX scores only 1 or 5",
        lambda: set(arr(e3_rows("cogvideox"), "plausibility")) <= {1.0, 5.0}, "the 210 CogVideoX rows",
        "set of scores", kind="claim",
        note="Actual counts: 1 x191, 3 x11, 5 x8. Eleven CogVideoX clips scored 3.")
    for m, p, anchor in [("ltx", "0.075", r"the correlation between tracker fit $R^2$ and $P$ is $0.075$,"),
                         ("dynamicrafter", "0.019", r"$0.019$ and $-0.164$ respectively"),
                         ("cogvideox", "-0.164", r"$0.019$ and $-0.164$ respectively")]:
        add(MAIN, anchor, p, (lambda m=m: e3_corr(m)), f"the 210 {NAME[m]} rows",
            "np.corrcoef(r2, plausibility)", note="'respectively' maps the three values to LTX-Video, DynamiCrafter, "
            "CogVideoX; the data give LTX-Video 0.019, DynamiCrafter -0.164, CogVideoX 0.075.")
    add(MAIN, r"collapses into texture noise ($R^2=0.48$)", "0.48",
        lambda: e3_clip("cogvideox_projectile_seed4_34.mp4")["r2"], "cogvideox_projectile_seed4_34.mp4 (theta=3)", "r2")
    add(MAIN, r"scored $5/5$ while a cleanly tracked LTX-Video fall ($R^2=0.99$)", "5",
        lambda: e3_clip("cogvideox_projectile_seed4_34.mp4")["plausibility"], "same clip", "plausibility", kind="int")
    add(MAIN, r"scored $5/5$ while a cleanly tracked LTX-Video fall ($R^2=0.99$)", "0.99",
        lambda: e3_clip("ltx_projectile_seed3_3.mp4")["r2"], "ltx_projectile_seed3_3.mp4 (theta=5)", "r2")
    add(MAIN, r"$1/5$ (truncation, parsing failure", "1",
        lambda: e3_clip("ltx_projectile_seed3_3.mp4")["plausibility"], "same clip", "plausibility", kind="int")
    # ---- Nuisance parameters -----------------------------------------------
    add(MAIN, r"projectile $r=0.984$, inclined slide $r=0.997$)", "0.984",
        lambda: J("v1", "e5a_cotracker_comparison.json")["projectile_ltx"]["summary"]["corr_blob_cotracker_theta_hat"],
        "results_v1/e5a_cotracker_comparison.json:projectile_ltx", "experiments/e5a_cotracker_analysis.py (stored)")
    add(MAIN, r"projectile $r=0.984$, inclined slide $r=0.997$)", "0.997",
        lambda: J("v1", "e5a_cotracker_comparison.json")["inclined_slide_ltx"]["summary"]["corr_blob_cotracker_theta_hat"],
        "…:inclined_slide_ltx", "stored")
    fam = lambda pre: (lambda: sum(k.startswith(pre) for k in J("v1", "e5bdef_ablation_comparison.json")["ltx"]))
    add(MAIN, r"Across five disk-size and frame-rate rescalings, four guidance values, two", "five", fam("scale"),
        "results_v1/e5bdef_ablation_comparison.json:ltx", "count of scale variants", kind="int")
    add(MAIN, r"Across five disk-size and frame-rate rescalings, four guidance values, two", "four", fam("cfg"),
        "same", "count of cfg variants", kind="int")
    add(MAIN, r"Across five disk-size and frame-rate rescalings, four guidance values, two", "two", fam("prompt"),
        "same", "count of prompt variants", kind="int")
    add(MAIN, r"prompt templates and two conditioning resolutions", "two", fam("res"), "same", "count of res variants",
        kind="int")
    add(MAIN, r"(LTX-Video $-0.26$ to $+1.38$ over 13", "-0.26", lambda: min(e5b_slopes("ltx")), "LTX-Video, 13 variants",
        "min slope_in (experiments/e5bdef_ablation_analysis.py, stored)")
    add(MAIN, r"(LTX-Video $-0.26$ to $+1.38$ over 13", "1.38", lambda: max(e5b_slopes("ltx")), "same", "max")
    add(MAIN, r"(LTX-Video $-0.26$ to $+1.38$ over 13", "13", lambda: len(e5b_slopes("ltx")), "same", "count", kind="int")
    add(MAIN, r"variants; DynamiCrafter $-0.25$ to $+0.12$ over 7", "-0.25", lambda: min(e5b_slopes("dynamicrafter")),
        "DynamiCrafter, 7 variants", "min")
    add(MAIN, r"variants; DynamiCrafter $-0.25$ to $+0.12$ over 7", "0.12", lambda: max(e5b_slopes("dynamicrafter")),
        "same", "max")
    add(MAIN, r"variants; DynamiCrafter $-0.25$ to $+0.12$ over 7", "7", lambda: len(e5b_slopes("dynamicrafter")),
        "same", "count", kind="int")
    e5c = lambda: J("v1", "e5c_fit_gate_sensitivity.json")
    add(MAIN, r"null does not flip at any threshold from $0.5$ to $0.95$", "no CI excludes 0",
        lambda: all(v["slope_in"][1] <= 0 <= v["slope_in"][2] for m in e5c() for s in e5c()[m]
                    for v in e5c()[m][s].values() if isinstance(v.get("slope_in"), list) and None not in v["slope_in"]),
        "results_v1/e5c_fit_gate_sensitivity.json", "every slope CI at every gate includes 0", kind="claim")
    add(MAIN, r"null does not flip at any threshold from $0.5$ to $0.95$", "0.5",
        lambda: min(float(g) for m in e5c() for s in e5c()[m] for g in e5c()[m][s]), "same", "min gate")
    add(MAIN, r"null does not flip at any threshold from $0.5$ to $0.95$", "0.95",
        lambda: max(float(g) for m in e5c() for s in e5c()[m] for g in e5c()[m][s]), "same", "max gate")
    # ---- Frame channel (v1 E8) ----------------------------------------------
    e8 = lambda s: J("v1", f"e8_conditioning_channel_{s}_dynamicrafter.json")["summary"]
    for i, p in enumerate(["0.017", "-0.008", "0.047"]):
        add(MAIN, r"$\hat g\approx0$ (slope $0.017$, CI $[-0.008,0.047]$)", p, (lambda i=i: e8("projectile")["slope_in_ci"][i]),
            "results_v1/e8_conditioning_channel_projectile_dynamicrafter.json:summary.slope_in_ci",
            "experiments/e8_conditioning_channel.py (stored)")
    add(MAIN, r"Inclined slide is starker still, $\hat\mu$ near $1.7$--$1.8$", "1.7--1.8",
        lambda: "gated in-range mu_hat: " + ", ".join(f"{x['theta_hat']:.2f}" for x in sorted(
            [x for x in J("v1", "e8_conditioning_channel_inclined_slide_dynamicrafter.json")["rows"]
             if x["split"] == "in" and x["r2"] is not None and x["r2"] >= 0.8 and x["theta_hat"] is not None],
            key=lambda x: x["theta_hat"])),
        "results_v1/e8_conditioning_channel_inclined_slide_dynamicrafter.json rows", "values", kind="qual",
        note="14 of 16 lie in 1.69-1.80; two are 2.11 and 2.20.")
    c2 = lambda s: J("v1", f"e3e5_default_{s}_dynamicrafter.json")["summary"]["dropped_rate"]
    for p, fn, src in [("10", lambda: 100 * e8("projectile")["dropped_rate"], "e8 projectile (frame channel)"),
                       ("30", lambda: 100 * c2("projectile"), "e3e5_default_projectile_dynamicrafter (text channel)"),
                       ("23", lambda: 100 * e8("inclined_slide")["dropped_rate"], "e8 inclined slide")]:
        add(MAIN, r"frame channel on all three axes ($10\%$ vs.\ $30\%$ projectile, $23\%$", p, fn,
            f"results_v1/{src}:summary.dropped_rate", "pooled in+out, 1 - gated/all")
    for p, fn, src in [("29", lambda: 100 * c2("inclined_slide"), "e3e5_default_inclined_slide_dynamicrafter"),
                       ("63", lambda: 100 * e8("bouncing_ball")["dropped_rate"], "e8 bouncing ball"),
                       ("86", lambda: 100 * c2("bouncing_ball"), "e3e5_default_bouncing_ball_dynamicrafter")]:
        add(MAIN, r"vs.\ $29\%$ inclined slide, $63\%$ vs.\ $86\%$ bouncing ball)", p, fn,
            f"results_v1/{src}:summary.dropped_rate", "pooled")
    # ---- Limitations --------------------------------------------------------
    add(MAIN, r"\textbf{Trackability bounds coverage.} Trackability never exceeds $80\%$", "80",
        lambda: max(coverage(m, s) for m in MODELS_V1 for s in SHORT), "9 coverage cells", "max")
    add(MAIN, r"and is $0\%$ on ten of eighteen pairs", "ten",
        lambda: sum(coverage(m, s) == 0 for m in MODELS_V1 for s in SYSTEMS_V1), "18 pairs", "count", kind="int")
    add(MAIN, r"motion. It also looks closable, since Wan reports an $8.19$\,GB", "8.19", None, "Wan 2.1 paper \\citep{wan2025}",
        "quoted", kind="external")
    add(MAIN, r"text-to-video variant at $1.3$B", "1.3", None, "Wan paper", "quoted", kind="external")
    add(MAIN, r"model-axis pair and refitting $\beta$, $10{,}000$ times on the five", "10,000", lambda: 10000,
        "perm_p(n=10000)", "parameter of the recreated test", kind="int")
    add(MAIN, r"null distribution (two-sided permutation $p$ from $0.56$ to $0.91$)", "0.56",
        lambda: min(perm_p(m, s) for m, s in SLOPE_CELLS), "the five slope cells, gated in-range",
        "label permutation, 10,000 draws, rng seed 0 (recreated)", kind="approx", tol=0.01)
    add(MAIN, r"null distribution (two-sided permutation $p$ from $0.56$ to $0.91$)", "0.91",
        lambda: max(perm_p(m, s) for m, s in SLOPE_CELLS), "same", "max", kind="approx", tol=0.01)
    add(MAIN, r"TOST against a pre-specified smallest effect $\epsilon=0.2$ at", "0.2", lambda: 0.2, "tost_p(eps=0.2)",
        "parameter")
    add(MAIN, r"LTX-Video/projectile is formally equivalent to zero ($p_\text{TOST}<0.001$)", "0.001",
        lambda: tost_p("ltx", "projectile"), "LTX-Video projectile slope CI", "TOST, SE from the bootstrap CI (recreated)",
        kind="lt")
    add(MAIN, r"contain $\beta=1$, do not clear the bar ($p_\text{TOST}$ from $0.14$ to", "0.14",
        lambda: min(tost_p(m, s) for m, s in SLOPE_CELLS[1:]), "the other four cells", "min")
    add(MAIN, r"$0.64$), consistent with underpowered", "0.64",
        lambda: max(tost_p(m, s) for m, s in SLOPE_CELLS[1:]), "the other four cells", "max")
    add(MAIN, r"model identity ($24$, $49$ trimmed to $24$, $16$ frames)", "24/49/16", None,
        "experiments/e0_pilot.py, e0_pilot_cogvideox.py, e0_pilot_dynamicrafter.py constants", "code constants",
        kind="unarchived", note="Not stored in the v1 result files except DynamiCrafter's n_frames=16.")
    add(MAIN, r"CogVideoX for the pipeline reasons above. Adjudication covers 8 of 18 pairs", "8",
        lambda: sum(e2(m, s).get("status") == "adjudicated" for m in MODELS_V1 for s in SYSTEMS_V1), "18 pairs", "count",
        kind="int")
    e10 = lambda: [x for m in ["ltx", "cogvideox"] for x in J("v1", f"e10_multi_parameter_{m}.json")["rows"]]
    add(MAIN, r"returned $0\%$ trackability (best $R^2=0.14$)", "0",
        lambda: 100 * sum((x["r2"] or 0) >= 0.8 for x in e10()) / len(e10()),
        "results_v1/e10_multi_parameter_{ltx,cogvideox}.json, 90 rows", "100 x gated / all")
    add(MAIN, r"returned $0\%$ trackability (best $R^2=0.14$)", "0.14", lambda: max((x["r2"] or 0) for x in e10()),
        "same", "max R2")


def build_appendix():
    for anchor, key, printed in [(r"Damped pendulum & $\omega$   & $\{2,3,4,5\}$ rad/s", "damped_pendulum_omega",
                                  ([2, 3, 4, 5], [0.5, 1, 8, 12]))]:
        add(APPX, anchor, (sorted(map(float, printed[0])), sorted(map(float, printed[1]))), (lambda k=key: grid(k)),
            f"code/physweep/configs/systems.yaml:{key}", "grid", kind="set",
            note="F7: fixed in main.tex Table 1 (Step 2) but not here; systems.yaml has {8, 12}.")
    name = {"ltx": "LTX-Video", "cogvideox": "CogVideoX", "dynamicrafter": "DynamiCrafter"}
    axis = {"projectile": "projectile", "pendulum_omega": r"pendulum $\omega$", "pendulum_zeta": r"pendulum $\zeta$",
            "bouncing_ball": "bouncing ball", "spring_mass": "spring-mass", "inclined_slide": "inclined slide"}
    table = {
        ("ltx", "projectile"): ("5/10", 55, 12), ("ltx", "pendulum_omega"): ("5/55", 130, 1),
        ("ltx", "pendulum_zeta"): ("5/15", 60, 0), ("ltx", "bouncing_ball"): ("5/15", 65, 5),
        ("ltx", "spring_mass"): ("5/15", 80, 0), ("ltx", "inclined_slide"): ("5/5", 35, 11),
        ("cogvideox", "projectile"): ("5/5", 40, 32), ("cogvideox", "pendulum_omega"): ("5/13", 46, 0),
        ("cogvideox", "pendulum_zeta"): ("5/13", 54, 0), ("cogvideox", "bouncing_ball"): ("5/33", 119, 10),
        ("cogvideox", "spring_mass"): ("5/13", 72, 0), ("cogvideox", "inclined_slide"): ("5/13", 59, 0),
        ("dynamicrafter", "projectile"): ("5/10", 55, 33), ("dynamicrafter", "pendulum_omega"): ("5/5", 30, 0),
        ("dynamicrafter", "pendulum_zeta"): ("5/5", 30, 1), ("dynamicrafter", "bouncing_ball"): ("5/10", 50, 11),
        ("dynamicrafter", "spring_mass"): ("5/5", 40, 0), ("dynamicrafter", "inclined_slide"): ("5/10", 50, 36)}

    def spt(m, s):
        rows = v1rows(m, s)
        c = {sp: max(collections.Counter(x["theta"] for x in rows if x["split"] == sp).values()) for sp in ("in", "out")}
        return f"{c['in']}/{c['out']}"

    for (m, s), (seeds, gen, gat) in table.items():
        anchor = f"{name[m]} & {axis[s]} & ${seeds}$"
        src = f"results_v1/{v1file(m, s)}:rows"
        add(APPX, anchor, seeds, (lambda m=m, s=s: spt(m, s)), src, "max rows per grid value, per split", kind="str")
        add(APPX, anchor, str(gen), (lambda m=m, s=s: len(v1rows(m, s))), src, "len(rows)", kind="int")
        add(APPX, anchor, str(gat), (lambda m=m, s=s: len(gated(v1rows(m, s)))), src, "gated rows, in+out", kind="int")
    add(APPX, r"i.e.\ $110$ out-of-range attempts", "110",
        lambda: sum(x["split"] == "out" for x in v1rows("ltx", "pendulum_omega")), "results_v1/e4_pendulum_omega_ltx.json",
        "out-of-range rows", kind="int")
    add(APPX, r"Plausibility prompt (verbatim", "prompt text",
        lambda: J("v1", "e3_plausibility_default_projectile_ltx.json")["prompt"].startswith(
            "You are watching a short video clip of a physics simulation"), "results_v1/e3_plausibility_*.json:prompt",
        "stored prompt starts with the quoted text", kind="claim")
    add(APPX, r"identical for all $630$ ratings", "630", lambda: sum(len(e3_rows(m)) for m in MODELS_V1),
        "18 e3_plausibility files", "count", kind="int")
    add(APPX, r"identical for all $630$ ratings", "one prompt",
        lambda: len({J("v1", f"e3_plausibility_default_{s}_{m}.json")["prompt"] for m in MODELS_V1 for s in SYSTEMS_V1}) == 1,
        "the 18 files' prompt fields", "a single distinct prompt", kind="claim")
    add(APPX, r"\paragraph{Classifier-free guidance values swept.} $1.0$, $1.5$, $4.5$,", [1.0, 1.5, 4.5, 9.0],
        lambda: sorted(float(k[3:]) for k in J("v1", "e5bdef_ablation_comparison.json")["ltx"] if k.startswith("cfg")),
        "results_v1/e5bdef_ablation_comparison.json:ltx", "cfg variants", kind="set")
    add(APPX, r"or fine-tuning at any point). Peak VRAM at load: LTX-Video $14.25$\,GB", "14.25", None,
        "CLAUDE.md §6 (2026-07-04 Vast.ai session)", "not logged to a file", kind="unarchived")
    add(APPX, r"CogVideoX-5B-I2V $25.3$\,GB with VAE tiling", "25.3", None, "CLAUDE.md §5", "not logged", kind="unarchived")
    add(APPX, r"All generation and analysis ran on NVIDIA A100-SXM4", "40", None, "CLAUDE.md §6", "hardware record",
        kind="unarchived", note="Panther A100 nodes are 'NVIDIA A100 80GB PCIe' (v2 run_meta); see main.tex entry.")
    for m, anchor, unit in [("ltx", r"LTX-Video $\sim\!2$--$6$\,s;", 1), ("cogvideox", r"CogVideoX $\sim\!2.3$--$5.9$\,min", 60),
                            ("dynamicrafter", r"DynamiCrafter $\sim\!70$--$85$\,s", 1)]:
        add(APPX, anchor, "range", (lambda m=m, u=unit: "per-file mean s/clip over the logged files: "
                                    f"{per_file_rate_range(m)[0] / u:.2f}-{per_file_rate_range(m)[1] / u:.2f}"
                                    + (" min" if u == 60 else " s")),
            "the logged results_v1 files of this model", "elapsed_seconds / rows per file", kind="qual")
    add(APPX, r"\textbf{Total wall-clock GPU-hours: $\sim\!57$", "57", v1_gpu_hours, "see main.tex entry", "sum",
        kind="approx", tol=0.5)
    add(APPX, r"audit).} $54.4$\,h is a direct sum over the $69$ of $\sim\!134$ result", "54.4",
        lambda: sum(e for _, e, _ in v1_timed()) / 3600, "results_v1/*.json with summary.elapsed_seconds", "sum / 3600")
    add(APPX, r"audit).} $54.4$\,h is a direct sum over the $69$ of $\sim\!134$ result", "69", lambda: len(v1_timed()),
        "same", "count", kind="int")
    add(APPX, r"audit).} $54.4$\,h is a direct sum over the $69$ of $\sim\!134$ result", "134",
        lambda: len([f for f in os.listdir(DATA["v1"]) if f.endswith(".json")]), "results_v1/*.json", "count", kind="int")
    add(APPX, r"$\sim\!95$ clips (the CogVideoX and DynamiCrafter projectile pilots", "95",
        lambda: len(J("v1", PF["cogvideox"])["rows"]) + len(J("v1", PF["dynamicrafter"])["rows"]),
        "results_v1/e0_pilot_{cogvideox,dynamicrafter}.json", "40 + 55 rows", kind="int",
        note="e0_pilot.json (LTX-Video, 55 rows) is also untimed; at 3.96 s/clip it adds 0.06 h.")
    add(APPX, r"estimated at $\sim\!2.6$\,h by applying each model's own measured", "2.6", v1_untimed_hours,
        "same + per-model rates", "rows x mean s/clip")
    for m, p, anchor in [("ltx", "3.96", r"logged files: LTX $3.96$\,s/clip,"),
                         ("cogvideox", "122.45", r"CogVideoX $122.45$\,s/clip, DynamiCrafter $79.19$\,s/clip)"),
                         ("dynamicrafter", "79.19", r"CogVideoX $122.45$\,s/clip, DynamiCrafter $79.19$\,s/clip)")]:
        add(APPX, anchor, p, (lambda m=m: v1_rate(m)), f"the logged {NAME[m]} files", "sum elapsed / sum rows")
    add(APPX, r"un-logged clip counts. The VLM plausibility-scoring pass ($630$ clips", "630",
        lambda: sum(len(e3_rows(m)) for m in MODELS_V1), "e3 files", "count", kind="int")
    add(APPX, r"scored in one job) is estimated separately at $\sim\!0.3$\,h from that", "0.3", vlm_hours,
        "provenance/v1_file_times.json (first/last e3_plausibility_* write; log slurm_jobs/e3_score_380931.out)",
        "last - first write", kind="approx", tol=0.05,
        note="The scoring window is 0.17 h; model load (~minutes) was not logged, so 0.3 h cannot be reproduced.")


def build_steps():
    # ---------------- STEP 1 ----------------
    D1 = S[1]
    inj_src = "results_v2/validity_injection.json"
    inj_how = "experiments/v2_validity_injection.py (stored rows)"
    add(D1, "| clean | 65/65 |", "65/65", lambda: f"{inj_sum('clean', 'fit_gate_pass')}/{inj_sum('clean', 'n')}", inj_src,
        inj_how, kind="str")
    add(D1, "| clean | 65/65 |", "1.000", lambda: min(inj_median("clean", s, "r2") for s in ("projectile", "bouncing_ball",
                                                                                           "inclined_slide")),
        inj_src, "min of per-system median R2")
    add(D1, "| clean | 65/65 |", "0.04", lambda: max(inj_median("clean", s, "rel") for s in ("projectile", "bouncing_ball",
                                                                                          "inclined_slide")),
        inj_src, "max of per-system median relative error", kind="le")
    add(D1, "| clean | 65/65 | 1.000 | ≤ 0.04 | 65/65 |", "65/65",
        lambda: f"{inj_sum('clean', 'valid')}/{inj_sum('clean', 'n')}", inj_src, "valid / n", kind="str")
    two = ("projectile", "inclined_slide")
    add(D1, "| still object (projectile, slide) | 45/45 |", "45/45",
        lambda: f"{inj_sum('still', 'fit_gate_pass', two)}/{inj_sum('still', 'n', two)}", inj_src, "fit gate / n", kind="str")
    add(D1, "| still object (projectile, slide) | 45/45 | — | — | 45/45", "45/45",
        lambda: f"{inj_sum('still', 'valid_static', two)}/{inj_sum('still', 'n', two)}", inj_src,
        "valid_static / n", kind="str")
    for kind_, anchor, fit, r2rng, rels in [
            ("drip", "| dripping fragments | 46/65 |", "46/65", ("0.99", "1.00"), ("0.72", "3.72")),
            ("duplicate", "| duplicated object | 63/65 |", "63/65", ("1.000", None), ("0.50", "3.12")),
            ("balloon", "| ballooning object | 45/65 |", "45/65", ("1.000", None), ("0.91", "5.38"))]:
        add(D1, anchor, fit, (lambda k=kind_: f"{inj_sum(k, 'fit_gate_pass')}/{inj_sum(k, 'n')}"), inj_src, "fit gate / n",
            kind="str", note="validity_injection.json was regenerated on 2026-10-17 for amendment 3 (floor-strip "
            "pixels ignored); one dripping clip then fell below the fit gate. STEP1 still shows the 2026-10-15 run.")
        meds = (lambda k=kind_: [inj_median(k, s, "r2") for s in ("projectile", "bouncing_ball", "inclined_slide")])
        add(D1, anchor, r2rng[0], (lambda f=meds: min(f())), inj_src, "min per-system median R2 (fit-gate passes)")
        if r2rng[1]:
            add(D1, anchor, r2rng[1], (lambda f=meds: max(f())), inj_src, "max per-system median R2")
        add(D1, anchor, rels[0], (lambda k=kind_: inj_median(k, "projectile", "rel")), inj_src,
            "median |theta_hat-theta|/theta, projectile, fit-gate passes")
        add(D1, anchor, rels[1], (lambda k=kind_: inj_median(k, "inclined_slide", "rel")), inj_src, "same, slide")
        add(D1, anchor, "0", (lambda k=kind_: inj_sum(k, "valid")), inj_src, "valid count", kind="int")
    va_src = "results_v2/validity_reanalysis.json:summaries (630 saved v1 clips)"
    va_how = "experiments/v2_validity_reanalysis.py (stored)"
    rows_ = [("| projectile / LTX | 40 |", "projectile/ltx", [40, 19, 11, 8, 0, 11, "0.277", "0.019"]),
             ("| projectile / DynamiCrafter | 40 |", "projectile/dynamicrafter", [40, 28, 8, 20, 0, 8, "-0.063", "0.005"]),
             ("| bouncing ball / LTX | 35 |", "bouncing_ball/ltx", [35, 2, 2, 0, 0, 0, None, None]),
             ("| bouncing ball / CogVideoX | 35 |", "bouncing_ball/cogvideox", [35, 1, 0, 1, 0, 0, None, None]),
             ("| bouncing ball / DynamiCrafter | 35 |", "bouncing_ball/dynamicrafter", [35, 5, 0, 1, 4, 0, "55.2", None]),
             ("| inclined slide / LTX | 35 |", "inclined_slide/ltx", [35, 11, 8, 3, 0, 6, "-0.464", "-0.037"]),
             ("| inclined slide / DynamiCrafter | 35 |", "inclined_slide/dynamicrafter", [35, 25, 9, 16, 0, 8, "0.703", "0.665"]),
             ("| pendulum ζ / DynamiCrafter | 30 |", "pendulum_zeta/dynamicrafter", [30, 4, 0, 1, 3, 0, None, None])]
    fields = [lambda s: s["n"], lambda s: s["n_fit_ok"], lambda s: s["n_valid"], lambda s: s["n_invalid_shape"],
              lambda s: s["n_invalid_static"], lambda s: s["second_tracker"]["confirmed"],
              lambda s: s["in_range_old_gate"]["slope"], lambda s: s["in_range_valid"]["slope"]]
    for anchor, key, vals in rows_:
        for f, v in zip(fields, vals):
            if v is None:
                continue
            add(D1, anchor, str(v), (lambda f=f, k=key: f(va(k))), f"{va_src}:{key}", va_how,
                kind="int" if isinstance(v, int) else "num")
    add(D1, "| all other 10 pairs | 360 |", "10",
        lambda: sum(1 for k in J("v2", "validity_reanalysis.json")["summaries"] if va(k)["n_fit_ok"] == 0), va_src,
        "pairs with no fit-gate pass", kind="int")
    add(D1, "| all other 10 pairs | 360 |", "360",
        lambda: sum(va(k)["n"] for k in J("v2", "validity_reanalysis.json")["summaries"] if va(k)["n_fit_ok"] == 0), va_src,
        "their clips", kind="int", note="Arithmetic slip in the report: 630 - 285 (the 8 listed pairs) = 345.")
    tot = lambda: J("v2", "validity_reanalysis.json")["totals"]
    for p, fn in [("630", lambda: tot()["n"]), ("95", lambda: tot()["n_fit_ok"]), ("38", lambda: tot()["n_valid"]),
                  ("50", lambda: tot()["n_invalid_shape"]), ("7", lambda: tot()["n_invalid_static"]),
                  ("33", lambda: tot()["second_tracker"]["confirmed"])]:
        add(D1, "| **total** | **630** |", p, fn, "results_v2/validity_reanalysis.json:totals", va_how, kind="int")
    add(D1, "**60% of clips that passed the old gate (57/95)", "60",
        lambda: 100 * (tot()["n_fit_ok"] - tot()["n_valid"]) / tot()["n_fit_ok"], "totals", "100 x 57/95")
    add(D1, "**60% of clips that passed the old gate (57/95)", "57/95",
        lambda: f"{tot()['n_fit_ok'] - tot()['n_valid']}/{tot()['n_fit_ok']}", "totals", "fit-ok minus valid", kind="str")
    for p, key in [("0.019", "projectile/ltx"), ("0.005", "projectile/dynamicrafter"), ("-0.037", "inclined_slide/ltx")]:
        add(D1, "clips the in-range slope is about 0 (0.019, 0.005, −0.037)", p,
            (lambda k=key: va(k)["in_range_valid"]["slope"]), f"{va_src}:{key}.in_range_valid", va_how)
    add(D1, "DC slide at 0.665, rests on 5 clips, 4 when restricted to", "0.665",
        lambda: va("inclined_slide/dynamicrafter")["in_range_valid"]["slope"], va_src, va_how)
    add(D1, "DC slide at 0.665, rests on 5 clips, 4 when restricted to", "5",
        lambda: va("inclined_slide/dynamicrafter")["in_range_valid"]["n"], va_src, va_how, kind="int")
    add(D1, "DC slide at 0.665, rests on 5 clips, 4 when restricted to", "4",
        lambda: va("inclined_slide/dynamicrafter")["in_range_valid_confirmed"]["n"], va_src, va_how, kind="int")
    add(D1, "(slope 0.23).", "0.23", lambda: va("inclined_slide/dynamicrafter")["in_range_valid_confirmed"]["slope"],
        va_src, va_how)
    add(D1, "- Projectile: all 19 valid clips have |ĝ| < 0.5", "19",
        lambda: len(va_rows(system="projectile", label="valid")), "results_v2/validity_reanalysis.json:rows", "count",
        kind="int")
    add(D1, "- Projectile: all 19 valid clips have |ĝ| < 0.5", "|g_hat| < 0.5",
        lambda: all(abs(x["theta_hat"]) < 0.5 for x in va_rows(system="projectile", label="valid")), "same", "max", kind="claim")
    add(D1, "- DC slide: 7 of 9 valid clips sit within 0.15 of tan 60° = 1.732", "7",
        lambda: sum(abs(x["theta_hat"] - math.tan(math.radians(60))) <= 0.15
                    for x in va_rows(system="inclined_slide", model="dynamicrafter", label="valid")),
        "rows, DC slide valid", "count within 0.15 of tan 60", kind="int")
    add(D1, "- DC slide: 7 of 9 valid clips sit within 0.15 of tan 60° = 1.732", "9",
        lambda: len(va_rows(system="inclined_slide", model="dynamicrafter", label="valid")), "same", "count", kind="int")
    add(D1, "- DC projectile seed clusters (6.5, −2.1, 3.5)", "6.5, -2.1, 3.5",
        lambda: "; ".join(f"seed {z}: mean {np.mean([x['theta_hat'] for x in v]):.2f} ({collections.Counter(x['label'] for x in v)})"
                          for z in range(5) for v in [[x for x in va_rows(system='projectile', model='dynamicrafter', seed=z)
                                                       if x['fit_ok']]] if v),
        "validity_reanalysis rows, DC projectile, fit-gate passes", "per-seed means and labels", kind="qual")
    for z, p1, p2 in [(0, "0.10", "0.07"), (1, "6.51", "6.46"), (3, "-0.03", "-0.03"), (4, "-2.02", "-2.12")]:
        add(D1, "closely (e.g. DC projectile seeds 0/1/3/4: 0.10/6.51/−0.03/−2.02 vs", p1,
            (lambda z=z: float(np.mean([x["theta_hat"] for x in gated(v1rows("dynamicrafter", "projectile")) if x["seed"] == z]))),
            "results_v1/e0_pilot_dynamicrafter.json, gated in+out", "per-seed mean (paper's E0 run)")
        add(D1, "0.07/6.46/−0.03/−2.12).", p2,
            (lambda z=z: float(np.mean([x["theta_hat"] for x in J("v1", "e3e5_default_projectile_dynamicrafter.json")["rows"]
                                        if x["seed"] == z and ok(x)]))),
            "results_v1/e3e5_default_projectile_dynamicrafter.json, gated", "per-seed mean (saved-video run)")
    rt = lambda: J("v2", "validity_reanalysis.json")["retrack_check"]
    add(D1, "Re-tracking the mp4 reproduces it within 5% for 67/90 clips", "67/90",
        lambda: f"{rt()['n_close']}/{rt()['n_retracked']}", "validity_reanalysis.json:retrack_check", va_how, kind="str")
    far = lambda: [x for x in J("v2", "validity_reanalysis.json")["rows"] if x["fit_ok"] and x.get("retracked_theta_hat") is not None
                     and abs(x["retracked_theta_hat"] - x["theta_hat"]) > 0.05 * (abs(x["theta_hat"]) + 1)]
    add(D1, "Re-tracking the mp4 reproduces it within 5% for 67/90 clips; 13 of the 23", "23", lambda: len(far()),
        "validity_reanalysis rows", "fit_ok, retracked, |diff| > 0.05 (|theta_hat| + 1) (the script's rule)", kind="int")
    add(D1, "Re-tracking the mp4 reproduces it within 5% for 67/90 clips; 13 of the 23", "13",
        lambda: sum(x["label"] == "invalid_shape" for x in far()), "same rows", "of those, label invalid_shape", kind="int")
    # ---------------- STEP 2 ----------------
    D2 = S[2]
    pc_src = "results_v2/positive_control.json:results.<style>.pooled"
    pc_how = "experiments/v2_positive_control.py (stored)"
    for style, anchor, pre_, sl in [("minimal", "| minimal | 190 |", ["0.0035", "0.0021", "0.0052"], ["1.0002", "1.0001", "1.0003"]),
                                    ("structured", "| structured | 190 |", ["0.0035", "0.0021", "0.0052"], ["1.0002", "1.0001", "1.0003"]),
                                    ("shaded", "| shaded | 190 |", ["0.0039", "0.0024", "0.0057"], ["1.0002", "1.0001", "1.0003"])]:
        add(D2, anchor, "190", (lambda st_=style: pc(st_)["n_fit_ok"]), pc_src, pc_how, kind="int")
        add(D2, anchor, "190", (lambda st_=style: pc(st_)["n_valid"]), pc_src, pc_how, kind="int")
        add(D2, anchor, "0", (lambda st_=style: pc(st_)["fit_ok_but_not_valid"]), pc_src, pc_how, kind="int")
        for i, p in enumerate(pre_):
            add(D2, anchor, p, (lambda st_=style, i=i: pc(st_)["PRE_in"][i]), pc_src, pc_how)
        for i, p in enumerate(sl):
            add(D2, anchor, p, (lambda st_=style, i=i: pc(st_)["slope_in"][i]), pc_src, pc_how)
    add(D2, "215 clips per style", "215", lambda: pc("structured")["n"], pc_src, pc_how, kind="int")
    add(D2, "- The 25 non-fitting clips in every style", "25",
        lambda: max(pc(s)["n"] - pc(s)["n_fit_ok"] for s in ("minimal", "structured", "shaded")), pc_src, "n - fit ok",
        kind="int")
    add(D2, "570 fit-passing clips across the three styles", "570", lambda: sum(pc(s)["n_fit_ok"] for s in ("minimal", "structured", "shaded")),
        pc_src, "sum", kind="int")
    for i, p in enumerate(["1.076", "1.003", "1.181"]):
        add(D2, "is 1.076 [1.003, 1.181] (structured)", p, (lambda i=i: pc("structured", "bouncing_ball")["slope_in"][i]),
            "positive_control.json:results.structured.per_system.bouncing_ball", pc_how)
    add(D2, "- `minimal` (the default) is **bit-identical**", "bit-identical", render_bit_identical,
        "code/physweep/render.py vs 4-ICLR/physweep/render.py", "np.array_equal on 5 simulators x 3 seeds", kind="claim")
    # ---------------- STEP 3 ----------------
    D3 = S[3]
    ds = lambda: J("v2", "design_selftest.json")
    ds_how = "experiments/v2_design_selftest.py (stored)"
    add(D3, "| crossed design size, unique ids", "304", lambda: ds()["design"]["n_crossed"], "design_selftest.json:design",
        ds_how, kind="int")
    add(D3, "| crossed design size, unique ids", "pass",
        lambda: ds()["design"]["scene_noise_disjoint"] and ds()["design"]["api_noise_unique"], "same", "flags", kind="claim")
    add(D3, "| text conditioning identical across noise seeds", "pass",
        lambda: ds()["conditioning"]["text_same_across_noise"] and ds()["conditioning"]["text_differs_across_scene"],
        "design_selftest.json:conditioning", ds_how, kind="claim")
    add(D3, "| frame-channel conditioning varies with θ | pass |", "pass",
        lambda: ds()["conditioning"]["frame_channel_varies_with_theta"], "same", ds_how, kind="claim")
    add(D3, "(single draw, 40% clips dropped) | 6/6 scenarios |", "6/6",
        lambda: f"{sum(v['ok'] for v in ds()['decomposition'].values())}/{len(ds()['decomposition'])}",
        "design_selftest.json:decomposition", ds_how, kind="str")
    add(D3, "| repeated over 20 random draws each |", "119/120", None, "an ad hoc run on 2026-10-15",
        "not saved (v2_design_selftest.py has no repeated-draw mode)", kind="unarchived",
        note="Also the source of 'median error 0.01-0.04; worst 0.14' and the ±0.05/±0.14/±0.075 limitation. "
             "To recreate: add a fixed-seed repeated-draw mode (RESUME.md, open item).")
    add(D3, "| false positives on no-structure data", "0/40", None, "same ad hoc run", "not saved", kind="unarchived")
    add(D3, "shares split 0.49/0.49", "0.49", lambda: ds()["coupled_v1_design"]["shares"]["scene"],
        "design_selftest.json:coupled_v1_design", ds_how)
    add(D3, "shares split 0.49/0.49", "0.49", lambda: ds()["coupled_v1_design"]["shares"]["noise"], "same", ds_how)
    add(D3, "shares split 0.49/0.49", "confounded", lambda: ds()["coupled_v1_design"]["confounded"], "same", ds_how, kind="claim")
    add(D3, "(0.89 estimated vs 1.00 true)", "0.89", None, "the pre-fix estimator (replaced in Step 3)",
        "historical; the old code path no longer exists", kind="unarchived")
    # ---------------- STEP 4 ----------------
    D4 = S[4]
    spec_rows = [("| ltx (v1) | LTXImageToVideoPipeline | 768×512 | 25 @ 24 | 30 | 3.0 |", "ltx"),
                 ("| cogvideox (v1) | CogVideoXImageToVideoPipeline | 720×480 | 49 @ 8 | 30 | 6.0 |", "cogvideox"),
                 ("| dynamicrafter (v1) | subprocess (v1 call) | 512×320 | 16 @ 24 | 50 | 7.5 |", "dynamicrafter"),
                 ("| wan22_ti2v_5b | WanImageToVideoPipeline | 1280×704 | 49 @ 24 | 50 | 5.0 |", "wan22_ti2v_5b"),
                 ("| cogvideox15_i2v | CogVideoXImageToVideoPipeline | 1360×768 | 81 @ 16 | 50 | 6.0 |", "cogvideox15_i2v"),
                 ("| wan22_i2v_a14b | WanImageToVideoPipeline | 832×480 | 49 @ 16 | 40 |", "wan22_i2v_a14b"),
                 ("| hunyuan15_i2v | HunyuanVideo15ImageToVideoPipeline | 1280×720 | 61 @ 24 | 50 |", "hunyuan15_i2v"),
                 ("| ltx2 | LTX2ImageToVideoPipeline | 768×512 | 49 @ 24 | 40 | 4.0 |", "ltx2"),
                 ("| cosmos2_2b | Cosmos2VideoToWorldPipeline | 1280×704 | 93 @ 16 | 35 | 7.0 |", "cosmos2_2b")]
    for anchor, m in spec_rows:
        printed = re.search(r"\| (\d+)×(\d+) \| (\d+) @ (\d+) \| (\d+) \|", anchor).groups()
        add(D4, anchor, "×".join(printed[:2]) + f" {printed[2]}@{printed[3]} {printed[4]} steps",
            (lambda m=m: (lambda sp: f"{sp['W']}×{sp['H']} {sp['num_frames']}@{sp['fps']} {sp['steps']} steps")(specs()[m])),
            "code/physweep/generators.py:MODEL_SPECS", "current spec", kind="str",
            note="superseded for hunyuan15_i2v by the 'Step 4 closed' table (option B: 480p, 848x480, 33 frames)")
    pil = [("| ltx | 12 | 4 | 15.4 | 3 | 2 | 7 | 0 | 3 | 0.3 |", "pilot", "ltx", [12, 4, "15.4", 3, 2, 7, 0, 3, "0.3"]),
           ("| cogvideox | 12 | 144 | 25.4 | 1 | 3 | 8 | 0 | 1 | 12.1 |", "pilot", "cogvideox", [12, 144, "25.4", 1, 3, 8, 0, 1, "12.1"]),
           ("| dynamicrafter | 11 (+1 timeout) | 69 |", "pilot", "dynamicrafter", [11, 69, None, 5, 2, 4, 0, 5, "5.8"]),
           ("| wan22_ti2v_5b | 12 | 126 | 45.3 | 7 | 2 | 3 | 0 | 7 | 10.6 |", "pilot", "wan22_ti2v_5b", [12, 126, "45.3", 7, 2, 3, 0, 7, "10.6"]),
           ("| cogvideox15_i2v | 12 | **1021** | 28.6 | 4 | 0 | 8 | 0 | 4 | **86.2** |", "pilot", "cogvideox15_i2v", [12, 1021, "28.6", 4, 0, 8, 0, 4, "86.2"]),
           ("| wan22_i2v_a14b | 12 | 152 | 78.8 | 11 | 0 | 1 | 0 | 11 | 12.9 |", "pilot", "wan22_i2v_a14b", [12, 152, "78.8", 11, 0, 1, 0, 11, "12.9"]),
           ("| hunyuan15_i2v | 12 | **1200** | 50.7 | 4 | 0 | 7 | 1 | 4 | **101.3** |", "pilot", "hunyuan15_i2v", [12, 1200, "50.7", 4, 0, 7, 1, 4, "101.3"]),
           ("| ltx2 | 12 | 19 | 73.3 | 6 | 0 | 6 | 0 | 6 | 1.6 |", "pilot", "ltx2", [12, 19, "73.3", 6, 0, 6, 0, 6, "1.6"])]
    pf = [lambda p: p["done"], lambda p: p["sec"], lambda p: p["vram"], lambda p: p["lab"].get("valid", 0),
          lambda p: p["lab"].get("invalid_shape", 0), lambda p: p["lab"].get("invalid_fit", 0),
          lambda p: p["lab"].get("invalid_camera", 0), lambda p: p["conf"], lambda p: p["hours"]]
    pnames = ["done", "s/clip", "peak VRAM", "valid", "broken obj.", "fit fail", "camera", "confirmed", "GPU-h"]
    for anchor, run, m, vals in pil:
        for f, nm, v in zip(pf, pnames, vals):
            if v is None:
                continue
            add(D4, anchor, str(v), (lambda f=f, run=run, m=m: f(pilot_row(run, m))),
                f"runs/{run}/{m}/clips_rescored.jsonl", f"v2_pilot_summary.py logic ({nm})",
                kind="approx" if nm == "s/clip" else ("int" if isinstance(v, int) else "num"),
                tol=0.5 if nm == "s/clip" else None,
                note="superseded: rescored again after amendment 3 (shadows); see the 'Step 4 closed' table")
    add(D4, "Projected text-channel sweep: 231 GPU-h (without Cosmos).", "231",
        lambda: sum(pilot_row("pilot", m)["hours"] for m in ["ltx", "cogvideox", "dynamicrafter", "wan22_ti2v_5b",
                                                             "cogvideox15_i2v", "wan22_i2v_a14b", "hunyuan15_i2v", "ltx2"]),
        "runs/pilot", "sum of projected hours", kind="approx", tol=0.5,
        note="superseded: recomputed from the current rescore")
    dl = lambda: [float(x) for x in re.findall(r"^OK .*?: ([0-9.]+) GB", log_text("logs_v2", "pw2_download_425643.out"), re.M)]
    add(D4, "Download: 8/8 repos, 455 GB on", "8", lambda: len(dl()), "slurm/v2/pw2_download_425643.out", "OK lines", kind="int")
    add(D4, "Download: 8/8 repos, 455 GB on", "455", lambda: sum(dl()), "same", "sum of GB on OK lines", kind="approx", tol=0.5)
    fin = [("| ltx | 768×512, 25 fr @24 | pilot |", "pilot", "ltx", 4, "3/12", "0.3"),
           ("| cogvideox | 720×480, 49 fr @8 | pilot |", "pilot", "cogvideox", 144, "1/12", "12.1"),
           ("| dynamicrafter | 512×320, 16 fr | pilot |", "pilot", "dynamicrafter", 69, "5/11", "5.8"),
           ("| wan22_ti2v_5b | 1280×704, 49 fr @24 | pilot |", "pilot", "wan22_ti2v_5b", 126, "6/12", "10.6"),
           ("| cogvideox15_i2v | 1360×768, **81** fr @16 (native) | pilot |", "pilot", "cogvideox15_i2v", 1021, "4/12", "86.2"),
           ("| wan22_i2v_a14b | 832×480, 49 fr @16 | pilot |", "pilot", "wan22_i2v_a14b", 152, "11/12", "12.9"),
           ("| hunyuan15_i2v | **480p** checkpoint, 848×480, 33 fr @24 | pilot_b |", "pilot_b", "hunyuan15_i2v", 116, "8/12", "9.8"),
           ("| ltx2 | 768×512, 49 fr @24 | pilot |", "pilot", "ltx2", 19, "6/12", "1.6"),
           ("| cosmos2_2b | 1280×704, 93 fr @16, guardrail on | pilot_b (job 426984) |", "pilot_b", "cosmos2_2b", 290, "0/12", "24.5")]
    for anchor, run, m, sec, val, hrs in fin:
        src = f"runs/{run}/{m}/clips_rescored.jsonl"
        add(D4, anchor, str(sec), (lambda run=run, m=m: pilot_row(run, m)["sec"]), src, "median gen_seconds",
            kind="approx", tol=0.5 if m != "cosmos2_2b" else 10)
        add(D4, anchor, val, (lambda run=run, m=m: f"{pilot_row(run, m)['lab'].get('valid', 0)}/{pilot_row(run, m)['done']}"),
            src, "valid / done", kind="str")
        add(D4, anchor, hrs, (lambda run=run, m=m: pilot_row(run, m)["hours"]), src, "median s x 304 / 3600",
            kind="approx", tol=0.05 if m != "cosmos2_2b" else 0.6)
    add(D4, "| **total** | | | | | **≈ 164**", "164",
        lambda: sum(pilot_row(run, m)["hours"] for _, run, m, *_ in fin), "the 9 rows above", "sum", kind="approx", tol=1.0)
    add(D4, "11/11 retried clips generated without error", "11/11",
        lambda: (lambda t: "{0}/{0}".format(re.search(r"(\d+) to do", t).group(1)))(log_text("logs_v2", "pw2_repilot_cosmos_426984.out")),
        "slurm/v2/pw2_repilot_cosmos_426984.out", "'N to do' line", kind="str")
    add(D4, "and camera shift was 0 px", "0",
        lambda: max(x.get("ground_row_shift") or 0 for x in recs("pilot_b", "cosmos2_2b") if "error" not in x),
        "runs/pilot_b/cosmos2_2b", "max ground_row_shift", kind="int")
    add(D4, "(5.7 → 10.2, 8.4 → 10.2)", "5.7 -> 10.2, 8.4 -> 10.2",
        lambda: "; ".join(f"scene {z}: " + ", ".join(f"g={x['theta']}: {x['theta_hat']:.1f}" for x in sorted(
            valid(recs("pilot_b", "hunyuan15_i2v"), system="projectile", scene_seed=z), key=lambda x: x["theta"]))
            for z in (0, 1)),
        "runs/pilot_b/hunyuan15_i2v, valid projectile clips", "per scene", kind="qual")
    add(D4, "so its published ĝ values are 9× too large", "9", lambda: (24 / specs()["cogvideox"]["fps"]) ** 2,
        "MODEL_SPECS cogvideox fps = 8", "(24/8)^2", kind="int")
    add(D4, "drift: it passes the fit gate on 60/65 clips and is rejected on 65/65", "60/65",
        lambda: f"{inj_sum('camera', 'fit_gate_pass')}/{inj_sum('camera', 'n')}", inj_src, inj_how, kind="str")
    add(D4, "drift: it passes the fit gate on 60/65 clips and is rejected on 65/65", "65/65",
        lambda: f"{inj_sum('camera', 'n') - inj_sum('camera', 'valid')}/{inj_sum('camera', 'n')}", inj_src, "n - valid",
        kind="str")
    # ---------------- STEP 5 ----------------
    D5 = S[5]
    add(D5, "| `main_text` | crossed", "2736", lambda: sum(len(recs("main_text", m)) for m in run_models("main_text")),
        "runs/main_text/*/clips_rescored.jsonl", "count", kind="int")
    add(D5, "| `api_text` | \"API mode\"", "1064", lambda: sum(len(recs("api_text", m)) for m in run_models("api_text")),
        "runs/api_text", "count", kind="int")
    add(D5, "**Completion:** `main_text` 9 × 304/304 clips, `api_text` 7 × 152/152; 0", "0",
        lambda: sum(1 for run in ("main_text", "api_text") for m in run_models(run) for x in recs(run, m) if "error" in x),
        "both runs", "error records", kind="int")
    add(D5, "errors, no resubmits. Measured compute: **192.5 GPU-h**", "192.5",
        lambda: gpu_hours_v2("main_text") + gpu_hours_v2("api_text"), "runs/*/clips_shard*.jsonl gen_seconds + run_meta load_seconds",
        "sum / 3600")
    add(D5, "changed only 1–11 labels per model", "1",
        lambda: min(list(label_changes("main_text").values()) + list(label_changes("api_text").values())),
        "clips_rescored.jsonl original_label vs label", "min over models and runs", kind="int",
        note="CogVideoX1.5 (main_text) had 0 label changes, so the range is 0-11.")
    add(D5, "changed only 1–11 labels per model", "11",
        lambda: max(list(label_changes("main_text").values()) + list(label_changes("api_text").values())), "same", "max",
        kind="int")
    nv = lambda: sum(len(valid(recs("main_text", m))) for m in run_models("main_text"))
    add(D5, "**Validity (main run):** 1007 / 2736 clips valid (37%), 973 of them confirmed", "1007", nv,
        "runs/main_text/*/clips_rescored.jsonl", "label == valid", kind="int")
    add(D5, "**Validity (main run):** 1007 / 2736 clips valid (37%), 973 of them confirmed", "37",
        lambda: 100 * nv() / 2736, "same", "100 x 1007/2736")
    add(D5, "**Validity (main run):** 1007 / 2736 clips valid (37%), 973 of them confirmed", "973",
        lambda: sum(x.get("second_tracker") == "confirmed" for m in run_models("main_text") for x in valid(recs("main_text", m))),
        "same", "valid and second_tracker == confirmed", kind="int")
    for anchor, pairs_ in [("by CoTracker3. By model: LTX-2 179", [("ltx2", 179), ("wan22_i2v_a14b", 170), ("hunyuan15_i2v", 161)]),
                           ("Wan2.2-5B 119, DynamiCrafter 103", [("wan22_ti2v_5b", 119), ("dynamicrafter", 103), ("ltx", 86),
                                                                 ("cogvideox", 69), ("cosmos2_2b", 67)]),
                           ("CogVideoX1.5 53.", [("cogvideox15_i2v", 53)])]:
        for m, v in pairs_:
            add(D5, anchor, str(v), (lambda m=m: len(valid(recs("main_text", m)))), f"runs/main_text/{m}/clips_rescored.jsonl",
                "label == valid", kind="int")
    inc0 = lambda c: (lambda: f"{sum(v['beta_in_ci'][0] <= 0 <= v['beta_in_ci'][1] for v in est_pairs(c).values())}/{len(est_pairs(c))}")
    add(D5, "   in 24/24 estimable model × system pairs (22/22 confirmed-only) and", "24/24", inc0(False),
        "results_v2/main_text_analysis.json:results.*.beta_in_ci", "experiments/v2_analyze.py; CI includes 0", kind="str")
    add(D5, "   in 24/24 estimable model × system pairs (22/22 confirmed-only) and", "22/22", inc0(True),
        "results_v2/main_text_confirmed_analysis.json", "same, confirmed-only", kind="str")
    add(D5, "   excludes 1 (faithful) in 19/24.", "19/24",
        lambda: f"{sum(not (v['beta_in_ci'][0] <= 1 <= v['beta_in_ci'][1]) for v in est_pairs().values())}/{len(est_pairs())}",
        "main_text_analysis.json", "CI excludes 1", kind="str")
    for anchor, factor, p_main, p_conf in [("   noise share significant (p < 0.01) in 14/22 pairs (16/21 confirmed-only);", "noise", "14/22", "16/21"),
                                           ("   scene share in 6/22 (5/21), mostly the older models", "scene", "6/22", "5/21"),
                                           ("request share in only 4/22", "request", "4/22", None)]:
        add(D5, anchor, p_main, (lambda f=factor: "{}/{}".format(*n_sig(f))),
            "main_text_analysis.json:results.*.decomposition.p_value", "count p < 0.01", kind="str")
        if p_conf:
            add(D5, anchor, p_conf, (lambda f=factor: "{}/{}".format(*n_sig(f, True))),
                "main_text_confirmed_analysis.json", "same, confirmed-only", kind="str")
    add(D5, "request share in only 4/22 (the same 4 in both", "the same 4",
        lambda: {k for k, v in dec_pairs().items() if v["p_value"]["request"] < 0.01}
        == {k for k, v in dec_pairs(True).items() if v["p_value"]["request"] < 0.01}, "both analyses", "set equality",
        kind="claim")
    hm = lambda: median_by_theta("main_text", "hunyuan15_i2v", "projectile")
    add(D5, "3. **HunyuanVideo-1.5 partly responds to the request:** median ĝ 1.1 for the", "1.1", lambda: hm()[1.6],
        "runs/main_text/hunyuan15_i2v, valid projectile clips", "median theta_hat at g = 1.6")
    add(D5, "\"Moon\" request (1.6), rising from ~6–7 at g = 5–9.8 to ~9.4 at 12–15, then", "6–7",
        lambda: ", ".join(f"g={t}: {hm()[t]:.2f}" for t in (5, 7, 9.8)), "same", "medians", kind="qual")
    add(D5, "\"Moon\" request (1.6), rising from ~6–7 at g = 5–9.8 to ~9.4 at 12–15, then", "9.4",
        lambda: ", ".join(f"g={t}: {hm()[t]:.2f}" for t in (12, 15)), "same", "medians", kind="qual")
    add(D5, "   3.7 at g = 25; Spearman ρ 0.47;", "3.7", lambda: hm()[25], "same", "median at g = 25",
        note="Eight valid clips; np.median = (3.56 + 3.73) / 2 = 3.65. 3.7 matches the upper middle value only.")
    hp = lambda: analysis()["results"]["hunyuan15_i2v/projectile"]
    add(D5, "   3.7 at g = 25; Spearman ρ 0.47;", "0.47", lambda: hp()["spearman_rho"], "main_text_analysis.json", "stored")
    for i, p in [(None, "0.08"), (0, "-0.30"), (1, "0.37")]:
        add(D5, "   3.7 at g = 25; Spearman ρ 0.47;", p,
            (lambda i=i: hp()["beta_in"] if i is None else hp()["beta_in_ci"][i]), "main_text_analysis.json", "stored")
    wm = lambda: median_by_theta("main_text", "wan22_i2v_a14b", "bouncing_ball")
    add(D5, "   (ê 0.82 vs 0.96–0.99 elsewhere).", "0.82", lambda: wm()[0.2], "runs/main_text/wan22_i2v_a14b, valid ball",
        "median at e = 0.2")
    add(D5, "   (ê 0.82 vs 0.96–0.99 elsewhere).", "0.96", lambda: min(v for t, v in wm().items() if t != 0.2), "same",
        "min median elsewhere")
    add(D5, "   (ê 0.82 vs 0.96–0.99 elsewhere).", "0.99", lambda: max(v for t, v in wm().items() if t != 0.2), "same",
        "max median elsewhere")
    add(D5, "falls (Wan2.2-A14B, ĝ = −14,", "-14",
        lambda: min(x["theta_hat"] for x in valid(recs("main_text", "wan22_i2v_a14b"), system="projectile")),
        "runs/main_text/wan22_i2v_a14b, valid projectile", "most negative theta_hat", kind="approx", tol=0.5)
    add(D5, "bounces (HunyuanVideo, ê ≈ 3.5–4.8,", "3.5–4.8",
        lambda: ", ".join(f"{x['theta_hat']:.2f} (cot {x.get('cot_theta_hat') or float('nan'):.2f})" for x in sorted(
            [x for x in valid(recs("main_text", "hunyuan15_i2v"), system="bouncing_ball") if x["theta_hat"] > 1.5],
            key=lambda x: x["theta_hat"])),
        "runs/main_text/hunyuan15_i2v, valid ball with e_hat > 1.5", "values (blob, CoTracker3)", kind="qual")
    add(D5, "**Seed-free tier (seeded vs API mode, 7 models):** β CIs overlap in 16/16", "16/16",
        lambda: "{}/{}".format(*ci_overlap_count()), "main_text_analysis.json: results vs compare_results", "overlap count",
        kind="str")
    add(D5, "rates differ at p < 0.01 in 5/21 pairs.", "5/21",
        lambda: f"{sum(p < 0.01 for p in api_valid_rate_tests().values())}/{len(api_valid_rate_tests())}",
        "runs/main_text and runs/api_text rescored, 7 models x 3 systems",
        "two-sided Fisher exact test on valid counts (RECREATED: the original test was not saved)", kind="str")
    # ---------------- STEP 6 ----------------
    D6 = S[6]
    for anchor, rel, vals in [("| text (regression) | 12/12 | 0.4% / 1.5% | ≤ 0.14 px |", "fcdry/text/simulator", ("0.4", "1.5", "0.14")),
                              ("| pair | 12/12 | 1.3% / 6.5% | ≤ 0.49 px |", "fcdry/frame/simulator_pair", ("1.3", "6.5", "0.49"))]:
        add(D6, anchor, "12/12", (lambda rel=rel: f"{len(valid(dry(rel)))}/{len(dry(rel))}"), f"results_v2/dryruns/{rel}",
            "valid / clips", kind="str")
        add(D6, anchor, vals[0], (lambda rel=rel: 100 * float(np.median(rel_errs(dry(rel))))), f"results_v2/dryruns/{rel}",
            "median relative error, %")
        add(D6, anchor, vals[1], (lambda rel=rel: 100 * max(rel_errs(dry(rel)))), f"results_v2/dryruns/{rel}", "max, %")
        add(D6, anchor, vals[2], (lambda rel=rel: max(e for x in dry(rel) for e in (x.get("key_frame_err_px") or []) if e is not None)),
            f"results_v2/dryruns/{rel}", "max key_frame_err_px", kind="le")
    pre_rel = "fcdry/frame/simulator_prefix"
    add(D6, "| prefix (16 fps, k = 5) | 12/12 |", "12/12", lambda: f"{len(valid(dry(pre_rel)))}/{len(dry(pre_rel))}",
        f"results_v2/dryruns/{pre_rel}", "valid / clips", kind="str")
    add(D6, "| prefix (16 fps, k = 5) | 12/12 |", "3",
        lambda: 100 * max(rel_errs([x for x in dry(pre_rel) if x["system"] != "bouncing_ball"])), "same",
        "max rel. error, projectile and slide, %", kind="le")
    add(D6, "| prefix (16 fps, k = 5) | 12/12 |", "4",
        lambda: 100 * min(rel_errs([x for x in dry(pre_rel) if x["system"] == "bouncing_ball"])), "same", "min, ball, %",
        kind="approx", tol=0.5)
    add(D6, "| prefix (16 fps, k = 5) | 12/12 |", "15",
        lambda: 100 * max(rel_errs([x for x in dry(pre_rel) if x["system"] == "bouncing_ball"])), "same", "max, ball, %",
        kind="approx", tol=0.5)
    add(D6, "| prefix (16 fps, k = 5) | 12/12 |", "0.14",
        lambda: max(e for x in dry(pre_rel) for e in (x.get("key_frame_err_px") or []) if e is not None), "same",
        "max key_frame_err_px", kind="le")
    add(D6, "| LTX-2 | prefix: 9 frames at latent index 0", "9", lambda: specs()["ltx2"]["frame_k"],
        "MODEL_SPECS['ltx2']['frame_k']", "spec", kind="int")
    add(D6, "| Cosmos-Predict2-2B | prefix: 5 frames", "5", lambda: specs()["cosmos2_2b"]["frame_k"],
        "MODEL_SPECS['cosmos2_2b']['frame_k']", "spec", kind="int")


# =============================================================================
# Runner
# =============================================================================
def norm(s):
    s = s.replace("−", "-").replace("{,}", ",").replace("\\!", "").replace("$", "").replace("\\,", "")
    return s.replace("{", "").replace("}", "").replace("+", "")


def decimals(p):
    m = re.search(r"\.(\d+)", p)
    return len(m.group(1)) if m else 0


@functools.lru_cache(None)
def doc_lines(doc):
    with open(os.path.join(REV, doc)) as f:
        return f.read().split("\n")


def locate(e):
    lines = doc_lines(e.doc)
    if "\n" in e.anchor:
        hits = [i for i, l in enumerate(lines) if l.endswith(e.anchor.rstrip("\n"))]
    else:
        hits = [i for i, l in enumerate(lines) if e.anchor in l]
    return hits


def check(e):
    _CUR[0] = e.id
    hits = locate(e)
    line = hits[0] + 1 if len(hits) == 1 else None
    res = dict(id=e.id, line=line, value=None, status=None, detail="")
    if len(hits) != 1:
        res.update(status="ANCHOR", detail=f"anchor found {len(hits)} times")
        return res
    if e.kind in ("unarchived", "external"):
        res["status"] = e.kind
        return res
    try:
        v = e.fn()
    except Missing as ex:
        res.update(status="missing", detail=str(ex))
        return res
    except Exception as ex:  # noqa: BLE001 - report, don't stop the whole check
        res.update(status="ERROR", detail=f"{type(ex).__name__}: {ex}")
        return res
    finally:
        _CUR[0] = None
    res["value"] = v
    p = e.printed
    if e.kind == "qual":
        res["status"] = "qualitative"
        return res
    if e.kind == "claim":
        good = bool(v)
    elif e.kind == "set":
        good = [sorted(map(float, x)) for x in v] == [sorted(map(float, x)) for x in p] if isinstance(p, tuple) \
            else sorted(map(float, v)) == sorted(map(float, p))
    elif e.kind == "str":
        good = str(v) == str(p)
    elif e.kind == "int":
        q = str(p).replace(",", "")
        good = int(round(v)) == WORDS.get(q.lower(), int(q) if q.lstrip("-").isdigit() else None)
    else:
        pv = float(str(p).replace("−", "-"))
        half = 0.5 * 10 ** -decimals(str(p)) + 1e-12
        if e.kind == "approx":
            good = abs(v - pv) <= (e.tol if e.tol is not None else half)
        elif e.kind == "ge":
            good = v >= pv - half
        elif e.kind == "le":
            good = v <= pv + half
        elif e.kind == "lt":
            good = v < pv
        else:
            good = abs(v - pv) <= half
    res["status"] = "match" if good else ("superseded" if e.note.startswith("superseded") else "MISMATCH")
    # the printed value must also appear on the located line (catches a stale anchor)
    if e.kind in ("num", "approx", "ge", "le", "lt", "int") and not isinstance(p, (list, tuple)):
        txt = norm(doc_lines(e.doc)[hits[0]]).lower()
        token = norm(str(p)).lower().lstrip("-") if e.kind != "int" else str(p).lower()
        if token not in txt:
            res["detail"] = f"printed value '{p}' not found on line {line}"
    return res


def fmt(v):
    if isinstance(v, bool) or v is None:
        return str(v)
    if isinstance(v, float):
        return f"{v:.6g}"
    return str(v)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_md(results, path):
    by = {r["id"]: r for r in results}
    docs = []
    for e in REG:
        if e.doc not in docs:
            docs.append(e.doc)
    counts = collections.Counter(r["status"] for r in results)
    out = ["# PROVENANCE: where every number comes from", "",
           "Generated by `code/experiments/reproduce_numbers.py --write-md`. Do not edit by hand: change the",
           "registry in that script and regenerate. Re-run the check before answering any question about a",
           "number (`python experiments/reproduce_numbers.py --find <value>` or `--show <id>`).", "",
           f"Status counts: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())), "",
           "Data roots used for this run: " + ", ".join(f"`{k}` = `{v}`" for k, v in DATA.items()
                                                       if k in ("v1", "v2", "runs", "logs_v1", "logs_v2", "prov")), "",
           "Status: `match` recomputed value rounds to the printed one; `MISMATCH` it does not; `superseded` an",
           "earlier table that a later table in the same report replaces; `qualitative` a wording claim, values",
           "shown; `unarchived` never saved as data; `external` quoted from another paper; `missing` input absent.", ""]
    bad = [e for e in REG if by[e.id]["status"] in ("MISMATCH", "ERROR", "ANCHOR", "missing")]
    out += ["## Problems found", ""]
    if not bad:
        out.append("None.")
    for e in bad:
        rr = by[e.id]
        out.append(f"- **{e.id}** `{e.doc}`:{rr['line']} printed `{e.printed}`, recomputed `{fmt(rr['value'])}` "
                   f"({rr['status']}{'; ' + rr['detail'] if rr['detail'] else ''}). {e.note}")
    out += ["", "## Not reproducible from archived data", ""]
    for e in REG:
        if by[e.id]["status"] in ("unarchived", "external"):
            out.append(f"- **{e.id}** `{e.doc}`:{by[e.id]['line']} `{e.printed}` from {e.src}. {e.note}")
    for doc in docs:
        out += ["", f"## `{doc}`", "", "| id | line | printed | recomputed | status | source | how |", "|---|---|---|---|---|---|---|"]
        for e in REG:
            if e.doc != doc:
                continue
            rr = by[e.id]
            cl = _CLIPS.get(e.id)
            ckey = ""
            if cl:
                u = sorted(set(cl))
                ckey = f" [{len(u)} clips, sha1 {hashlib.sha1(chr(10).join(u).encode()).hexdigest()[:10]}]"
            val = fmt(rr["value"]).replace("|", "/")
            note = f" — {e.note}" if e.note else ""
            out.append(f"| {e.id} | {rr['line']} | `{str(e.printed).replace('|', '/')}` | `{val[:120]}` | {rr['status']} | "
                       f"{e.src.replace('|', '/')}{ckey} | {e.how.replace('|', '/')}{note.replace('|', '/')} |")
    files = sorted({f for s in _USED.values() for f in s})
    out += ["", "## Input files (sha256)", "", "| area | file | bytes | sha256 |", "|---|---|---|---|"]
    for area, rel in files:
        p = os.path.join(DATA[area], rel)
        out.append(f"| {area} | `{rel}` | {os.path.getsize(p)} | `{sha256(p)}` |")
    out += ["", "## Code version (sha256 of the files the check imports)", "", "| file | sha256 |", "|---|---|"]
    for f in CODE_FILES:
        p = os.path.join(CODE_DIR, f)
        if os.path.exists(p):
            out.append(f"| `code/{f}` | `{sha256(p)}` |")
    out.append("")
    with open(path, "w") as f:
        f.write("\n".join(out))


def recompute_v2():
    """Re-run v2_analyze.py on the archived runs into a temp dir and compare byte-for-byte."""
    tmp = tempfile.mkdtemp(prefix="pw_recompute_")
    env = dict(os.environ, PHYSWEEP_OUT=DATA["runs"], PYTHONNOUSERSITE="1")
    out = []
    for extra, tag in [(["--compare", "api_text"], "main_text"), (["--confirmed-only"], "main_text_confirmed")]:
        subprocess.run([sys.executable, os.path.join(CODE_DIR, "experiments", "v2_analyze.py"), "--run", "main_text",
                        "--results-dir", tmp] + extra, check=True, env=env, stdout=subprocess.DEVNULL)
        for ext in ("json", "md"):
            a, b = os.path.join(tmp, f"{tag}_analysis.{ext}"), os.path.join(DATA["v2"], f"{tag}_analysis.{ext}")
            out.append((f"{tag}_analysis.{ext}", open(a, "rb").read() == open(b, "rb").read()))
    return out


def main():
    ap = argparse.ArgumentParser()
    for k in ("v1", "v2", "runs", "logs_v1", "logs_v2", "prov"):
        ap.add_argument(f"--{k.replace('_', '-')}", default=None)
    ap.add_argument("--write-md", action="store_true")
    ap.add_argument("--md-path", default=os.path.join(REV, "PROVENANCE.md"))
    ap.add_argument("--recompute", action="store_true")
    ap.add_argument("--show")
    ap.add_argument("--find")
    a = ap.parse_args()
    for k in ("v1", "v2", "runs", "logs_v1", "logs_v2", "prov"):
        if getattr(a, k):
            DATA[k] = os.path.abspath(getattr(a, k))
    build_main()
    build_appendix()
    build_steps()
    ids = [e.id for e in REG]
    assert len(ids) == len(set(ids)), "duplicate entry ids"
    sel = REG
    if a.show:
        sel = [e for e in REG if e.id == a.show]
    elif a.find:
        sel = [e for e in REG if a.find in str(e.printed)]
    results = [check(e) for e in sel]
    by = {r["id"]: r for r in results}
    if a.show or a.find:
        for e in sel:
            rr = by[e.id]
            print(f"{e.id}  {e.doc}:{rr['line']}  printed {e.printed!r}  recomputed {fmt(rr['value'])}  -> {rr['status']}"
                  f"{'  (' + rr['detail'] + ')' if rr['detail'] else ''}")
            print(f"    source: {e.src}\n    how:    {e.how}")
            if e.note:
                print(f"    note:   {e.note}")
            for area, rel in sorted(_USED.get(e.id, [])):
                print(f"    input:  {area}:{rel}")
            if _CLIPS.get(e.id):
                print(f"    clips:  {len(set(_CLIPS[e.id]))} aggregated")
        return
    counts = collections.Counter(r["status"] for r in results)
    for e in REG:
        rr = by[e.id]
        if rr["status"] in ("MISMATCH", "ERROR", "ANCHOR", "missing") or rr["detail"]:
            print(f"{rr['status']:<10} {e.id:<14} {e.doc}:{rr['line']}  printed {e.printed!r}  recomputed {fmt(rr['value'])}"
                  f"  {rr['detail']}  {e.note[:160]}")
    print("\n" + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())) + f"  (total {len(results)})")
    if a.recompute:
        for name, same in recompute_v2():
            print(f"recompute {name}: {'IDENTICAL' if same else 'DIFFERS'}")
    if a.write_md:
        write_md(results, a.md_path)
        print(f"wrote {a.md_path}")


if __name__ == "__main__":
    main()
