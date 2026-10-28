#!/bin/bash
#SBATCH -J pw2_download
#SBATCH -o pw2_download_%j.out
#SBATCH -e pw2_download_%j.err
#SBATCH -p cpu-all
#SBATCH -c 4
#SBATCH --mem=16000MB
#SBATCH -t 2-00:00:00
# Downloads all weights into $HF_HOME on /export/hbku-research (~350-450 GB).
# Needs: 00_setup_envs.sh done; HF_TOKEN in 4-ICLR/.env (read by cluster.env); the Cosmos
# license accepted at https://huggingface.co/nvidia/Cosmos-Predict2-2B-Video2World
# Safe to re-run: snapshot_download skips files already present.
set -euo pipefail
source "/export/home/rakh90100/Rasul_research_ideas (2)/4-ICLR/REVISION/slurm/v2/cluster.env"
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate "$ENV_MAIN"
df -h "$BASE" | tail -1
python - <<'PY'
import os, time
from huggingface_hub import snapshot_download
repos = [
    ("Lightricks/LTX-Video", ["model_index.json", "scheduler/*", "text_encoder/*", "tokenizer/*", "transformer/*", "vae/*"],
     None),  # diffusers subfolders only; the root holds ~270 GB of single-file checkpoints we do not use
    ("zai-org/CogVideoX-5b-I2V", None, None),
    ("Wan-AI/Wan2.2-TI2V-5B-Diffusers", None, None),
    ("zai-org/CogVideoX1.5-5B-I2V", None, None),
    ("Wan-AI/Wan2.2-I2V-A14B-Diffusers", None, None),
    ("hunyuanvideo-community/HunyuanVideo-1.5-Diffusers-720p_i2v", None, None),   # used by the first pilot only
    ("hunyuanvideo-community/HunyuanVideo-1.5-Diffusers-480p_i2v", None, None),   # option B
    ("Lightricks/LTX-2", ["model_index.json", "scheduler/*", "text_encoder/*", "tokenizer/*", "transformer/*", "vae/*",
                          "audio_vae/*", "connectors/*", "vocoder/*"], None),  # diffusers subfolders only
    ("nvidia/Cosmos-Predict2-2B-Video2World", None, ["*.pt"]),                   # gated; diffusers format only
]
failed = []
for repo, allow, ignore in repos:
    t0 = time.time()
    try:
        p = snapshot_download(repo, allow_patterns=allow, ignore_patterns=ignore)
        size = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(p) for f in fs) / 1e9
        print(f"OK   {repo}: {size:.1f} GB in {time.time() - t0:.0f}s", flush=True)
    except Exception as e:
        failed.append(repo)
        print(f"FAIL {repo}: {type(e).__name__}: {str(e)[:300]}", flush=True)
print("FAILED:", failed if failed else "none")
PY
df -h "$BASE" | tail -1
