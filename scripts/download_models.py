"""Download the models the Bokin workflows use into a ComfyUI folder.

    python scripts/download_models.py <ComfyUI folder> [fast|sd15|sdxl|flux|all ...]

Finished files are skipped and partial downloads resume. For gated
HuggingFace repos set the HF_TOKEN environment variable first.
Only the Python standard library is used, so any Python 3.10+ can run it.
"""

from __future__ import annotations

import os
import ssl
import sys
import time
import urllib.request
from pathlib import Path

HF = "https://huggingface.co"
GH = "https://github.com/xinntao/Real-ESRGAN/releases/download"

# group -> [(models subfolder, file name, url, approximate size in MB)]
CATALOG = {
    "upscalers": [
        ("upscale_models", "4x-UltraSharp.pth", f"{HF}/lokCX/4x-Ultrasharp/resolve/main/4x-UltraSharp.pth", 67),
        ("upscale_models", "RealESRGAN_x4plus.pth", f"{GH}/v0.1.0/RealESRGAN_x4plus.pth", 64),
        ("upscale_models", "RealESRGAN_x4plus_anime_6B.pth", f"{GH}/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth", 18),
    ],
    "sd15": [
        ("checkpoints", "v1-5-pruned-emaonly-fp16.safetensors",
         f"{HF}/Comfy-Org/stable-diffusion-v1-5-archive/resolve/main/v1-5-pruned-emaonly-fp16.safetensors", 2000),
        ("controlnet", "control_v11f1e_sd15_tile_fp16.safetensors",
         f"{HF}/comfyanonymous/ControlNet-v1-1_fp16_safetensors/resolve/main/control_v11f1e_sd15_tile_fp16.safetensors", 690),
    ],
    "sdxl": [
        ("checkpoints", "sd_xl_base_1.0.safetensors",
         f"{HF}/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors", 6600),
        ("controlnet", "xinsir-controlnet-tile-sdxl-1.0.safetensors",
         f"{HF}/xinsir/controlnet-tile-sdxl-1.0/resolve/main/diffusion_pytorch_model.safetensors", 2400),
    ],
    "flux": [
        # Black Forest Labs non-commercial licence.
        ("checkpoints", "flux1-dev-fp8.safetensors", f"{HF}/Comfy-Org/flux1-dev/resolve/main/flux1-dev-fp8.safetensors", 16400),
    ],
}

PRESETS = {
    "none": [],
    "fast": ["upscalers"],
    "sd15": ["upscalers", "sd15"],
    "sdxl": ["upscalers", "sdxl"],
    "flux": ["upscalers", "flux"],
    "all": ["upscalers", "sd15", "sdxl", "flux"],
}


def preset_size_mb(presets: list[str]) -> int:
    groups = {g for p in presets for g in PRESETS[p]}
    return sum(size for g in groups for *_, size in CATALOG[g])


def _ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    if not context.cert_store_stats().get("x509_ca"):
        # Standalone Python builds may not find the system certificates.
        try:
            import certifi

            context.load_verify_locations(certifi.where())
        except ImportError:
            pass
    return context


def fetch(url: str, dest: Path, context: ssl.SSLContext) -> None:
    """Download ``url`` to ``dest``, resuming a previous ``.part`` file."""
    part = dest.with_name(dest.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    request = urllib.request.Request(url, headers={"User-Agent": "bokin-downloader"})
    if have:
        request.add_header("Range", f"bytes={have}-")
    token = os.environ.get("HF_TOKEN")
    if token and url.startswith(HF):
        # Not forwarded on redirects, so the token never reaches the CDN.
        request.add_unredirected_header("Authorization", f"Bearer {token}")

    with urllib.request.urlopen(request, timeout=60, context=context) as response:
        if have and response.status != 206:  # server ignored the range: start over
            have = 0
        total = response.length + have if response.length is not None else None
        done, last, started = have, 0.0, time.monotonic()
        with open(part, "ab" if have else "wb") as f:
            while chunk := response.read(1 << 20):
                f.write(chunk)
                done += len(chunk)
                now = time.monotonic()
                if now - last > 0.5:
                    last = now
                    speed = (done - have) / max(now - started, 1e-6) / 1e6
                    pct = f"{done * 100 // total:3d}% " if total else ""
                    print(f"\r    {pct}{done / 1e6:,.0f}/{(total or 0) / 1e6:,.0f} MB  {speed:,.1f} MB/s   ",
                          end="", flush=True)
    print(f"\r    {done / 1e6:,.0f} MB" + " " * 40)
    part.replace(dest)


def download(comfy_dir: Path, presets: list[str]) -> list[str]:
    """Download every model in ``presets``. Returns the ones that failed."""
    models = Path(comfy_dir) / "models"
    if not models.is_dir():
        raise SystemExit(f"Không thấy thư mục {models} - kiểm tra lại đường dẫn ComfyUI.")
    for p in presets:
        if p not in PRESETS:
            raise SystemExit(f"Preset không hợp lệ: {p} (chọn {', '.join(PRESETS)})")

    context = _ssl_context()
    failed, seen = [], set()
    for group in [g for p in presets for g in PRESETS[p]]:
        for folder, name, url, size in CATALOG[group]:
            if (folder, name) in seen:
                continue
            seen.add((folder, name))
            dest = models / folder / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                print(f"  ✓ đã có  {folder}/{name}")
                continue
            print(f"  ↓ tải    {folder}/{name}  (~{size:,} MB)")
            for attempt in range(3):
                try:
                    fetch(url, dest, context)
                    break
                except Exception as e:  # network hiccup: retry, resuming the .part file
                    print(f"\n    lỗi: {e}")
                    if attempt == 2:
                        failed.append(f"{folder}/{name}  <-  {url}")
                    else:
                        time.sleep(3)
    return failed


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):  # Vietnamese text must not crash on cp1252 pipes
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 1
    failed = download(Path(argv[0]), argv[1:] or ["fast"])
    if failed:
        print("Không tải được (hãy tải thủ công vào thư mục models tương ứng):", file=sys.stderr)
        for line in failed:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("Xong. Khởi động lại ComfyUI (hoặc bấm R) để thấy model mới.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
