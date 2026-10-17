"""Colour correction after diffusion refinement.

Diffusion models drift colours slightly, and each tile can drift differently.
These helpers pull the refined image's colours back to a reference (the plain
model upscale) while keeping the new detail.

Images use ComfyUI's layout: (batch, height, width, channels), floats in 0..1.
"""

from __future__ import annotations

import torch
import torch.nn.functional as F

METHODS = ("wavelet", "adain", "none")


def _wavelet_blur(image: torch.Tensor, radius: int) -> torch.Tensor:
    """Dilated 3x3 binomial blur of a (B, C, H, W) tensor."""
    channels = image.shape[1]
    kernel = torch.tensor([[1, 2, 1], [2, 4, 2], [1, 2, 1]], dtype=image.dtype, device=image.device) / 16
    kernel = kernel[None, None].repeat(channels, 1, 1, 1)
    # Replicate padding fails when the pad is not smaller than the image side.
    mode = "replicate" if radius < min(image.shape[-2:]) else "constant"
    image = F.pad(image, (radius, radius, radius, radius), mode=mode)
    return F.conv2d(image, kernel, groups=channels, dilation=radius)


def _wavelet_split(image: torch.Tensor, levels: int = 5) -> tuple[torch.Tensor, torch.Tensor]:
    """Split (B, C, H, W) into (high frequencies, low frequencies)."""
    high = torch.zeros_like(image)
    for i in range(levels):
        low = _wavelet_blur(image, 2 ** i)
        high += image - low
        image = low
    return high, image


def wavelet_color_fix(image: torch.Tensor, reference: torch.Tensor) -> torch.Tensor:
    """Detail from ``image``, overall colour and tone from ``reference``."""
    img = image.movedim(-1, 1).float()
    ref = reference.movedim(-1, 1).to(img)
    high, _ = _wavelet_split(img)
    _, low = _wavelet_split(ref)
    return (high + low).clamp(0, 1).movedim(1, -1).to(image.dtype)


def adain_color_fix(image: torch.Tensor, reference: torch.Tensor, eps: float = 1e-5) -> torch.Tensor:
    """Match each channel's mean and standard deviation to ``reference``."""
    img = image.float()
    ref = reference.to(img)
    dims = (1, 2)
    img_mean, img_std = img.mean(dims, keepdim=True), img.std(dims, keepdim=True)
    ref_mean, ref_std = ref.mean(dims, keepdim=True), ref.std(dims, keepdim=True)
    out = (img - img_mean) / (img_std + eps) * ref_std + ref_mean
    return out.clamp(0, 1).to(image.dtype)


def color_fix(image: torch.Tensor, reference: torch.Tensor, method: str, strength: float = 1.0) -> torch.Tensor:
    if method == "none" or strength <= 0:
        return image
    if reference.shape[1:3] != image.shape[1:3]:
        reference = F.interpolate(
            reference.movedim(-1, 1).float(), size=image.shape[1:3], mode="bicubic", align_corners=False
        ).clamp(0, 1).movedim(1, -1)
    if method == "wavelet":
        fixed = wavelet_color_fix(image, reference)
    elif method == "adain":
        fixed = adain_color_fix(image, reference)
    else:
        raise ValueError(f"Unknown colour fix method: {method}")
    if strength >= 1:
        return fixed
    return image + (fixed - image) * strength
