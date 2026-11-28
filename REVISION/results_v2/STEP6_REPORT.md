# Step 6 — Frame-implied channel (2026-10-21): code written and dry-run tested, pilot not yet run

## Design

θ is given only through rendered frames. The prompt is **neutral**: it names
the system but states no value (e.g. "a dark ball moving under gravity on a
plain background, simple physics simulation"). Any faithfulness must
therefore come from the frames. v1 kept the value in the text, which mixed
the two channels.

| model | frame input | how θ enters | time base for the fit |
|---|---|---|---|
| DynamiCrafter (interp checkpoint) | pair: first + middle (projectile) / last frame | positions at two times | key-frame interval / (n_out − 1) |
| Wan2.2-I2V-A14B | pair via `last_image` | same | same |
| LTX-2 | prefix: 9 frames at latent index 0 (`LTX2ConditionPipeline`; condition length is trimmed to 8m+1) | the first 9 frames of the motion | 1 / 24 s; the 9 given frames are not fitted |
| Cosmos-Predict2-2B | prefix: 5 frames (`video=`; gives 2 latent conditioning frames) | the first 5 frames of the motion | 1 / 16 s; the 5 given frames are not fitted |

Prefix frames are rendered at the model's own frame rate, over the same ~1 s
scene duration as the 24-frame clip. Each clip records `key_frame_err_px`:
the ball-position error between the output and the frames it should
reproduce. This checks whether a pair model really starts and ends on its key
frames; Wan2.2-A14B was not specifically trained for first/last-frame input.

## Checked against sources (installed diffusers 0.39.0)

- `LTX2ConditionPipeline` uses the same weights; its `audio_scheduler` is
  optional (copied from `scheduler`). A condition's `index` is a LATENT
  index, and its length is trimmed to 8m+1 frames.
- `Cosmos2VideoToWorldPipeline` with `video` of k frames conditions on
  (k − 1)//4 + 1 latent frames and copies the input to the start of the output.
- `WanImageToVideoPipeline` handles `last_image` generically: it places the
  last frame at the end of the conditioning video.

## Verified (CPU dry run with simulator stand-ins)

| mode | valid | median / max rel. error | key-frame error |
|---|---|---|---|
| text (regression) | 12/12 | 0.4% / 1.5% | ≤ 0.14 px |
| pair | 12/12 | 1.3% / 6.5% | ≤ 0.49 px |
| prefix (16 fps, k = 5) | 12/12 | projectile, slide ≤ 3%; ball 4–15% (fewer bounces in 16 frames, the known floor) | ≤ 0.14 px |

Two bugs were caught by the dry run before any GPU time:
1. The simulator's pair mode rendered a shorter clip, which changes the
   projectile's launch speed. Fixed by sampling a dense clip of the same
   duration.
2. Prefix frames rendered over 24 frames at 16 fps stretched the scene to
   1.44 s, so the projectile arc left the top of the frame at high g (2/12
   clips failed). Fixed with `prefix_clip_frames()`: the same ~1 s duration
   at any frame rate.

## Jobs

`pilot_frame_a100.tasks` (DynamiCrafter) and `pilot_frame_h200.tasks`
(Wan2.2-A14B, LTX-2, Cosmos), run with the existing `20_sweep_*.sh`
workers, which now pass extra arguments (`--channel frame --pilot`) through
from the task file.

---

# Pilot on the GPU (2026-11-27)

Jobs 482639 (DynamiCrafter, A100) and 482640 (Wan2.2-A14B, LTX-2, Cosmos, H200), run `pilot_frame`: 12
clips per model (lowest and highest in-range θ, scene seeds 0–1, noise seed 1000), 0 errors. Numbers
below are from the rescored records (`clips_rescored.jsonl`; no label changed on rescoring).

## Gate 1: does the output reproduce the given frames?

Yes, for every model. Ball-position error at the conditioning frames, median / max over all key frames:
DynamiCrafter 0.22 / 0.36 px, Wan2.2-A14B 0.20 / 0.50 px, LTX-2 0.12 / 2.18 px (one clip's 9th prefix
frame), Cosmos 0.22 / 0.33 px. Wan2.2 handles `last_image` correctly even though it was not trained
specifically for first/last-frame input.

## Gate 2: do the given frames carry θ? (ideal observer, ground-truth inputs, CPU)

| system | pair (first + middle/last frame) | prefix (LTX-2: 9 frames at 24 fps; Cosmos: 5 at 16 fps) |
|---|---|---|
| projectile | strong: key-frame rise 23 px (g=5) to 69 px (g=15) | strong: prefix acceleration ∝ g |
| inclined slide | weak: displacement 112 → 92 px over μ = 0.1 → 0.4 | weak: prefix displacement differs by 2.5 px (LTX-2) / 1.5 px (Cosmos) over the in-range grid |
| bouncing ball | **none**: first and last frame are the same for e = 0.2–0.8 | partial: the prefix contains the first bounce |

Bouncing ball is therefore left out for the two pair models in the main run (it cannot test anything).

## Pilot results (valid clips; θ̂ per clip)

| model | valid | projectile | inclined slide | bouncing ball |
|---|---|---|---|---|
| DynamiCrafter (pair) | 7/12 | g=5: 1.87, 2.93; g=15: 7.20, 14.65 | μ=0.1: 2.87; μ=0.4: 1.42, 1.48 | 0/4 valid |
| Wan2.2-A14B (pair) | 9/12 | g=5: 92.8, 117.1; g=15: 16.3, 16.1 | μ=0.1: 1.34, 1.49; μ=0.4: 1.67, 1.71 | e=0.9: 0.93 |
| LTX-2 (prefix) | 8/12 | g=15: 9.13 | μ=0.1: 1.14, 1.16; μ=0.4: 1.13, 1.16 | e=0.6: 0.97; e=0.9: 0.96, 1.10 |
| Cosmos (prefix) | 2/12 | 0/4 valid | μ=0.1: 1.72; μ=0.4: 1.71 | 0/4 valid |

Readings to test in the main run (12 clips per model is too few for claims):
- **Pair mode measures the in-between timing, given fixed endpoints.** Two reference points:
  linear interpolation gives g = 0 and μ = tan 60° = 1.73 (zero acceleration); a physical ease-out gives
  the true θ. Wan2.2 at g = 15 follows the physical profile (RMS 2.1 px from it vs 14.6 px from linear);
  on the slide both pair models land much closer to the linear reference than to the true μ (μ̂ 1.34–1.71,
  one DynamiCrafter clip 2.87, i.e. decelerating). The main analysis
  should report pair-mode θ̂ against both references, not only against θ.
- **Wan2.2 at g = 5 meets the apex key frame by inserting a bounce**: the ball falls to the floor, then
  rises above its start (energy gain). The fit uses only the pre-contact fall, so θ̂ ≈ 93–117 is a correct
  measurement of the generated fall. This is a failure of the generated motion, not of the measurement;
  no validity rule was added after seeing the pilot. Count it separately (ground contact before the second
  key frame: 2/4 Wan2.2 projectile clips, 0/4 DynamiCrafter).
- **Prefix models continue at their own default.** LTX-2's slide continues with the same deceleration for
  μ = 0.1 and 0.4 (μ̂ 1.13–1.16), and its ball converges to e ≈ 1, as in the text channel; Cosmos's slide
  continues at constant speed (μ̂ ≈ 1.71 ≈ tan 60°). The slide signal in a 5–9-frame prefix is weak (gate 2),
  so the projectile is the decisive system for these two models.

## Main run (submitted after this pilot)

Run `main_frame`, crossed design, 4 scene × 4 noise seeds, full grid (in-range + lowest and highest
out-of-range θ): `frame_a100.tasks` (DynamiCrafter, projectile + slide, 208 clips, ~6 GPU-h) and
`frame_h200.tasks` (Wan2.2-A14B 208 clips in 2 shards ~9 GPU-h; LTX-2 304 clips ~2 GPU-h; Cosmos 304 clips
in 3 shards ~24 GPU-h). Total ≈ 41 GPU-h. Per-clip times from the pilot: DynamiCrafter 107 s, Wan2.2 149 s
(+33 min load), LTX-2 20 s (+26 min load), Cosmos 282 s.

---

# Main run complete (2026-11-28)

Run `main_frame`, jobs 483547 (DynamiCrafter) and 483548 (Wan2.2-A14B, LTX-2, Cosmos): 1,024 clips (Cosmos 304,
LTX-2 304, Wan2.2 208, DynamiCrafter 208), 0 errors, all rescored. Files: `main_frame_analysis.md`
(v2_analyze: validity, β, PRE, variance shares), `main_frame_frame.md` (v2_frame_analysis: key frames, frame vs
text, pair-mode timing, rebounds, sweep-level CIs), `lostframe_check.md`, `window_sensitivity.md`.

**Key frames are reproduced** by all four models: median error 0.12–0.26 px; 3 LTX-2 bouncing-ball clips
miss a prefix frame by more than 2 px (max 2.24 px).

**In-range slope, frame vs. text channel (valid clips).** A slope is called nonzero only if both the clip-level
and the sweep-level CI exclude 0.

| model / system | mode | valid frame | β frame [clip CI] (sweep CI) | β text [clip CI] |
|---|---|---|---|---|
| LTX-2 / projectile | prefix | 56/112 | **0.92 [0.29, 1.46] (0.23, 1.60)** | −0.05 [−0.26, 0.15] |
| LTX-2 / slide | prefix | 96/96 | −0.07 [−0.82, 0.65] | −0.03 [−0.78, 0.77] |
| LTX-2 / ball | prefix | 39/96 | 0.28 [0.02, 0.54] (−0.02, 0.63): not claimed | −0.18 [−1.80, 1.15] |
| Cosmos / projectile | prefix | 0/112 | – | −0.00 [−0.02, 0.02] |
| Cosmos / slide | prefix | 10/96 | 0.03 [−0.07, 0.17] | −0.01 [−0.07, 0.06] |
| DynamiCrafter / projectile | pair | 102/112 | −0.11 [−0.47, 0.29] | 0.01 [−0.02, 0.03] |
| DynamiCrafter / slide | pair | 85/96 | −0.53 [−1.58, 0.42] | −0.16 [−2.19, 1.78] |
| Wan2.2 / projectile | pair | 97/112 | −3.05 [−14.43, 10.90] | 0.05 [−0.10, 0.23] |
| Wan2.2 / slide | pair | 92/96 | **0.27 [0.10, 0.46] (0.10, 0.44)** | −0.05 [−1.05, 0.96] |

**Readings.**
1. **The frame channel carries θ for one model.** LTX-2 continues a 9-frame projectile prefix with the
   prefix's acceleration: median ĝ 1.50, 3.84, 5.00, 7.07, 9.71, 14.78, 20.29 for g = 1.6 … 25 (valid clips). The
   same model ignores g in the text channel. Request share of θ̂ variance 0.19 (p = 0.004).
2. **Valid rate falls with g for LTX-2** (16/16 clips at g = 1.6; 3–6/16 at g ≥ 9.8). Cause, from the tracks:
   the ball falls to 10–25 px above the drawn floor line and rebounds without touching it (48/112 clips, 43 of
   its 52 invalid_fit). The fit window ends only at contact with the drawn floor, so it runs into the
   rebound. (`early_rebound`, defined after the run; changes no label.)
3. **Cosmos follows the prefix for about one second, then the object degrades.** Registered: 0/112 projectile
   clips valid (93-frame, 5.8-s clips; the ball shrinks and fades). Over the scene's own 1 s with the same
   rules (exploratory, `window_sensitivity.md`): 93/112 valid, β = 0.71 [0.54, 0.89].
4. **Pair mode interpolates timing, not physics.** Between fixed endpoints, the tracked path is closer to
   constant-speed motion than to the true motion in most clips: DynamiCrafter projectile 36/102 closer to
   physics (median RMS 6.1 px physics vs 3.9 px linear), slide 5/85; Wan2.2 projectile 30/97, slide 0/92 (1.0 px
   from linear). Wan2.2's small positive slide slope: μ̂ rises from 1.59 to 1.71 over the grid, just below
   tan 60° = 1.73 (constant speed), i.e. a slight acceleration that shrinks as μ grows; its cause is not
   established. Wan2.2 meets the apex key frame by inserting a bounce in 33/112 projectile clips.
5. **Sensitivity checks** (both exploratory, defined after seeing the data): the 1-s window gives LTX-2
   β = 0.71 [0.56, 0.86], ρ = 0.90 on 108/112 clips, and leaves every text-channel slope CI including 0; the
   lost-frame rule check adds 7 valid frame-channel clips and removes none.

**For the paper:** text-specified θ is ignored by all nine generators; frame-implied θ is followed by LTX-2
for the projectile (and by Cosmos briefly, before its object degrades); pair-conditioned models interpolate
between the key frames at nearly constant speed. One model and one system: state it as such. Register every
number above in `reproduce_numbers.py` before use.
