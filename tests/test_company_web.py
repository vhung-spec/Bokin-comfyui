"""company_web/server.py against a fake TensorArt (TAMS) API."""
import base64
import importlib.util
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("company_web_server", Path(__file__).parents[1] / "company_web" / "server.py")
web = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web)

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==")

# Fields each fake AI Tool exposes as TA Nodes, in the shape GET /v1/workflows/{id} returns them.
TOOLS = {
    "111": [
        {"nodeId": "1", "fieldName": "image", "nodeName": "LoadImage", "fieldValue": ""},
        {"nodeId": "12", "fieldName": "denoise", "nodeName": "BasicScheduler", "fieldValue": "0.12"},
        {"nodeId": "12", "fieldName": "steps", "nodeName": "BasicScheduler", "fieldValue": "4"},
        {"nodeId": "15", "fieldName": "megapixels", "nodeName": "ImageScaleToTotalPixels", "fieldValue": "8"},
        {"nodeId": "8", "fieldName": "text", "nodeName": "CLIPTextEncode", "fieldValue": "autumn scenery"},
        {"nodeId": "11", "fieldName": "sampler_name", "nodeName": "KSamplerSelect", "fieldValue": "euler",
         "inputString": json.dumps({"options": {"values": ["euler", "dpmpp_2m"]}})},
    ],
    "222": [
        {"nodeId": "1", "fieldName": "image", "nodeName": "LoadImage", "fieldValue": ""},
        {"nodeId": "12", "fieldName": "denoise", "nodeName": "BasicScheduler", "fieldValue": "0.2"},
    ],
    "333": [{"nodeId": "12", "fieldName": "denoise", "nodeName": "BasicScheduler", "fieldValue": "0.2"}],
}

UPSCALERS = {"upscalers": [
    {"key": "klein-4k", "name": "Klein 4K", "description": "rẻ", "tool_id": "${TA_TOOL_ID}",
     "params": {"denoise": {"label": "Mức vẽ lại", "min": 0.05, "max": 0.25, "step": 0.01},
                "megapixels": {"min": 4, "max": 16, "step": 1}, "steps": {"hidden": True}}},
    {"key": "flux1-4k", "name": "FLUX.1 4K", "tool_id": "222"},
    {"key": "no-image", "name": "Hỏng", "tool_id": "333"},
    {"key": "not-set", "name": "Chưa cấu hình", "tool_id": "${TA_TOOL_ID_MISSING}"},
]}


class FakeTams(BaseHTTPRequestHandler):
    """The TAMS calls the server makes, plus the presigned upload and result URLs."""
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
            tool = self.path.rsplit("/", 1)[-1]
            if tool not in TOOLS:
                return self.reply({"error": "no such tool"}, 404)
            self.reply({"name": f"tool {tool}", "fields": {"fieldAttrs": TOOLS[tool]}})
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
def app(tmp_path):
    tams = serve(FakeTams)
    FakeTams.uploads, FakeTams.jobs, FakeTams.created, FakeTams.fail_next = {}, {}, [], False
    config = tmp_path / "upscalers.json"
    config.write_text(json.dumps(UPSCALERS), encoding="utf-8")
    web.load_config({"TAMS_API_KEY": "test-key", "TA_TOOL_ID": "111", "UPSCALERS_FILE": str(config),
                     "TAMS_BASE_URL": f"http://127.0.0.1:{tams.server_port}"})
    site = serve(web.Handler)
    yield f"http://127.0.0.1:{site.server_port}"
    site.shutdown()
    tams.shutdown()


def call(url, data=None, ctype=None, auth=None):
    req = urllib.request.Request(url, data=data)
    if ctype:
        req.add_header("Content-Type", ctype)
    if auth:
        req.add_header("Authorization", "Basic " + base64.b64encode(auth.encode()).decode())
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def jobs_url(app, type_=None, params=None):
    query = {}
    if type_:
        query["type"] = type_
    if params is not None:
        query["params"] = params if isinstance(params, str) else json.dumps(params)
    return app + "/api/jobs" + ("?" + urllib.parse.urlencode(query) if query else "")


def test_lists_upscale_types_with_settings(app):
    ups = {u["key"]: u for u in json.loads(call(app + "/api/upscalers")[2])["upscalers"]}
    assert list(ups) == ["klein-4k", "flux1-4k", "no-image"]  # not-set has no tool id, so it is hidden

    klein = {p["key"]: p for p in ups["klein-4k"]["params"]}
    assert list(klein) == ["denoise", "megapixels", "text", "sampler_name"]  # image is implicit, steps hidden
    assert klein["denoise"] == {"key": "denoise", "label": "Mức vẽ lại", "type": "number", "integer": False,
                                "default": 0.12, "min": 0.05, "max": 0.25, "step": 0.01,
                                "hint": "Cao hơn thì thêm nhiều chi tiết nhưng dễ đổi ảnh."}
    assert klein["megapixels"]["integer"] is True and klein["megapixels"]["default"] == 8.0
    assert klein["text"]["type"] == "text" and klein["text"]["default"] == "autumn scenery"
    assert klein["sampler_name"]["type"] == "select" and klein["sampler_name"]["options"] == ["euler", "dpmpp_2m"]

    assert [p["key"] for p in ups["flux1-4k"]["params"]] == ["denoise"]
    assert ups["flux1-4k"]["params"][0]["max"] == 1.0  # no override: the built-in range for denoise
    assert "Load Image" in ups["no-image"]["error"] and ups["no-image"]["params"] == []


