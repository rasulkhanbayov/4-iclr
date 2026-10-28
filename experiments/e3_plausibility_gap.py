#!/usr/bin/env python3
"""
experiments/e3_plausibility_gap.py
=====================================
E3 -- PLAUSIBILITY-MEASUREMENT GAP (runbook Section "EXPERIMENTS").

Objective: show that a plausibility rater (VLM auto-rater) misses the
wrong-parameter problem that PRE catches -- pairs (mean plausibility, PRE)
on the SAME out-of-range clips, testing the paper's Contribution 1
hypothesis directly (high P, high PRE) rather than arguing it only
conceptually.

Prerequisite: run experiments/e3e5_extended.py with --save-video first, for
every (model, system) pair you want E3 coverage on -- this script reads the
saved .mp4 clips it produces (results/e3e5_videos/) and the matching
per-clip PRE/theta_hat rows (results/e3e5_default_{system}_{model}.json).
It does NOT generate anything itself; it is pure VLM inference over
already-saved video.

VLM: Qwen2.5-VL-7B-Instruct (same model + loading pattern already proven
working on this cluster in the sibling 3-ACL project's rendequiv_infer.py --
not re-derived from scratch). Scores each clip on a 1-5 plausibility scale
via a fixed prompt, per the runbook's "VLM auto-rater (record exact model
name, version, prompt)" requirement.

Usage:
  python3 experiments/e3_plausibility_gap.py --model ltx --system projectile
Writes results/e3_plausibility_{system}_{model}.json
"""
from __future__ import annotations
import sys, os, json, re, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HF_HOME"] = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".hf_home")

import numpy as np
import torch

from physweep_metrics import pre, bootstrap_ci

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(REPO_ROOT, "results")
FIT_R2_GATE = 0.8

VLM_MODEL_ID = "Qwen/Qwen2.5-VL-7B-Instruct"  # exact model + version, recorded per the runbook's requirement

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


class QwenPlausibilityRater:
    """Loads Qwen2.5-VL-7B-Instruct once; scores one video clip per call.
    Loading pattern matches 3-ACL/generator_build/rendequiv_infer.py's
    already-verified-working setup for this exact model on this cluster,
    adapted from single-image to video content."""

    def __init__(self):
        from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration
        print(f"Loading {VLM_MODEL_ID}...")
        self.processor = AutoProcessor.from_pretrained(VLM_MODEL_ID)
        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            VLM_MODEL_ID, torch_dtype=torch.bfloat16, device_map="cuda")
        self.model.eval()

    def score(self, video_path: str) -> float:
        from qwen_vl_utils import process_vision_info
        messages = [{"role": "user", "content": [
            {"type": "video", "video": video_path, "fps": 24},
            {"type": "text", "text": PLAUSIBILITY_PROMPT},
        ]}]
        prompt_text = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True)
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = self.processor(
            text=[prompt_text], images=image_inputs, videos=video_inputs,
            padding=True, return_tensors="pt").to(self.model.device)
        with torch.no_grad():
            out_ids = self.model.generate(**inputs, max_new_tokens=8, do_sample=False)
        gen_ids = out_ids[:, inputs["input_ids"].shape[1]:]
        response = self.processor.batch_decode(gen_ids, skip_special_tokens=True)[0].strip()
        match = re.search(r"[1-5]", response)
        if match is None:
            print(f"  WARNING: could not parse a 1-5 rating from response {response!r}; "
                 f"recording as nan (excluded from the mean, not silently zeroed).")
            return float("nan")
        return float(match.group())


