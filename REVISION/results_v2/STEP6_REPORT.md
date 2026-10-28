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
