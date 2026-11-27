#!/usr/bin/env python3
"""
Step 7 (plan E-D): rate the plausibility of the saved v2 clips with a VLM, to test whether "plausibility
does not track measurement validity or parameter faithfulness" holds for a larger current rater and not only
for v1's Qwen2.5-VL-7B.

Raters (commits pinned in env/hf_snapshots.json):
  qwen3vl_30b_a3b  Qwen/Qwen3-VL-30B-A3B-Instruct   the plan's larger current rater
  qwen25vl_7b      Qwen/Qwen2.5-VL-7B-Instruct      v1's rater, re-run on the v2 clips
Prompt: v1's, verbatim (`--self-check` compares it with e3_plausibility_gap.py).
Frames: decoded from the saved mp4; N = min(T, 32) uniformly spaced indices, rounded down to an even
number (both models group frames in pairs); resized so the long side is 448 px. The rater is told the real
frame times (index / fps), so a 2 s clip is seen as 2 s whatever N is.
Answer: greedy decoding. `score` is the first digit 1-5 in the answer; `probs` are the probabilities of the
tokens "1".."5" at that answer position (renormalized over the five), `expected` = sum k * p_k, and
`digit_mass` is how much of the probability the five digits held before renormalizing.

Usage:  python experiments/v2_rate_plausibility.py --rater qwen3vl_30b_a3b --run main_text [--models ...]
        python experiments/v2_rate_plausibility.py --self-check       # CPU, no model weights
Writes: <out-root>/<run>/<model>/plausibility_<rater>.jsonl, one line per clip; resumable.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import sys
import time

CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CODE_DIR)

import numpy as np

from physweep.runio import load_latest, raw_files

REV_DIR = os.path.dirname(CODE_DIR)
SNAPSHOTS = os.path.join(REV_DIR, "env", "hf_snapshots.json")
RATERS = {
    "qwen3vl_30b_a3b": dict(repo="Qwen/Qwen3-VL-30B-A3B-Instruct", cls="Qwen3VLMoeForConditionalGeneration"),
    "qwen25vl_7b": dict(repo="Qwen/Qwen2.5-VL-7B-Instruct", cls="Qwen2_5_VLForConditionalGeneration"),
}
MAX_FRAMES = 32
LONG_SIDE = 448

# Verbatim copy of e3_plausibility_gap.PLAUSIBILITY_PROMPT (that module sets HF_HOME and imports torch on
# import, so it is not imported here; --self-check confirms the two are identical).
PLAUSIBILITY_PROMPT = (
    "You are watching a short video clip of a physics simulation (a ball or "
    "similar object moving under some physical process such as falling, "
    "swinging, bouncing, or sliding). Rate how PHYSICALLY PLAUSIBLE the "
    "motion looks, on a scale from 1 to 5, where 1 means the motion looks "
    "clearly unnatural, broken, or impossible (e.g. teleporting, "
    "morphing, floating with no cause), and 5 means the motion looks "
    "completely natural and physically believable, like something you "
    "could film in the real world. Respond with ONLY a single digit from "
    "1 to 5, nothing else."
)
PROMPT_SHA = hashlib.sha256(PLAUSIBILITY_PROMPT.encode()).hexdigest()[:16]
FRAME_RULE = f"min(T,{MAX_FRAMES}) uniform, even, long side {LONG_SIDE}px, real timestamps"


def frame_indices(T: int) -> np.ndarray:
    n = min(T, MAX_FRAMES)
    n -= n % 2
    return np.linspace(0, T - 1, max(n, 2)).round().astype(int)


def resize(frames: np.ndarray) -> np.ndarray:
    from PIL import Image
    h, w = frames.shape[1:3]
    s = LONG_SIDE / max(h, w)
    size = (max(1, round(w * s)), max(1, round(h * s)))
    return np.stack([np.asarray(Image.fromarray(f).resize(size, Image.BICUBIC)) for f in frames])


def read_clip(path: str):
    import imageio.v2 as iio
    reader = iio.get_reader(path)
    fps = float(reader.get_meta_data().get("fps") or 0) or None
    frames = np.stack([np.asarray(f)[..., :3] for f in reader])
    reader.close()
    return frames, fps


def first_digit(text: str):
    m = re.search(r"[1-5]", text)
    return int(m.group()) if m else None


class Rater:
    def __init__(self, name: str, device: str = "cuda", dtype: str = "auto"):
        import torch
        import transformers
        spec = RATERS[name]
        self.name, self.repo = name, spec["repo"]
        self.revision = json.load(open(SNAPSHOTS))[self.repo]["revision"]
        self.qwen3 = name.startswith("qwen3")
        if dtype == "auto":
            dtype = "bf16" if device == "cuda" else "fp32"
        dtype = {"bf16": torch.bfloat16, "fp32": torch.float32}[dtype]
        self.proc = transformers.AutoProcessor.from_pretrained(self.repo, revision=self.revision)
        self.model = getattr(transformers, spec["cls"]).from_pretrained(
            self.repo, revision=self.revision, dtype=dtype, device_map=device, attn_implementation="sdpa").eval()
        tok = self.proc.tokenizer
        self.digit_ids = [tok.convert_tokens_to_ids(str(k)) for k in range(1, 6)]
        assert len(set(self.digit_ids)) == 5 and tok.unk_token_id not in self.digit_ids, self.digit_ids
        msgs = [{"role": "user", "content": [{"type": "video"}, {"type": "text", "text": PLAUSIBILITY_PROMPT}]}]
        self.text = self.proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        self.device = device

    def score(self, frames: np.ndarray, fps: float) -> dict:
        import torch
        T = len(frames)
        idx = frame_indices(T)
        sel = resize(frames[idx])
        if self.qwen3:
            md = dict(total_num_frames=T, fps=fps, frames_indices=idx.tolist(), duration=T / fps,
                      height=sel.shape[1], width=sel.shape[2])
            inputs = self.proc(text=[self.text], videos=[sel], video_metadata=[md], do_sample_frames=False,
                               return_tensors="pt")
        else:
            eff_fps = fps * (len(idx) - 1) / (idx[-1] - idx[0])     # frames per second of the selected frames
            inputs = self.proc(text=[self.text], videos=[sel], fps=eff_fps, do_sample_frames=False,
                               return_tensors="pt")
        inputs = inputs.to(self.device)
        with torch.no_grad():
            out = self.model.generate(**inputs, max_new_tokens=8, do_sample=False, output_scores=True,
                                      return_dict_in_generate=True)
        gen = out.sequences[0, inputs["input_ids"].shape[1]:].tolist()
        answer = self.proc.tokenizer.decode(gen, skip_special_tokens=True).strip()
        pos = next((i for i, t in enumerate(gen) if t in self.digit_ids), None)
        probs = mass = expected = None
        if pos is not None:
            p = torch.softmax(out.scores[pos][0].float(), dim=-1)[self.digit_ids].cpu().numpy()
            mass = float(p.sum())
            probs = (p / p.sum()).round(6).tolist()
            expected = float(np.dot(np.arange(1, 6), p / p.sum()))
        return dict(score=first_digit(answer), expected=expected, probs=probs, digit_mass=mass, answer=answer,
                    n_frames_in=len(idx), video_tokens=int((inputs["input_ids"] == self.model.config.video_token_id).sum()))


def rate_run(rater: Rater, root: str, models, limit=None):
    for model in models:
        mdir = os.path.join(root, model)
        if not os.path.isdir(mdir) or not raw_files(mdir):
            continue
        recs = [r for r in load_latest(mdir, prefer_rescored=True).values() if "error" not in r and r.get("video")]
        out_path = os.path.join(mdir, f"plausibility_{rater.name}.jsonl")
        done = set()
        if os.path.exists(out_path):
            done = {json.loads(l)["clip_id"] for l in open(out_path) if l.strip()}
        todo = [r for r in sorted(recs, key=lambda r: r["clip_id"]) if r["clip_id"] not in done][:limit]
        print(f"[{rater.name}] {model}: {len(recs)} clips with video, {len(done)} already rated, {len(todo)} to do",
              flush=True)
        with open(out_path, "a") as f:
            for i, r in enumerate(todo, 1):
                t0 = time.time()
                try:
                    frames, fps = read_clip(os.path.join(mdir, r["video"]))
                    res = rater.score(frames, fps or r["fps"])
                except Exception as e:                       # one unreadable clip must not stop the run
                    res = dict(error=f"{type(e).__name__}: {e}"[:300])
                row = dict(clip_id=r["clip_id"], model=model, system=r["system"], theta=r["theta"],
                           scene_seed=r.get("scene_seed"), noise_seed=r.get("noise_seed"), label=r["label"],
                           rater=rater.name, repo=rater.repo, revision=rater.revision, prompt_sha=PROMPT_SHA,
                           frame_rule=FRAME_RULE, seconds=round(time.time() - t0, 2), **res)
                f.write(json.dumps(row) + "\n")
                f.flush()
                if i % 50 == 0 or i == len(todo) or "error" in res:
                    print(f"  {i}/{len(todo)} {r['clip_id']}: score={res.get('score')} "
                          f"E={res.get('expected')} {res.get('error', '')}", flush=True)


def self_check():
    src = open(os.path.join(CODE_DIR, "experiments", "e3_plausibility_gap.py")).read()
    v1 = next(ast.literal_eval(n.value) for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "PLAUSIBILITY_PROMPT" for t in n.targets))
    assert v1 == PLAUSIBILITY_PROMPT, "prompt differs from v1"
    for T, n in ((16, 16), (25, 24), (33, 32), (49, 32), (81, 32), (93, 32)):
        idx = frame_indices(T)
        assert len(idx) == n and idx[0] == 0 and idx[-1] == T - 1 and len(set(idx)) == n, (T, idx)
    assert resize(np.zeros((2, 704, 1280, 3), np.uint8)).shape == (2, 246, 448, 3)
    assert first_digit(" 4") == 4 and first_digit("Rating: 2.") == 2 and first_digit("none") is None
    snaps = json.load(open(SNAPSHOTS))
    for name, spec in RATERS.items():
        assert spec["repo"] in snaps, f"{spec['repo']} not recorded in env/hf_snapshots.json"
    print(f"self-check OK: prompt identical to v1 (sha {PROMPT_SHA}); frame rule: {FRAME_RULE}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rater", choices=sorted(RATERS))
    ap.add_argument("--run", default="main_text")
    ap.add_argument("--out-root", default=os.environ.get("PHYSWEEP_OUT", os.path.join(CODE_DIR, "..", "runs")))
    ap.add_argument("--models", nargs="*")
    ap.add_argument("--limit", type=int, default=None, help="clips per model (smoke test)")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--dtype", default="auto", choices=["auto", "bf16", "fp32"], help="auto: bf16 on GPU, fp32 on CPU")
    ap.add_argument("--self-check", action="store_true")
    a = ap.parse_args()
    if a.self_check:
        self_check()
        return
    if not a.rater:
        ap.error("--rater is required")
    self_check()
    root = os.path.join(a.out_root, a.run)
    rater = Rater(a.rater, a.device, a.dtype)
    print(f"{a.rater}: {rater.repo}@{rater.revision[:8]} on {a.device}", flush=True)
    rate_run(rater, root, sorted(a.models or os.listdir(root)), a.limit)


if __name__ == "__main__":
    main()
