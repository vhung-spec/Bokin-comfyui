"""Bokin Upscale web: staff pick an upscale type, adjust its settings, upload images and download the results.

Each upscale type is a published TensorArt AI Tool listed in upscalers.json. The settings shown on the page are the
fields the AI Tool exposes as TA Nodes (denoise, steps, megapixels...), read from TensorArt, with labels and ranges
from upscalers.json. Adding a type means publishing another AI Tool and adding an entry; no code changes.

The page talks only to this server. This server calls the TensorArt (TAMS) API with the company's key, so the key
never reaches a browser. Python 3.9+, standard library only.

    TAMS_API_KEY=... TA_TOOL_ID=... python3 server.py

API flow (same calls as TensorArt's own ComfyUI_TENSOR_ART nodes):
    GET  {base}/v1/workflows/{toolId}       -> fields.fieldAttrs: the AI Tool's editable fields (nodeId, fieldName, ...)
    POST {base}/v1/resource/image           -> resourceId, putUrl, headers; then PUT the file to putUrl
    POST {base}/v1/jobs/workflow/template   -> job.id  (templateId = the AI Tool, fieldAttrs = image + settings)
    GET  {base}/v1/jobs/{id}                -> job.status WAITING / RUNNING / SUCCESS / FAILED, successInfo.images[].url
"""
import base64
import hmac
import json
import math
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
JOB_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
FIELDS_TTL = 600  # seconds to cache an AI Tool's field list

# Labels and ranges for common ComfyUI fields, used when upscalers.json says nothing about a field.
KNOWN_FIELDS = {
    "denoise": {"label": "Mức vẽ lại (denoise)", "min": 0.0, "max": 1.0, "step": 0.01,
                "hint": "Cao hơn thì thêm nhiều chi tiết nhưng dễ đổi ảnh."},
    "steps": {"label": "Số bước", "min": 1, "max": 50, "step": 1, "hint": "Nhiều bước hơn thì chậm và tốn credit hơn."},
    "guidance": {"label": "FluxGuidance", "min": 0.0, "max": 10.0, "step": 0.1},
    "megapixels": {"label": "Kích thước ra (megapixel)", "min": 1.0, "max": 16.0, "step": 0.5,
                   "hint": "8 MP khoảng 4K. Ảnh càng lớn càng tốn credit."},
    "noise_seed": {"label": "Seed", "min": 0, "step": 1},
    "seed": {"label": "Seed", "min": 0, "step": 1},
    "cfg": {"label": "CFG", "min": 0.0, "max": 20.0, "step": 0.1},
    "text": {"label": "Prompt", "type": "text"},
    "size": {"label": "Thu nhỏ ảnh gốc về (px)", "min": 256, "max": 4096, "step": 8},
}

CONFIG = {}


def expand(value, env):
    return re.sub(r"\$\{(\w+)\}", lambda m: env.get(m.group(1), ""), str(value or "")).strip()


def load_config(env=os.environ):
    path = Path(env.get("UPSCALERS_FILE") or HERE / "upscalers.json")
    entries = json.loads(path.read_text("utf-8"))["upscalers"] if path.exists() else \
        [{"key": "klein-4k", "name": "Klein 4K", "tool_id": "${TA_TOOL_ID}"}]
    upscalers = []
    for entry in entries:
        tool_id = expand(entry.get("tool_id"), env)
        if tool_id and entry.get("key"):
            upscalers.append({**entry, "tool_id": tool_id})
    CONFIG.clear()
    CONFIG.update(
        api_key=env.get("TAMS_API_KEY", ""),
        base_url=env.get("TAMS_BASE_URL", "https://ap-east-1.tensorart.cloud").rstrip("/"),
        image_node_id=env.get("TA_IMAGE_NODE_ID", ""),
        password=env.get("ACCESS_PASSWORD", ""),
        max_upload=int(float(env.get("MAX_UPLOAD_MB", "25")) * 1024 * 1024),
        upscalers=upscalers,
    )
    _tool_fields.clear()


class TamsError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def tams(method, path, body=None, timeout=60):
    req = urllib.request.Request(CONFIG["base_url"] + path, method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Accept": "application/json",
                                          "Authorization": "Bearer " + CONFIG["api_key"]})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        raise TamsError(f"TensorArt trả lỗi {e.code} cho {path}: {detail}") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise TamsError(f"Không kết nối được TensorArt ({path}): {e}") from None


