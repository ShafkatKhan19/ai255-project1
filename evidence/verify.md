Verification of https://cloud.gadgetgroveny.com, run 2026-10-26 09:15 UTC: **13 of 13 checks passed.**

| Check | Result | Detail |
|---|---|---|
| DNS A record for domain | pass | cloud.gadgetgroveny.com -> 34.72.141.1 |
| DNS A record for www | pass | www.cloud.gadgetgroveny.com -> 34.72.141.1 |
| HTTP redirects to HTTPS | pass | HTTP 308 -> https://cloud.gadgetgroveny.com/ |
| TLS certificate valid and trusted | pass | TLSv1.3, issuer Let's Encrypt (YE2), names ['cloud.gadgetgroveny.com'], expires 2027-01-24 (89 days) |
| GET / (page from bucket) | pass | HTTP 200, text/html; charset=utf-8, 2176 bytes |
| GET /api/health | pass | HTTP 200, application/json, 16 bytes |
| GET /api/files | pass | HTTP 200, application/json, 176 bytes |
| GET /files/hello.txt | pass | HTTP 200, text/plain, 104 bytes |
| Path traversal is rejected | pass | HTTP 400, page not leaked |
| GET /api/info (runs on the VM) | pass | {"service": "ai255-web", "version": "1.0.0", "instance": "web-1", "zone": "us-central1-a", "storage": "gs://ai255-p1-shafkat-web-content", "uptime_seconds": 574} |
| Security headers | pass | strict-transport-security: max-age=31536000, x-content-type-options: nosniff, x-frame-options: DENY |
| www redirects to main domain | pass | HTTP 301 -> https://cloud.gadgetgroveny.com/ |
| Bucket is not public | pass | anonymous read of https://storage.googleapis.com/ai255-p1-shafkat-web-content/public/hello.txt -> HTTP 403 |
