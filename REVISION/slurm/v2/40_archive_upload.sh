#!/bin/bash
#SBATCH -J pw2_archive
#SBATCH -o pw2_archive_%j.out
#SBATCH -e pw2_archive_%j.err
#SBATCH -p cpu-all
#SBATCH -c 4
#SBATCH --mem=16000MB
#SBATCH -t 1-00:00:00
# CPU job (the 01_download job showed cpu-all has internet): upload the archive to the private HF dataset,
# download all of it back into $BASE/verify_restore, check every sha256, and recompute every number from
# the downloaded copy. Deletes nothing. Safe to resubmit: it reuses a complete staging manifest, and
# upload_large_folder and restore_data.py both skip work already done.
# Needs: a WRITE token in the HF_TOKEN= line of 4-ICLR/.env (or HF_TOKEN exported before sbatch).
set -euo pipefail
source "/export/home/rakh90100/Rasul_research_ideas (2)/4-ICLR/REVISION/slurm/v2/cluster.env"
PY="$ENV_MAIN/bin/python"
V="$BASE/verify_restore"
cd "$ICLR/REVISION"

echo "== 1/4 upload ($(date))"
REUSE=""
[ -f "$BASE/hf_archive_staging/MANIFEST.sha256" ] && REUSE="--reuse-staging"
"$PY" archive/upload_to_hf.py --upload $REUSE

echo "== 2/4 compare every file on HF with the local original, no download ($(date))"
"$PY" archive/check_hf.py

echo "== 3/4 download everything back and check sha256; waits out HF's rate limit ($(date))"
"$PY" archive/restore_data.py --source hf --snapshot --target-root "$V" --download-dir "$V.dl"

echo "== 4/4 recompute every number from the downloaded copy ($(date))"
cd "$CODE"
"$PY" -W ignore experiments/reproduce_numbers.py --v1 "$V/4-ICLR/REVISION/results_v1" --v2 "$V/4-ICLR/REVISION/results_v2" \
    --runs "$V/physweep_revision/runs" --logs-v1 "$V/4-ICLR/slurm_jobs" --logs-v2 "$V/4-ICLR/REVISION/slurm/v2" \
    --prov "$V/4-ICLR/REVISION/provenance" --recompute | tail -6
echo "== expected: 4 x 'IDENTICAL' and 'MISMATCH: 12, external: 2, match: 582, qualitative: 11, superseded: 6, unarchived: 9  (total 622)'"
echo "== done $(date)"
