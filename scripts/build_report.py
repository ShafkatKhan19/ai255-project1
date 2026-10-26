"""Build docs/REPORT.md from docs/REPORT.template.md and the evidence files.

    python cost/cost_model.py
    python scripts/verify.py --from-terraform infra
    gcloud compute ssh web-1 --zone us-central1-a --tunnel-through-iap --command iam-check > evidence/iam-check.txt
    python scripts/build_report.py

Sections whose evidence file does not exist yet are marked PENDING instead of
being filled with made-up results.
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(*parts):
    path = os.path.join(ROOT, *parts)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        raw = f.read()
    # PowerShell's ">" writes UTF-16 with a byte-order mark; everything else here is UTF-8.
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8-sig", errors="replace")
    return text.replace("\r\n", "\n").strip()


def main():
    template = read("docs", "REPORT.template.md")
    cost = read("cost", "cost_estimate.md") or "PENDING: run `python cost/cost_model.py`."
    verify = read("evidence", "verify.md") or ("PENDING: run `python scripts/verify.py --from-terraform infra` "
                                               "after the site is live.")
    iam = read("evidence", "iam-check.txt")
    iam_block = f"```\n{iam}\n```" if iam else "PENDING: save the output of the command above to `evidence/iam-check.txt`."
    url = "PENDING (fill in after deployment)"
    vj = read("evidence", "verify.json")
    if vj:
        url = f"https://{json.loads(vj)['domain']}"
    report = (template.replace("{{URL}}", url).replace("{{COST}}", cost)
              .replace("{{VERIFY}}", verify).replace("{{IAM_CHECK}}", iam_block))
    with open(os.path.join(ROOT, "docs", "REPORT.md"), "w", encoding="utf-8") as f:
        f.write(report + "\n")
    pending = report.count("PENDING")
    print(f"wrote docs/REPORT.md ({pending} section(s) still pending)")


if __name__ == "__main__":
    main()
