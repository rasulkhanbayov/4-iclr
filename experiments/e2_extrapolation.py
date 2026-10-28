#!/usr/bin/env python3
"""
experiments/e2_extrapolation.py
==================================
E2 -- EXTRAPOLATION + PRIOR REVERSION, formalized across ALL systems and
models (paper Section "Experimental Protocol" / runbook E2).

Generalizes what e7_mechanism_adjudication.py did for CogVideoX/projectile
only: computes the Extrapolation Gap (EG), the paired-bootstrap
PRE(out)-PRE(in) significance test, and select_mechanism() (H1 shrinkage vs
H2 clamp) for EVERY model-system pair that already has enough gated
out-of-range data.

This is a PURE ANALYSIS script -- numpy/yaml only, no torch, no GPU, no
model loading. It reads the row-level data already written by e0_pilot*.py
(projectile) and e4_generality.py (the other 5 systems) and does not
generate anything itself. Safe to run on the Panther LOGIN NODE or any
plain CPU shell; no sbatch job is needed for this script itself (see
CLAUDE.md's E2 section for which sbatch jobs feed data INTO this script).

select_mechanism() requires >=4 gated out-of-range points to compute its
leave-one-out R^2 (see physweep_metrics.py). Model-system pairs short of
that are reported as "insufficient_data" with the actual count, so a
SLURM job targeting exactly that gap can be sized correctly (see
--seeds-out / --merge in experiments/e4_generality.py).

Usage: python3 experiments/e2_extrapolation.py
Writes results/e2_extrapolation.json
"""
from __future__ import annotations
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import yaml

from physweep_metrics import select_mechanism, paired_bootstrap_pre_difference, extrapolation_gap

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(REPO_ROOT, "results")
CONFIG_PATH = os.path.join(REPO_ROOT, "physweep", "configs", "systems.yaml")
FIT_R2_GATE = 0.8
MIN_GATED_OUT = 4   # select_mechanism()'s own leave-one-out minimum

MODELS = ["ltx", "cogvideox", "dynamicrafter"]
# projectile lives in the E0-family files (rows keyed g_true/g_hat, not
# theta/theta_hat like E4's files) -- normalize both shapes to theta/theta_hat
# below so the rest of this script doesn't need to special-case projectile.
PROJECTILE_FILES = {"ltx": "e0_pilot.json", "cogvideox": "e0_pilot_cogvideox.json",
                    "dynamicrafter": "e0_pilot_dynamicrafter.json"}
E4_SYSTEMS = ["pendulum_omega", "pendulum_zeta", "bouncing_ball", "spring_mass", "inclined_slide"]


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _normalize_rows(rows):
    """E0-family rows use g_true/g_hat; E4-family rows use theta/theta_hat.
    Normalize to theta/theta_hat so the rest of this script is system-agnostic."""
    out = []
    for r in rows:
        if "g_true" in r:
            out.append(dict(theta=r["g_true"], theta_hat=r["g_hat"], r2=r["r2"],
                            split=r["split"], seed=r["seed"]))
        else:
            out.append(r)
    return out


