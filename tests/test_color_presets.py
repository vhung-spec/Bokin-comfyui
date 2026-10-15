import pytest
import torch

from bokin import color, presets


def test_wavelet_split_is_lossless():
    image = torch.rand(1, 3, 64, 80)
    high, low = color._wavelet_split(image)
    assert torch.allclose(high + low, image, atol=1e-5)


def test_wavelet_fix_removes_colour_cast_and_keeps_detail():
    torch.manual_seed(0)
    reference = torch.rand(1, 1, 1, 3).expand(1, 128, 128, 3) * 0.5 + 0.25
    detail = (torch.rand(1, 128, 128, 1) - 0.5) * 0.1
    image = (reference + detail + torch.tensor([0.15, -0.1, 0.05])).clamp(0, 1)

    fixed = color.wavelet_color_fix(image, reference)

    assert (fixed.mean((1, 2)) - reference.mean((1, 2))).abs().max() < 0.01
    assert fixed.std((1, 2)).min() > 0.02  # the added texture survives


def test_adain_matches_statistics():
    image = torch.rand(1, 32, 32, 3) * 0.3
    reference = torch.rand(1, 48, 48, 3) * 0.6 + 0.2
    fixed = color.adain_color_fix(image, reference)
    assert torch.allclose(fixed.mean((1, 2)), reference.mean((1, 2)), atol=1e-3)
    assert torch.allclose(fixed.std((1, 2)), reference.std((1, 2)), atol=1e-2)


def test_color_fix_dispatch_and_strength():
    image = torch.rand(1, 64, 64, 3)
    reference = torch.rand(1, 32, 32, 3)
    assert color.color_fix(image, reference, "none") is image
    assert color.color_fix(image, reference, "wavelet", strength=0) is image
    full = color.color_fix(image, reference, "adain")
    half = color.color_fix(image, reference, "adain", strength=0.5)
    assert full.shape == image.shape
    assert torch.allclose(half, (image + full) / 2, atol=1e-6)
    with pytest.raises(ValueError):
        color.color_fix(image, reference, "nope")


def test_resolve_denoise():
    assert presets.resolve_denoise("Custom", 0.42, False) == 0.42
    assert presets.resolve_denoise("Custom", 0.42, True) == 0.42
    for mode in ("Faithful", "Balanced", "Creative"):
        plain, guided = presets.resolve_denoise(mode, 0, False), presets.resolve_denoise(mode, 0, True)
        assert 0 < plain < guided < 1
    assert presets.resolve_denoise("Faithful", 0, False) < presets.resolve_denoise("Creative", 0, False)
    with pytest.raises(ValueError):
        presets.resolve_denoise("Turbo", 0.3, False)
