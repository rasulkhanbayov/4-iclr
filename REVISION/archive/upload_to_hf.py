#!/usr/bin/env python3
"""
Build the Hugging Face archive and (only with --upload) push it.

  python archive/upload_to_hf.py                    # build staging + manifest, print the plan; uploads nothing
  python archive/upload_to_hf.py --upload           # also create the PRIVATE dataset repo and upload
  python archive/upload_to_hf.py --staging DIR      # build the staging folder somewhere else

Staging is a folder of symlinks to the real files (no copies) plus README.md (the dataset card),
MANIFEST.sha256 and snapshot/4-ICLR_small_files.tar.gz. upload_large_folder resumes if interrupted:
re-run the same command. After uploading, verify before deleting anything:
  python archive/restore_data.py --source hf --target-root /tmp/pw_verify     # full download + sha256 check
"""

from __future__ import annotations

import argparse
import collections
import os
import shutil
import sys
import tarfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from archive_lib import BASE, PARTS, REPO_ID, REV, ROOT, SNAPSHOT_EXCLUDE, hf_token, list_part, sha256  # noqa: E402

MARKER = ".physweep_staging"


def build_snapshot(dest_tar):
    """Tarball of every small project file under 4-ICLR (code, paper, docs, slurm scripts, CLAUDE.md).
    .env is excluded and the result is checked for it."""
    names = []

    def keep(rel):
        parts = rel.split(os.sep)
        if any(p == "__pycache__" or p == ".env" for p in parts):
            return False
        return not any(rel == x or rel.startswith(x + os.sep) for x in SNAPSHOT_EXCLUDE)

    with tarfile.open(dest_tar, "w:gz") as tar:
        for r, dirs, fs in os.walk(ROOT):
            rel_dir = os.path.relpath(r, ROOT)
            dirs[:] = sorted(d for d in dirs if keep(os.path.normpath(os.path.join(rel_dir, d))))
            for f in sorted(fs):
                rel = os.path.normpath(os.path.join(rel_dir, f))
                if keep(rel) and not os.path.islink(os.path.join(r, f)):
                    tar.add(os.path.join(r, f), arcname=os.path.join("4-ICLR", rel), recursive=False)
                    names.append(rel)
    assert not any(os.path.basename(n) == ".env" for n in names), ".env found in snapshot"
    return names


def build_staging(staging):
    if os.path.exists(staging):
        if not os.path.exists(os.path.join(staging, MARKER)):
            sys.exit(f"{staging} exists and was not made by this script; choose another --staging")
        shutil.rmtree(staging)               # our own symlink folder, rebuilt from scratch
    os.makedirs(staging)
    open(os.path.join(staging, MARKER), "w").close()
    files = []
    for part in PARTS:
        for repo_path, local in list_part(part):
            dst = os.path.join(staging, repo_path)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.symlink(os.path.realpath(local), dst)
            files.append((part["name"], repo_path, local))
    os.makedirs(os.path.join(staging, "snapshot"))
    tar = os.path.join(staging, "snapshot", "4-ICLR_small_files.tar.gz")
    names = build_snapshot(tar)
    with open(os.path.join(staging, "snapshot", "4-ICLR_small_files.list.txt"), "w") as f:
        f.write("\n".join(names) + "\n")
    files += [("snapshot", "snapshot/4-ICLR_small_files.tar.gz", tar),
              ("snapshot", "snapshot/4-ICLR_small_files.list.txt", os.path.join(staging, "snapshot", "4-ICLR_small_files.list.txt"))]
    shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dataset_card.md"), os.path.join(staging, "README.md"))
    print(f"hashing {len(files)} files ...", flush=True)
    with open(os.path.join(staging, "MANIFEST.sha256"), "w") as f:
        for _, repo_path, local in sorted(files, key=lambda x: x[1]):
            f.write(f"{sha256(local)}  {repo_path}\n")
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--staging", default=os.path.join(BASE, "hf_archive_staging"))
    ap.add_argument("--repo-id", default=REPO_ID)
    ap.add_argument("--upload", action="store_true", help="actually create the repo and upload (needs approval)")
    ap.add_argument("--public", action="store_true", help="create the repo public (default: private)")
    ap.add_argument("--reuse-staging", action="store_true",
                    help="resume: keep the existing staging folder (and upload_large_folder's progress cache)")
    a = ap.parse_args()
    if a.reuse_staging and os.path.exists(os.path.join(a.staging, MARKER)) \
            and os.path.exists(os.path.join(a.staging, "MANIFEST.sha256")):
        files = [(p.split("/")[0], p, os.path.join(a.staging, p))
                 for p in (line.rstrip("\n").split("  ", 1)[1] for line in open(os.path.join(a.staging, "MANIFEST.sha256")))]
    else:
        files = build_staging(a.staging)
    size = collections.Counter()
    count = collections.Counter()
    for name, _, local in files:
        size[name] += os.path.getsize(local)
        count[name] += 1
    print(f"\nstaging: {a.staging}")
    for name in sorted(size, key=lambda k: -size[k]):
        print(f"  {name:<14} {count[name]:>6} files  {size[name] / 1e9:8.3f} GB")
    print(f"  {'total':<14} {sum(count.values()):>6} files  {sum(size.values()) / 1e9:8.3f} GB")
    if not a.upload:
        print("\nNothing uploaded. Re-run with --upload once approved.")
        return
    from huggingface_hub import HfApi
    tok = hf_token()
    if not tok:
        sys.exit("no HF token (set HF_TOKEN or put an HF_TOKEN= line in 4-ICLR/.env)")
    api = HfApi(token=tok)
    api.create_repo(a.repo_id, repo_type="dataset", private=not a.public, exist_ok=True)
    api.upload_large_folder(repo_id=a.repo_id, repo_type="dataset", folder_path=a.staging,
                            ignore_patterns=[MARKER, ".cache/**"], private=not a.public)
    print(f"\nuploaded to https://huggingface.co/datasets/{a.repo_id}"
          f"\nNext: python archive/restore_data.py --source hf --target-root /tmp/pw_verify")


if __name__ == "__main__":
    main()
