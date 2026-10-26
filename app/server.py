"""A small web service for AI 255 Project 1.

It serves a web page and a JSON API. Its files live in a private Cloud
Storage bucket. On the VM it reads them with the VM's own service account:
the access token comes from the metadata server, so there are no keys or
passwords on the machine. Only the Python standard library is used, so
nothing has to be installed with pip.

Routes (GET and HEAD only):
    /                  web page (site/index.html from the bucket)
    /api/health        {"status": "ok"}  (used by the verification script)
    /api/info          service name, version, VM name and zone, uptime
    /api/files         list of the files under public/ in the bucket
    /files/<name>      one file from public/ in the bucket

Settings come from environment variables:
    BUCKET       bucket name (if unset, LOCAL_DIR is used instead)
    LOCAL_DIR    folder used as the "bucket" for local runs and tests
    PORT         default 8080
    HOST         default 127.0.0.1 (Caddy forwards public traffic to it)
    APP_VERSION  default "dev"
"""

import json
import mimetypes
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SERVICE_NAME = "ai255-web"
START_TIME = time.time()
METADATA = "http://metadata.google.internal/computeMetadata/v1"
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")   # no slashes, so no path traversal
LIST_CACHE_SECONDS = 60          # listing a bucket is a Class A operation; cache it to save cost
PAGE_CACHE_SECONDS = 60


class NotFound(Exception):
    pass


class StorageError(Exception):
    pass


# --------------------------------------------------------------------------
# Storage backends
# --------------------------------------------------------------------------

