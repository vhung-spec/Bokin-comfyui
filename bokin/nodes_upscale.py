"""Bokin upscale nodes for ComfyUI.

The main node works like the upscaler on Shakker:
1. enlarge the image with an ESRGAN-style model (4x-UltraSharp, RealESRGAN, ...),
2. redraw it tile by tile with a diffusion model at low denoise to add real
   detail, optionally guided by a tile ControlNet,
3. pull the colours back to the plain upscale so tiles do not drift.
"""

from __future__ import annotations

import logging

import torch

import comfy.model_management
import comfy.sample
import comfy.samplers
import comfy.utils
import latent_preview
import nodes as comfy_nodes

from . import color, presets, tiling

log = logging.getLogger("Bokin")

CATEGORY = "Bokin/upscale"


def _is_oom(e: Exception) -> bool:
    mm = comfy.model_management
    if hasattr(mm, "is_oom"):
        return mm.is_oom(e)
    return isinstance(e, mm.OOM_EXCEPTION)


def upscale_with_model(upscale_model, image: torch.Tensor) -> torch.Tensor:
    """Run a model from "Load Upscale Model" once over a (B, H, W, C) image."""
    mm = comfy.model_management
    scale = upscale_model.scale
    memory_required = (512 * 512 * 3) * image.element_size() * max(scale, 1.0) * 384.0
    memory_required += image.nelement() * image.element_size()

    patcher = getattr(upscale_model, "patcher", None)
    if patcher is not None:
        mm.load_models_gpu([patcher], memory_required=memory_required, force_full_load=True)
        device = patcher.load_device
    else:  # older ComfyUI: the model is moved by hand
        device = mm.get_torch_device()
        mm.free_memory(memory_required, device)
        upscale_model.to(device)

    try:
        in_img = image.movedim(-1, -3).to(device)
        tile, overlap = 512, 32
        while True:
            try:
                steps = in_img.shape[0] * comfy.utils.get_tiled_scale_steps(
                    in_img.shape[3], in_img.shape[2], tile_x=tile, tile_y=tile, overlap=overlap
                )
                out = comfy.utils.tiled_scale(
                    in_img,
                    lambda a: upscale_model(a.float()),
                    tile_x=tile,
                    tile_y=tile,
                    overlap=overlap,
                    upscale_amount=scale,
                    pbar=comfy.utils.ProgressBar(steps),
                )
                break
            except Exception as e:
                if not _is_oom(e) or tile // 2 < 128:
                    raise
                tile //= 2
    finally:
        if patcher is None:
            upscale_model.to("cpu")

    return torch.clamp(out.movedim(-3, -1), 0, 1).float()


def model_upscale(image: torch.Tensor, width: int, height: int, upscale_model=None) -> torch.Tensor:
    """Enlarge ``image`` to exactly ``width`` x ``height``.

    The upscale model is applied as many times as needed to reach the size,
    then the result is resized to the exact target. Without a model this is a
    plain bicubic resize.
    """
    if upscale_model is not None:
        while image.shape[2] < width or image.shape[1] < height:
            image = upscale_with_model(upscale_model, image)
            if upscale_model.scale <= 1:
                break
    return tiling.resize_image(image, width, height)


def _apply_controlnet(positive, negative, control_net, hint, strength, end_percent, vae):
    apply = comfy_nodes.ControlNetApplyAdvanced().apply_controlnet
    try:
        return apply(positive, negative, control_net, hint, strength, 0.0, end_percent, vae=vae)
    except TypeError:  # ComfyUI versions without the vae argument
        return apply(positive, negative, control_net, hint, strength, 0.0, end_percent)


