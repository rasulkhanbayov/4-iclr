#!/usr/bin/env python3
"""
Check the Hugging Face archive against the local originals without downloading it (about 10 API calls).

  python archive/check_hf.py               # list the repo, re-hash every local original, compare
  python archive/check_hf.py --no-rehash   # trust MANIFEST.sha256 for the local side (skips reading 9.5 GB)

Every file in MANIFEST.sha256, plus README.md and the manifest itself, must be on HF with the same size
and the same content hash as the local original: HF's sha256 for LFS/Xet files, and the git blob id
(sha1 of "blob <size>\\0" + content) for small files stored directly in git. Read-only: it never
uploads, changes or deletes anything. Exits 1 on any difference.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from archive_lib import BASE, REPO_ID, hf_retry, hf_token, read_manifest  # noqa: E402

ALLOWED_EXTRA = {".gitattributes"}


def hashes(path, bufsize=1 << 22):
    """(size, sha256, git blob sha1) in one read."""
    size = os.path.getsize(path)
    s256, s1 = hashlib.sha256(), hashlib.sha1(b"blob %d\0" % size)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(bufsize), b""):
            s256.update(chunk)
            s1.update(chunk)
    return size, s256.hexdigest(), s1.hexdigest()


def compare(remote, manifest, staging, rehash=True, log=print):
    """remote: {path: (size, lfs_sha256 or None, blob_id)}. Returns {problem kind: [paths]} and per-part stats."""
    expected = sorted(manifest) + ["MANIFEST.sha256", "README.md"]
    problems = collections.defaultdict(list)
    stats = collections.defaultdict(lambda: [0, 0])
    for i, p in enumerate(expected, 1):
        local = os.path.join(staging, p)            # a symlink to the real file, or the file itself
        if not os.path.exists(local):
            problems["local file missing"].append(p)
            continue
        r = remote.get(p)
        if r is None:
            problems["missing on HF"].append(p)
            continue
        size, lfs_sha, blob = r
        if lfs_sha is not None and not rehash and p in manifest:
            lsize, lsha, lblob = os.path.getsize(local), manifest[p], None
        else:
            lsize, lsha, lblob = hashes(local)
            if p in manifest and lsha != manifest[p]:
                problems["local file changed since the manifest"].append(p)
        if size != lsize:
            problems["size differs"].append(p)
        elif (lfs_sha != lsha) if lfs_sha is not None else (blob != lblob):
            problems["content differs"].append(p)
        else:
            part = p.split("/")[0] if "/" in p else "(top level)"
            stats[part][0] += 1
            stats[part][1] += lsize
        if i % 1000 == 0:
            log(f"  compared {i}/{len(expected)}", flush=True)
    for p in sorted(set(remote) - set(expected) - ALLOWED_EXTRA):
        problems["on HF but not in the manifest"].append(p)
    return problems, stats, len(expected)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-id", default=REPO_ID)
    ap.add_argument("--revision", default=None, help="archive commit (default: latest)")
    ap.add_argument("--staging", default=os.path.join(BASE, "hf_archive_staging"),
                    help="the upload's staging folder (symlinks to the originals + MANIFEST.sha256)")
    ap.add_argument("--no-rehash", action="store_true")
    a = ap.parse_args()
    if not os.path.exists(os.path.join(a.staging, "MANIFEST.sha256")):
        sys.exit(f"no MANIFEST.sha256 in {a.staging}")
    manifest = read_manifest(os.path.join(a.staging, "MANIFEST.sha256"))

    from huggingface_hub import HfApi
    from huggingface_hub.hf_api import RepoFile
    api = HfApi(token=hf_token())
    info = hf_retry(api.dataset_info, a.repo_id, revision=a.revision)
    print(f"HF dataset {a.repo_id}, commit {info.sha}, private={info.private}, last modified {info.last_modified}")
    listing = hf_retry(lambda: list(api.list_repo_tree(a.repo_id, repo_type="dataset", recursive=True, revision=info.sha)))
    remote = {f.path: (f.lfs.size if f.lfs else f.size, f.lfs.sha256 if f.lfs else None, f.blob_id)
              for f in listing if isinstance(f, RepoFile)}
    n_lfs = sum(v[1] is not None for v in remote.values())
    print(f"files on HF: {len(remote)} ({n_lfs} LFS/Xet, {len(remote) - n_lfs} in git), "
          f"{sum(v[0] for v in remote.values()) / 1e9:.3f} GB")
    print(f"comparing with the local originals ({'manifest hashes' if a.no_rehash else 're-hashing every file'}) ...",
          flush=True)

    problems, stats, n_expected = compare(remote, manifest, a.staging, rehash=not a.no_rehash)
    print(f"\n  {'part':<14} {'files':>6} {'GB':>8}   (identical on HF and on disk)")
    for part in sorted(stats, key=lambda k: -stats[k][1]):
        print(f"  {part:<14} {stats[part][0]:>6} {stats[part][1] / 1e9:8.3f}")
    n_ok = sum(v[0] for v in stats.values())
    print(f"  {'total':<14} {n_ok:>6} {sum(v[1] for v in stats.values()) / 1e9:8.3f}   of {n_expected} expected")
    for kind, paths in problems.items():
        print(f"\n{kind}: {len(paths)}")
        for p in paths[:20]:
            print(f"  {p}")
    if problems or n_ok != n_expected:
        print("\nRESULT: PROBLEMS FOUND (see above). Do not delete anything.")
        sys.exit(1)
    print(f"\nRESULT: OK. All {n_expected} files are on Hugging Face, byte-identical to the local originals.")


if __name__ == "__main__":
    main()
