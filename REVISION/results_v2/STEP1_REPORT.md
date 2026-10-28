# Step 1 — Measurement validity layer (2026-10-15)

CPU only. Code: `code/physweep/validity.py`,
`code/experiments/v2_validity_injection.py`,
`code/experiments/v2_validity_reanalysis.py`. Data:
`results_v2/validity_injection.json`, `results_v2/validity_reanalysis.json`.

## What the checks are

Beyond the old fit gate ($R^2 \ge 0.8$): exactly one object in ≥90% of frames;
object area within 0.5–2× its first-frame area in ≥90% of frames; agreement
with CoTracker3; and (amendment 1, see below) a static object is invalid for
the bouncing ball, pendulum and spring. Thresholds were fixed in code before
the re-analysis. Amendment 1 was added after the first pass and is reported as
such.

## 1. Injection test: the checks catch what the fit gate misses

Simulator clips with injected artifacts (5 seeds × in-range grid):

| artifact | fit gate passes | median $R^2$ | median rel. error | new checks pass |
|---|---|---|---|---|
| clean | 65/65 | 1.000 | ≤ 0.04 | 65/65 |
| still object (projectile, slide) | 45/45 | — | — | 45/45 (flagged static) |
| dripping fragments | 46/65 | 0.99–1.00 | 0.72 (proj.), 3.72 (slide) | **0** |
| duplicated object | 63/65 | 1.000 | 0.50 (proj.), 3.12 (slide) | **0** |
| ballooning object | 45/65 | 1.000 | 0.91 (proj.), 5.38 (slide) | **0** |

So a perfect fit can come with a 50–540% error, and every such artifact is
rejected. This directly answers reviewer Novy (N1).

## 2. Re-analysis of the 630 saved clips

| pair | clips | old gate | valid | broken object | static, unidentifiable | 2nd tracker confirms | in-range slope, old gate | in-range slope, valid |
|---|---|---|---|---|---|---|---|---|
| projectile / LTX | 40 | 19 | 11 | 8 | 0 | 11 | 0.277 | 0.019 |
| projectile / DynamiCrafter | 40 | 28 | 8 | 20 | 0 | 8 | −0.063 | 0.005 |
| bouncing ball / LTX | 35 | 2 | 2 | 0 | 0 | 0 | — | — |
| bouncing ball / CogVideoX | 35 | 1 | 0 | 1 | 0 | 0 | — | — |
| bouncing ball / DynamiCrafter | 35 | 5 | 0 | 1 | 4 | 0 | 55.2 | — |
| inclined slide / LTX | 35 | 11 | 8 | 3 | 0 | 6 | −0.464 | −0.037 |
| inclined slide / DynamiCrafter | 35 | 25 | 9 | 16 | 0 | 8 | 0.703 | 0.665 |
| pendulum ζ / DynamiCrafter | 30 | 4 | 0 | 1 | 3 | 0 | — | — |
| all other 10 pairs | 360 | 0 | 0 | 0 | 0 | 0 | — | — |
| **total** | **630** | **95** | **38** | **50** | **7** | **33** | | |

**60% of clips that passed the old gate (57/95) are not valid measurements.**
Every rejection checked by eye was correct: fragmentation (DC projectile seed
1), a second ball (DC projectile seed 0, DC slide seed 0), ballooning (LTX
projectile seed 4), and a camera zoom-out with a tilting floor (LTX slide
seed 1).

## 3. What survives, and what doesn't

**Survives:** "conditioning does not move the realized parameter". On valid
clips the in-range slope is about 0 (0.019, 0.005, −0.037). The one exception,
DC slide at 0.665, rests on 5 clips, 4 when restricted to confirmed ones
(slope 0.23).

**New, simpler reading of the "confident wrong defaults":** the valid clips
mostly show **no acceleration at all**.
- Projectile: all 19 valid clips have |ĝ| < 0.5 m/s², i.e. the ball doesn't fall.
- DC slide: 7 of 9 valid clips sit within 0.15 of tan 60° = 1.732, the value
  the fitter returns for zero acceleration (no sliding).
- DC bouncing ball: the ê ≈ 1.0 of Figure 1(b) comes from a ball moving < 1 px,
  i.e. sub-pixel jitter (now labelled invalid_static).

**Does not survive (on the models with saved video):**
- DC projectile seed clusters (6.5, −2.1, 3.5): all broken objects. Only seed 3
  (ĝ ≈ 0, still ball) is valid.
- The "split-default" variant (DC slide seed 0): a duplicated object.
- Figure 1(b), "always perfectly elastic": a static ball.
- LTX seed 4's apparent response to g: a ballooning, splitting object.

**Not yet testable:** Figure 1(a), CogVideoX projectile (ĝ ≈ −11.4 / −7.1),
the only clusters with real falling motion. The E0 run saved no video, and the
saved-video run used a shorter frame budget where no clip passed the gate. The
only visual evidence is three stills of one clean ball falling
(`results_v1/e0_debug_evidence/cogvideox_g25_*`). It must be regenerated with
video in step 5.

## 4. Caveats

- The saved clips are a later replication run, not the paper's own E0/E4 run.
  The two runs are not bit-identical, but per-seed cluster means reproduce
  closely (e.g. DC projectile seeds 0/1/3/4: 0.10/6.51/−0.03/−2.02 vs
  0.07/6.46/−0.03/−2.12).
- Stored θ̂ was computed on in-memory frames before mp4 compression.
  Re-tracking the mp4 reproduces it within 5% for 67/90 clips; 13 of the 23
  mismatches are broken-object clips. The labels above use the stored θ̂ and
  shape statistics from the mp4.
- CoTracker3 values come from the earlier run (`e5a_cotracker_comparison.json`);
  no GPU was used in this step.

## 5. Consequences for the plan

1. The headline must change from "the seed picks a wrong constant" to roughly:
   *under text conditioning these generators almost never realize the
   requested dynamics. Valid clips show no acceleration, and over half of the
   apparently well-fit clips are broken objects that a fit-quality gate
   accepts.* The seed question is still worth asking in step 5, but only on
   valid clips.
2. Step 2 (scenes with a visible slope, floor, rod and spring) matters more
   now: a lone dot may simply not read as a physical scene, which could explain
   the static outputs.
3. The validity layer is part of the protocol from here on, and every new run
   saves its video.
