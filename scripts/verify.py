"""Check the live deployment from the outside and save the results as evidence.

    python scripts/verify.py --from-terraform infra
    python scripts/verify.py --domain example.me --ip 34.1.2.3 --bucket my-project-web-content

Checks:
  1. DNS: the domain and www resolve to the VM's static IP
  2. HTTP on port 80 redirects to HTTPS
  3. TLS: certificate is valid, trusted, issued by Let's Encrypt, covers the domain
  4. Every endpoint answers over HTTPS with the expected status and content
  5. Security headers are present (HSTS, nosniff, frame options)
  6. www redirects to the main domain
  7. The bucket is NOT readable from the internet without credentials
Writes evidence/verify.md and evidence/verify.json. Uses only the Python standard library.
"""

import argparse
import datetime as dt
import http.client
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def terraform_outputs(infra_dir):
    exe = shutil.which("terraform") or "terraform"
    out = subprocess.run([exe, f"-chdir={infra_dir}", "output", "-json"],
                         capture_output=True, text=True, check=True).stdout
    data = {k: v["value"] for k, v in json.loads(out).items()}
    return data["url"].removeprefix("https://"), data["static_ip"], data["bucket"]


class Checker:
    def __init__(self):
        self.results = []

    def check(self, name, fn):
        start = time.perf_counter()
        try:
            ok, detail = fn()
        except Exception as e:                # a failed check must not stop the others
            ok, detail = False, f"{type(e).__name__}: {e}"
        ms = (time.perf_counter() - start) * 1000
        self.results.append({"check": name, "ok": bool(ok), "detail": detail, "ms": round(ms)})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def resolve(host):
    return sorted({ai[4][0] for ai in socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)})


def http_get(host, path, https=True, timeout=10):
    conn_cls = http.client.HTTPSConnection if https else http.client.HTTPConnection
    kwargs = {"context": ssl.create_default_context()} if https else {}
    conn = conn_cls(host, timeout=timeout, **kwargs)
    conn.request("GET", path, headers={"User-Agent": "ai255-verify"})
    r = conn.getresponse()
    body = r.read()
    headers = {k.lower(): v for k, v in r.getheaders()}
    conn.close()
    return r.status, headers, body


def certificate(host):
    ctx = ssl.create_default_context()        # verifies the chain and the host name
    with socket.create_connection((host, 443), timeout=10) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as tls:
            return tls.getpeercert(), tls.version()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-terraform", metavar="INFRA_DIR")
    ap.add_argument("--domain")
    ap.add_argument("--ip")
    ap.add_argument("--bucket")
    args = ap.parse_args()
    if args.from_terraform:
        domain, ip, bucket = terraform_outputs(args.from_terraform)
    else:
        if not args.domain:
            ap.error("give --from-terraform INFRA_DIR or --domain")
        domain, ip, bucket = args.domain, args.ip, args.bucket

    c = Checker()
    print(f"Verifying https://{domain}  (expected IP {ip or 'not given'}, bucket {bucket or 'not given'})\n")

    def dns(host):
        def f():
            addrs = resolve(host)
            return (ip is None or addrs == [ip]), f"{host} -> {', '.join(addrs)}"
        return f
    c.check("DNS A record for domain", dns(domain))
    c.check("DNS A record for www", dns(f"www.{domain}"))

    def redirect():
        status, h, _ = http_get(domain, "/", https=False)
        loc = h.get("location", "")
        return status in (301, 302, 307, 308) and loc.startswith("https://"), f"HTTP {status} -> {loc}"
    c.check("HTTP redirects to HTTPS", redirect)

    def tls():
        cert, version = certificate(domain)
        issuer = dict(x[0] for x in cert["issuer"])
        sans = [v for k, v in cert.get("subjectAltName", []) if k == "DNS"]
        not_after = dt.datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=dt.timezone.utc)
        days = (not_after - dt.datetime.now(dt.timezone.utc)).days
        ok = domain in sans and days > 0 and "Let's Encrypt" in issuer.get("organizationName", "")
        return ok, (f"{version}, issuer {issuer.get('organizationName')} ({issuer.get('commonName')}), "
                    f"names {sans}, expires {not_after:%Y-%m-%d} ({days} days)")
    c.check("TLS certificate valid and trusted", tls)

    def endpoint(path, expect_status, must_contain):
        def f():
            status, h, body = http_get(domain, path)
            ok = status == expect_status and must_contain.encode() in body
            return ok, f"HTTP {status}, {h.get('content-type')}, {len(body)} bytes"
        return f
    c.check("GET / (page from bucket)", endpoint("/", 200, "First Cloud Deployment"))
    c.check("GET /api/health", endpoint("/api/health", 200, '"status": "ok"'))
    c.check("GET /api/files", endpoint("/api/files", 200, "hello.txt"))
    c.check("GET /files/hello.txt", endpoint("/files/hello.txt", 200, "Hello from Cloud Storage"))
    def traversal():
        status, _, body = http_get(domain, "/files/..%2Fsite%2Findex.html")
        return status in (400, 404) and b"First Cloud Deployment" not in body, f"HTTP {status}, page not leaked"
    c.check("Path traversal is rejected", traversal)

    def info():
        status, _, body = http_get(domain, "/api/info")
        data = json.loads(body)
        return status == 200 and data.get("instance") not in (None, "local"), json.dumps(data)
    c.check("GET /api/info (runs on the VM)", info)

    def headers():
        _, h, _ = http_get(domain, "/api/health")
        want = {"strict-transport-security": "max-age", "x-content-type-options": "nosniff", "x-frame-options": "DENY"}
        missing = [k for k, v in want.items() if v not in h.get(k, "")]
        return not missing, "missing: " + ", ".join(missing) if missing else ", ".join(f"{k}: {h[k]}" for k in want)
    c.check("Security headers", headers)

    def www():
        status, h, _ = http_get(f"www.{domain}", "/")
        return status in (301, 308) and h.get("location", "").startswith(f"https://{domain}"), f"HTTP {status} -> {h.get('location')}"
    c.check("www redirects to main domain", www)

    if bucket:
        def private_bucket():
            url = f"https://storage.googleapis.com/{bucket}/public/hello.txt"
            try:
                with urllib.request.urlopen(url, timeout=10) as r:
                    return False, f"PUBLICLY READABLE: HTTP {r.status}"
            except urllib.error.HTTPError as e:
                return e.code in (401, 403), f"anonymous read of {url} -> HTTP {e.code}"
        c.check("Bucket is not public", private_bucket)

    passed = sum(r["ok"] for r in c.results)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{passed}/{len(c.results)} checks passed ({stamp})")

    os.makedirs(os.path.join(ROOT, "evidence"), exist_ok=True)
    with open(os.path.join(ROOT, "evidence", "verify.json"), "w") as f:
        json.dump({"time": stamp, "domain": domain, "ip": ip, "bucket": bucket, "results": c.results}, f, indent=2)
    lines = [f"Verification of https://{domain}, run {stamp}: **{passed} of {len(c.results)} checks passed.**", "",
             "| Check | Result | Detail |", "|---|---|---|"]
    lines += [f"| {r['check']} | {'pass' if r['ok'] else 'FAIL'} | {r['detail'].replace('|', '/')} |" for r in c.results]
    with open(os.path.join(ROOT, "evidence", "verify.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("saved evidence/verify.md and evidence/verify.json")
    return 0 if passed == len(c.results) else 1


if __name__ == "__main__":
    sys.exit(main())
