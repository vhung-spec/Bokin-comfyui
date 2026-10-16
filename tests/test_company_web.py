"""company_web/server.py against a fake TensorArt (TAMS) API."""
import base64
import importlib.util
import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("company_web_server", Path(__file__).parents[1] / "company_web" / "server.py")
web = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web)

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==")


class FakeTams(BaseHTTPRequestHandler):
    """The four TAMS calls the server makes, plus the presigned upload and result URLs."""
    uploads, jobs, created = {}, {}, []
    fail_next = False

    def log_message(self, *args):
        pass

    def reply(self, data, status=200, ctype="application/json"):
        body = data if isinstance(data, bytes) else json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def authed(self):
        if self.headers.get("Authorization") != "Bearer test-key":
            self.reply({"error": "unauthorized"}, 401)
            return False
        return True

    def body(self):
        return self.rfile.read(int(self.headers.get("Content-Length") or 0))

    def do_POST(self):
        if not self.authed():
            return
        base = f"http://127.0.0.1:{self.server.server_port}"
        if self.path == "/v1/resource/image":
            self.body()
            rid = f"res-{len(self.uploads) + 1}"
            self.uploads[rid] = None
            self.reply({"resourceId": rid, "putUrl": f"{base}/put/{rid}", "headers": {"Content-Type": "image/png", "x-sig": "ok"}})
        elif self.path == "/v1/jobs/workflow/template":
            req = json.loads(self.body())
            FakeTams.created.append(req)
            attr = req["fields"]["fieldAttrs"][0]
            assert self.uploads.get(attr["fieldValue"]) is not None, "job created before the image was uploaded"
            jid = f"job-{len(self.jobs) + 1}"
            self.jobs[jid] = {"polls": 0, "resource": attr["fieldValue"], "fail": FakeTams.fail_next}
            FakeTams.fail_next = False
            self.reply({"job": {"id": jid, "status": "CREATED"}})
        else:
            self.reply({"error": "not found"}, 404)

    def do_PUT(self):
        rid = self.path.rsplit("/", 1)[-1]
        if self.headers.get("x-sig") != "ok" or rid not in self.uploads:
            return self.reply({"error": "bad signature"}, 403)
        self.uploads[rid] = self.body()
        self.reply(b"", 200, "text/plain")

    def do_GET(self):
        base = f"http://127.0.0.1:{self.server.server_port}"
        if self.path.startswith("/out/"):
            job = self.jobs[self.path[5:].removesuffix(".png")]
            return self.reply(self.uploads[job["resource"]], 200, "image/png")
        if not self.authed():
            return
        if self.path.startswith("/v1/workflows/"):
            self.reply({"name": "Bokin Klein 4K", "fields": {"fieldAttrs": [
                {"nodeId": "8", "fieldName": "text", "nodeName": "CLIPTextEncode", "fieldValue": "autumn"},
                {"nodeId": "1", "fieldName": "image", "nodeName": "LoadImage", "fieldValue": ""}]}})
        elif self.path.startswith("/v1/jobs/"):
            jid = self.path.rsplit("/", 1)[-1]
            job = self.jobs[jid]
            job["polls"] += 1
            if job["polls"] == 1:
                self.reply({"job": {"id": jid, "status": "WAITING", "waitingInfo": {"queueRank": 2, "queueLen": 5}}})
            elif job["polls"] == 2:
                self.reply({"job": {"id": jid, "status": "RUNNING"}})
            elif job["fail"]:
                self.reply({"job": {"id": jid, "status": "FAILED", "failedInfo": {"reason": "out of credits"}}})
            else:
                self.reply({"job": {"id": jid, "status": "SUCCESS", "successInfo": {"images": [{"url": f"{base}/out/{jid}.png"}]}}})
        else:
            self.reply({"error": "not found"}, 404)


def serve(handler):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


