"""Tests for server.py. Run from the repository root:  python -m pytest -q app"""

import io
import json
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import server  # noqa: E402

CONTENT = os.path.join(os.path.dirname(__file__), "..", "content")


@pytest.fixture
def app():
    return server.App(server.LocalStorage(CONTENT), version="test")


def body_json(result):
    return json.loads(result[2])


def test_health(app):
    status, ctype, body, _ = app.handle("/api/health")
    assert status == 200 and ctype == "application/json" and json.loads(body) == {"status": "ok"}


def test_info(app):
    info = body_json(app.handle("/api/info"))
    assert info["service"] == "ai255-web" and info["version"] == "test"
    assert info["instance"] == "local" and info["uptime_seconds"] >= 0


def test_index_page_comes_from_storage(app):
    status, ctype, body, _ = app.handle("/")
    assert status == 200 and ctype.startswith("text/html") and b"First Cloud Deployment" in body


def test_index_falls_back_when_missing(tmp_path):
    app = server.App(server.LocalStorage(tmp_path))
    status, _, body, _ = app.handle("/")
    assert status == 200 and body == server.FALLBACK_PAGE


def test_file_list(app):
    data = body_json(app.handle("/api/files"))
    names = [f["name"] for f in data["files"]]
    assert names == sorted(names) and "hello.txt" in names and data["count"] == len(names)


def test_file_download(app):
    status, ctype, body, _ = app.handle("/files/hello.txt")
    assert status == 200 and ctype == "text/plain" and body.startswith(b"Hello from Cloud Storage")


@pytest.mark.parametrize("path", ["/files/..%2Fsite%2Findex.html", "/files/../site/index.html",
                                  "/files/.hidden", "/files/", "/files/a%2Fb"])
def test_path_traversal_and_bad_names_rejected(app, path):
    status = app.handle(path)[0]
    assert status in (400, 404)
    assert b"First Cloud Deployment" not in app.handle(path)[2]


def test_missing_file_is_404(app):
    assert app.handle("/files/nope.txt")[0] == 404


def test_unknown_path_is_404(app):
    assert app.handle("/admin")[0] == 404


def test_query_string_ignored(app):
    assert app.handle("/api/health?x=1")[0] == 200


def test_storage_error_gives_502():
    class Broken:
        name = "broken"

        def list(self, prefix):
            raise server.StorageError("down")

        def read(self, key):
            raise server.StorageError("down")

    app = server.App(Broken())
    assert app.handle("/api/files")[0] == 502
    assert app.handle("/files/x.txt")[0] == 502
    assert app.handle("/")[0] == 200          # falls back to the built-in page


def test_file_list_is_cached(app):
    calls = []
    real = app.storage.list
    app.storage.list = lambda prefix: calls.append(prefix) or real(prefix)
    app.handle("/api/files")
    app.handle("/api/files")
    assert len(calls) == 1


# ---- GCS backend with a fake network --------------------------------------

class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def make_fake_opener(objects, seen):
    def opener(req, timeout=None):
        url = req.full_url
        seen.append((url, dict(req.header_items())))
        if url.endswith("/service-accounts/default/token"):
            assert req.get_header("Metadata-flavor") == "Google"
            return FakeResponse(json.dumps({"access_token": "tok123", "expires_in": 3600}).encode())
        assert req.get_header("Authorization") == "Bearer tok123"
        if "/o?" in url:
            prefix = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("prefix", [""])[0]
            items = [{"name": k, "size": str(len(v)), "updated": "2026-10-25T00:00:00Z"}
                     for k, v in objects.items() if k.startswith(prefix)]
            return FakeResponse(json.dumps({"items": items}).encode())
        key = urllib.request.unquote(url.split("/o/", 1)[1].split("?", 1)[0])
        if key not in objects:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return FakeResponse(objects[key])
    return opener


def test_gcs_backend_uses_metadata_token_and_json_api():
    seen = []
    objects = {"public/a.txt": b"A", "public/sub/b.txt": b"B", "site/index.html": b"<h1>x</h1>"}
    gcs = server.GCSStorage("my-bucket", opener=make_fake_opener(objects, seen))
    assert gcs.list("public/") == [{"name": "a.txt", "size": 1, "updated": "2026-10-25T00:00:00Z"}]
    assert gcs.read("public/a.txt") == b"A"
    with pytest.raises(server.NotFound):
        gcs.read("public/missing.txt")
    token_calls = [u for u, _ in seen if u.endswith("/token")]
    assert len(token_calls) == 1                       # token is cached between requests
    assert any("/b/my-bucket/o/public%2Fa.txt?alt=media" in u for u, _ in seen)


def test_gcs_permission_error_is_storage_error():
    def opener(req, timeout=None):
        if req.full_url.endswith("/token"):
            return FakeResponse(b'{"access_token": "t", "expires_in": 3600}')
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)
    gcs = server.GCSStorage("b", opener=opener)
    with pytest.raises(server.StorageError):
        gcs.read("public/a.txt")


# ---- real HTTP server on a random local port ---------------------------------

def test_http_server_end_to_end(app):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(app))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/api/health") as r:
            assert r.status == 200 and json.load(r) == {"status": "ok"}
        req = urllib.request.Request(base + "/api/health", method="HEAD")
        with urllib.request.urlopen(req) as r:
            assert r.status == 200 and r.read() == b""
        req = urllib.request.Request(base + "/api/health", data=b"x", method="POST")
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code == 405
    finally:
        httpd.shutdown()
