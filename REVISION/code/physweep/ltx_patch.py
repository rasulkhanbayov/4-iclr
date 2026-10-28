#!/usr/bin/env python3
"""
physweep/ltx_patch.py
======================
Workaround for a bug in diffusers==0.39.0's LTXConditionPipeline: unlike
LTXImageToVideoPipeline (which correctly computes and passes `mu` for the
scheduler's dynamic-shifting flow-match sampling), LTXConditionPipeline's
__call__ calls scheduler.set_timesteps(timesteps=..., device=...) without
`mu`, which raises "`mu` must be passed when `use_dynamic_shifting` is set to
be `True`" -- and Lightricks/LTX-Video's shipped scheduler_config.json does
set use_dynamic_shifting=True. Confirmed by comparing both pipeline source
files directly; this is a real gap in diffusers 0.39.0, not a config error on
our end.

The fix computes `mu` EXACTLY as LTXImageToVideoPipeline does -- from the
real video_sequence_length (latent_num_frames * latent_height * latent_width)
for the actual height/width/num_frames of the call -- not an approximation,
so generation quality matches what a fixed LTXConditionPipeline would produce.

Call apply_ltx_condition_pipeline_patch() once before instantiating
LTXConditionPipeline. Safe to call multiple times (idempotent).

Remove this module once diffusers ships a fix (check LTXConditionPipeline
.__call__'s source for a `mu = calculate_shift(...)` line before the
retrieve_timesteps call, matching LTXImageToVideoPipeline's pattern).
"""
from __future__ import annotations
import functools

_PATCHED = False


def apply_ltx_condition_pipeline_patch():
    global _PATCHED
    if _PATCHED:
        return
    from diffusers.pipelines.ltx.pipeline_ltx_condition import LTXConditionPipeline, calculate_shift

    original_call = LTXConditionPipeline.__call__

    @functools.wraps(original_call)
    def patched_call(self, *args, height=512, width=704, num_frames=161, **kwargs):
        latent_num_frames = (num_frames - 1) // self.vae_temporal_compression_ratio + 1
        latent_height = height // self.vae_spatial_compression_ratio
        latent_width = width // self.vae_spatial_compression_ratio
        video_sequence_length = latent_num_frames * latent_height * latent_width
        mu = calculate_shift(
            video_sequence_length,
            self.scheduler.config.get("base_image_seq_len", 256),
            self.scheduler.config.get("max_image_seq_len", 4096),
            self.scheduler.config.get("base_shift", 0.5),
            self.scheduler.config.get("max_shift", 1.15),
        )

        scheduler = self.scheduler
        original_set_timesteps = scheduler.set_timesteps

        @functools.wraps(original_set_timesteps)
        def set_timesteps_with_mu(*a, **kw):
            kw.setdefault("mu", mu)
            return original_set_timesteps(*a, **kw)

        scheduler.set_timesteps = set_timesteps_with_mu
        try:
            return original_call(self, *args, height=height, width=width, num_frames=num_frames, **kwargs)
        finally:
            scheduler.set_timesteps = original_set_timesteps

    LTXConditionPipeline.__call__ = patched_call
    _PATCHED = True
