"""Start Bokin Upscaler: run ComfyUI in the background and open the app window.

Copied next to the ComfyUI folder by the installer and started by the
"Bokin Upscaler" shortcut. Keep the console window open while using the app;
closing it (or Ctrl+C) stops the server.
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMFY = ROOT / "ComfyUI"
HOST = "127.0.0.1"


def http_ok(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status == 200
    except OSError:
        return False


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((HOST, port))
            return True
        except OSError:
            return False


def pick_port(preferred: int) -> tuple[int, bool]:
    """A port to use, and whether Bokin is already running there."""
    for port in range(preferred, preferred + 20):
        if http_ok(f"http://{HOST}:{port}/bokin"):
            return port, True
        if port_free(port):
            return port, False
    raise SystemExit("Không tìm được cổng mạng trống để chạy Bokin.")


def pictures_dir() -> Path:
    if sys.platform.startswith("linux") and shutil.which("xdg-user-dir"):
        try:
            out = subprocess.run(["xdg-user-dir", "PICTURES"], capture_output=True, text=True, timeout=5).stdout.strip()
            if out and Path(out).is_dir() and Path(out) != Path.home():
                return Path(out)
        except (OSError, subprocess.SubprocessError):
            pass
    pictures = Path.home() / "Pictures"
    return pictures if pictures.is_dir() else Path.home()


def app_browser() -> str | None:
    """Edge or Chrome, which can open the page as its own app window."""
    if os.name == "nt":
        bases = [os.environ.get(k) for k in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
        rel = [r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"]
        candidates = [str(Path(b) / r) for r in rel for b in bases if b]
    elif sys.platform == "darwin":
        candidates = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                      "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]
    else:
        candidates = [shutil.which(n) for n in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge")]
    return next((c for c in candidates if c and Path(c).exists()), None)


def open_window(url: str) -> None:
    browser = app_browser()
    if browser:
        try:
            subprocess.Popen([browser, f"--app={url}", "--window-size=1440,920"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except OSError:
            pass
    webbrowser.open(url)


def gpu_available() -> bool:
    """Whether PyTorch can use a GPU. ComfyUI crashes on start without --cpu otherwise."""
    if sys.platform == "darwin":
        return True  # Metal, or ComfyUI's own CPU fallback
    probe = ("import sys, torch; xpu = getattr(torch, 'xpu', None); "
             "sys.exit(0 if torch.cuda.is_available() or (xpu is not None and xpu.is_available()) else 3)")
    return subprocess.run([sys.executable, "-c", probe], capture_output=True).returncode != 3


def wait_ready(proc: subprocess.Popen, port: int, timeout: float = 900) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        if http_ok(f"http://{HOST}:{port}/system_stats"):
            return True
        time.sleep(1)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Chạy Bokin Upscaler")
    parser.add_argument("--port", type=int, default=8188)
    parser.add_argument("--no-browser", action="store_true", help="không tự mở cửa sổ app")
    parser.add_argument("--output-dir", type=Path, help="nơi lưu ảnh kết quả")
    args, comfy_args = parser.parse_known_args()

    if not (COMFY / "main.py").exists():
        raise SystemExit(f"Không thấy ComfyUI tại {COMFY}. Hãy chạy lại bộ cài.")

    port, running = pick_port(args.port)
    url = f"http://{HOST}:{port}/bokin"
    if running:
        print(f"Bokin Upscaler đang chạy sẵn: {url}")
        if not args.no_browser:
            open_window(url)
        return 0

    output = args.output_dir or pictures_dir() / "Bokin Upscaler"
    output.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "main.py", "--listen", HOST, "--port", str(port), "--preview-method", "auto",
           "--disable-auto-launch", "--output-directory", str(output), *comfy_args]

    print("=" * 60)
    print("  Bokin Upscaler")
    print("=" * 60)
    if "--cpu" not in comfy_args and not gpu_available():
        cmd.append("--cpu")
        print("Không dùng được GPU: chạy bằng CPU (chế độ vẽ lại sẽ rất chậm).")
    print(f"Ảnh kết quả lưu tại: {output}")
    print("Đang khởi động (lần đầu có thể mất 1-2 phút)…\n", flush=True)
    proc = subprocess.Popen(cmd, cwd=COMFY)
    try:
        if not wait_ready(proc, port):
            print("\nKhông khởi động được ComfyUI. Xem thông báo lỗi ở trên.")
            proc.terminate()
            return proc.wait() or 1
        print("\n" + "=" * 60)
        print(f"  Bokin Upscaler đã sẵn sàng: {url}")
        print("  Giữ cửa sổ này mở trong lúc dùng app. Đóng cửa sổ (hoặc Ctrl+C) để tắt.")
        print("=" * 60, flush=True)
        if not args.no_browser:
            open_window(url)
        return proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        return 0


if __name__ == "__main__":
    sys.exit(main())
