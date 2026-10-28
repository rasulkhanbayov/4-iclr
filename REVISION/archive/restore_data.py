#!/usr/bin/env python3
"""
Restore the archived data to the paths the code expects, and check every file against MANIFEST.sha256.

  python archive/restore_data.py --source hf                         # download everything, put it in place
  python archive/restore_data.py --source hf --parts runs            # only one part (see archive_lib.PARTS)
  python archive/restore_data.py --source hf --sample                # small files + one model's videos
  python archive/restore_data.py --source hf --target-root /tmp/x    # restore under /tmp/x (verification)
  python archive/restore_data.py --source DIR ...                    # from a local copy (staging or an earlier download)
  python archive/restore_data.py --check-only                        # verify files already in place
  python archive/restore_data.py --source hf --snapshot --target-root /tmp/x   # also unpack the project-file tarball

An existing file is never overwritten: if it matches the manifest it is skipped, otherwise it is
reported as a conflict and left alone (use --overwrite to replace it).
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import shutil
import sys
import tarfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from archive_lib import (BASE, PARTS, REPO_ID, SAMPLE_VIDEOS, hf_retry, hf_token, part_of, read_manifest,  # noqa: E402
                         sha256, to_local)


def select(manifest, parts, sample):
    names = {p["name"] for p in PARTS} if parts == ["all"] else set(parts)
    out = []
    for path in manifest:
        part = part_of(path)
        if part is None or part["name"] not in names:
            continue
        if sample and path.endswith(".mp4") and path.startswith("runs/") and not any(path.startswith(s) for s in SAMPLE_VIDEOS):
            continue
        out.append(path)
    return sorted(out)


def resolve_revision(repo_id, revision):
    """The archive's commit hash. With a hash, snapshot_download skips files it already put in local_dir
    without asking HF, so a retry after a 429 resumes instead of starting over."""
    from huggingface_hub import HfApi
    return hf_retry(HfApi(token=hf_token()).dataset_info, repo_id, revision=revision).sha


def fetch_hf(repo_id, revision, download_dir, patterns):
    from huggingface_hub import snapshot_download
    return hf_retry(snapshot_download, repo_id=repo_id, repo_type="dataset", revision=revision,
                    local_dir=download_dir, allow_patterns=patterns, token=hf_token())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="hf", help="'hf' or a local folder with the repo layout")
    ap.add_argument("--repo-id", default=REPO_ID)
    ap.add_argument("--revision", default=None, help="archive commit to restore (default: latest)")
    ap.add_argument("--parts", default="all", help="comma-separated part names, or 'all'")
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--snapshot", action="store_true", help="also unpack snapshot/4-ICLR_small_files.tar.gz")
    ap.add_argument("--target-root", default=None, help="restore under this folder instead of the real paths")
    ap.add_argument("--download-dir", default=os.path.join(BASE, "hf_archive_download"))
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    parts = [x.strip() for x in a.parts.split(",")]

    if a.source == "hf":
        src = a.download_dir
        a.revision = resolve_revision(a.repo_id, a.revision)
        print(f"archive commit {a.revision}", flush=True)
        fetch_hf(a.repo_id, a.revision, src, ["MANIFEST.sha256", "README.md"])
    else:
        src = os.path.abspath(a.source)
    manifest = read_manifest(os.path.join(src, "MANIFEST.sha256"))
    wanted = select(manifest, parts, a.sample)
    if a.snapshot:
        wanted += [p for p in manifest if p.startswith("snapshot/")]
    print(f"{len(wanted)} files selected ({'sample' if a.sample else 'full'}; parts: {a.parts})", flush=True)
    in_place = {p for p in wanted if not p.startswith("snapshot/") and os.path.exists(to_local(p, a.target_root))
                and sha256(to_local(p, a.target_root)) == manifest[p]}
    if a.source == "hf" and not a.check_only:
        fetch_hf(a.repo_id, a.revision, src, [p for p in wanted if p not in in_place])

    ok = skipped = 0
    bad, conflicts, missing = [], [], []
    for path in wanted:
        if path.startswith("snapshot/"):
            continue
        dst = to_local(path, a.target_root)
        if not a.check_only:
            if path in in_place:
                skipped += 1
                continue
            s = os.path.join(src, path)
            if not os.path.exists(s):
                missing.append(path)
                continue
            if os.path.exists(dst) and not a.overwrite:
                conflicts.append(path)
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if a.source == "hf":
                shutil.move(s, dst)                  # out of the download folder: no second copy on disk
            else:
                shutil.copy2(s, dst)                 # follows symlinks: a staging folder works as a source
        if not os.path.exists(dst):
            missing.append(path)
        elif sha256(dst) == manifest[path]:
            ok += 1
        else:
            bad.append(path)
    if a.snapshot:
        tar = os.path.join(src, "snapshot", "4-ICLR_small_files.tar.gz")
        if sha256(tar) != manifest["snapshot/4-ICLR_small_files.tar.gz"]:
            bad.append("snapshot/4-ICLR_small_files.tar.gz")
        else:
            dest = os.path.join(a.target_root or os.path.join(BASE, "restored_snapshot"), "snapshot")
            os.makedirs(dest, exist_ok=True)
            with tarfile.open(tar) as t:
                t.extractall(dest)
            print(f"snapshot unpacked under {dest} (compare it with your git checkout; nothing was overwritten)")
    print(f"verified {ok}, already in place {skipped}, sha256 mismatch {len(bad)}, conflicts {len(conflicts)}, "
          f"missing {len(missing)}")
    for name, lst in (("MISMATCH", bad), ("CONFLICT", conflicts), ("MISSING", missing)):
        for p in lst[:20]:
            print(f"  {name} {p}")
    sys.exit(1 if bad or missing else 0)


if __name__ == "__main__":
    main()
