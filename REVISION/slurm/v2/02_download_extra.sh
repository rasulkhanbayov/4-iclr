#!/bin/bash
#SBATCH -J pw2_download_extra
#SBATCH -o pw2_download_extra_%j.out
#SBATCH -e pw2_download_extra_%j.err
#SBATCH -p cpu-all
#SBATCH -c 4
#SBATCH --mem=16000MB
#SBATCH -t 12:00:00
# Option B + Cosmos guardrail (2026-10-16): the 480p HunyuanVideo-1.5 I2V
# checkpoint, and the guardrail files Cosmos downloads at load time
# (nvidia/Cosmos-1.0-Guardrail is gated; its license must be accepted).
set -euo pipefail
source "/export/home/rakh90100/Rasul_research_ideas (2)/4-ICLR/REVISION/slurm/v2/cluster.env"
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate "$ENV_MAIN"
python - <<'PY'
import os, time
from huggingface_hub import snapshot_download
jobs = [
    ("hunyuanvideo-community/HunyuanVideo-1.5-Diffusers-480p_i2v", None),
    ("nvidia/Cosmos-1.0-Guardrail", ["blocklist/*", "face_blur_filter/*", "video_content_safety_filter/*"]),
    ("Qwen/Qwen3Guard-Gen-0.6B", None),
]
failed = []
for repo, allow in jobs:
    t0 = time.time()
    try:
        p = snapshot_download(repo, allow_patterns=allow)
        size = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(p) for f in fs) / 1e9
        print(f"OK   {repo}: {size:.1f} GB in {time.time() - t0:.0f}s", flush=True)
    except Exception as e:
        failed.append(repo)
        print(f"FAIL {repo}: {type(e).__name__}: {str(e)[:300]}", flush=True)
print("FAILED:", failed if failed else "none")
PY