_tool_fields = {}
_tool_fields_lock = threading.Lock()


def tool_fields(tool_id):
    """The AI Tool's editable fields, cached for FIELDS_TTL seconds."""
    with _tool_fields_lock:
        hit = _tool_fields.get(tool_id)
        if hit and time.time() - hit[0] < FIELDS_TTL:
            return hit[1]
    tool = tams("GET", f"/v1/workflows/{urllib.parse.quote(tool_id)}")
    fields = [f for f in (tool.get("fields") or {}).get("fieldAttrs") or [] if f.get("nodeId") and f.get("fieldName")]
    with _tool_fields_lock:
        _tool_fields[tool_id] = (time.time(), fields)
    return fields


def find_upscaler(key):
    for up in CONFIG["upscalers"]:
        if not key or up["key"] == key:
            return up
    raise TamsError("Kiểu upscale không tồn tại.", 400)


def is_number(text):
    try:
        return math.isfinite(float(text))
    except (TypeError, ValueError):
        return False


def options_of(field):
    try:
        values = (json.loads(field.get("inputString") or "{}").get("options") or {}).get("values")
    except (ValueError, AttributeError):
        return None
    return [str(v) for v in values] if isinstance(values, list) and values else None


def describe(up):
    """Image field and adjustable settings of one upscale type: TensorArt's fields + upscalers.json + KNOWN_FIELDS."""
    fields = tool_fields(up["tool_id"])
    image_node = up.get("image_node_id") or CONFIG["image_node_id"]
    images = [f for f in fields if f["fieldName"] == "image" and (not image_node or str(f["nodeId"]) == str(image_node))]
    images.sort(key=lambda f: "LoadImage" not in str(f.get("nodeName", "")))
    if images:
        image = (str(images[0]["nodeId"]), images[0]["fieldName"])
    elif image_node:
        image = (str(image_node), "image")
    else:
        raise TamsError(f"AI Tool của \"{up.get('name', up['key'])}\" không có ô ảnh đầu vào. Trên TensorArt, đánh dấu "
                        "ô image của node Load Image là TA Node rồi Publish lại.", 500)

    names = [f["fieldName"] for f in fields]
    overrides = up.get("params") or {}
    params = []
    for f in fields:
        node, name = str(f["nodeId"]), f["fieldName"]
        if (node, name) == image:
            continue
        key = name if names.count(name) == 1 else f"{name}#{node}"
        meta = {**KNOWN_FIELDS.get(name, {}), **overrides.get(f"{node}.{name}", overrides.get(key, {}))}
        if meta.get("hidden"):
            continue
        raw_default = str(f.get("fieldValue", "") if f.get("fieldValue") is not None else "")
        options = meta.get("options") or options_of(f)
        kind = meta.get("type") or ("select" if options else "number" if is_number(meta.get("default", raw_default)) else "text")
        param = {"key": key, "label": meta.get("label", name), "type": kind, "hint": meta.get("hint", ""),
                 "node": node, "field": name}
        if kind == "number":
            param["integer"] = bool(meta.get("integer", re.fullmatch(r"-?\d+", raw_default) and
                                                not isinstance(meta.get("step", 1), float)))
            param["default"] = float(meta.get("default", raw_default if is_number(raw_default) else meta.get("min", 0)))
            for k in ("min", "max", "step"):
                if k in meta:
                    param[k] = meta[k]
        elif kind == "select":
            param["options"] = [str(o) for o in options or []]
            param["default"] = str(meta.get("default", raw_default))
        else:
            param["default"] = str(meta.get("default", raw_default))
        params.append(param)
    return image, params


def public_upscalers():
    out = []
    for up in CONFIG["upscalers"]:
        item = {"key": up["key"], "name": up.get("name", up["key"]), "description": up.get("description", "")}
        try:
            item["params"] = [{k: v for k, v in p.items() if k not in ("node", "field")} for p in describe(up)[1]]
        except TamsError as e:
            item["params"], item["error"] = [], str(e)
        out.append(item)
    return out


