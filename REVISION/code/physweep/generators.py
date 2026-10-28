"""
physweep/generators.py
======================
One interface for every video generator in the v2 study:

    gen = load_generator(name)                      # loads weights once
    out = gen.generate(cond_frames, prompt, noise_seed, row)
    out["frames"]  -> (T, H, W, 3) uint8, the model's raw output
    out["fps"]     -> the model's declared playback rate (used as dt = 1/fps)

Canvas convention (all models): the 256x256 scene is scaled to the model's
height and padded left/right by edge replication to the model's width, so
geometry is preserved; `to_analysis_frames` crops the centre square back and
resizes to 256 px, so tracking, validity checks and pixel-to-metre conversion
are unchanged.

Settings were taken from each pipeline's __call__ signature in diffusers 0.39.0
and each repo's model_index.json (checked 2026-10-15). `num_frames` is
shortened from some defaults to bound cost (2–6 s per clip); the step 4 pilot
measures whether that is enough. Nothing here has run on a GPU yet.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

import numpy as np
from PIL import Image

from physweep.prompts import NEGATIVE_PROMPT

ANALYSIS_SIZE = 256

# Hugging Face commit of every repo the v2 runs loaded (pinned 2026-10-28). Each repo had exactly one
# snapshot in $HF_HOME and refs/main pointed to it, so these are the weights every pilot and sweep used.
# The last three are loaded by third-party code (cosmos_guardrail, open_clip), which takes no revision;
# the restore kit downloads them at these commits and writes refs/main itself.
REVISIONS = {
    "Lightricks/LTX-Video": "8984fa25007f376c1a299016d0957a37a2f797bb",
    "zai-org/CogVideoX-5b-I2V": "a6f0f4858a8395e7429d82493864ce92bf73af11",
    "Wan-AI/Wan2.2-TI2V-5B-Diffusers": "b8fff7315c768468a5333511427288870b2e9635",
    "zai-org/CogVideoX1.5-5B-I2V": "46c90528707aebbe69066390b4fe7e7d24c9c2a4",
    "Wan-AI/Wan2.2-I2V-A14B-Diffusers": "596658fd9ca6b7b71d5057529bbf319ecbc61d74",
    "hunyuanvideo-community/HunyuanVideo-1.5-Diffusers-480p_i2v": "5a700ee883ff4c1b3d887ec4188755a7a5e2f698",
    "hunyuanvideo-community/HunyuanVideo-1.5-Diffusers-720p_i2v": "dcf088ef4e420dd54bc25930ee810bb6613dfcb5",  # first pilot only
    "Lightricks/LTX-2": "dfcc2108383fe1aaa0584bdf55d368a4bdadd90c",
    "nvidia/Cosmos-Predict2-2B-Video2World": "f50c09f5d8ab133a90cac3f4886a6471e9ba3f18",
    "nvidia/Cosmos-1.0-Guardrail": "cf03c0395fac8c4de386c0bdab12cc4fc8d66362",
    "Qwen/Qwen3Guard-Gen-0.6B": "fada3b2f655b89601929198343c94cd2f64d93cc",
    "laion/CLIP-ViT-H-14-laion2B-s32B-b79K": "1c2b8495b28150b8a4922ee1c8edee224c284c0c",
}

# name: repo, pipeline class, canvas (W, H), frames, fps, steps, guidance, queue, env
MODEL_SPECS = {
    # --- v1 models, re-run under the v2 design ---
    "ltx": dict(repo="Lightricks/LTX-Video", cls="LTXImageToVideoPipeline", W=768, H=512, num_frames=25,
                fps=24, steps=30, guidance=3.0, queue="a100", env="main", extra=dict(frame_rate=24)),
    "cogvideox": dict(repo="zai-org/CogVideoX-5b-I2V", cls="CogVideoXImageToVideoPipeline", W=720, H=480,
                      num_frames=49, fps=8, steps=30, guidance=6.0, queue="a100", env="main", vae_tiling=True),
    "dynamicrafter": dict(repo=None, cls="subprocess", W=512, H=320, num_frames=16, fps=24, steps=50,
                          guidance=7.5, queue="a100", env="main", frame_mode="pair"),
    # --- new open models ---
    "wan22_ti2v_5b": dict(repo="Wan-AI/Wan2.2-TI2V-5B-Diffusers", cls="WanImageToVideoPipeline", W=1280, H=704,
                          num_frames=49, fps=24, steps=50, guidance=5.0, queue="a100", env="main", wan_vae_fp32=True),
    # native 81 frames (2026-10-17, user decision): the 49-frame option-B re-pilot changed the model's output
    # (ball grows then vanishes; 1/12 valid vs 4/12 at 81), so the shortened clip is not a fair test
    "cogvideox15_i2v": dict(repo="zai-org/CogVideoX1.5-5B-I2V", cls="CogVideoXImageToVideoPipeline", W=1360, H=768,
                            num_frames=81, fps=16, steps=50, guidance=6.0, queue="a100", env="main", vae_tiling=True),
    "wan22_i2v_a14b": dict(repo="Wan-AI/Wan2.2-I2V-A14B-Diffusers", cls="WanImageToVideoPipeline", W=832, H=480,
                           num_frames=49, fps=16, steps=40, guidance=3.5, queue="h200", env="main", wan_vae_fp32=True,
                           extra=dict(guidance_scale_2=3.5), frame_mode="pair"),
    # option B (2026-10-16): official non-distilled 480p I2V checkpoint (same architecture, target_size 640)
    # and 33 frames, instead of 720p at 61 frames (pilot: 1200 s/clip)
    "hunyuan15_i2v": dict(repo="hunyuanvideo-community/HunyuanVideo-1.5-Diffusers-480p_i2v",
                          cls="HunyuanVideo15ImageToVideoPipeline", W=848, H=480, num_frames=33, fps=24, steps=50,
                          guidance=None, queue="h200", env="main", vae_tiling=True),
    "ltx2": dict(repo="Lightricks/LTX-2", cls="LTX2ImageToVideoPipeline", W=768, H=512, num_frames=49, fps=24,
                 steps=40, guidance=4.0, queue="h200", env="main", extra=dict(frame_rate=24.0),
                 # frame channel: LTX2ConditionPipeline (same weights; audio_scheduler is optional) with a
                 # 9-frame prefix at latent index 0 (condition length is trimmed to 8m+1 frames)
                 frame_mode="prefix", frame_k=9, frame_cls="LTX2ConditionPipeline"),
    "cosmos2_2b": dict(repo="nvidia/Cosmos-Predict2-2B-Video2World", cls="Cosmos2VideoToWorldPipeline", W=1280, H=704,
                       num_frames=93, fps=16, steps=35, guidance=7.0, queue="h200", env="cosmos", extra=dict(fps=16),
                       frame_mode="prefix", frame_k=5),   # Video2World: 5 frames -> 2 latent conditioning frames
    # --- CPU dry run: returns the ground-truth continuation, to test the harness end to end ---
    "simulator": dict(repo=None, cls="simulator", W=768, H=512, num_frames=24, fps=24, steps=0, guidance=None,
                      queue="cpu", env="main"),
    # CPU dry runs of the frame channel's timing logic: a "pair" model that returns 16 frames spanning the two
    # key frames, and a 16 fps "prefix" model that returns the given 5 frames followed by the true continuation
    "simulator_pair": dict(repo=None, cls="simulator", W=512, H=320, num_frames=16, fps=24, steps=0,
                           guidance=None, queue="cpu", env="main", frame_mode="pair"),
    "simulator_prefix": dict(repo=None, cls="simulator", W=768, H=512, num_frames=24, fps=16, steps=0,
                             guidance=None, queue="cpu", env="main", frame_mode="prefix", frame_k=5),
}


# ---------------------------------------------------------------------------
# Canvas in / analysis frames out
# ---------------------------------------------------------------------------
def to_canvas(gray256: np.ndarray, W: int, H: int) -> Image.Image:
    sq = Image.fromarray(gray256).convert("RGB").resize((H, H), Image.NEAREST)
    arr = np.asarray(sq)
    if W > H:
        left = (W - H) // 2
        arr = np.pad(arr, ((0, 0), (left, W - H - left), (0, 0)), mode="edge")
    elif W < H:
        top = (H - W) // 2
        arr = arr[:, top:top + W]
    return Image.fromarray(arr)


def to_analysis_frames(frames: np.ndarray) -> np.ndarray:
    """(T, h, w, 3) uint8 -> (T, 256, 256) uint8 grayscale, centre square crop."""
    T, h, w = frames.shape[:3]
    side = min(h, w)
    y0, x0 = (h - side) // 2, (w - side) // 2
    out = np.empty((T, ANALYSIS_SIZE, ANALYSIS_SIZE), dtype=np.uint8)
    for i in range(T):
        crop = Image.fromarray(frames[i, y0:y0 + side, x0:x0 + side]).convert("L")
        out[i] = np.asarray(crop.resize((ANALYSIS_SIZE, ANALYSIS_SIZE), Image.BILINEAR))
    return out


def _as_uint8_video(video) -> np.ndarray:
    """Pipelines return a list of PIL images, or an array in [0, 1] or [0, 255]."""
    if isinstance(video, (list, tuple)) and video and isinstance(video[0], Image.Image):
        return np.stack([np.asarray(f.convert("RGB")) for f in video])
    arr = np.asarray(video)
    if hasattr(video, "detach"):
        arr = video.detach().float().cpu().numpy()
    if arr.ndim == 4 and arr.shape[1] in (1, 3) and arr.shape[-1] not in (1, 3):
        arr = arr.transpose(0, 2, 3, 1)
    if arr.dtype != np.uint8:
        arr = np.clip(arr * 255.0 if arr.max() <= 1.0 + 1e-6 else arr, 0, 255).round().astype(np.uint8)
    if arr.shape[-1] == 1:
        arr = np.repeat(arr, 3, axis=-1)
    return arr


def _fix_cosmos_guardrail_device(pipe):
    """Work around a bug in cosmos-guardrail 0.3.2 (found 2026-10-17): its
    CosmosSafetyChecker.device/.dtype read `.device` from wrapper modules
    (Qwen3Guard, RetinaFaceFilter) that are plain nn.Modules without one, so
    diffusers' pipe._execution_device raises AttributeError on every call.
    This only answers the device/dtype query from the modules' parameters; the
    guardrail itself is untouched and still checks every prompt and video (the
    NVIDIA Open Model License forbids bypassing it)."""
    import torch

    sc = getattr(pipe, "safety_checker", None)
    if sc is None:
        return

    def _first_param(self):
        for m in self.nn_models:
            for p in m.parameters():
                return p
        return None

    cls = type(sc)
    cls.device = property(lambda self: (_first_param(self).device if _first_param(self) is not None
                                        else torch.device("cpu")))
    cls.dtype = property(lambda self: (_first_param(self).dtype if _first_param(self) is not None
                                       else torch.float32))


def _pin_execution_device(pipe, device):
    """Second Cosmos fix (2026-10-17): Cosmos2VideoToWorldPipeline moves its
    safety checker to CPU after every check, and diffusers' pipe.device
    returns the device of the alphabetically first module, which is
    `safety_checker`. So every call after the first built its inputs on CPU
    (pilot: clip 1 ran, clips 2-12 failed with a cpu/cuda mismatch). We run
    Cosmos on one GPU with no offloading, so the execution device is pinned
    to that GPU. The guardrail is untouched."""
    cls = type(pipe)
    pipe.__class__ = type(cls.__name__ + "PinnedDevice", (cls,),
                          {"_execution_device": property(lambda self: device),
                           "device": property(lambda self: device)})


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------
class DiffusersGenerator:
    def __init__(self, name: str, spec: dict, offload: bool = False, channel: str = "text"):
        import torch
        import diffusers

        self.name, self.spec, self.torch = name, spec, torch
        self.cls_name = spec.get("frame_cls", spec["cls"]) if channel == "frame" else spec["cls"]
        cls = getattr(diffusers, self.cls_name)
        rev = REVISIONS[spec["repo"]]
        kw = dict(torch_dtype=torch.bfloat16, revision=rev)
        if spec.get("wan_vae_fp32"):
            kw["vae"] = diffusers.AutoencoderKLWan.from_pretrained(spec["repo"], subfolder="vae", torch_dtype=torch.float32,
                                                                   revision=rev)
        self.pipe = cls.from_pretrained(spec["repo"], **kw)
        if spec["cls"] == "Cosmos2VideoToWorldPipeline":
            _fix_cosmos_guardrail_device(self.pipe)
        if offload:
            self.pipe.enable_model_cpu_offload()
        else:
            self.pipe.to("cuda")
            if spec["cls"] == "Cosmos2VideoToWorldPipeline":
                _pin_execution_device(self.pipe, torch.device("cuda"))
        if spec.get("vae_tiling") and hasattr(self.pipe, "vae") and hasattr(self.pipe.vae, "enable_tiling"):
            self.pipe.vae.enable_tiling()
        self.pipe.set_progress_bar_config(disable=True)

    def generate(self, cond_frames, prompt, noise_seed, row):
        s = self.spec
        images = [to_canvas(f, s["W"], s["H"]) for f in cond_frames]
        gen = self.torch.Generator(device="cuda").manual_seed(int(noise_seed))
        kw = dict(prompt=prompt, negative_prompt=NEGATIVE_PROMPT, num_frames=s["num_frames"],
                  num_inference_steps=s["steps"], generator=gen, **s.get("extra", {}))
        if self.cls_name != "HunyuanVideo15ImageToVideoPipeline":   # Hunyuan sizes from the image
            kw.update(height=s["H"], width=s["W"])
        if s["guidance"] is not None:
            kw["guidance_scale"] = s["guidance"]
        if self.cls_name == "LTX2ConditionPipeline":
            from diffusers.pipelines.ltx2.pipeline_ltx2_condition import LTX2VideoCondition
            kw["conditions"] = [LTX2VideoCondition(frames=images, index=0, strength=1.0)]
        elif len(images) == 1:
            kw["image"] = images[0]
        elif s["cls"] == "WanImageToVideoPipeline" and len(images) == 2:
            kw.update(image=images[0], last_image=images[1])
        elif s["cls"] == "Cosmos2VideoToWorldPipeline":
            kw["video"] = images
        else:
            raise NotImplementedError(f"{self.name}: frame channel with {len(images)} frames")
        out = self.pipe(**kw)
        return dict(frames=_as_uint8_video(out.frames[0]), fps=s["fps"])


class DynamiCrafterGenerator:
    """Subprocess call identical to v1 (experiments/e0_pilot_dynamicrafter.py
    for text, e8_conditioning_channel.py for interp), using the v2 canvas."""

    def __init__(self, spec):
        self.spec = spec
        self.root = os.environ["DC_ROOT"]
        self.python = os.environ["DC_PYTHON"]

    def generate(self, cond_frames, prompt, noise_seed, row):
        s = self.spec
        interp = len(cond_frames) == 2
        work = tempfile.mkdtemp(prefix="dc_")
        try:
            pdir, rdir = os.path.join(work, "input"), os.path.join(work, "results")
            os.makedirs(pdir)
            names = ["clip_01", "clip_02"] if interp else ["clip"]
            for f, n in zip(cond_frames, names):
                to_canvas(f, s["W"], s["H"]).save(os.path.join(pdir, f"{n}.png"))
            with open(os.path.join(pdir, "prompts.txt"), "w") as fh:
                fh.write(prompt + "\n")
            ckpt = ("checkpoints/dynamicrafter_512_interp_v1/model.ckpt" if interp
                    else "checkpoints/dynamicrafter_512_v1/model.ckpt")
            stride = 5 if interp else 24
            cmd = [self.python, "scripts/evaluation/inference.py", "--seed", str(noise_seed), "--ckpt_path", ckpt,
                   "--config", "configs/inference_512_v1.0.yaml", "--savedir", rdir, "--n_samples", "1",
                   "--bs", "1", "--height", str(s["H"]), "--width", str(s["W"]),
                   "--unconditional_guidance_scale", "7.5", "--ddim_steps", "50", "--ddim_eta", "1.0",
                   "--prompt_dir", pdir, "--text_input", "--video_length", "16", "--frame_stride", str(stride),
                   "--timestep_spacing", "uniform_trailing", "--guidance_rescale", "0.7", "--perframe_ae"]
            if interp:
                cmd.append("--interp")
            # 1800 s: the first call in a fresh job pays a cold start (the pilot hit the old
            # 900 s limit once; later calls took ~70 s)
            proc = subprocess.run(cmd, cwd=self.root, capture_output=True, text=True, timeout=1800)
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr[-2000:])
            path = os.path.join(rdir, "samples_separate", f"{names[0]}_sample0.mp4")
            import imageio.v3 as iio
            return dict(frames=_as_uint8_video(iio.imread(path)), fps=stride)
        finally:
            shutil.rmtree(work, ignore_errors=True)


class SimulatorGenerator:
    """CPU dry run: returns the true continuation on the model canvas."""

    def __init__(self, spec):
        self.spec = spec

    def generate(self, cond_frames, prompt, noise_seed, row):
        from physweep import render as R
        from physweep.conditioning import render_ground_truth
        s, mode = self.spec, (self.spec.get("frame_mode") if row.get("channel") == "frame" else None)
        if mode == "pair":
            # num_frames frames spanning key frame 1 -> key frame 2, as an interpolation model would produce.
            # Render one dense clip with the SAME total duration as the 24-frame conditioning clip (the
            # projectile's launch speed depends on the clip duration) and sample it at the key-frame spacing.
            K = s["num_frames"] - 1
            second = (R.N_FRAMES // 2) if row["system"] == "projectile" else R.N_FRAMES - 1
            dense = render_ground_truth(row["system"], row["theta"], row["scene_seed"], row["style"],
                                        n_frames=(R.N_FRAMES - 1) * K + 1, dt_scale=1.0 / K)
            gt = dense[np.arange(s["num_frames"]) * second]
        elif mode == "prefix":
            # exactly the clip build_conditioning renders (same length and frame rate), so the
            # continuation is consistent with the given prefix
            from physweep.conditioning import prefix_clip_frames
            gt = render_ground_truth(row["system"], row["theta"], row["scene_seed"], row["style"],
                                     n_frames=prefix_clip_frames(s.get("frame_k", 5), s["fps"]),
                                     dt_scale=R.FPS / s["fps"])
        else:
            gt = render_ground_truth(row["system"], row["theta"], row["scene_seed"], row["style"],
                                     n_frames=s["num_frames"])
        frames = np.stack([np.asarray(to_canvas(f, s["W"], s["H"])) for f in gt])
        return dict(frames=frames, fps=s["fps"])


def load_generator(name: str, offload: bool = False, channel: str = "text"):
    spec = MODEL_SPECS[name]
    if spec["cls"] == "simulator":
        return SimulatorGenerator(spec)
    if spec["cls"] == "subprocess":
        return DynamiCrafterGenerator(spec)
    return DiffusersGenerator(name, spec, offload=offload, channel=channel)
