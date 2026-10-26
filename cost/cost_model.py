"""Monthly cost estimate at three traffic levels.

    python cost/cost_model.py        # writes cost/cost_estimate.md and cost/cost_estimate.json

All prices come from cost/prices.json, which lists the source page of each one.
Every assumption is a named constant below, so it is easy to change one and
see the effect.
"""

import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
P = json.load(open(os.path.join(HERE, "prices.json")))
price = {k: v["value"] for k, v in P["prices"].items()}
FREE = P["free_tier"]
HOURS = P["hours_per_month"]

# ---------------------------------------------------------------- assumptions
AVG_RESPONSE_KB = 50          # average bytes sent per request: page, API JSON, files and their headers
AVG_REQUEST_KB = 1            # average bytes received per request (headers)
FILE_DOWNLOAD_SHARE = 0.20    # share of requests that are /files/<name> downloads (one Class B read each)
DNS_QUERIES_PER_REQUEST = 0.1 # resolvers cache records for the 300 s TTL, so most visits need no query
CACHE_SECONDS = 60            # the app caches the file list and the page (server.py)
STORAGE_GIB = 0.01            # bucket size: the page, a few files and the release

LEVELS = [
    {"name": "Low", "requests": 10_000,
     "story": "class demo and testing: a few hundred requests a day"},
    {"name": "Medium", "requests": 1_000_000,
     "story": "small public site: about 33,000 requests a day, 0.4 per second on average"},
    {"name": "High", "requests": 30_000_000,
     "story": "busy site: about 1 million requests a day, 11.6 per second on average, peaks around 5x that"},
]

GIB = 1024 ** 3

UNITS = {   # unit of each unit price, keyed by the start of the item name
    "Compute Engine e2-micro": "per hour", "Compute Engine e2-small": "per hour",
    "Standard persistent disk": "per GB-month", "Static external IPv4 in use": "per hour",
    "Load balancer forwarding rule": "per hour", "Load balancer data processed": "per GiB",
    "Cloud DNS managed zone": "per zone-month", "Cloud DNS queries": "per million",
    "Cloud Storage": "per GiB-month", "Cloud Storage Class A operations": "per 1,000",
    "Cloud Storage Class B operations": "per 1,000",
}


def egress_cost(gib):
    """Premium Tier internet egress to North America, using the tiered prices."""
    cost, lower = 0.0, 0.0
    for upper, rate in price["egress_premium_to_north_america_tiers"]:
        upper = math.inf if upper is None else upper
        if gib > lower:
            cost += (min(gib, upper) - lower) * rate
        lower = upper
    return cost


def gcs_ops(requests, vms):
    """Class A (list) and Class B (read) operations per month.

    Page and file list are cached for CACHE_SECONDS per VM, so they cost at
    most one read each per minute per VM, and never more than the number of
    requests. File downloads are not cached by the app: one read each.
    """
    per_month_cap = HOURS * 3600 / CACHE_SECONDS * vms
    page_and_list = min(requests, per_month_cap)
    class_a = page_and_list                                 # object list = Class A
    class_b = page_and_list + requests * FILE_DOWNLOAD_SHARE  # page read + downloads = Class B
    return class_a, class_b


def line(item, quantity, unit_price, cost, note=""):
    return {"item": item, "quantity": quantity, "unit_price": unit_price, "cost": round(cost, 2), "note": note}


