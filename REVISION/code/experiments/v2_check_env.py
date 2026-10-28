#!/usr/bin/env python3
"""
Verify a v2 environment: packages import from THIS env (not ~/.local, the v1
shadowing bug), versions match the pins, and the pipeline classes the
adapters need exist. Exit code 1 on any failure.

Usage:  python experiments/v2_check_env.py --env main|cosmos
"""

import argparse
import importlib
import importlib.metadata as md
import os
import sys

PINS_MAIN = {"numpy": "2.2.6", "scipy": "1.15.3", "diffusers": "0.39.0", "transformers": "4.57.6",
             "huggingface_hub": "0.36.2", "accelerate": "1.14.0", "imageio": "2.37.3", "ftfy": "6.3.1"}
PINS_COSMOS = {"numpy": "2.2.6", "diffusers": "0.39.0", "cosmos-guardrail": "0.3.2", "ftfy": "6.3.1"}
PIPES_MAIN = ["LTXImageToVideoPipeline", "CogVideoXImageToVideoPipeline", "WanImageToVideoPipeline",
              "HunyuanVideo15ImageToVideoPipeline", "LTX2ImageToVideoPipeline", "AutoencoderKLWan"]
PIPES_COSMOS = ["Cosmos2VideoToWorldPipeline"]
MODULES = {"cosmos-guardrail": "cosmos_guardrail", "huggingface_hub": "huggingface_hub"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", choices=["main", "cosmos"], required=True)
    env = ap.parse_args().env
    pins, pipes = (PINS_MAIN, PIPES_MAIN) if env == "main" else (PINS_COSMOS, PIPES_COSMOS)
    prefix = os.path.realpath(sys.prefix)
    ok = True
    print(f"python {sys.version.split()[0]} at {sys.executable}  PYTHONNOUSERSITE={os.environ.get('PYTHONNOUSERSITE')}")
    for pkg, want in pins.items():
        try:
            have = md.version(pkg)
            mod = importlib.import_module(MODULES.get(pkg, pkg))
            inside = os.path.realpath(mod.__file__).startswith(prefix)
            good = have == want and inside
            print(f"  {'OK ' if good else 'BAD'} {pkg:18s} {have:10s} (want {want}) from_this_env={inside}")
            ok &= good
        except Exception as e:
            print(f"  BAD {pkg:18s} import failed: {e}")
            ok = False
    import torch
    print(f"  torch {torch.__version__}  cuda_available={torch.cuda.is_available()}")
    import diffusers
    for p in pipes:
        has = hasattr(diffusers, p)
        print(f"  {'OK ' if has else 'BAD'} diffusers.{p}")
        ok &= has
    if env == "cosmos":
        import transformers
        print(f"  transformers {transformers.__version__} (resolver-chosen, must be >=5)")
        ok &= int(transformers.__version__.split(".")[0]) >= 5
    print("ENV OK" if ok else "ENV CHECK FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
