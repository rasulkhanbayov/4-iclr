"""
archive/archive_lib.py
======================
What goes into the Hugging Face archive and where each part lives locally.
Shared by upload_to_hf.py, restore_data.py and restore_weights.py, so the
upload and the restore can never disagree about a path.

Repo layout (dataset repo, private while the project is paused):
  README.md                 dataset card
  MANIFEST.sha256           "<sha256>  <repo path>" for every other file (sha256sum -c format)
  runs/                     $BASE/runs: every v2 run (records, rescored files, run_meta, videos)
  results_v1/               REVISION/results_v1: the 134 v1 result files, 630 videos, debug frames
  results_v2/               REVISION/results_v2: v2 analysis outputs, step reports, dry runs
  provenance/               REVISION/provenance: values frozen for the provenance check
  env/                      REVISION/env: lock files, pinned weight hashes, DynamiCrafter patch
  logs/v1/slurm_jobs/       4-ICLR/slurm_jobs: v1 job scripts and logs
  logs/v1/root/             the two v1 logs left in the 4-ICLR root
  logs/v2/                  REVISION/slurm/v2: v2 job logs
  snapshot/                 a tarball of every small project file (code, paper, docs), as a
                            safety net if something was never committed to git
"""

from __future__ import annotations

import fnmatch
import hashlib
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REV = os.path.dirname(HERE)
ROOT = os.path.dirname(REV)
BASE = os.environ.get("PHYSWEEP_BASE", "/export/hbku-research/rakh90100/physweep_revision")
REPO_ID = os.environ.get("PHYSWEEP_HF_REPO", "rasulkhanbayov/physweep-revision-archive")

PARTS = [
    dict(name="runs", repo="runs", local="{BASE}/runs", include=["*"]),
    dict(name="results_v1", repo="results_v1", local="{REV}/results_v1", include=["*"]),
    dict(name="results_v2", repo="results_v2", local="{REV}/results_v2", include=["*"]),
    dict(name="provenance", repo="provenance", local="{REV}/provenance", include=["*"]),
    dict(name="env", repo="env", local="{REV}/env", include=["*"]),
    dict(name="logs_v1", repo="logs/v1/slurm_jobs", local="{ROOT}/slurm_jobs", include=["*"]),
    dict(name="logs_v1_root", repo="logs/v1/root", local="{ROOT}",
         include=["e2_dynamicrafter_371751.out", "e2_dynamicrafter_371751.err"]),
    dict(name="logs_v2", repo="logs/v2", local="{REV}/slurm/v2", include=["*.out", "*.err", "logs/*"]),
]
EXCLUDE = ["*/__pycache__/*", "__pycache__/*", "*.pyc", ".env", "*/.env", ".cache/*", "*/.cache/*"]

# Snapshot of the small project files. Everything under ROOT except these (relative to ROOT).
SNAPSHOT_EXCLUDE = ["external", "results", ".hf_home", ".env", "REVISION/results_v1", "REVISION/results_v2",
                    "REVISION/archive/staging", "__pycache__"]

# Sample used by the restore test: every small file, but videos for one model only.
SAMPLE_VIDEOS = ["runs/main_text/ltx2/videos/"]


def local_dir(part, target_root=None):
    """Local directory of a part; under target_root the same tree is re-rooted (restore test)."""
    if target_root:
        roots = dict(BASE=os.path.join(target_root, "physweep_revision"), REV=os.path.join(target_root, "4-ICLR", "REVISION"),
                     ROOT=os.path.join(target_root, "4-ICLR"))
    else:
        roots = dict(BASE=BASE, REV=REV, ROOT=ROOT)
    return part["local"].format(**roots)


def _included(rel, part):
    if any(fnmatch.fnmatch(rel, x) for x in EXCLUDE):
        return False
    return any(fnmatch.fnmatch(rel, x) for x in part["include"])


def list_part(part):
    """(repo path, local path) for every file of a part that exists now."""
    d = local_dir(part)
    # "*" means the whole tree; otherwise walk only as deep as the patterns reach (logs_v1_root sits in
    # the 4-ICLR root, which also holds external/)
    depth = None if part["include"] == ["*"] else max(x.count("/") for x in part["include"])
    out = []
    for r, dirs, fs in os.walk(d):
        rel_dir = os.path.relpath(r, d)
        level = 0 if rel_dir == "." else rel_dir.count(os.sep) + 1
        dirs[:] = sorted(x for x in dirs if x not in ("__pycache__", ".cache")) if depth is None or level < depth else []
        for f in sorted(fs):
            rel = f if rel_dir == "." else os.path.join(rel_dir, f)
            if _included(rel, part):
                out.append((f"{part['repo']}/{rel}", os.path.join(r, f)))
    return out


def part_of(repo_path):
    for part in sorted(PARTS, key=lambda x: -len(x["repo"])):
        if repo_path == part["repo"] or repo_path.startswith(part["repo"] + "/"):
            return part
    return None


def to_local(repo_path, target_root=None):
    part = part_of(repo_path)
    if part is None:
        return None
    return os.path.join(local_dir(part, target_root), os.path.relpath(repo_path, part["repo"]))


def sha256(path, bufsize=1 << 22):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(bufsize), b""):
            h.update(chunk)
    return h.hexdigest()


def read_manifest(path):
    out = {}
    with open(path) as f:
        for line in f:
            if line.strip():
                h, p = line.rstrip("\n").split("  ", 1)
                out[p] = h
    return out


def hf_token():
    """HF_TOKEN from the environment, else ONLY the HF_TOKEN line of 4-ICLR/.env (never source that file:
    it also sets HF_HOME to an old cache in the full home directory). Never printed."""
    tok = os.environ.get("HF_TOKEN")
    if tok:
        return tok
    env = os.path.join(ROOT, ".env")
    if os.path.exists(env):
        for line in open(env):
            if line.startswith("HF_TOKEN="):
                return line.split("=", 1)[1].strip().strip("'\"")
    return None
