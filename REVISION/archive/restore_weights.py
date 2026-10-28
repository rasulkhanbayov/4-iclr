#!/usr/bin/env python3
"""
Re-download model weights at the exact revisions the runs used, and check them.

  python archive/restore_weights.py --list                       # models, sizes, which step needs them
  python archive/restore_weights.py --step step6                 # what the frame-channel pilot/sweep needs
  python archive/restore_weights.py --models ltx2 cosmos2_2b     # specific models
  python archive/restore_weights.py --all                        # everything the text sweep used
  python archive/restore_weights.py --verify-only --all          # check what is already in $HF_HOME
  add --dry-run to print the plan, --deep to sha256 every LFS file (slow)

Hugging Face repos are fetched with snapshot_download(revision=<pinned commit>), restricted to the exact
file list recorded in env/hf_snapshots.json, and refs/main is set to that commit so code that loads
without a revision (cosmos_guardrail, open_clip) resolves to the same files. Run jobs with
HF_HUB_OFFLINE=1 afterwards so nothing updates silently.

DynamiCrafter: code from GitHub's tarball of commit 859021927d8e (no git needed), our patched
scripts/evaluation/inference.py from env/dynamicrafter/, and the two model.ckpt files from
Doubiiu/DynamiCrafter_512(_Interp) at their pinned commits, each checked against env/weights_sha256.txt.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tarfile
import tempfile
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from archive_lib import BASE, REV, ROOT, hf_token, sha256  # noqa: E402

ENV = os.path.join(REV, "env")
SNAP = json.load(open(os.path.join(ENV, "hf_snapshots.json")))

DC_COMMIT = "859021927d8e0f8eb4d91d16f86711b8c25a2023"
DC_INFERENCE_SHA = "33c76256d932951f00c08960d2a3d266f37ea882a9eb0b5cb55fcc106257f48a"
DC_CKPTS = {  # local path under DC_ROOT: (repo, pinned commit, sha256 of model.ckpt)
    "checkpoints/dynamicrafter_512_v1/model.ckpt":
        ("Doubiiu/DynamiCrafter_512", "9eb874455b7903c0244fe7bf53ca21cb979cd05a",
         "87b5eb1981ffa96110369dfc358c5a9e90b8ee18b24d711badab4e58baeaba97"),
    "checkpoints/dynamicrafter_512_interp_v1/model.ckpt":
        ("Doubiiu/DynamiCrafter_512_Interp", "5163d01e6f5601a64dbdd8f89a27b1a700313324",
         "a322c00daeb077d79f3de8f9627db4914f4321a8fadaf24dd9ccc62ee8c49d23"),
}

# model name (as in MODEL_SPECS) -> HF repos it loads; "dynamicrafter" also needs the DC code and checkpoints
MODELS = {
    "ltx": ["Lightricks/LTX-Video"],
    "cogvideox": ["zai-org/CogVideoX-5b-I2V"],
    "dynamicrafter": ["laion/CLIP-ViT-H-14-laion2B-s32B-b79K"],
    "wan22_ti2v_5b": ["Wan-AI/Wan2.2-TI2V-5B-Diffusers"],
    "cogvideox15_i2v": ["zai-org/CogVideoX1.5-5B-I2V"],
    "wan22_i2v_a14b": ["Wan-AI/Wan2.2-I2V-A14B-Diffusers"],
    "hunyuan15_i2v": ["hunyuanvideo-community/HunyuanVideo-1.5-Diffusers-480p_i2v"],
    "hunyuan15_i2v_720p": ["hunyuanvideo-community/HunyuanVideo-1.5-Diffusers-720p_i2v"],   # first pilot only
    "ltx2": ["Lightricks/LTX-2"],
    "cosmos2_2b": ["nvidia/Cosmos-Predict2-2B-Video2World", "nvidia/Cosmos-1.0-Guardrail", "Qwen/Qwen3Guard-Gen-0.6B"],
}
TEXT_SWEEP = ["ltx", "cogvideox", "dynamicrafter", "wan22_ti2v_5b", "cogvideox15_i2v", "wan22_i2v_a14b",
              "hunyuan15_i2v", "ltx2", "cosmos2_2b"]
STEPS = {
    "step6": ["dynamicrafter", "wan22_i2v_a14b", "ltx2", "cosmos2_2b"],   # frame-channel pilot and sweep
    "text_sweep": TEXT_SWEEP,                                             # re-run any part of main_text/api_text
    "analysis": [],                                                       # rescore, analysis, figures, writing
}


def repo_bytes(repo):
    return SNAP[repo]["total_bytes"]


def model_bytes(m):
    b = sum(repo_bytes(r) for r in MODELS[m])
    if m == "dynamicrafter":
        b += sum(10437548346 for _ in DC_CKPTS)
    return b


def verify_repo(repo, hf_home, deep=False):
    rec = SNAP[repo]
    d = os.path.join(hf_home, "hub", "models--" + repo.replace("/", "--"))
    snap = os.path.join(d, "snapshots", rec["revision"])
    problems = []
    for rel, f in rec["files"].items():
        p = os.path.join(snap, rel)
        if not os.path.exists(p):
            problems.append(f"missing {rel}")
        elif os.path.getsize(p) != f["bytes"]:
            problems.append(f"size {rel}")
        elif deep and len(f["blob"]) == 64 and sha256(p) != f["blob"]:
            problems.append(f"sha256 {rel}")
    refs = os.path.join(d, "refs", "main")
    if not os.path.exists(refs) or open(refs).read().strip() != rec["revision"]:
        problems.append("refs/main does not point to the pinned commit")
    return problems


def fetch_repo(repo, hf_home):
    from huggingface_hub import snapshot_download
    rec = SNAP[repo]
    snapshot_download(repo, revision=rec["revision"], allow_patterns=sorted(rec["files"]),
                      cache_dir=os.path.join(hf_home, "hub"), token=hf_token())
    refs = os.path.join(hf_home, "hub", "models--" + repo.replace("/", "--"), "refs")
    os.makedirs(refs, exist_ok=True)
    with open(os.path.join(refs, "main"), "w") as f:
        f.write(rec["revision"])


def restore_dynamicrafter(dc_root, verify_only=False):
    problems = []
    if not verify_only and not os.path.exists(os.path.join(dc_root, "scripts", "evaluation", "inference.py")):
        if os.path.exists(dc_root) and os.listdir(dc_root):
            sys.exit(f"{dc_root} exists without DynamiCrafter code; move it away first")
        url = f"https://github.com/Doubiiu/DynamiCrafter/archive/{DC_COMMIT}.tar.gz"
        with tempfile.TemporaryDirectory() as tmp:
            tgz = os.path.join(tmp, "dc.tar.gz")
            urllib.request.urlretrieve(url, tgz)
            with tarfile.open(tgz) as t:
                t.extractall(tmp)
            shutil.move(os.path.join(tmp, f"DynamiCrafter-{DC_COMMIT}"), dc_root)
        shutil.copy2(os.path.join(ENV, "dynamicrafter", "inference.py"), os.path.join(dc_root, "scripts", "evaluation", "inference.py"))
    inf = os.path.join(dc_root, "scripts", "evaluation", "inference.py")
    if not os.path.exists(inf) or sha256(inf) != DC_INFERENCE_SHA:
        problems.append("scripts/evaluation/inference.py is missing or not the patched version")
    for rel, (repo, rev, digest) in DC_CKPTS.items():
        dst = os.path.join(dc_root, rel)
        if not verify_only and not os.path.exists(dst):
            from huggingface_hub import hf_hub_download
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with tempfile.TemporaryDirectory(dir=os.path.dirname(dst)) as tmp:
                p = hf_hub_download(repo, "model.ckpt", revision=rev, local_dir=tmp, token=hf_token())
                shutil.move(p, dst)
        if not os.path.exists(dst):
            problems.append(f"missing {rel}")
        elif sha256(dst) != digest:
            problems.append(f"sha256 mismatch {rel}")
    return problems


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--models", nargs="+", choices=sorted(MODELS))
    g.add_argument("--step", choices=sorted(STEPS))
    g.add_argument("--all", action="store_true")
    g.add_argument("--list", action="store_true")
    ap.add_argument("--hf-home", default=os.environ.get("HF_HOME", os.path.join(BASE, "hf_home")))
    ap.add_argument("--dc-root", default=os.environ.get("DC_ROOT", os.path.join(ROOT, "external", "DynamiCrafter")))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--deep", action="store_true")
    a = ap.parse_args()
    if a.list or not (a.models or a.step or a.all):
        print(f"{'model':<20}{'GB':>8}  steps")
        for m in MODELS:
            steps = [s for s, ms in STEPS.items() if m in ms] or ["first pilot only"]
            print(f"{m:<20}{model_bytes(m) / 1e9:8.1f}  {', '.join(steps)}")
        for s, ms in STEPS.items():
            print(f"step {s:<15}{sum(model_bytes(m) for m in ms) / 1e9:8.1f} GB  {' '.join(ms) or '(no weights)'}")
        print("CoTracker3 (second tracker) lives in $TORCH_HOME, which is kept on disk during the pause.")
        return
    models = a.models or (STEPS[a.step] if a.step else TEXT_SWEEP)
    repos = sorted({r for m in models for r in MODELS[m]})
    total = sum(model_bytes(m) for m in models)
    print(f"models: {' '.join(models)}\nrepos: {len(repos)}, about {total / 1e9:.1f} GB, into {a.hf_home}")
    if a.dry_run:
        return
    failed = False
    for repo in repos:
        if not a.verify_only and verify_repo(repo, a.hf_home):
            print(f"downloading {repo}@{SNAP[repo]['revision'][:8]} ({repo_bytes(repo) / 1e9:.1f} GB) ...", flush=True)
            fetch_repo(repo, a.hf_home)
        problems = verify_repo(repo, a.hf_home, a.deep)
        print(f"{'OK  ' if not problems else 'FAIL'} {repo}" + (f": {problems[:5]}" if problems else ""), flush=True)
        failed |= bool(problems)
    if "dynamicrafter" in models:
        problems = restore_dynamicrafter(a.dc_root, a.verify_only)
        print(f"{'OK  ' if not problems else 'FAIL'} DynamiCrafter code + checkpoints in {a.dc_root}"
              + (f": {problems}" if problems else ""))
        failed |= bool(problems)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