@pytest.fixture()
def app():
    tams = serve(FakeTams)
    FakeTams.uploads, FakeTams.jobs, FakeTams.created, FakeTams.fail_next = {}, {}, [], False
    web.load_config({"TAMS_API_KEY": "test-key", "TA_TOOL_ID": "123456789",
                     "TAMS_BASE_URL": f"http://127.0.0.1:{tams.server_port}"})
    site = serve(web.Handler)
    yield f"http://127.0.0.1:{site.server_port}"
    site.shutdown()
    tams.shutdown()


def call(url, data=None, ctype=None, auth=None, method=None):
    req = urllib.request.Request(url, data=data, method=method)
    if ctype:
        req.add_header("Content-Type", ctype)
    if auth:
        req.add_header("Authorization", "Basic " + base64.b64encode(auth.encode()).decode())
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def test_upload_run_and_download(app):
    status, _, body = call(app + "/api/jobs", PNG, "image/png")
    assert status == 200, body
    job = json.loads(body)["jobId"]

    created = FakeTams.created[0]
    assert created["templateId"] == "123456789"
    assert created["fields"]["fieldAttrs"] == [{"nodeId": "1", "fieldName": "image", "fieldValue": "res-1"}]
    assert FakeTams.uploads["res-1"] == PNG

    states = [json.loads(call(f"{app}/api/jobs/{job}")[2]) for _ in range(3)]
    assert states[0] == {"status": "waiting", "queueRank": 2, "queueLen": 5}
    assert states[1] == {"status": "running"}
    assert states[2]["status"] == "done"

    status, headers, image = call(f"{app}/api/jobs/{job}/image?name=" + urllib.request.quote("Ảnh phố cổ.jpg"))
    assert status == 200 and image == PNG
    assert headers["Content-Type"] == "image/png"
    assert headers["Content-Disposition"].startswith('attachment; filename="nh_ph_c_4k.png"')
    assert "filename*=UTF-8''" + urllib.request.quote("Ảnh_phố_cổ_4k.png") in headers["Content-Disposition"]

    _, headers, _ = call(f"{app}/api/jobs/{job}/image?view=1")
    assert headers["Content-Disposition"].startswith("inline;")


def test_failed_job_reports_reason(app):
    FakeTams.fail_next = True
    job = json.loads(call(app + "/api/jobs", PNG, "image/jpeg")[2])["jobId"]
    for _ in range(2):
        call(f"{app}/api/jobs/{job}")
    assert json.loads(call(f"{app}/api/jobs/{job}")[2]) == {"status": "failed", "error": "out of credits"}
    assert call(f"{app}/api/jobs/{job}/image")[0] == 409


def test_rejects_bad_uploads_and_job_ids(app):
    assert call(app + "/api/jobs", b"hello", "text/plain")[0] == 400
    web.CONFIG["max_upload"] = 10
    assert call(app + "/api/jobs", PNG, "image/png")[0] == 413
    assert call(app + "/api/jobs/..%2F..%2Fetc")[0] == 400
    assert not FakeTams.created


def test_password(app):
    web.CONFIG["password"] = "mật-khẩu"
    assert call(app + "/")[0] == 401
    assert call(app + "/", auth="nv:sai")[0] == 401
    status, headers, body = call(app + "/", auth="nhanvien:mật-khẩu")
    assert status == 200 and b"Bokin Upscale 4K" in body
    assert call(app + "/api/jobs", PNG, "image/png", auth="nv:mật-khẩu")[0] == 200


def test_missing_config():
    web.load_config({})
    site = serve(web.Handler)
    base = f"http://127.0.0.1:{site.server_port}"
    assert json.loads(call(base + "/api/status")[2]) == {"configured": False, "missing": ["TAMS_API_KEY", "TA_TOOL_ID"]}
    status, _, body = call(base + "/api/jobs", PNG, "image/png")
    assert status == 500 and "TAMS_API_KEY" in json.loads(body)["error"]
    site.shutdown()
