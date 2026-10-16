"""Bokin Upscale web: staff upload an image, TensorArt runs the Klein 4K workflow, they download the result.

The page talks only to this server. This server calls the TensorArt (TAMS) API with the company's key, so the key
never reaches a browser. Python 3.9+, standard library only.

    TAMS_API_KEY=... TA_TOOL_ID=... python3 server.py

API flow (same calls as TensorArt's own ComfyUI_TENSOR_ART nodes):
    POST {base}/v1/resource/image           -> resourceId, putUrl, headers; then PUT the file to putUrl
    POST {base}/v1/jobs/workflow/template   -> job.id  (templateId = the published AI Tool, image field = resourceId)
    GET  {base}/v1/jobs/{id}                -> job.status WAITING / RUNNING / SUCCESS / FAILED, successInfo.images[].url
"""
import base64
import hmac
import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
JOB_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

CONFIG = {}


def load_config(env=os.environ):
    CONFIG.update(
        api_key=env.get("TAMS_API_KEY", ""),
        base_url=env.get("TAMS_BASE_URL", "https://ap-east-1.tensorart.cloud").rstrip("/"),
        tool_id=env.get("TA_TOOL_ID", ""),
        image_node_id=env.get("TA_IMAGE_NODE_ID", ""),
        password=env.get("ACCESS_PASSWORD", ""),
        max_upload=int(float(env.get("MAX_UPLOAD_MB", "25")) * 1024 * 1024),
    )
    _image_field.clear()


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


_image_field = {}
_image_field_lock = threading.Lock()


def image_field():
    """(nodeId, fieldName) of the AI Tool's Load Image input, looked up once."""
    with _image_field_lock:
        if not _image_field:
            if CONFIG["image_node_id"]:
                _image_field["value"] = (CONFIG["image_node_id"], "image")
            else:
                tool = tams("GET", f"/v1/workflows/{urllib.parse.quote(CONFIG['tool_id'])}")
                fields = (tool.get("fields") or {}).get("fieldAttrs") or []
                images = [f for f in fields if f.get("fieldName") == "image"]
                images.sort(key=lambda f: "LoadImage" not in str(f.get("nodeName", "")))
                if not images:
                    raise TamsError("AI Tool không có ô ảnh đầu vào. Trên TensorArt, đánh dấu node Load Image là "
                                    "TA Node rồi Publish lại, hoặc đặt TA_IMAGE_NODE_ID.", 500)
                _image_field["value"] = (str(images[0]["nodeId"]), images[0]["fieldName"])
        return _image_field["value"]


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


def create_job(resource_id):
    node_id, field_name = image_field()
    resp = tams("POST", "/v1/jobs/workflow/template", {
        "requestId": uuid.uuid4().hex,
        "templateId": CONFIG["tool_id"],
        "fields": {"fieldAttrs": [{"nodeId": node_id, "fieldName": field_name, "fieldValue": resource_id}]},
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
    return [name for name, key in (("TAMS_API_KEY", "api_key"), ("TA_TOOL_ID", "tool_id")) if not CONFIG[key]]


class Handler(BaseHTTPRequestHandler):
    server_version = "BokinUpscaleWeb/1.0"

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
        if urllib.parse.urlsplit(self.path).path != "/api/jobs":
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
        data = self.rfile.read(length)
        try:
            self.send_json({"jobId": create_job(upload_image(data, content_type))})
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
    if not CONFIG["password"]:
        print("Cảnh báo: chưa đặt ACCESS_PASSWORD, ai vào được trang này cũng dùng được credit TensorArt.")
    print(f"Bokin Upscale web: http://{'127.0.0.1' if host == '0.0.0.0' else host}:{port}", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
