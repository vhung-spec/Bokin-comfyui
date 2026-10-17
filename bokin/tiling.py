"""Tile planning and blending for tiled img2img refinement.

Pure PyTorch with no ComfyUI imports, so it can be unit-tested on its own.
Images use ComfyUI's layout: (batch, height, width, channels), floats in 0..1.

Tiles are refined one after another (row by row). Each new tile is pasted with
a soft ramp over the strip it shares with tiles that were already refined
(left and top), so the overlap fades from the old pixels into the new ones and
no hard seam is left. Its right and bottom edges need no ramp: the next tiles
fade over them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import torch
import torch.nn.functional as F

# Tile positions and sizes snap to this many pixels. It is a multiple of every
# common latent downscale ratio (8 for SD1.5/SDXL/Flux, 16 for newer VAEs) and
# of Flux/SD3's 2x2 patching, so tiles always map exactly onto latent pixels.
ALIGN = 32


@dataclass(frozen=True)
class Tile:
    x: int
    y: int
    w: int
    h: int
    blend_left: int  # pixels shared with the tile to the left (0 = image border)
    blend_top: int  # pixels shared with the tile above (0 = image border)


def align_up(value: int, multiple: int) -> int:
    return -(-value // multiple) * multiple


def align_down(value: int, multiple: int) -> int:
    return value // multiple * multiple


def axis_starts(length: int, tile: int, overlap: int, align: int = ALIGN) -> list[int]:
    """Start offsets of tiles covering ``[0, length)`` along one axis.

    ``length`` and ``tile`` must be multiples of ``align``. The first tile starts
    at 0, the last one ends exactly at ``length``, every neighbouring pair
    shares at least ``overlap`` pixels, and all starts are multiples of
    ``align``.
    """
    if length % align or tile % align:
        raise ValueError(f"length ({length}) and tile ({tile}) must be multiples of {align}")
    if tile >= length:
        return [0]
    length_u, tile_u = length // align, tile // align
    overlap_u = math.ceil(max(overlap, 0) / align)
    stride_u = max(tile_u - overlap_u, 1)
    span_u = length_u - tile_u
    count = math.ceil(span_u / stride_u) + 1
    # Spread the tiles evenly: consecutive starts differ by at most stride_u.
    return [(i * span_u) // (count - 1) * align for i in range(count)]


def plan_tiles(width: int, height: int, tile_size: int, overlap: int, align: int = ALIGN) -> list[Tile]:
    """Row-major list of tiles covering a ``width`` x ``height`` canvas."""
    tile_size = max(align_down(tile_size, align), align)
    tw, th = min(tile_size, width), min(tile_size, height)
    xs = axis_starts(width, tw, overlap, align)
    ys = axis_starts(height, th, overlap, align)
    tiles = []
    for r, y in enumerate(ys):
        blend_top = ys[r - 1] + th - y if r else 0
        for c, x in enumerate(xs):
            blend_left = xs[c - 1] + tw - x if c else 0
            tiles.append(Tile(x, y, tw, th, blend_left, blend_top))
    return tiles


def _ramp(n: int) -> torch.Tensor:
    """Smoothstep from ~0 to ~1 over ``n`` pixels, never exactly 0 or 1."""
    t = (torch.arange(n, dtype=torch.float32) + 0.5) / n
    return t * t * (3 - 2 * t)


def blend_mask(tile: Tile) -> torch.Tensor:
    """(h, w) weights of the new tile when pasting it over the canvas."""
    mask = torch.ones(tile.h, tile.w)
    if tile.blend_left:
        n = min(tile.blend_left, tile.w)
        mask[:, :n] = torch.minimum(mask[:, :n], _ramp(n)[None, :])
    if tile.blend_top:
        n = min(tile.blend_top, tile.h)
        mask[:n, :] = torch.minimum(mask[:n, :], _ramp(n)[:, None])
    return mask


def crop(image: torch.Tensor, tile: Tile) -> torch.Tensor:
    return image[:, tile.y:tile.y + tile.h, tile.x:tile.x + tile.w, :]


def paste(canvas: torch.Tensor, tile_image: torch.Tensor, tile: Tile) -> None:
    """Blend ``tile_image`` into ``canvas`` in place."""
    mask = blend_mask(tile).to(canvas)[None, :, :, None]
    region = crop(canvas, tile)
    region.copy_(region * (1 - mask) + tile_image.to(canvas) * mask)


def pad_to_multiple(image: torch.Tensor, multiple: int = ALIGN) -> torch.Tensor:
    """Pad the bottom/right edges by repeating border pixels up to ``multiple``."""
    _, h, w, _ = image.shape
    ph, pw = align_up(h, multiple) - h, align_up(w, multiple) - w
    if not ph and not pw:
        return image
    return F.pad(image.movedim(-1, 1), (0, pw, 0, ph), mode="replicate").movedim(1, -1)


def resize_image(image: torch.Tensor, width: int, height: int) -> torch.Tensor:
    """Antialiased bicubic resize; works for both enlarging and shrinking."""
    if image.shape[1] == height and image.shape[2] == width:
        return image
    out = F.interpolate(
        image.movedim(-1, 1).float(), size=(height, width), mode="bicubic", align_corners=False, antialias=True
    )
    return out.clamp(0, 1).movedim(1, -1).to(image.dtype)


def scale_schedule(total: float, passes: int) -> list[float]:
    """Cumulative scale after each pass, growing by the same factor every pass."""
    passes = max(int(passes), 1)
    return [total ** ((i + 1) / passes) for i in range(passes)]


def scaled_size(width: int, height: int, scale: float) -> tuple[int, int]:
    return max(round(width * scale), 1), max(round(height * scale), 1)
