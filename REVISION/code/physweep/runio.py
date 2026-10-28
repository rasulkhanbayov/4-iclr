"""
physweep/runio.py
=================
Reading and writing per-clip records for a run.

Each shard of a model appends to its own file, `clips_shard<i>of<n>.jsonl`
(older pilot runs used a single `clips.jsonl`), because several shards of one
model running at once must not append to the same file on NFS. Readers merge
all raw files of a model directory. `clips_rescored.jsonl` is the merged,
re-scored copy written by experiments/v2_rescore.py.
"""

from __future__ import annotations

import glob
import json
import os

RESCORED = "clips_rescored.jsonl"


def shard_path(model_dir: str, index: int, count: int) -> str:
    return os.path.join(model_dir, f"clips_shard{index}of{count}.jsonl")


def raw_files(model_dir: str) -> list[str]:
    return sorted(p for p in glob.glob(os.path.join(model_dir, "clips*.jsonl"))
                  if os.path.basename(p) != RESCORED)


def load_latest(model_dir: str, prefer_rescored: bool = False) -> dict:
    """clip_id -> record. A successful record is never replaced by a later
    error; otherwise the latest record wins (retries)."""
    rescored = os.path.join(model_dir, RESCORED)
    files = [rescored] if prefer_rescored and os.path.exists(rescored) else raw_files(model_dir)
    latest = {}
    for path in files:
        with open(path) as f:
            for line in f:
                if not line.strip():
                    continue
                r = json.loads(line)
                old = latest.get(r["clip_id"])
                if old is not None and "error" not in old and "error" in r:
                    continue
                latest[r["clip_id"]] = r
    return latest