def format_number(value, integer):
    if integer:
        return str(int(round(value)))
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text if "." in text else text + ".0"


def field_values(params, raw):
    """Validated settings as TensorArt fieldAttrs. Missing values use the default; numbers are clamped to the range."""
    attrs = []
    for p in params:
        value = raw.get(p["key"], p["default"])
        if p["type"] == "number":
            if not is_number(value):
                raise TamsError(f"\"{p['label']}\" phải là số.", 400)
            number = min(max(float(value), p.get("min", -math.inf)), p.get("max", math.inf))
            text = format_number(number, p["integer"])
        elif p["type"] == "select":
            text = str(value)
            if text not in p["options"]:
                raise TamsError(f"\"{p['label']}\" không có lựa chọn \"{text}\".", 400)
        else:
            text = str(value)[:4000]
        attrs.append({"nodeId": p["node"], "fieldName": p["field"], "fieldValue": text})
    return attrs


def upload_image(data, content_type):
    info = tams("POST", "/v1/resource/image", {})
    if "putUrl" not in info or "resourceId" not in info:
        raise TamsError(f"TensorArt không trả về chỗ tải ảnh lên: {info}")
    headers = info.get("headers") or {"Content-Type": content_type}
    req = urllib.request.Request(info["putUrl"], data=data, method="PUT", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120):
            pass
    except (urllib.error.URLError, TimeoutError) as e:
        raise TamsError(f"Tải ảnh lên TensorArt thất bại: {e}") from None
    return info["resourceId"]


def create_job(up, resource_id, settings):
    (image_node, image_field), params = describe(up)
    attrs = [{"nodeId": image_node, "fieldName": image_field, "fieldValue": resource_id}] + field_values(params, settings)
    resp = tams("POST", "/v1/jobs/workflow/template", {
        "requestId": uuid.uuid4().hex,
        "templateId": up["tool_id"],
        "fields": {"fieldAttrs": attrs},
    })
    job = resp.get("job") or {}
    if not job.get("id"):
        raise TamsError(f"TensorArt không tạo được job: {resp}")
    return str(job["id"])


def job_status(job_id):
    job = tams("GET", f"/v1/jobs/{job_id}", timeout=30).get("job") or {}
    status = job.get("status", "")
    out = {"status": {"WAITING": "waiting", "RUNNING": "running", "SUCCESS": "done", "FAILED": "failed"}.get(status, "running")}
    if status == "WAITING":
        info = job.get("waitingInfo") or {}
        out["queueRank"], out["queueLen"] = info.get("queueRank"), info.get("queueLen")
    elif status == "SUCCESS":
        images = (job.get("successInfo") or {}).get("images") or []
        if not images:
            return {"status": "failed", "error": "TensorArt chạy xong nhưng không trả về ảnh."}
        out["imageUrl"] = images[0].get("url")
    elif status == "FAILED":
        info = job.get("failedInfo") or {}
        out["error"] = info.get("reason") or info.get("message") or "TensorArt báo job thất bại."
    return out


def missing_config():
    missing = [] if CONFIG["api_key"] else ["TAMS_API_KEY"]
    if not CONFIG["upscalers"]:
        missing.append("TA_TOOL_ID (hoặc tool_id trong upscalers.json)")
    return missing


