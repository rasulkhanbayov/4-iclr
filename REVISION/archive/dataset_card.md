---
license: other
license_name: research-non-commercial-mixed
pretty_name: PhysWeep revision archive
annotations_creators:
  - machine-generated
tags:
  - video-generation
  - physics
  - evaluation
viewer: false
---

# PhysWeep revision archive (private)

Everything the PhysWeep paper's numbers depend on that cannot be re-downloaded: every generated clip,
the per-clip records, re-scored records, analysis outputs, v1 results, job logs, environment lock files
and pinned weight hashes. It is the data half of the project; the code half is the git repository.

**All videos in this archive are machine-generated** by the image-to-video models listed below, from
synthetic scenes rendered by the PhysWeep code. No real footage and no human-subject data.

## Layout

| path | contents |
|---|---|
| `runs/<run>/<model>/` | v2 runs: `clips_shard*.jsonl` (raw records), `clips_rescored.jsonl`, `run_meta_shard*.json`, `videos/<clip_id>.mp4`. Runs: `pilot`, `pilot_b`, `main_text` (9 models x 304 clips), `api_text` (7 x 152) |
| `results_v1/` | the 134 result files and 630 saved clips behind the submitted WACV paper |
| `results_v2/` | v2 analysis outputs, step reports, CPU dry runs |
| `provenance/` | values frozen for the provenance check (file times) |
| `env/` | conda/pip lock files of all four environments, `hf_snapshots.json` (pinned commit + file list of every model repo), `weights_sha256.txt`, DynamiCrafter patch |
| `logs/` | SLURM logs of v1 and v2 jobs |
| `snapshot/` | tarball of the small project files (code, paper sources, notes) |
| `MANIFEST.sha256` | sha256 of every file above (`sha256sum -c MANIFEST.sha256`) |

Restore with `REVISION/archive/restore_data.py` from the code repository (see `REVISION/RESTORE.md`).
Every number in the paper is mapped to these files in `REVISION/PROVENANCE.md`.

## Generators and their terms

The clips inherit the terms of the model that generated them. Checked 2026-10-28 against each license
at the pinned revision. Use is limited to research and non-commercial purposes overall.

| model | repo @ commit | license | conditions on outputs |
|---|---|---|---|
| LTX-Video 2B v0.9 | `Lightricks/LTX-Video@8984fa2` | RAIL-M (2024-11-22) | research purposes only; outputs must be disclosed as machine-generated; Attachment A use restrictions pass through |
| LTX-2 | `Lightricks/LTX-2@dfcc210` | LTX-2 Community License (2026-01-05) | disclose as machine-generated; no training of other models for commercial use; revenue clause unclear for institutions — **check before publishing** |
| CogVideoX-5B-I2V, CogVideoX1.5-5B-I2V | `zai-org/...@a6f0f48`, `@46c9052` | CogVideoX License | outputs belong to the user; academic use free |
| Wan2.2-TI2V-5B, Wan2.2-I2V-A14B | `Wan-AI/...@b8fff73`, `@596658f` | Apache-2.0 | no rights claimed over outputs |
| HunyuanVideo-1.5 480p/720p I2V | `hunyuanvideo-community/...@5a700ee`, `@dcf088e` | Tencent Hunyuan Community License | **outputs may not be used, distributed or displayed in the EU, UK or South Korea**; no use of outputs to improve other AI models; disclose as machine-generated |
| Cosmos-Predict2-2B Video2World | `nvidia/Cosmos-Predict2-2B-Video2World@f50c09f` | NVIDIA Open Model License | generated with the guardrail active; "Built on NVIDIA Cosmos" applies to models trained on these outputs |
| DynamiCrafter 512 (+ Interp) | `Doubiiu/DynamiCrafter_512@9eb8744`, `_Interp@5163d01` | Apache-2.0 file; model card says research/non-commercial | treat as research/non-commercial |

This repository must stay private until the HunyuanVideo-1.5 and LTX-2 points above are resolved (drop
or gate those clips before any public release). It contains no model weights.
