"""
VEGA AI — Pre-download all models to local cache.
Run this ONCE with internet access. After this, VEGA runs fully offline.

Usage:
    python download_models.py

What it downloads:
    Image:
      - stabilityai/sdxl-turbo          (~6.6 GB)   — default image model
    Video:
      - Wan-AI/Wan2.1-T2V-1.3B-diffusers (~12 GB)   — best local video (RTX 4060 8GB)
      - THUDM/CogVideoX-2b               (~13 GB)   — alternative video
      - Lightricks/LTX-Video             (~5 GB)    — fastest video
      - guoyww/animatediff-motion-adapter-v1-5-3 (~0.5 GB)
      - runwayml/stable-diffusion-v1-5   (~4 GB)    — AnimateDiff base

Total: ~41 GB  (skip any you don't want by commenting out below)
"""

import sys
import time


def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def download_model(label: str, fn, *args, **kwargs):
    print(f"\n[DOWNLOAD] {label}")
    t0 = time.time()
    try:
        fn(*args, **kwargs)
        elapsed = time.time() - t0
        print(f"[OK] {label} — done in {elapsed:.0f}s")
    except Exception as e:
        print(f"[SKIP] {label} failed: {e}")


def main():
    print("\nVEGA Model Downloader")
    print("=====================")
    print("Downloads all models to HuggingFace cache (~/.cache/huggingface/hub/)")
    print("After this completes, VEGA runs fully offline — no re-downloads needed.\n")

    try:
        import torch
        from diffusers import (
            AutoPipelineForText2Image,
            WanPipeline,
            CogVideoXPipeline,
            LTXPipeline,
            AnimateDiffPipeline,
            MotionAdapter,
        )
    except ImportError as e:
        print(f"[ERROR] Missing dependencies: {e}")
        print("Run first:  pip install torch diffusers transformers accelerate")
        sys.exit(1)

    dtype = torch.float16

    # ─── IMAGE MODELS ────────────────────────────────────────────────
    section("Image Models")

    download_model(
        "SDXL Turbo (default image, ~6.6 GB)",
        AutoPipelineForText2Image.from_pretrained,
        "stabilityai/sdxl-turbo",
        torch_dtype=dtype,
    )

    # ─── VIDEO MODELS ────────────────────────────────────────────────
    section("Video Models")

    download_model(
        "Wan 2.1 T2V-1.3B-Diffusers (best 8GB video, ~12 GB)",
        WanPipeline.from_pretrained,
        "Wan-AI/Wan2.1-T2V-1.3B-Diffusers",
        torch_dtype=dtype,
    )

    download_model(
        "CogVideoX-2b (~13 GB)",
        CogVideoXPipeline.from_pretrained,
        "THUDM/CogVideoX-2b",
        torch_dtype=dtype,
    )

    download_model(
        "LTX-Video 0.9 (~5 GB)",
        LTXPipeline.from_pretrained,
        "Lightricks/LTX-Video",
        torch_dtype=dtype,
    )

    download_model(
        "AnimateDiff motion adapter (~0.5 GB)",
        MotionAdapter.from_pretrained,
        "guoyww/animatediff-motion-adapter-v1-5-3",
        torch_dtype=dtype,
    )

    download_model(
        "Stable Diffusion v1-5 (AnimateDiff base, ~4 GB)",
        AutoPipelineForText2Image.from_pretrained,
        "runwayml/stable-diffusion-v1-5",
        torch_dtype=dtype,
    )

    # ─── DONE ─────────────────────────────────────────────────────────
    print("\n" + "="*60)
    print("  All models downloaded. VEGA will now run fully offline.")
    print("  Restart VEGA: double-click restart.bat")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
