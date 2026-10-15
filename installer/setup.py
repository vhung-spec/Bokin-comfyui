"""Bokin Upscaler installer - the cross-platform part.

Started by installer/windows/setup.ps1 (Windows) or installer/install.sh
(Linux/macOS) with the Python of the app's own virtual environment. Installs
everything into one folder:

    <dir>/.venv          Python + PyTorch + ComfyUI requirements
    <dir>/ComfyUI        ComfyUI, with the Bokin node pack in custom_nodes
    <dir>/tools          uv and its Python builds
    <dir>/bokin_launcher.py, "Bokin Upscaler" launcher script, icon

Running it again updates the Bokin node pack and skips what is already there.
"""

from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

COMFYUI_TAG = "v0.40.0"
COMFYUI_ZIP = "https://github.com/comfyanonymous/ComfyUI/archive/refs/tags/{tag}.zip"
TORCH_INDEX = {
    "cuda": "https://download.pytorch.org/whl/cu128",
    "cpu": "https://download.pytorch.org/whl/cpu",
}
SRC = Path(__file__).resolve().parent.parent  # the Bokin repository / node pack
INSTALLER = SRC / "installer"
APP_NAME = "Bokin Upscaler"

def utf8_output() -> None:
    """Never crash on Vietnamese text when output goes to a non-UTF-8 pipe (e.g. cp1252)."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


utf8_output()

MODEL_CHOICES = [
    ("sdxl", "SDXL + ControlNet Tile", "khuyên dùng, GPU NVIDIA 8 GB+"),
    ("sd15", "SD 1.5 + ControlNet Tile", "GPU 4 GB+"),
    ("fast", "Chỉ upscale nhanh", "máy yếu / không có GPU"),
    ("flux", "Flux.1 dev fp8", "chi tiết nhất, GPU 12 GB+"),
]


class Tee:
    """Mirror everything printed into the install log."""

    def __init__(self, stream, log):
        self.stream, self.log = stream, log

    def write(self, text):
        self.stream.write(text)
        self.log.write(text)
        return len(text)

    def flush(self):
        self.stream.flush()
        self.log.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)


def step(n: int, total: int, text: str) -> None:
    print(f"\n[{n}/{total}] {text}", flush=True)


def run(cmd: list) -> None:
    """Run a command in this console, so its own progress bars stay visible."""
    print("  $ " + " ".join(str(c) for c in cmd), flush=True)
    code = subprocess.run([str(c) for c in cmd]).returncode
    if code:
        raise SystemExit(f"Lệnh thất bại (mã {code}): {Path(str(cmd[0])).name} - xem install-log.txt")


def load_downloader():
    spec = importlib.util.spec_from_file_location("bokin_download_models", SRC / "scripts" / "download_models.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------- hardware

def detect_gpu() -> dict:
    if sys.platform == "darwin":
        return {"kind": "mps" if platform.machine() == "arm64" else "cpu", "name": platform.machine(), "vram_gb": 0}
    smi = shutil.which("nvidia-smi")
    if smi:
        try:
            out = subprocess.run([smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=30).stdout.strip().splitlines()
            if out:
                name, mem = [part.strip() for part in out[0].split(",")[:2]]
                return {"kind": "cuda", "name": name, "vram_gb": round(float(mem) / 1024, 1)}
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    return {"kind": "cpu", "name": platform.processor() or platform.machine(), "vram_gb": 0}


def default_models(gpu: dict) -> str:
    if gpu["kind"] == "cuda":
        return "sdxl" if gpu["vram_gb"] >= 7.5 else "sd15"
    if gpu["kind"] == "mps":
        return "sd15"
    return "fast"


def ask_models(gpu: dict, sizes) -> str:
    default = default_models(gpu)
    print("\nChọn bộ model muốn tải:")
    for i, (key, label, note) in enumerate(MODEL_CHOICES, 1):
        mark = "  <- gợi ý cho máy này" if key == default else ""
        print(f"  {i}) {label:<26} ~{sizes(key) / 1000:,.1f} GB  ({note}){mark}")
    default_index = [k for k, *_ in MODEL_CHOICES].index(default) + 1
    while True:
        answer = input(f"Chọn 1-{len(MODEL_CHOICES)} [mặc định {default_index}]: ").strip()
        if not answer:
            return default
        if answer.isdigit() and 1 <= int(answer) <= len(MODEL_CHOICES):
            return MODEL_CHOICES[int(answer) - 1][0]


# ---------------------------------------------------------------- steps

def install_comfyui(target: Path, tag: str) -> None:
    if (target / "main.py").exists():
        print(f"  ✓ đã có ComfyUI tại {target}")
        return
    url = COMFYUI_ZIP.format(tag=tag)
    print(f"  ↓ tải ComfyUI {tag}")
    with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
        try:
            archive = Path(tmp) / "comfyui.zip"
            request = urllib.request.Request(url, headers={"User-Agent": "bokin-installer"})
            with urllib.request.urlopen(request, timeout=120) as response, open(archive, "wb") as f:
                shutil.copyfileobj(response, f)
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(tmp)
            extracted = next(p for p in Path(tmp).iterdir() if p.is_dir() and (p / "main.py").exists())
        except (OSError, zipfile.BadZipFile, StopIteration) as e:
            git = shutil.which("git")
            if not git:
                raise SystemExit(f"Không tải được ComfyUI ({e}). Kiểm tra kết nối Internet rồi chạy lại.")
            print(f"  tải zip lỗi ({e}), thử git clone")
            extracted = Path(tmp) / "ComfyUI"
            run([git, "clone", "--depth", "1", "--branch", tag, "https://github.com/comfyanonymous/ComfyUI.git", extracted])
        shutil.move(str(extracted), target)
    print(f"  ✓ ComfyUI {tag}")


def install_torch(uv: Path, python: Path, kind: str, index: str | None) -> None:
    if kind == "skip":
        print("  - bỏ qua PyTorch (--torch skip)")
        return
    if index is None:
        index = TORCH_INDEX.get(kind)
    cmd = [uv, "pip", "install", "--python", python, "torch", "torchvision", "torchaudio"]
    if index:
        cmd += ["--index-url", index]
    run(cmd)


def install_node_pack(comfy: Path) -> None:
    dest = comfy / "custom_nodes" / "Bokin-comfyui"
    if dest.is_symlink() or dest.is_file():
        dest.unlink()
    elif dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(SRC, dest, ignore=shutil.ignore_patterns(
        ".git", ".github", "tests", "installer", "dist", "__pycache__", "*.pyc", ".pytest_cache", ".ruff_cache"))
    print(f"  ✓ Bokin node pack -> {dest}")


def write_launchers(root: Path) -> Path:
    """Copy the launcher and icon into ``root``; return the file users start."""
    shutil.copy2(INSTALLER / "bokin_launcher.py", root / "bokin_launcher.py")
    for icon in ("bokin.ico", "bokin.png"):
        shutil.copy2(INSTALLER / "assets" / icon, root / icon)
    if os.name == "nt":
        start = root / f"{APP_NAME}.bat"
        shutil.copy2(INSTALLER / "windows" / f"{APP_NAME}.bat", start)
    else:
        name = f"{APP_NAME}.command" if sys.platform == "darwin" else "bokin-upscaler.sh"
        start = root / name
        start.write_text(
            "#!/usr/bin/env bash\n"
            'cd "$(dirname "$0")"\n'
            'exec ./.venv/bin/python ./bokin_launcher.py "$@"\n',
            encoding="utf-8",
        )
        start.chmod(0o755)
    print(f"  ✓ {start}")
    return start


def desktop_dir() -> Path:
    if os.name == "nt":
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"],
                                 capture_output=True, text=True, timeout=30).stdout.strip()
            if out:
                return Path(out)
        except (OSError, subprocess.SubprocessError):
            pass
    return Path.home() / "Desktop"


def create_shortcuts(root: Path, start: Path) -> None:
    desktop = desktop_dir()
    if os.name == "nt":
        script = (
            "$ws = New-Object -ComObject WScript.Shell; "
            "foreach ($dir in @('{desktop}', [Environment]::GetFolderPath('Programs'))) {{ "
            "$s = $ws.CreateShortcut((Join-Path $dir '{name}.lnk')); "
            "$s.TargetPath = '{target}'; $s.WorkingDirectory = '{root}'; $s.IconLocation = '{icon}'; $s.Save() }}"
        ).format(desktop=str(desktop).replace("'", "''"), name=APP_NAME, target=str(start).replace("'", "''"),
                 root=str(root).replace("'", "''"), icon=str(root / "bokin.ico").replace("'", "''"))
        run(["powershell", "-NoProfile", "-Command", script])
        print("  ✓ shortcut trên Desktop và Start Menu")
    elif sys.platform == "darwin":
        if desktop.is_dir():
            link = desktop / start.name
            if link.exists() or link.is_symlink():
                link.unlink()
            link.symlink_to(start)
            print(f"  ✓ {link}")
    else:
        entry = (
            "[Desktop Entry]\nType=Application\n"
            f"Name={APP_NAME}\nComment=Phóng to ảnh kiểu Shakker\n"
            f'Exec="{start}"\nIcon={root / "bokin.png"}\nTerminal=true\nCategories=Graphics;\n'
        )
        apps = Path.home() / ".local" / "share" / "applications"
        apps.mkdir(parents=True, exist_ok=True)
        targets = [apps / "bokin-upscaler.desktop"]
        if desktop.is_dir():
            targets.append(desktop / "bokin-upscaler.desktop")
        for path in targets:
            path.write_text(entry, encoding="utf-8")
            path.chmod(0o755)
            print(f"  ✓ {path}")


# ---------------------------------------------------------------- main

def main() -> int:
    parser = argparse.ArgumentParser(description="Cài Bokin Upscaler")
    parser.add_argument("--dir", required=True, type=Path, help="thư mục cài đặt")
    parser.add_argument("--uv", required=True, type=Path, help="đường dẫn tới uv")
    parser.add_argument("--models", choices=["sdxl", "sd15", "fast", "flux", "all", "none"],
                        help="bộ model cần tải (bỏ trống = hỏi)")
    parser.add_argument("--torch", default="auto", choices=["auto", "cuda", "cpu", "mps", "skip"],
                        help="bản PyTorch: auto = theo GPU của máy")
    parser.add_argument("--torch-index", help="index PyTorch tự chọn (mặc định theo --torch)")
    parser.add_argument("--comfyui-tag", default=COMFYUI_TAG)
    parser.add_argument("--no-shortcut", action="store_true", help="không tạo shortcut")
    parser.add_argument("--yes", action="store_true", help="không hỏi gì, dùng lựa chọn mặc định")
    args = parser.parse_args()

    root = args.dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    log = open(root / "install-log.txt", "a", encoding="utf-8")
    log.write(f"\n===== {datetime.datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
    sys.stdout = Tee(sys.stdout, log)
    sys.stderr = Tee(sys.stderr, log)

    python = Path(sys.executable)
    comfy = root / "ComfyUI"
    downloader = load_downloader()
    gpu = detect_gpu()

    print("=" * 60)
    print(f"  {APP_NAME} - cài đặt")
    print("=" * 60)
    print(f"Thư mục cài: {root}")
    if gpu["kind"] == "cuda":
        print(f"GPU: {gpu['name']} ({gpu['vram_gb']} GB)")
    elif gpu["kind"] == "mps":
        print("GPU: Apple Silicon (Metal)")
    else:
        print("Không thấy GPU NVIDIA: sẽ chạy bằng CPU (chế độ vẽ lại sẽ rất chậm).")

    models = args.models
    if models is None:
        if args.yes or not sys.stdin.isatty():
            models = default_models(gpu)
        else:
            models = ask_models(gpu, lambda key: downloader.preset_size_mb([key]))
    torch_kind = args.torch
    if torch_kind == "auto":
        torch_kind = {"cuda": "cuda", "mps": "mps"}.get(gpu["kind"], "cpu")
    if sys.platform == "darwin" and torch_kind in ("cpu", "mps"):
        torch_kind = "mps"  # macOS wheels on PyPI already include Metal and CPU
    print(f"PyTorch: {torch_kind} · Model: {models}")

    total = 6
    step(1, total, f"Tải ComfyUI {args.comfyui_tag}")
    install_comfyui(comfy, args.comfyui_tag)

    step(2, total, "Cài PyTorch (file lớn, có thể mất vài phút)")
    install_torch(args.uv, python, torch_kind, args.torch_index)

    step(3, total, "Cài thư viện của ComfyUI")
    run([args.uv, "pip", "install", "--python", python, "-r", comfy / "requirements.txt"])

    step(4, total, "Cài bộ node Bokin")
    install_node_pack(comfy)

    step(5, total, f"Tải model ({models})")
    failed = downloader.download(comfy, [models])

    step(6, total, "Tạo shortcut")
    start = write_launchers(root)
    if not args.no_shortcut:
        create_shortcuts(root, start)
    (root / "bokin.json").write_text(json.dumps({
        "comfyui_tag": args.comfyui_tag, "torch": torch_kind, "gpu": gpu, "models": models,
        "installed": datetime.datetime.now().isoformat(timespec="seconds"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    cache = os.environ.get("UV_CACHE_DIR")
    if cache and Path(cache).resolve().is_relative_to(root):
        subprocess.run([str(args.uv), "cache", "clean"], capture_output=True)

    print("\n" + "=" * 60)
    if failed:
        print("Cài xong nhưng một số model chưa tải được. Hãy tải tay và đặt vào thư mục tương ứng trong")
        print(f"  {comfy / 'models'}")
        for line in failed:
            print(f"  - {line}")
    else:
        print("Cài đặt hoàn tất!")
    print(f"Mở app: bấm shortcut '{APP_NAME}' trên Desktop, hoặc chạy:\n  {start}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