def score_one(model, system, variant, rater):
    """Score every already-saved clip for one (model, system, variant) and
    write results/e3_plausibility_{variant}_{system}_{model}.json. Returns
    True if it produced output, False if skipped (no rows file / no videos)."""
    rows_path = os.path.join(RESULTS_DIR, f"e3e5_{variant}_{system}_{model}.json")
    if not os.path.exists(rows_path):
        print(f"SKIP {model}/{system}: {rows_path} not found. Run experiments/e3e5_extended.py "
             f"--model {model} --systems {system} --save-video first.")
        return False
    with open(rows_path) as f:
        rows = json.load(f)["rows"]

    scoreable = [r for r in rows if r.get("video_path") and os.path.exists(r["video_path"])]
    print(f"{model}/{system}: {len(scoreable)}/{len(rows)} rows have a saved video to score.")
    if not scoreable:
        print(f"SKIP {model}/{system}: nothing to score -- was this file generated with --save-video?")
        return False

    for r in scoreable:
        p = rater.score(r["video_path"])
        r["plausibility"] = p
        print(f"  theta={r['theta']} seed={r['seed']} split={r['split']}: "
             f"plausibility={p} PRE-relevant r2={r['r2']:.3f}")

    out_path = os.path.join(RESULTS_DIR, f"e3_plausibility_{variant}_{system}_{model}.json")
    with open(out_path, "w") as f:
        json.dump({"rows": scoreable, "vlm_model": VLM_MODEL_ID, "prompt": PLAUSIBILITY_PROMPT}, f, indent=2,
                 default=lambda o: None if isinstance(o, float) and np.isnan(o) else o)
    print(f"Wrote {out_path}")

    # E3's headline pairing: (mean plausibility, PRE) on the out-of-range
    # split specifically -- the runbook's hypothesis is high P, high PRE.
    out_scored = [r for r in scoreable if r["split"] == "out"
                 and r.get("plausibility") is not None
                 and not (isinstance(r["plausibility"], float) and np.isnan(r["plausibility"]))]
    if len(out_scored) >= 2:
        mean_p = float(np.mean([r["plausibility"] for r in out_scored]))
        gated_out = [r for r in out_scored if r["r2"] is not None and r["r2"] >= FIT_R2_GATE
                    and not (isinstance(r["theta_hat"], float) and np.isnan(r["theta_hat"]))]
        print(f"Out-of-range mean plausibility = {mean_p:.2f}/5 (n={len(out_scored)})")
        if len(gated_out) >= 2:
            theta_out = np.array([r["theta"] for r in gated_out])
            hat_out = np.array([r["theta_hat"] for r in gated_out])
            pre_out = pre(theta_out, hat_out)
            print(f"PRE(out-of-range) = {pre_out:.4f} (n_gated={len(gated_out)})")
            print(f"E3 headline pair ({model}/{system}): (mean plausibility={mean_p:.2f}, PRE(out)={pre_out:.4f})")
            if mean_p >= 3.5 and pre_out >= 0.3:
                print("Consistent with the hypothesis: high plausibility, high PRE -- "
                     "a plausibility rater would NOT have caught the parameter-recovery failure.")
            else:
                print("Report the actual pair as measured -- do not force the hypothesized reading "
                     "if the numbers don't support it (this project's standing 'reading outcomes "
                     "honestly' rule).")
        else:
            print(f"Too few fit-quality-gated out-of-range points to compute PRE(out) for {model}/{system} "
                 "(this is the same fit-quality gate used everywhere else, see CLAUDE.md).")
    else:
        print(f"Too few scored out-of-range clips for {model}/{system} to compute the headline pair.")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["ltx", "cogvideox", "dynamicrafter"])
    parser.add_argument("--system")
    parser.add_argument("--models", nargs="*", choices=["ltx", "cogvideox", "dynamicrafter"],
                        help="score multiple models in ONE process (one VLM load, not one per call) -- "
                             "use this instead of --model in a shell loop to avoid reloading the 7B "
                             "rater from disk on every (model, system) pair.")
    parser.add_argument("--systems", nargs="*",
                        help="score multiple systems in ONE process, paired with --models (all "
                             "model x system combinations are scored, not zipped pairwise).")
    parser.add_argument("--variant", default="default",
                        help="which e3e5_extended.py variant's rows/videos to score (default: 'default')")
    args = parser.parse_args()

    models = args.models if args.models else ([args.model] if args.model else None)
    systems = args.systems if args.systems else ([args.system] if args.system else None)
    if not models or not systems:
        print("ERROR: provide either --model/--system, or --models/--systems.")
        sys.exit(1)

    rater = QwenPlausibilityRater()
    any_scored = False
    for model in models:
        for system in systems:
            any_scored |= score_one(model, system, args.variant, rater)

    if not any_scored:
        print("\nNothing was scored across any requested (model, system) pair.")
        sys.exit(1)


if __name__ == "__main__":
    main()
