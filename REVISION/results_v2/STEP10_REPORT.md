# Step 10 — Figures from real frames (2026-11-28)

Review items: T1/M3 (blocking: the v1 paper showed no frame), N3/K4 (AI-drawn, unreadable figures).
Figure 2 (pipeline) stays with you (PaperBanana prompt in `figure2_paperbanana_prompt.md`).

Code: `code/experiments/v2_figures.py` (CPU; runs in `envs/fig`, lock files `env/fig.pip-freeze.txt` and
`env/fig.python-version.txt`, so the pinned `physweep2` env is untouched). Output: `figures/fig_*.{pdf,png}`
and `figures/figures_manifest.json`, which records the selection rules, the chosen clip ids and every
number printed on a figure. Frames are the saved generator outputs, centre-cropped and resized to the
256 × 256 analysis frame, so the overlaid tracks sit in the same coordinates the measurement used.

No clip is chosen by eye. Rules (also in the manifest):

| figure | rule |
|---|---|
| teaser (a) | model with the most valid projectile clips in `main_text` (Wan2.2-I2V-A14B, 85/112); first (scene seed, noise seed) in seed order where g = 1.6, 9.8 and 25 are all valid (scene 0, noise 1000) |
| failures | per failure type, the most extreme clip in `main_text` over all models: most objects in a frame; largest area ratio (size failure only); largest floor-line shift; smallest displacement; for invalid_fit, the lowest R² among clips with one stable object tracked in ≥ 95% of frames |
| trackers | every valid clip whose two trackers disagree (5 of 1,007), ordered by relative difference |

## Draft captions (numbers from the manifest; register them in reproduce_numbers.py before use)

**Teaser.** (a) Three clips from Wan2.2-I2V-A14B that differ only in the requested gravity (scene seed 0,
noise seed 1000); eight frames of each clip are overlaid and the blob track is drawn in red. The ball falls
along nearly the same straight, constant-speed path whether g = 1.6, 9.8 or 25 m s⁻² is requested;
recovered ĝ = −0.05, 0.34 and 0.17 (fit R² ≥ 0.998). (b) Median recovered ĝ against requested g on valid
projectile clips, all nine generators (a point is drawn where at least two clips are valid). Eight
generators stay near ĝ = 0 over the whole grid; HunyuanVideo-1.5 rises within the training range but its
in-range slope is not distinguishable from 0 (`main_text_analysis.md`). Shaded: in-range grid.

**Scenes.** The three systems of the v2 sweep. Left: the conditioning frame in the structured style
(main sweep) and the shaded style (ablation, review T3). Right: the simulator's own motion for three values
of the parameter (height above the floor, or distance along the slope, from the blob track of the rendered
clip; 24 frames, 1 s).

**Failures.** One example per validity failure: extra objects (HunyuanVideo-1.5, up to 7 in a frame), the
ball growing (DynamiCrafter, area up to 78.9× frame 0), a moving floor line (CogVideoX-5B, 8 px), no motion
(DynamiCrafter, at most 0.1 px), and a clean single ball whose motion does not fit the system (Cosmos, fit
R² = −1.46). Labels are assigned in the order fit → camera → shape → static (`validity.classify`), so the
camera example, whose ball also smears along the floor, carries the camera label.

**Trackers.** All five valid clips (of 1,007) on which the blob centroid and CoTracker3 give estimates that
fail the agreement test. Top: tracks over the fitted frames. Bottom: the fitted coordinate over time;
dashed lines mark where each tracker detects floor contact, which ends its fit window. In two clips
(Wan2.2 projectile, LTX-2 slide) the tracks coincide and the estimates differ only because contact is
detected one or several frames apart: fitted on the same frames they agree (7.87 vs 7.68; 0.84 vs 0.84). In
the DynamiCrafter slide both estimates are near zero (−0.11, 0.03). The two bouncing-ball clips are genuine
tracking differences, because restitution is read from bounce-peak heights a few pixels apart: LTX-Video
0.44 vs 0.93, HunyuanVideo-1.5 4.75 vs 3.46 (both above 1: the generated ball gains energy at the bounce).

Same-window estimates are computed by `same_window_estimates()` in the figure script and stored in the
manifest (`trackers.shown[*].same_window_*`).

## Still to do for step 10

- A frame-channel figure once `main_frame` is complete (pair mode: tracked coordinate against the physics
  and linear references; prefix mode: given frames vs. continuation).
- Figure 2: yours.
