"""
physweep/conditioning.py
========================
Build a generator's input for one design row. Depends on the scene seed only,
never on the noise seed.

  text channel   first rendered frame + a prompt stating theta
  frame channel  rendered frames whose motion already implies theta, plus a
                 NEUTRAL prompt that does not state theta (added 2026-10-21),
                 so any faithfulness must come from the frames. Two forms:
    "pair"    two key frames, for first/last-frame models (DynamiCrafter-interp,
              Wan2.2). The generated clip is assumed to span key frame 1 ->
              key frame 2, so its frame interval is (t2 - t1) / (n_out - 1);
              the run records whether the output really starts and ends on
              the key frames.
    "prefix"  the first k frames, for video-continuation models (LTX-2,
              Cosmos), rendered AT THE MODEL'S OWN FRAME RATE (dt_scale =
              24 / model_fps): otherwise a 16 fps model would read our 24 fps
              frames as slower motion. The k given frames reappear at the
              start of the output and are excluded from the fit.

Key-frame choice for the pair (from v1, experiments/e8_conditioning_channel.py):
the projectile arc is symmetric, so its last frame is identical for every g;
the middle frame is used instead. For the other systems the last frame varies
with theta and is used.
"""

from __future__ import annotations

import numpy as np

from physweep import render as R
from physweep.design import CFG_KEY, load_cfg
from physweep.prompts import build_prompt

PROJECTILE_CLEARANCE_PX = 100   # ball clearly mid-air, as in every v1 run

NEUTRAL_PROMPTS = {
    "projectile": "a dark ball moving under gravity on a plain background, simple physics simulation",
    "bouncing_ball": "a dark ball bouncing on the ground, simple physics simulation, plain background",
    "inclined_slide": "a dark ball sliding down an incline, simple physics simulation, plain background",
    "pendulum_omega": "a dark ball on a pendulum swinging, simple physics simulation, plain background",
    "pendulum_zeta": "a dark ball on a pendulum swinging, simple physics simulation, plain background",
    "spring_mass": "a dark ball attached to a spring oscillating, simple physics simulation, plain background",
}


def prefix_clip_frames(k: int, model_fps: float) -> int:
    """Length of the clip the prefix is cut from: the same ~1 s duration as the 24-frame, 24 fps clip.
    (The projectile's launch speed is set from the clip duration, so rendering 24 frames at 16 fps
    would stretch the arc to 1.44 s and send it off the top of the frame at high g.)"""
    return max(k, int(round(R.N_FRAMES * float(model_fps) / R.FPS)))


def render_ground_truth(system: str, theta: float, scene_seed: int, style: str, n_frames: int | None = None,
                        cfg: dict | None = None, dt_scale: float = 1.0) -> np.ndarray:
    cfg = cfg or load_cfg()
    sc = cfg["systems"][CFG_KEY.get(system, system)]
    n = n_frames or sc.get("n_frames", R.N_FRAMES)
    kw = dict(seed=scene_seed, n_frames=n, style=style, dt_scale=dt_scale)
    if system == "projectile":
        return R.simulate_projectile(g=theta, ground_clearance_px=PROJECTILE_CLEARANCE_PX, **kw)[0]
    if system == "pendulum_omega":
        return R.simulate_damped_pendulum(omega=theta, zeta=sc["fixed_zeta"], **kw)[0]
    if system == "pendulum_zeta":
        return R.simulate_damped_pendulum(omega=sc["fixed_omega"], zeta=theta, **kw)[0]
    if system == "bouncing_ball":
        return R.simulate_bouncing_ball(e=theta, **kw)[0]
    if system == "spring_mass":
        return R.simulate_spring_mass(k=theta, mass_kg=sc["mass_kg"], **kw)[0]
    if system == "inclined_slide":
        return R.simulate_inclined_slide(mu=theta, incline_deg=sc["incline_deg"], **kw)[0]
    raise ValueError(system)


def build_conditioning(row: dict, frame_mode: str = "pair", k: int = 5, model_fps: float | None = None) -> dict:
    """Return {"frames", "prompt", "channel", "frame_mode", "key_times", "n_given"}.

    key_times: seconds (in the scene's own time) of each conditioning frame.
    n_given: number of leading OUTPUT frames that are copies of the input and
             must be excluded from the fit (prefix mode only)."""
    out = dict(channel=row["channel"], frame_mode=None, n_given=0)
    if row["channel"] == "text":
        gt = render_ground_truth(row["system"], row["theta"], row["scene_seed"], row["style"])
        out.update(frames=[gt[0]], key_times=[0.0],
                   prompt=build_prompt(row["system"], row["theta"], row.get("prompt_variant", "default")))
        return out
    if row["channel"] != "frame":
        raise ValueError(row["channel"])
    out["prompt"] = NEUTRAL_PROMPTS[row["system"]]
    out["frame_mode"] = frame_mode
    if frame_mode == "pair":
        gt = render_ground_truth(row["system"], row["theta"], row["scene_seed"], row["style"])
        second = len(gt) // 2 if row["system"] == "projectile" else len(gt) - 1
        out.update(frames=[gt[0], gt[second]], key_times=[0.0, second * R.DT])
    elif frame_mode == "prefix":
        if not model_fps:
            raise ValueError("prefix mode needs the model's frame rate")
        gt = render_ground_truth(row["system"], row["theta"], row["scene_seed"], row["style"],
                                 n_frames=prefix_clip_frames(k, model_fps), dt_scale=R.FPS / float(model_fps))
        out.update(frames=list(gt[:k]), key_times=[i / float(model_fps) for i in range(k)], n_given=k)
    else:
        raise ValueError(frame_mode)
    return out