def estimate(level):
    n = level["requests"]
    out_gib = n * AVG_RESPONSE_KB * 1024 / GIB
    in_gib = n * AVG_REQUEST_KB * 1024 / GIB
    dns_q = n * DNS_QUERIES_PER_REQUEST
    lines = []

    if level["name"] in ("Low", "Medium"):
        # The deployed design: one e2-micro with a static IP, Caddy terminates TLS.
        vms = 1
        lines.append(line("Compute Engine e2-micro (1 VM, 730 h)", "730 h", price["e2_micro_per_hour"],
                          max(0, HOURS - FREE["e2_micro_hours"]) * price["e2_micro_per_hour"],
                          "covered by the free tier"))
        lines.append(line("Standard persistent disk, 10 GB", "10 GB-month", price["pd_standard_per_gb_month"],
                          max(0, 10 - FREE["pd_standard_gb_month"]) * price["pd_standard_per_gb_month"],
                          "free tier covers 30 GB"))
        lines.append(line("Static external IPv4 in use", "730 h", price["external_ip_in_use_per_hour"],
                          HOURS * price["external_ip_in_use_per_hour"], "not in the free tier"))
        lines.append(line("Internet egress (Premium Tier, to North America)", f"{out_gib:,.1f} GiB", "tiered",
                          egress_cost(out_gib), "first 1 GiB free"))
        tls = "Let's Encrypt certificate via Caddy: $0"
    else:
        # Scaled design: 2 x e2-small in a managed instance group behind a global
        # external Application Load Balancer with a Google-managed certificate.
        vms = 2
        lines.append(line("Compute Engine e2-small (2 VMs, 730 h each)", "1,460 h", price["e2_small_per_hour"],
                          2 * HOURS * price["e2_small_per_hour"], "free tier only covers e2-micro"))
        lines.append(line("Standard persistent disk, 2 x 10 GB", "20 GB-month", price["pd_standard_per_gb_month"],
                          max(0, 20 - FREE["pd_standard_gb_month"]) * price["pd_standard_per_gb_month"],
                          "free tier covers 30 GB"))
        lines.append(line("Load balancer forwarding rule", "730 h", price["lb_forwarding_rule_per_hour"],
                          HOURS * price["lb_forwarding_rule_per_hour"], "its IP address is free"))
        lines.append(line("Load balancer data processed (in + out)", f"{in_gib + out_gib:,.0f} GiB",
                          price["lb_data_processed_per_gib"], (in_gib + out_gib) * price["lb_data_processed_per_gib"]))
        lines.append(line("Internet egress (Premium Tier, to North America)", f"{out_gib:,.0f} GiB", "tiered",
                          egress_cost(out_gib), "first 1 GiB free"))
        tls = "Google-managed certificate on the load balancer: $0"

    lines.append(line("Cloud DNS managed zone", "1 zone", price["dns_zone_per_month"], price["dns_zone_per_month"],
                      "no free tier"))
    lines.append(line("Cloud DNS queries", f"{dns_q:,.0f}", price["dns_queries_per_million"],
                      dns_q / 1e6 * price["dns_queries_per_million"]))
    lines.append(line("Cloud Storage, Standard", f"{STORAGE_GIB} GiB", price["gcs_standard_per_gib_month"],
                      max(0, STORAGE_GIB - FREE["gcs_storage_gb_month"]) * price["gcs_standard_per_gib_month"],
                      "free tier covers 5 GB"))
    a, b = gcs_ops(n, vms)
    lines.append(line("Cloud Storage Class A operations (list)", f"{a:,.0f}", price["gcs_class_a_per_1000"],
                      max(0, a - FREE["gcs_class_a_ops"]) / 1000 * price["gcs_class_a_per_1000"],
                      "free tier covers 5,000"))
    lines.append(line("Cloud Storage Class B operations (read)", f"{b:,.0f}", price["gcs_class_b_per_1000"],
                      max(0, b - FREE["gcs_class_b_ops"]) / 1000 * price["gcs_class_b_per_1000"],
                      "free tier covers 50,000"))
    total = sum(x["cost"] for x in lines)
    return {**level, "egress_gib": round(out_gib, 1), "lines": lines, "total": round(total, 2), "tls": tls,
            "per_million_requests": round(total / n * 1e6, 2)}


def to_markdown(results):
    md = [f"Prices for {P['region']}, retrieved {P['retrieved']}, in {P['currency']}. "
          f"A month is {HOURS} hours. Sources are listed in `cost/prices.json`.", "",
          "**Assumptions:** " + "; ".join([
              f"{AVG_RESPONSE_KB} KB sent per request on average",
              f"{AVG_REQUEST_KB} KB received per request",
              f"{int(FILE_DOWNLOAD_SHARE * 100)}% of requests are file downloads",
              f"{DNS_QUERIES_PER_REQUEST} DNS queries per request (records are cached for their 300 s TTL)",
              f"the app caches the page and the file list for {CACHE_SECONDS} s",
              "all users in North America",
              "storage operations are an upper bound (any request may trigger a page or list read, at most once per minute per VM because of the cache)",
              "free tier applied; free-trial credits not applied"]) + ".", "",
          "| Level | Requests per month | Data sent | Architecture | Monthly cost | Cost per million requests |",
          "|---|---|---|---|---|---|"]
    for r in results:
        arch = "1 x e2-micro, static IP, Caddy TLS" if r["name"] != "High" else "2 x e2-small behind a global HTTPS load balancer"
        md.append(f"| {r['name']} | {r['requests']:,} | {r['egress_gib']:,} GiB | {arch} | "
                  f"**${r['total']:,.2f}** | ${r['per_million_requests']:,.2f} |")
    for r in results:
        md += ["", f"#### {r['name']}: {r['requests']:,} requests per month ({r['story']})", "",
               "| Item | Quantity | Unit price | Cost | Note |", "|---|---|---|---|---|"]
        for x in r["lines"]:
            up = x["unit_price"] if isinstance(x["unit_price"], str) else f"${x['unit_price']:g} {UNITS.get(x['item'].split(' (')[0].split(',')[0], '')}".strip()
            md.append(f"| {x['item']} | {x['quantity']} | {up} | ${x['cost']:,.2f} | {x['note']} |")
        md.append(f"| **Total** | | | **${r['total']:,.2f}** | {r['tls']} |")
    return "\n".join(md) + "\n"


def main():
    results = [estimate(level) for level in LEVELS]
    with open(os.path.join(HERE, "cost_estimate.json"), "w") as f:
        json.dump(results, f, indent=2)
    with open(os.path.join(HERE, "cost_estimate.md"), "w", encoding="utf-8") as f:
        f.write(to_markdown(results))
    for r in results:
        print(f"{r['name']:<7} {r['requests']:>11,} requests  {r['egress_gib']:>8,} GiB out  ${r['total']:>8,.2f} per month")


if __name__ == "__main__":
    main()
