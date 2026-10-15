"""End-to-end check of an installed Bokin Upscaler (used by CI).

Run with the installed app's Python:

    <dir>/.venv/bin/python installer/smoke_test.py --dir <dir>

Starts the launcher without a browser, checks the /bokin page and upscales a
small image with Bokin Upscale Fast through ComfyUI's API.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from PIL import Image


def get(url: str, timeout: float = 10):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read()


def get_json(url: str):
    return json.loads(get(url))


def post(url: str, data: bytes, content_type: str):
    request = urllib.request.Request(url, data=data, headers={"Content-Type": content_type})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"POST {url} -> {e.code}: {e.read().decode(errors='replace')}")


def combo(spec) -> list:
    if isinstance(spec[0], list):
        return spec[0]
    return spec[1].get("options", []) if spec[0] == "COMBO" else []


def kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    else:
        os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()


def check(base: str, proc: subprocess.Popen, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while True:
        if proc.poll() is not None:
            raise SystemExit(f"launcher exited early with code {proc.returncode}")
        try:
            get(f"{base}/system_stats", timeout=3)
            break
        except OSError:
            if time.monotonic() > deadline:
                raise SystemExit("server did not start in time")
            time.sleep(2)
    print("server up")

    page = get(f"{base}/bokin").decode()
    assert "Bokin Upscaler" in page, "app page missing"
    assert "BokinUpscale" in get_json(f"{base}/object_info/BokinUpscale"), "Bokin nodes not registered"
    upscalers = combo(get_json(f"{base}/object_info/UpscaleModelLoader")["UpscaleModelLoader"]["input"]["required"]["model_name"])
    print("app page ok, upscale models:", upscalers)

    buf = io.BytesIO()
    Image.new("RGB", (96, 64), (200, 120, 40)).save(buf, format="PNG")
    boundary = uuid.uuid4().hex
    body = b"".join([
        f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="smoke.png"\r\n'
        "Content-Type: image/png\r\n\r\n".encode(), buf.getvalue(), b"\r\n",
        f'--{boundary}\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n'.encode(),
        f"--{boundary}--\r\n".encode(),
    ])
    name = post(f"{base}/upload/image", body, f"multipart/form-data; boundary={boundary}")["name"]

    prompt = {"1": {"class_type": "LoadImage", "inputs": {"image": name}}}
    fast = {"image": ["1", 0], "upscale_by": 2.0}
    if upscalers:
        prompt["2"] = {"class_type": "UpscaleModelLoader", "inputs": {"model_name": upscalers[0]}}
        fast["upscale_model"] = ["2", 0]
    prompt["3"] = {"class_type": "BokinUpscaleFast", "inputs": fast}
    prompt["4"] = {"class_type": "SaveImage", "inputs": {"images": ["3", 0], "filename_prefix": "Bokin/smoke"}}
    prompt_id = post(f"{base}/prompt", json.dumps({"prompt": prompt}).encode(), "application/json")["prompt_id"]

    while True:
        history = get_json(f"{base}/history/{prompt_id}")
        if prompt_id in history:
            break
        if time.monotonic() > deadline:
            raise SystemExit("upscale did not finish in time")
        time.sleep(2)
    entry = history[prompt_id]
    if entry["status"]["status_str"] != "success":
        raise SystemExit(f"upscale failed: {json.dumps(entry['status'])[:2000]}")
    image = entry["outputs"]["4"]["images"][0]
    query = urllib.parse.urlencode({"filename": image["filename"], "subfolder": image["subfolder"], "type": image["type"]})
    size = Image.open(io.BytesIO(get(f"{base}/view?{query}"))).size
    assert size == (192, 128), f"unexpected output size {size}"
    print(f"upscale ok: {image['filename']} {size}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8199)
    parser.add_argument("--timeout", type=float, default=900)
    args = parser.parse_args()

    root = args.dir.resolve()
    log_path = root / "smoke-launcher.log"
    kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    with open(log_path, "w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            [sys.executable, str(root / "bokin_launcher.py"), "--no-browser", "--port", str(args.port),
             "--output-dir", str(root / "smoke-output")],
            stdout=log, stderr=subprocess.STDOUT, env={**os.environ, "PYTHONUTF8": "1"}, **kwargs,
        )
        try:
            check(f"http://127.0.0.1:{args.port}", proc, args.timeout)
        except BaseException:
            log.flush()
            print("---- launcher log ----")
            print(log_path.read_text(encoding="utf-8", errors="replace")[-8000:])
            raise
        finally:
            kill_tree(proc)
    print("SMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
