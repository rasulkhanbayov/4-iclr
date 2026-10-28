# Step 2 — Scenes with visible physics (2026-10-15)

CPU only. Code: `code/physweep/render.py` (new `style` argument),
`code/experiments/v2_positive_control.py`. Data: `results_v2/positive_control.json`.
Reference images: `figures/refs/`.

## What changed

Every simulator takes `style ∈ {minimal, structured, shaded}`:

| system | `structured` adds | `shaded` adds on top |
|---|---|---|
| projectile | (floor only, unchanged) | gradient background, textured floor, shaded ball with highlight, drop shadow |
| pendulum (ω, ζ) | ceiling mount, pivot, rod to the bob | same |
| bouncing ball | (floor only, unchanged) | same + drop shadow |
| spring–mass | wall, coil spring that stretches and compresses with the mass, table | same |
| inclined slide | 60° slope wedge the ball rests on (the ball stays radius + 1 px from the surface in every frame; measured) | same |

- `minimal` (the default) is **bit-identical** to the original renderer for
  all five simulators (checked with `np.array_equal` against the untouched
  `4-ICLR/physweep/render.py`), so every v1 result stays reproducible.
- All structure is drawn at grey ≥ 90, outside the tracker's disk mask (≤ 50),
  so the tracker and validity checks still see only the ball.

## Positive control (simulator video → tracker → fit → validity)

215 clips per style (6 axes × in + out grids × 5 seeds):

| style | clips passing fit gate | valid | fit-passing but rejected | pooled PRE (in) | pooled slope (in) | verdict |
|---|---|---|---|---|---|---|
| minimal | 190 | 190 | 0 | 0.0035 [0.0021, 0.0052] | 1.0002 [1.0001, 1.0003] | PASS |
| structured | 190 | 190 | 0 | 0.0035 [0.0021, 0.0052] | 1.0002 [1.0001, 1.0003] | PASS |
| shaded | 190 | 190 | 0 | 0.0039 [0.0024, 0.0057] | 1.0002 [1.0001, 1.0003] | PASS |

- The 25 non-fitting clips in every style are the known physical limits
  (heavily damped pendulum ζ ≥ 0.3, low-restitution balls with too few
  bounces), unchanged from the original E6.
- **The validity checks never reject a correct clip** (0 false rejections in
  570 fit-passing clips across the three styles).
- New in this control: the bouncing ball is now measured through the tracker
  (the original E6 used the simulator's own peak heights). Its in-range slope
  is 1.076 [1.003, 1.181] (structured), slightly above 1. This is the known
  few-bounce precision floor, now visible because the tracker is included.
  To report as is.

## Also fixed

- Table 1 (`paper/main.tex`): pendulum-ω out-of-range grid corrected from
  {0.5, 1, 8, 12} to {8, 12}, matching `systems.yaml` (F7).

## For later steps

- `figures/refs/cond_<system>_<style>.png` (frame 0, 4× upscaled) and
  `strip_<system>_structured.png` (6-frame ground-truth strips): use them as
  PaperBanana reference images, and for the scene-gallery figure.
- The main sweep (step 5) will use `structured` by default and `shaded` as the
  out-of-distribution ablation.