class Handler(BaseHTTPRequestHandler):
    server_version = "BokinUpscaleWeb/1.1"

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {self.address_string()} {fmt % args}", flush=True)

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def authorized(self):
        if not CONFIG["password"]:
            return True
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Basic "):
            try:
                _, _, password = base64.b64decode(auth[6:]).decode("utf-8").partition(":")
            except ValueError:
                password = ""
            if hmac.compare_digest(password.encode(), CONFIG["password"].encode()):
                return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Bokin Upscale", charset="UTF-8"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def do_GET(self):
        if not self.authorized():
            return
        path = urllib.parse.urlsplit(self.path).path
        try:
            if path in ("/", "/index.html"):
                body = (HERE / "index.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path == "/api/status":
                self.send_json({"configured": not missing_config(), "missing": missing_config()})
            elif path == "/api/upscalers":
                self.send_json({"upscalers": public_upscalers() if CONFIG["api_key"] else []})
            elif m := re.fullmatch(r"/api/jobs/([^/]+)", path):
                self.send_json(job_status(self.job_id(m.group(1))))
            elif m := re.fullmatch(r"/api/jobs/([^/]+)/image", path):
                self.send_result(self.job_id(m.group(1)))
            else:
                self.send_json({"error": "Không tìm thấy."}, 404)
        except TamsError as e:
            self.send_json({"error": str(e)}, e.status)

    def do_POST(self):
        if not self.authorized():
            return
        url = urllib.parse.urlsplit(self.path)
        if url.path != "/api/jobs":
            return self.send_json({"error": "Không tìm thấy."}, 404)
        if missing_config():
            return self.send_json({"error": "Máy chủ chưa cấu hình: thiếu " + ", ".join(missing_config())}, 500)
        content_type = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if not content_type.startswith("image/"):
            return self.send_json({"error": "Chỉ nhận file ảnh."}, 400)
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return self.send_json({"error": "File rỗng."}, 400)
        if length > CONFIG["max_upload"]:
            return self.send_json({"error": f"Ảnh quá lớn (tối đa {CONFIG['max_upload'] // (1024 * 1024)} MB)."}, 413)
        query = urllib.parse.parse_qs(url.query)
        try:
            up = find_upscaler(query.get("type", [""])[0])
            settings = json.loads(query.get("params", ["{}"])[0] or "{}")
            if not isinstance(settings, dict):
                raise ValueError
        except ValueError:
            self.rfile.read(length)
            return self.send_json({"error": "Thông số không hợp lệ."}, 400)
        except TamsError as e:
            self.rfile.read(length)
            return self.send_json({"error": str(e)}, e.status)
        data = self.rfile.read(length)
        try:
            field_values(describe(up)[1], settings)  # reject bad settings before spending an upload
            self.send_json({"jobId": create_job(up, upload_image(data, content_type), settings)})
        except TamsError as e:
            self.send_json({"error": str(e)}, e.status)

    def job_id(self, raw):
        job_id = urllib.parse.unquote(raw)
        if not JOB_ID.match(job_id):
            raise TamsError("Mã job không hợp lệ.", 400)
        return job_id

    def send_result(self, job_id):
        state = job_status(job_id)
        if state["status"] != "done":
            return self.send_json({"error": "Ảnh chưa xong."}, 409)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        name = query.get("name", ["anh"])[0]
        disposition = "inline" if query.get("view") == ["1"] else "attachment"
        stem = re.sub(r"[^\w.-]+", "_", Path(name).stem)[:80] or "anh"
        ascii_stem = re.sub(r"[^A-Za-z0-9.-]+", "_", stem).strip("_") or "anh"
        try:
            resp = urllib.request.urlopen(state["imageUrl"], timeout=120)
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            raise TamsError(f"Không tải được ảnh kết quả từ TensorArt: {e}") from None
        with resp:
            ctype = resp.headers.get("Content-Type", "image/png")
            ext = {"image/jpeg": "jpg", "image/webp": "webp"}.get(ctype.split(";")[0], "png")
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            if resp.headers.get("Content-Length"):
                self.send_header("Content-Length", resp.headers["Content-Length"])
            self.send_header("Content-Disposition", f'{disposition}; filename="{ascii_stem}_4k.{ext}"; '
                                                    f"filename*=UTF-8''{urllib.parse.quote(f'{stem}_4k.{ext}')}")
            self.end_headers()
            while chunk := resp.read(1 << 16):
                self.wfile.write(chunk)


def main():
    load_config()
    host, port = os.environ.get("HOST", "0.0.0.0"), int(os.environ.get("PORT", "8080"))
    if missing_config():
        print("Chưa cấu hình: thiếu " + ", ".join(missing_config()) + ". Trang web vẫn mở nhưng chưa upscale được.")
    else:
        print("Kiểu upscale: " + ", ".join(f"{u.get('name', u['key'])} (AI Tool {u['tool_id']})" for u in CONFIG["upscalers"]))
    if not CONFIG["password"]:
        print("Cảnh báo: chưa đặt ACCESS_PASSWORD, ai vào được trang này cũng dùng được credit TensorArt.")
    print(f"Bokin Upscale web: http://{'127.0.0.1' if host == '0.0.0.0' else host}:{port}", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
