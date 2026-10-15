import itertools

import pytest
import torch

from bokin import tiling


@pytest.mark.parametrize(
    "length,tile,overlap",
    list(itertools.product([32, 512, 1024, 1056, 2048, 3008, 4096], [256, 512, 1024], [0, 32, 64, 100, 128, 256])),
)
def test_axis_starts_cover_and_overlap(length, tile, overlap):
    starts = tiling.axis_starts(length, tile, overlap)
    size = min(tile, length)
    assert starts[0] == 0
    assert starts[-1] + size == length
    assert all(s % tiling.ALIGN == 0 for s in starts)
    for a, b in zip(starts, starts[1:]):
        assert b > a
        assert a + size - b >= min(overlap, size - tiling.ALIGN)


def test_axis_starts_single_tile_when_image_is_small():
    assert tiling.axis_starts(512, 1024, 128) == [0]


def test_axis_starts_rejects_unaligned_sizes():
    with pytest.raises(ValueError):
        tiling.axis_starts(1000, 512, 64)


def test_plan_tiles_blend_matches_neighbours():
    tiles = tiling.plan_tiles(2048, 1536, 1024, 128)
    xs = sorted({t.x for t in tiles})
    ys = sorted({t.y for t in tiles})
    assert len(tiles) == len(xs) * len(ys)
    for t in tiles:
        assert (t.blend_left == 0) == (t.x == 0)
        assert (t.blend_top == 0) == (t.y == 0)
        if t.x:
            prev = xs[xs.index(t.x) - 1]
            assert t.blend_left == prev + t.w - t.x
            assert t.blend_left >= 128


def test_blend_mask_ramps_only_on_shared_edges():
    mask = tiling.blend_mask(tiling.Tile(0, 0, 64, 64, 0, 0))
    assert torch.all(mask == 1)

    mask = tiling.blend_mask(tiling.Tile(32, 0, 64, 64, 16, 0))
    assert mask[0, 0] < 0.05
    assert torch.all(mask[:, 16:] == 1)
    assert torch.all(mask[0, 1:16] > mask[0, :15])

    mask = tiling.blend_mask(tiling.Tile(0, 32, 64, 64, 0, 16))
    assert torch.all(mask[16:, :] == 1)
    assert mask[0, 30] < 0.05


@pytest.mark.parametrize("size,tile,overlap", [((768, 1280), 512, 128), ((1024, 1024), 1024, 64), ((1536, 640), 256, 64)])
def test_sequential_paste_reproduces_consistent_tiles(size, tile, overlap):
    """If every tile comes back as the same global image, so does the canvas."""
    h, w = size
    target = torch.rand(1, h, w, 3)
    canvas = torch.rand(1, h, w, 3)
    for t in tiling.plan_tiles(w, h, tile, overlap):
        tiling.paste(canvas, tiling.crop(target, t), t)
    assert torch.allclose(canvas, target, atol=1e-6)


def test_paste_blends_towards_previous_content():
    canvas = torch.zeros(1, 64, 96, 3)
    t = tiling.Tile(32, 0, 64, 64, 32, 0)
    tiling.paste(canvas, torch.ones(1, 64, 64, 3), t)
    assert torch.all(canvas[:, :, :32] == 0)
    row = canvas[0, 0, 32:, 0]
    assert row[0] < 0.05 and torch.all(row[32:] == 1)
    assert torch.all(row[1:] >= row[:-1])


def test_pad_to_multiple_repeats_edges():
    image = torch.rand(2, 100, 70, 3)
    padded = tiling.pad_to_multiple(image, 32)
    assert padded.shape == (2, 128, 96, 3)
    assert torch.equal(padded[:, :100, :70], image)
    assert torch.equal(padded[:, 127, :70], image[:, 99])
    assert torch.equal(padded[:, :100, 95], image[:, :, 69])
    assert tiling.pad_to_multiple(padded, 32) is padded


def test_scale_schedule():
    assert tiling.scale_schedule(2.0, 1) == [2.0]
    steps = tiling.scale_schedule(4.0, 2)
    assert steps[0] == pytest.approx(2.0) and steps[1] == pytest.approx(4.0)
    assert tiling.scale_schedule(3.0, 3)[-1] == pytest.approx(3.0)


def test_scaled_size_and_resize():
    assert tiling.scaled_size(1000, 750, 2.0) == (2000, 1500)
    assert tiling.scaled_size(333, 333, 1.5) == (500, 500)
    image = torch.rand(1, 40, 60, 3)
    up = tiling.resize_image(image, 150, 100)
    assert up.shape == (1, 100, 150, 3)
    assert up.min() >= 0 and up.max() <= 1
    assert tiling.resize_image(image, 60, 40) is image
