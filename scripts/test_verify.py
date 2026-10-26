"""Tests for verify.py with a simulated deployment (no network needed).

    python -m pytest -q scripts
"""

import json
import os
import sys
import urllib.error

sys.path.insert(0, os.path.dirname(__file__))
import verify  # noqa: E402

PAGE = b"<h1>AI 255 Project 1: First Cloud Deployment</h1>"
SEC = {"strict-transport-security": "max-age=31536000", "x-content-type-options": "nosniff", "x-frame-options": "DENY"}


def fake_http_get(host, path, https=True, timeout=10):
    if not https:
        return 308, {"location": f"https://{host}{path}"}, b""
    if host.startswith("www."):
        return 301, {"location": "https://example.me/"}, b""
    routes = {
        "/": (200, PAGE),
        "/api/health": (200, b'{"status": "ok"}'),
        "/api/files": (200, b'{"files": [{"name": "hello.txt"}]}'),
        "/files/hello.txt": (200, b"Hello from Cloud Storage."),
        "/api/info": (200, b'{"instance": "web-1", "zone": "us-central1-a"}'),
        "/files/..%2Fsite%2Findex.html": (400, b'{"error": "invalid file name"}'),
    }
    status, body = routes.get(path, (404, b"{}"))
    return status, {"content-type": "application/json", **SEC}, body


def fake_cert(host):
    return ({"issuer": ((("organizationName", "Let's Encrypt"),), (("commonName", "R11"),)),
             "subjectAltName": (("DNS", host),), "notAfter": "Jan 20 10:00:00 2099 GMT"}, "TLSv1.3")


def run(monkeypatch, tmp_path, **patches):
    monkeypatch.setattr(verify, "ROOT", str(tmp_path))
    monkeypatch.setattr(verify, "resolve", patches.get("resolve", lambda h: ["34.1.2.3"]))
    monkeypatch.setattr(verify, "http_get", patches.get("http_get", fake_http_get))
    monkeypatch.setattr(verify, "certificate", patches.get("certificate", fake_cert))

    def private(url, timeout=10):
        raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
    monkeypatch.setattr(verify.urllib.request, "urlopen", patches.get("urlopen", private))
    monkeypatch.setattr(sys, "argv", ["verify.py", "--domain", "example.me", "--ip", "34.1.2.3", "--bucket", "b"])
    code = verify.main()
    data = json.load(open(tmp_path / "evidence" / "verify.json"))
    return code, {r["check"]: r["ok"] for r in data["results"]}


def test_healthy_deployment_passes_everything(monkeypatch, tmp_path):
    code, results = run(monkeypatch, tmp_path)
    assert code == 0 and all(results.values()) and len(results) == 13
    assert (tmp_path / "evidence" / "verify.md").read_text().startswith("Verification of https://example.me")


def test_wrong_dns_fails(monkeypatch, tmp_path):
    code, results = run(monkeypatch, tmp_path, resolve=lambda h: ["9.9.9.9"])
    assert code == 1 and not results["DNS A record for domain"]


def test_self_signed_or_wrong_issuer_fails(monkeypatch, tmp_path):
    def other(host):
        cert, v = fake_cert(host)
        cert["issuer"] = ((("organizationName", "Someone Else"),),)
        return cert, v
    _, results = run(monkeypatch, tmp_path, certificate=other)
    assert not results["TLS certificate valid and trusted"]


def test_public_bucket_fails(monkeypatch, tmp_path):
    class Resp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
    _, results = run(monkeypatch, tmp_path, urlopen=lambda url, timeout=10: Resp())
    assert not results["Bucket is not public"]


def test_missing_hsts_fails(monkeypatch, tmp_path):
    def no_hsts(host, path, https=True, timeout=10):
        s, h, b = fake_http_get(host, path, https, timeout)
        h = {k: v for k, v in h.items() if k != "strict-transport-security"}
        return s, h, b
    _, results = run(monkeypatch, tmp_path, http_get=no_hsts)
    assert not results["Security headers"]


def test_exception_in_one_check_does_not_stop_others(monkeypatch, tmp_path):
    def boom(host):
        raise ConnectionRefusedError("port 443 closed")
    code, results = run(monkeypatch, tmp_path, certificate=boom)
    assert code == 1 and not results["TLS certificate valid and trusted"] and results["GET /api/health"]