def load_rows(model, system, cfg):
    """Returns normalized rows for (model, system), or None if the result
    file does not exist yet (not an error -- just not generated yet)."""
    if system == "projectile":
        path = os.path.join(RESULTS_DIR, PROJECTILE_FILES[model])
    else:
        path = os.path.join(RESULTS_DIR, f"e4_{system}_{model}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        d = json.load(f)
    return _normalize_rows(d["rows"])


def theta_edge_for(system, cfg):
    """The natural 'edge of experience' for select_mechanism()'s H2 clamp
    model: the boundary of the in-range grid nearest the out-of-range side
    that gets swept (matches e7_mechanism_adjudication.py's choice of 15.0
    for projectile, generalized to every system's actual in-range max)."""
    key = {"projectile": "projectile", "pendulum_omega": "damped_pendulum_omega",
          "pendulum_zeta": "damped_pendulum_zeta", "bouncing_ball": "bouncing_ball",
          "spring_mass": "spring_mass", "inclined_slide": "inclined_slide"}[system]
    return float(max(cfg["systems"][key]["in_range"]))


def analyze_pair(model, system, rows, theta_edge):
    gated = [r for r in rows if r["r2"] is not None and r["r2"] >= FIT_R2_GATE
            and r["theta_hat"] is not None
            and not (isinstance(r["theta_hat"], float) and np.isnan(r["theta_hat"]))]
    theta_in = np.array([r["theta"] for r in gated if r["split"] == "in"])
    hat_in = np.array([r["theta_hat"] for r in gated if r["split"] == "in"])
    theta_out = np.array([r["theta"] for r in gated if r["split"] == "out"])
    hat_out = np.array([r["theta_hat"] for r in gated if r["split"] == "out"])

    result = {"n_gated_in": len(theta_in), "n_gated_out": len(theta_out)}

    if len(theta_out) < MIN_GATED_OUT:
        result["status"] = "insufficient_data"
        result["note"] = (f"need >={MIN_GATED_OUT} gated out-of-range points for "
                          f"select_mechanism(); have {len(theta_out)}. Add seeds via "
                          f"e4_generality.py --seeds-out ... --start-seed ... --merge "
                          f"(projectile uses e0_pilot.py / e0_pilot_dynamicrafter.py, "
                          f"same flags -- see slurm_jobs/01-03_e2_gapfill_*.sh).")
        return result

    result["status"] = "adjudicated"
    result["theta_out"] = theta_out.tolist()
    result["hat_out"] = hat_out.tolist()

    mech_free = select_mechanism(theta_out, hat_out, theta0=None, theta_edge=theta_edge)
    result["select_mechanism_theta0_free"] = mech_free
    result["theta_edge"] = theta_edge

    if len(theta_in) >= 2:
        eg = extrapolation_gap(theta_in, hat_in, theta_out, hat_out)
        d, dlo, dhi, p = paired_bootstrap_pre_difference(theta_in, hat_in, theta_out, hat_out, n_boot=2000)
        result["extrapolation_gap"] = eg
        result["paired_bootstrap_PRE_out_minus_in"] = [d, dlo, dhi, p]

    return result


def main():
    cfg = load_config()
    systems = ["projectile"] + E4_SYSTEMS
    results = {}

    for model in MODELS:
        results[model] = {}
        for system in systems:
            rows = load_rows(model, system, cfg)
            if rows is None:
                results[model][system] = {"status": "no_data_file"}
                print(f"{model:14s} {system:16s}  NO DATA FILE YET")
                continue
            theta_edge = theta_edge_for(system, cfg)
            r = analyze_pair(model, system, rows, theta_edge)
            results[model][system] = r
            if r["status"] == "adjudicated":
                m = r["select_mechanism_theta0_free"]
                eg = r.get("extrapolation_gap")
                eg_str = f"EG={eg:.3f}" if eg is not None else "EG=n/a"
                print(f"{model:14s} {system:16s}  n_out={r['n_gated_out']:3d}  "
                     f"{eg_str}  PRI={m['PRI']:.3f}  dAIC={m['dAIC']:+.1f}  "
                     f"selected={m['selected']}")
            else:
                print(f"{model:14s} {system:16s}  n_out={r['n_gated_out']:3d}  "
                     f"INSUFFICIENT (need >={MIN_GATED_OUT})")

    out_path = os.path.join(RESULTS_DIR, "e2_extrapolation.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2,
                 default=lambda o: None if isinstance(o, float) and np.isnan(o) else o)
    print(f"\nWrote {out_path}")

    n_adjudicated = sum(1 for m in results.values() for s in m.values() if s.get("status") == "adjudicated")
    n_total = len(MODELS) * len(systems)
    print(f"\n{n_adjudicated}/{n_total} model-system pairs adjudicated this run. "
         f"See results/e2_extrapolation.json's 'note' field on each "
         f"'insufficient_data' entry for exactly what SLURM job would close that gap.")


if __name__ == "__main__":
    main()