class LocalStorage:
    """Reads files from a local folder. Used for local runs and tests."""

    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.name = f"local:{self.root}"

    def list(self, prefix):
        folder = os.path.join(self.root, prefix)
        if not os.path.isdir(folder):
            return []
        items = []
        for entry in sorted(os.listdir(folder)):
            path = os.path.join(folder, entry)
            if os.path.isfile(path):
                st = os.stat(path)
                items.append({"name": entry, "size": st.st_size,
                              "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(st.st_mtime))})
        return items

    def read(self, key):
        path = os.path.abspath(os.path.join(self.root, key))
        if not path.startswith(self.root + os.sep) or not os.path.isfile(path):
            raise NotFound(key)
        with open(path, "rb") as f:
            return f.read()


class GCSStorage:
    """Reads objects from Cloud Storage with the JSON API.

    The OAuth token is the VM service account's token from the metadata
    server. Which objects the VM may read is decided by IAM on the bucket,
    not by this code.
    """

    def __init__(self, bucket, opener=urllib.request.urlopen):
        self.bucket = bucket
        self.name = f"gs://{bucket}"
        self._open = opener
        self._token = None
        self._token_expiry = 0.0
        self._lock = threading.Lock()

    def _get_token(self):
        with self._lock:
            if self._token and time.time() < self._token_expiry - 60:
                return self._token
            req = urllib.request.Request(f"{METADATA}/instance/service-accounts/default/token",
                                         headers={"Metadata-Flavor": "Google"})
            with self._open(req, timeout=5) as r:
                data = json.load(r)
            self._token = data["access_token"]
            self._token_expiry = time.time() + int(data.get("expires_in", 300))
            return self._token

    def _get(self, url):
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self._get_token()}"})
        try:
            with self._open(req, timeout=10) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise NotFound(url) from e
            raise StorageError(f"Cloud Storage returned HTTP {e.code}") from e
        except urllib.error.URLError as e:
            raise StorageError(f"Cloud Storage not reachable: {e.reason}") from e

    def list(self, prefix):
        query = urllib.parse.urlencode({"prefix": prefix, "fields": "items(name,size,updated)"})
        url = f"https://storage.googleapis.com/storage/v1/b/{urllib.parse.quote(self.bucket)}/o?{query}"
        data = json.loads(self._get(url) or b"{}")
        items = []
        for obj in data.get("items", []):
            if not obj["name"].startswith(prefix):      # do not rely on the API filter alone
                continue
            name = obj["name"][len(prefix):]
            if name and "/" not in name:
                items.append({"name": name, "size": int(obj.get("size", 0)), "updated": obj.get("updated", "")})
        return sorted(items, key=lambda x: x["name"])

    def read(self, key):
        url = (f"https://storage.googleapis.com/storage/v1/b/{urllib.parse.quote(self.bucket)}"
               f"/o/{urllib.parse.quote(key, safe='')}?alt=media")
        return self._get(url)


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

class TimedCache:
    def __init__(self, seconds):
        self.seconds = seconds
        self._value = None
        self._time = 0.0
        self._lock = threading.Lock()

    def get(self, compute):
        with self._lock:
            if self._value is None or time.time() - self._time > self.seconds:
                self._value = compute()
                self._time = time.time()
            return self._value


def read_metadata(path, opener=urllib.request.urlopen):
    """Read one value from the GCE metadata server, or None when not on a VM."""
    try:
        req = urllib.request.Request(f"{METADATA}/{path}", headers={"Metadata-Flavor": "Google"})
        with opener(req, timeout=2) as r:
            return r.read().decode()
    except (urllib.error.URLError, OSError, ValueError):
        return None


FALLBACK_PAGE = b"""<!doctype html><html><head><meta charset="utf-8"><title>AI 255 Project 1</title></head>
<body><h1>AI 255 Project 1</h1><p>The page from the bucket is not available. Try <a href="/api/info">/api/info</a>.</p></body></html>"""


# --------------------------------------------------------------------------
# The application (independent of HTTP, so it is easy to test)
# --------------------------------------------------------------------------

class App:
    def __init__(self, storage, version="dev", instance=None, zone=None):
        self.storage = storage
        self.version = version
        self.instance = instance or "local"
        self.zone = zone or "local"
        self._list_cache = TimedCache(LIST_CACHE_SECONDS)
        self._page_cache = TimedCache(PAGE_CACHE_SECONDS)

    def handle(self, path):
        """Return (status, content_type, body_bytes, extra_headers) for a GET request path."""
        path = urllib.parse.urlparse(path).path
        if path == "/":
            return 200, "text/html; charset=utf-8", self._page(), {"Cache-Control": "no-cache"}
        if path == "/api/health":
            return self._json(200, {"status": "ok"})
        if path == "/api/info":
            return self._json(200, {"service": SERVICE_NAME, "version": self.version,
                                    "instance": self.instance, "zone": self.zone,
                                    "storage": self.storage.name,
                                    "uptime_seconds": int(time.time() - START_TIME)})
        if path == "/api/files":
            try:
                files = self._list_cache.get(lambda: self.storage.list("public/"))
            except StorageError as e:
                return self._json(502, {"error": str(e)})
            return self._json(200, {"files": files, "count": len(files)})
        if path.startswith("/files/"):
            name = urllib.parse.unquote(path[len("/files/"):])
            if not SAFE_NAME.match(name):
                return self._json(400, {"error": "invalid file name"})
            try:
                body = self.storage.read(f"public/{name}")
            except NotFound:
                return self._json(404, {"error": "file not found"})
            except StorageError as e:
                return self._json(502, {"error": str(e)})
            ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
            return 200, ctype, body, {"Cache-Control": "public, max-age=300"}
        return self._json(404, {"error": "not found"})

    def _page(self):
        def load():
            try:
                return self.storage.read("site/index.html")
            except (NotFound, StorageError):
                return None
        page = self._page_cache.get(load)
        return page if page is not None else FALLBACK_PAGE

    @staticmethod
    def _json(status, obj):
        return status, "application/json", json.dumps(obj).encode(), {"Cache-Control": "no-store"}


# --------------------------------------------------------------------------
# HTTP layer
# --------------------------------------------------------------------------

def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = SERVICE_NAME
        sys_version = ""

        def do_GET(self):
            self._respond(send_body=True)

        def do_HEAD(self):
            self._respond(send_body=False)

        def _not_allowed(self):
            body = b'{"error": "method not allowed"}'
            self.send_response(405)
            self.send_header("Allow", "GET, HEAD")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_POST = do_PUT = do_DELETE = do_PATCH = _not_allowed

        def _respond(self, send_body):
            try:
                status, ctype, body, headers = app.handle(self.path)
            except Exception as e:                      # never crash the server on one bad request
                print(f"error handling {self.path}: {e!r}", file=sys.stderr)
                status, ctype, body, headers = 500, "application/json", b'{"error": "internal error"}', {}
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in headers.items():
                self.send_header(k, v)
            self.end_headers()
            if send_body:
                self.wfile.write(body)

        def log_message(self, fmt, *args):                # one line per request to stdout (journald)
            sys.stdout.write(f"{self.address_string()} {fmt % args}\n")
            sys.stdout.flush()

    return Handler


def build_app_from_env():
    bucket = os.environ.get("BUCKET")
    storage = GCSStorage(bucket) if bucket else LocalStorage(os.environ.get("LOCAL_DIR", "content"))
    instance = read_metadata("instance/name") if bucket else None
    zone = read_metadata("instance/zone") if bucket else None
    return App(storage, version=os.environ.get("APP_VERSION", "dev"),
               instance=instance, zone=zone.rsplit("/", 1)[-1] if zone else None)


def main():
    app = build_app_from_env()
    host, port = os.environ.get("HOST", "127.0.0.1"), int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer((host, port), make_handler(app))
    print(f"{SERVICE_NAME} {app.version} serving {app.storage.name} on http://{host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