def refine_tiles(
    image: torch.Tensor,
    model,
    vae,
    positive,
    negative,
    *,
    seed: int,
    steps: int,
    cfg: float,
    sampler_name: str,
    scheduler: str,
    denoise: float,
    tile_size: int,
    tile_overlap: int,
    control_net=None,
    controlnet_strength: float = 0.0,
    controlnet_end: float = 1.0,
) -> torch.Tensor:
    """img2img over a single (1, H, W, C) image, one tile at a time."""
    _, height, width, _ = image.shape
    reference = tiling.pad_to_multiple(image)
    canvas = reference.clone()
    tiles = tiling.plan_tiles(canvas.shape[2], canvas.shape[1], tile_size, tile_overlap)
    use_controlnet = control_net is not None and controlnet_strength > 0

    # One noise map for the whole canvas, cut per tile: overlapping tiles see
    # the same noise where they overlap, and no noise pattern repeats per tile.
    noise = None
    for index, tile in enumerate(tiles, 1):
        comfy.model_management.throw_exception_if_processing_interrupted()
        log.info("Bokin Upscale: tile %d/%d (%dx%d at %d,%d)", index, len(tiles), tile.w, tile.h, tile.x, tile.y)

        latent = vae.encode(tiling.crop(canvas, tile))
        ratio_y, ratio_x = tile.h // latent.shape[-2], tile.w // latent.shape[-1]
        if noise is None:
            full = latent.shape[:-2] + (canvas.shape[1] // ratio_y, canvas.shape[2] // ratio_x)
            noise = comfy.sample.prepare_noise(torch.zeros(full, dtype=latent.dtype), seed)
        tile_noise = noise[
            ...,
            tile.y // ratio_y:(tile.y + tile.h) // ratio_y,
            tile.x // ratio_x:(tile.x + tile.w) // ratio_x,
        ]

        pos, neg = positive, negative
        if use_controlnet:
            hint = tiling.crop(reference, tile)
            pos, neg = _apply_controlnet(positive, negative, control_net, hint, controlnet_strength, controlnet_end, vae)

        samples = comfy.sample.sample(
            model,
            tile_noise,
            steps,
            cfg,
            sampler_name,
            scheduler,
            pos,
            neg,
            latent,
            denoise=denoise,
            callback=latent_preview.prepare_callback(model, steps),
            disable_pbar=not comfy.utils.PROGRESS_BAR_ENABLED,
            seed=seed,
        )
        decoded = vae.decode(samples)
        if decoded.ndim == 5:
            decoded = decoded.reshape(-1, *decoded.shape[-3:])
        tiling.paste(canvas, decoded[..., :3], tile)

    return canvas[:, :height, :width, :]


def _check_size(width: int, height: int) -> None:
    limit = comfy_nodes.MAX_RESOLUTION
    if width > limit or height > limit:
        raise ValueError(f"Ảnh đầu ra {width}x{height} vượt quá giới hạn {limit}px của ComfyUI. Hãy giảm upscale_by.")


class BokinUpscale:
    """Shakker-style upscale: model upscale + tiled diffusion redraw + colour fix."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "model": ("MODEL", {"tooltip": "Model dùng để vẽ lại chi tiết (SD1.5, SDXL, Flux...)."}),
                "positive": ("CONDITIONING", {"tooltip": "Prompt mô tả chất lượng/chi tiết mong muốn."}),
                "negative": ("CONDITIONING",),
                "vae": ("VAE",),
                "upscale_by": ("FLOAT", {
                    "default": 2.0, "min": 1.0, "max": 8.0, "step": 0.05,
                    "tooltip": "Hệ số phóng to (2 = gấp đôi chiều rộng và chiều cao).",
                }),
                "mode": (presets.MODES, {
                    "default": "Balanced",
                    "tooltip": "Mức độ sáng tạo khi vẽ lại chi tiết:\n"
                               "Faithful: giữ sát ảnh gốc\n"
                               "Balanced: cân bằng (khuyên dùng)\n"
                               "Creative: thêm nhiều chi tiết mới\n"
                               "Custom: dùng giá trị denoise bên dưới",
                }),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF, "control_after_generate": True}),
                "steps": ("INT", {"default": 20, "min": 1, "max": 200}),
                "cfg": ("FLOAT", {"default": 6.0, "min": 0.0, "max": 30.0, "step": 0.1, "round": 0.01,
                                  "tooltip": "Flux: để 1.0 và dùng FluxGuidance cho prompt."}),
                "sampler_name": (comfy.samplers.KSampler.SAMPLERS, {"default": "dpmpp_2m"}),
                "scheduler": (comfy.samplers.KSampler.SCHEDULERS, {"default": "karras"}),
                "denoise": ("FLOAT", {
                    "default": 0.35, "min": 0.0, "max": 1.0, "step": 0.01,
                    "tooltip": "Chỉ dùng khi mode = Custom. 0 = không vẽ lại (chỉ upscale bằng model).",
                }),
                "tile_size": ("INT", {
                    "default": 1024, "min": 256, "max": 4096, "step": 64,
                    "tooltip": "Kích thước mỗi ô vẽ lại. SDXL/Flux: 1024, SD1.5: 512-768.",
                }),
                "tile_overlap": ("INT", {
                    "default": 128, "min": 0, "max": 1024, "step": 32,
                    "tooltip": "Phần chồng lên nhau giữa các ô, càng lớn càng ít lộ đường nối.",
                }),
                "passes": ("INT", {
                    "default": 1, "min": 1, "max": 4,
                    "tooltip": "Chia việc phóng to thành nhiều lần (vd. 4x = 2 lần x2). "
                               "Mỗi lần đều vẽ lại chi tiết, đẹp hơn với hệ số lớn nhưng chậm hơn.",
                }),
                "color_fix": (color.METHODS, {
                    "default": "wavelet",
                    "tooltip": "Giữ màu giống ảnh gốc sau khi vẽ lại. wavelet: giữ chi tiết tốt nhất.",
                }),
            },
            "optional": {
                "upscale_model": ("UPSCALE_MODEL", {
                    "tooltip": "Model phóng to (4x-UltraSharp, RealESRGAN...). Bỏ trống = phóng to bicubic.",
                }),
                "control_net": ("CONTROL_NET", {
                    "tooltip": "ControlNet Tile để giữ bố cục khi vẽ lại, cho phép denoise cao hơn.",
                }),
                "controlnet_strength": ("FLOAT", {"default": 0.6, "min": 0.0, "max": 2.0, "step": 0.01}),
                "controlnet_end": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            },
        }

    RETURN_TYPES = ("IMAGE", "IMAGE")
    RETURN_NAMES = ("image", "base_upscale")
    OUTPUT_TOOLTIPS = (
        "Ảnh đã phóng to và vẽ lại chi tiết.",
        "Ảnh chỉ phóng to bằng model (để so sánh trước/sau).",
    )
    FUNCTION = "upscale"
    CATEGORY = CATEGORY
    DESCRIPTION = "Phóng to ảnh kiểu Shakker: upscale bằng model, vẽ lại chi tiết từng ô bằng diffusion, rồi sửa màu."

    def upscale(
        self,
        image,
        model,
        positive,
        negative,
        vae,
        upscale_by,
        mode,
        seed,
        steps,
        cfg,
        sampler_name,
        scheduler,
        denoise,
        tile_size,
        tile_overlap,
        passes,
        color_fix,
        upscale_model=None,
        control_net=None,
        controlnet_strength=0.6,
        controlnet_end=1.0,
    ):
        use_controlnet = control_net is not None and controlnet_strength > 0
        denoise = presets.resolve_denoise(mode, denoise, use_controlnet)
        image = image[..., :3]
        _, height, width, _ = image.shape
        final_w, final_h = tiling.scaled_size(width, height, upscale_by)
        _check_size(final_w, final_h)
        schedule = tiling.scale_schedule(upscale_by, passes)

        results, bases = [], []
        for i in range(image.shape[0]):
            current = image[i:i + 1]
            plain = None
            for scale in schedule:
                target_w, target_h = tiling.scaled_size(width, height, scale)
                base = model_upscale(current, target_w, target_h, upscale_model)
                if plain is None and len(schedule) == 1:
                    plain = base
                if denoise <= 0:
                    current = base
                    continue
                refined = refine_tiles(
                    base,
                    model,
                    vae,
                    positive,
                    negative,
                    seed=seed + i,
                    steps=steps,
                    cfg=cfg,
                    sampler_name=sampler_name,
                    scheduler=scheduler,
                    denoise=denoise,
                    tile_size=tile_size,
                    tile_overlap=tile_overlap,
                    control_net=control_net,
                    controlnet_strength=controlnet_strength,
                    controlnet_end=controlnet_end,
                )
                current = color.color_fix(refined, base, color_fix)
            if plain is None:
                plain = model_upscale(image[i:i + 1], final_w, final_h, upscale_model)
            results.append(current)
            bases.append(plain)

        return torch.cat(results), torch.cat(bases)


class BokinUpscaleFast:
    """Model-only upscale to an exact factor (Shakker's quick upscale)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "upscale_by": ("FLOAT", {"default": 2.0, "min": 0.25, "max": 8.0, "step": 0.05}),
            },
            "optional": {
                "upscale_model": ("UPSCALE_MODEL", {
                    "tooltip": "Model phóng to (4x-UltraSharp, RealESRGAN...). Bỏ trống = phóng to bicubic.",
                }),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "upscale"
    CATEGORY = CATEGORY
    DESCRIPTION = "Phóng to nhanh bằng model (không vẽ lại), ra đúng hệ số upscale_by."

    def upscale(self, image, upscale_by, upscale_model=None):
        _, height, width, _ = image.shape
        target_w, target_h = tiling.scaled_size(width, height, upscale_by)
        _check_size(target_w, target_h)
        return (model_upscale(image[..., :3], target_w, target_h, upscale_model),)


class BokinColorMatch:
    """Copy the colours of a reference image onto another image."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "reference": ("IMAGE", {"tooltip": "Ảnh lấy màu (thường là ảnh gốc hoặc base_upscale)."}),
                "method": (("wavelet", "adain"), {"default": "wavelet"}),
                "strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "match"
    CATEGORY = CATEGORY
    DESCRIPTION = "Đưa màu của ảnh về giống ảnh tham chiếu, giữ nguyên chi tiết."

    def match(self, image, reference, method, strength):
        last = reference.shape[0] - 1
        reference = reference[[min(i, last) for i in range(image.shape[0])]]
        return (color.color_fix(image[..., :3], reference[..., :3], method, strength),)


NODE_CLASS_MAPPINGS = {
    "BokinUpscale": BokinUpscale,
    "BokinUpscaleFast": BokinUpscaleFast,
    "BokinColorMatch": BokinColorMatch,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "BokinUpscale": "Bokin Upscale (Shakker-style)",
    "BokinUpscaleFast": "Bokin Upscale Fast (model only)",
    "BokinColorMatch": "Bokin Color Match",
}
