# Step 3 — Scene seed and noise seed separated (2026-10-15)

CPU only. New code: `code/physweep/design.py`, `code/physweep/conditioning.py`,
`code/physweep/prompts.py`, `code/physweep/decomposition.py`,
`code/experiments/v2_design_selftest.py`. Data: `results_v2/design_selftest.json`.

## Deviation from the plan's wording

The plan said "separate the seeds in every experiment script". Instead, the
v1 scripts are **left unchanged**, so the v1 numbers stay reproducible, and
all new runs go through one new harness built from these modules. The step 4
pilot and step 5 sweep will use only the new harness.

## What was built

- **`design.py`**: a fully crossed design of requested θ × `scene_seed` ×
  `noise_seed`. Scene seeds come from 0 and noise seeds from 1000, so the two
  ranges can never overlap. **API mode** gives every clip a fresh, never-reused
  noise seed (Tier 1, "no seed control"). Deterministic clip ids and sharding
  are included for SLURM arrays.
  - **Size correction:** the default grid is 7 θ for the projectile but 6 for
    the bouncing ball and slide (they have 4 in-range values, not 5), giving
    **304 clips per model**, not 336 as the plan said. The plan is updated.
- **`conditioning.py`**: builds the generator input from the scene seed only.
  Text channel = first frame + prompt; frame channel = first + middle frame
  (projectile) or first + last frame, or the first k frames for
  video-continuation models.
- **`prompts.py`**: the v1 prompt text copied verbatim, so any v1/v2
  difference comes from the scene, not the wording.
- **`decomposition.py`**: request / scene / noise / residual shares of the
  variance of θ̂ (LMG/Shapley over an additive dummy-coded model, robust to
  missing clips). It reports a chance-corrected share, permutation p-values,
  bootstrap CIs, and a `confounded` flag when scene and noise can't be
  separated.

## Self-test results

| check | result |
|---|---|
| crossed design size, unique ids, disjoint seed ranges, API seeds unique | pass (304 clips) |
| text conditioning identical across noise seeds, different across scene seeds | pass |
| frame-channel conditioning varies with θ | pass |
| decomposition recovers the true generating factor (single draw, 40% clips dropped) | 6/6 scenarios |
| repeated over 20 random draws each | 119/120 pass; median error 0.01–0.04; worst 0.14 (one mixed scene+noise draw) |
| false positives on no-structure data (pure noise, global default), p < 0.01 | 0/40 |
| v1 coupled design (one seed for scene and noise) | flagged `confounded`, shares split 0.49/0.49: not identifiable, as expected |

## Two corrections made during this step (both logged)

1. **Test criteria.** The first version required fixed share thresholds,
   which failed when a random draw happened to give a small scene effect, and
   on chance-level request shares. It now compares each estimate with the
   *realized* true share and uses permutation p-values for the no-structure
   scenarios. Changed after seeing failures, and recorded as such.
2. **Estimator.** The first chance correction subtracted the shuffled-label
   null mean. That over-corrects when a factor truly explains most of the
   variance (0.89 estimated vs 1.00 true). It was replaced by the standard
   adjusted-R²/ω² correction, (k−1)/(n−p) × residual share. This is a fix to
   the method itself, not only to the test.

## Limitation to state in the paper

With 4 scene and 4 noise levels, the scene/noise split for a *mixed* mechanism
is accurate to about ±0.05 typically and ±0.14 worst case. Single-mechanism
cases are within ±0.075.
