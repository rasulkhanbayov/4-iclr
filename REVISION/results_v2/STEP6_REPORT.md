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
