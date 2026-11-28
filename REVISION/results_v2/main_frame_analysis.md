# Analysis of run `main_frame`

Metrics on VALID clips only. β = in-range faithfulness slope (1 = faithful, 0 = ignores the request).
Shares = chance-corrected variance shares of θ̂ (request / scene / noise); p-values from label permutation.

| model / system | clips | valid | 2nd-tracker confirmed | β in-range [95% CI] | Spearman ρ | PRE in | PRE out | request share (p) | scene share (p) | noise share (p) |
|---|---|---|---|---|---|---|---|---|---|---|
| cosmos2_2b/bouncing_ball | 96 | 0 | 0 | — | — | — | — | — | — | — |
| cosmos2_2b/inclined_slide | 96 | 10 | 5 | 0.03 [-0.07, 0.17] | 0.07 | 1.17 | 1.03 | 0.18 (0.852) | 0.78 (0.022) | 0.04 (0.639) |
| cosmos2_2b/projectile | 112 | 0 | 0 | — | — | — | — | — | — | — |
| dynamicrafter/inclined_slide | 96 | 85 | 85 | -0.53 [-1.58, 0.42] | 0.19 | 1.12 | 0.96 | 0.00 (0.519) | 0.00 (0.864) | 0.11 (0.006) |
| dynamicrafter/projectile | 112 | 102 | 100 | -0.11 [-0.47, 0.29] | -0.21 | 0.78 | 0.70 | 0.19 (0.002) | 0.01 (0.437) | 0.25 (0.002) |
| ltx2/bouncing_ball | 96 | 39 | 35 | 0.28 [0.02, 0.54] | 0.32 | 0.13 | 0.37 | 0.20 (0.030) | 0.00 (0.888) | 0.17 (0.020) |
| ltx2/inclined_slide | 96 | 96 | 87 | -0.07 [-0.82, 0.65] | -0.17 | 1.20 | 0.97 | 0.09 (0.006) | 0.00 (0.798) | 0.58 (0.002) |
| ltx2/projectile | 112 | 56 | 51 | 0.92 [0.29, 1.46] | 0.54 | 0.51 | 0.25 | 0.19 (0.004) | 0.02 (0.271) | 0.23 (0.002) |
| wan22_i2v_a14b/inclined_slide | 96 | 92 | 92 | 0.27 [0.10, 0.46] | 0.43 | 1.16 | 2.83 | 0.13 (0.002) | 0.00 (0.944) | 0.10 (0.002) |
| wan22_i2v_a14b/projectile | 112 | 97 | 96 | -3.05 [-14.43, 10.90] | 0.07 | 8.87 | 25.36 | 0.00 (0.511) | 0.01 (0.339) | 0.02 (0.176) |