def test_upload_run_and_download(app):
    status, _, body = call(jobs_url(app, "klein-4k", {"denoise": 0.2, "megapixels": 12, "sampler_name": "dpmpp_2m"}),
                           PNG, "image/png")
    assert status == 200, body
    job = json.loads(body)["jobId"]

    created = FakeTams.created[0]
    assert created["templateId"] == "111"
    assert created["fields"]["fieldAttrs"] == [
        {"nodeId": "1", "fieldName": "image", "fieldValue": "res-1"},
        {"nodeId": "12", "fieldName": "denoise", "fieldValue": "0.2"},
        {"nodeId": "15", "fieldName": "megapixels", "fieldValue": "12"},
        {"nodeId": "8", "fieldName": "text", "fieldValue": "autumn scenery"},
        {"nodeId": "11", "fieldName": "sampler_name", "fieldValue": "dpmpp_2m"},
    ]
    assert FakeTams.uploads["res-1"] == PNG

    states = [json.loads(call(f"{app}/api/jobs/{job}")[2]) for _ in range(3)]
    assert states[0] == {"status": "waiting", "queueRank": 2, "queueLen": 5}
    assert states[1] == {"status": "running"}
    assert states[2]["status"] == "done"

    status, headers, image = call(f"{app}/api/jobs/{job}/image?name=" + urllib.parse.quote("Ảnh phố cổ.jpg"))
    assert status == 200 and image == PNG
    assert headers["Content-Type"] == "image/png"
    assert headers["Content-Disposition"].startswith('attachment; filename="nh_ph_c_4k.png"')
    assert "filename*=UTF-8''" + urllib.parse.quote("Ảnh_phố_cổ_4k.png") in headers["Content-Disposition"]

    _, headers, _ = call(f"{app}/api/jobs/{job}/image?view=1")
    assert headers["Content-Disposition"].startswith("inline;")


def test_settings_default_clamp_and_validate(app):
    assert call(jobs_url(app), PNG, "image/png")[0] == 200  # no type: first type, every setting at its default
    assert [a["fieldValue"] for a in FakeTams.created[-1]["fields"]["fieldAttrs"][1:]] == ["0.12", "8", "autumn scenery", "euler"]

    assert call(jobs_url(app, "klein-4k", {"denoise": 5, "megapixels": 1.4}), PNG, "image/png")[0] == 200
    attrs = FakeTams.created[-1]["fields"]["fieldAttrs"]
    assert attrs[1]["fieldValue"] == "0.25" and attrs[2]["fieldValue"] == "4"  # clamped to the configured range

    assert call(jobs_url(app, "flux1-4k", {"denoise": 0.3}), PNG, "image/png")[0] == 200
    assert FakeTams.created[-1]["templateId"] == "222"
    assert FakeTams.created[-1]["fields"]["fieldAttrs"][1] == {"nodeId": "12", "fieldName": "denoise", "fieldValue": "0.3"}

    uploads = len(FakeTams.uploads)
    for url, message in [(jobs_url(app, "klein-4k", {"sampler_name": "bogus"}), "không có lựa chọn"),
                         (jobs_url(app, "klein-4k", {"denoise": "abc"}), "phải là số"),
                         (jobs_url(app, "klein-4k", "not json"), "Thông số"),
                         (jobs_url(app, "nope"), "không tồn tại"),
                         (jobs_url(app, "no-image"), "Load Image")]:
        status, _, body = call(url, PNG, "image/png")
        assert status in (400, 500) and message in json.loads(body)["error"], (url, body)
    assert len(FakeTams.uploads) == uploads  # nothing uploaded for rejected requests


def test_failed_job_reports_reason(app):
    FakeTams.fail_next = True
    job = json.loads(call(jobs_url(app), PNG, "image/jpeg")[2])["jobId"]
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
    assert call(app + "/api/upscalers", auth="nv:sai")[0] == 401
    status, _, body = call(app + "/", auth="nhanvien:mật-khẩu")
    assert status == 200 and b"Bokin Upscale 4K" in body
    assert call(app + "/api/jobs", PNG, "image/png", auth="nv:mật-khẩu")[0] == 200


def test_missing_config(tmp_path):
    web.load_config({"UPSCALERS_FILE": str(tmp_path / "none.json")})
    site = serve(web.Handler)
    base = f"http://127.0.0.1:{site.server_port}"
    status = json.loads(call(base + "/api/status")[2])
    assert status["configured"] is False and status["missing"][0] == "TAMS_API_KEY" and "TA_TOOL_ID" in status["missing"][1]
    assert json.loads(call(base + "/api/upscalers")[2]) == {"upscalers": []}
    status, _, body = call(base + "/api/jobs", PNG, "image/png")
    assert status == 500 and "TAMS_API_KEY" in json.loads(body)["error"]
    site.shutdown()


def test_shipped_config_uses_env_tool_ids():
    web.load_config({"TAMS_API_KEY": "k", "TA_TOOL_ID": "1", "TA_TOOL_ID_FLUX1": "3"})
    assert [(u["key"], u["tool_id"]) for u in web.CONFIG["upscalers"]] == [("klein-4k", "1"), ("flux1-4k", "3")]
