"""Shakker-style upscale modes.

A mode only picks the denoise strength ("creativity"): how much the model is
allowed to redraw while adding detail. A tile ControlNet holds the structure
in place, so the same mode can redraw more when one is connected.
"""

from __future__ import annotations

MODES = ("Balanced", "Faithful", "Creative", "Custom")

# mode -> (denoise without ControlNet, denoise with a tile ControlNet)
DENOISE = {
    "Faithful": (0.20, 0.35),
    "Balanced": (0.30, 0.50),
    "Creative": (0.45, 0.70),
}


def resolve_denoise(mode: str, custom_denoise: float, has_controlnet: bool) -> float:
    if mode == "Custom":
        return custom_denoise
    if mode not in DENOISE:
        raise ValueError(f"Unknown mode: {mode}")
    return DENOISE[mode][1 if has_controlnet else 0]
