"""
physweep/design.py
==================
The v2 sweep design: requested parameter, scene seed and noise seed are three
separate, fully crossed factors.

In v1 one integer `seed` drove both the renderer (scene layout) and the
generator (sampling noise), so their effects were inseparable
(REVISION/01_review_analysis.md, N2). Here:

  scene_seed  seeds only the renderer (initial position, amplitude, ...)
  noise_seed  seeds only the generator's sampling noise

Seed ranges are disjoint (scene seeds from 0, noise seeds from NOISE_BASE),
so a value can never be reused by accident for both roles.

"api" mode gives every clip a fresh, never-reused noise seed. That is what a
closed API offers (no seed control), and it is used to show the seed-free
metrics work without seed access (plan §7, Tier 1).
"""

from __future__ import annotations

import hashlib
import os

import yaml

CFG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "configs", "systems.yaml")
CFG_KEY = {"pendulum_omega": "damped_pendulum_omega", "pendulum_zeta": "damped_pendulum_zeta"}
NOISE_BASE = 1000
API_NOISE_BASE = 500_000

# Default v2 grid: 5 in-range + the lowest and highest out-of-range value.
DEFAULT_SYSTEMS = ("projectile", "bouncing_ball", "inclined_slide")


def load_cfg() -> dict:
    with open(CFG_PATH) as f:
        return yaml.safe_load(f)


def theta_grid(system: str, cfg: dict | None = None, n_out: int = 2):
    cfg = cfg or load_cfg()
    sc = cfg["systems"][CFG_KEY.get(system, system)]
    out = sorted(sc["out_of_range"])
    if n_out == 2 and len(out) > 2:
        out = [out[0], out[-1]]
    return [(t, "in") for t in sc["in_range"]] + [(t, "out") for t in out]


def clip_id(row: dict) -> str:
    key = "|".join(str(row[k]) for k in ("system", "theta", "scene_seed", "noise_seed", "style", "channel", "prompt_variant"))
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def build_design(systems=DEFAULT_SYSTEMS, n_scene: int = 4, n_noise: int = 4, style: str = "structured",
                 channel: str = "text", prompt_variant: str = "default", mode: str = "crossed",
                 n_out: int = 2) -> list[dict]:
    """Return one dict per clip. mode="crossed": every theta x scene x noise.
    mode="api": every theta x scene x n_noise samples, each with a fresh noise seed."""
    cfg = load_cfg()
    rows, api_counter = [], 0
    for system in systems:
        for theta, split in theta_grid(system, cfg, n_out):
            for s in range(n_scene):
                for z in range(n_noise):
                    if mode == "crossed":
                        noise = NOISE_BASE + z
                    elif mode == "api":
                        noise = API_NOISE_BASE + api_counter
                        api_counter += 1
                    else:
                        raise ValueError(mode)
                    row = dict(system=system, theta=theta, split=split, scene_seed=s, noise_seed=noise,
                               style=style, channel=channel, prompt_variant=prompt_variant, mode=mode)
                    row["clip_id"] = clip_id(row)
                    rows.append(row)
    ids = [r["clip_id"] for r in rows]
    assert len(set(ids)) == len(ids), "clip_id collision"
    return rows


def shard(rows: list[dict], index: int, count: int) -> list[dict]:
    """Deterministic round-robin split for SLURM job arrays."""
    return rows[index::count]
