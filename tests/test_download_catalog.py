import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dm = load("download_models", "scripts/download_models.py")


def test_presets_reference_known_groups():
    for groups in dm.PRESETS.values():
        assert all(g in dm.CATALOG for g in groups)


def test_catalog_entries_are_unique_and_https():
    seen = set()
    for entries in dm.CATALOG.values():
        for folder, name, url, size in entries:
            assert folder in {"checkpoints", "controlnet", "upscale_models"}
            assert url.startswith("https://") and size > 0
            assert (folder, name) not in seen
            seen.add((folder, name))


def test_workflow_models_are_downloadable():
    """Every model the example workflows load can be fetched by the script."""
    import json

    names = {name for entries in dm.CATALOG.values() for _, name, _, _ in entries}
    loaders = {"CheckpointLoaderSimple", "UpscaleModelLoader", "ControlNetLoader"}
    for wf in (ROOT / "example_workflows").glob("*.json"):
        for node in json.loads(wf.read_text(encoding="utf-8"))["nodes"]:
            if node["type"] in loaders:
                assert node["widgets_values"][0] in names, (wf.name, node["widgets_values"][0])


def test_preset_size_counts_shared_groups_once():
    group = {g: sum(size for *_, size in entries) for g, entries in dm.CATALOG.items()}
    assert dm.preset_size_mb(["sdxl", "sd15"]) == group["upscalers"] + group["sdxl"] + group["sd15"]
    assert dm.preset_size_mb(["none"]) == 0


def test_download_rejects_unknown_preset(tmp_path):
    (tmp_path / "models").mkdir()
    with pytest.raises(SystemExit):
        dm.download(tmp_path, ["nope"])
