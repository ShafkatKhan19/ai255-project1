Prices for us-central1 (Iowa), retrieved 2026-10-25, in USD. A month is 730 hours. Sources are listed in `cost/prices.json`.

**Assumptions:** 50 KB sent per request on average; 1 KB received per request; 20% of requests are file downloads; 0.1 DNS queries per request (records are cached for their 300 s TTL); the app caches the page and the file list for 60 s; all users in North America; storage operations are an upper bound (any request may trigger a page or list read, at most once per minute per VM because of the cache); free tier applied; free-trial credits not applied.

| Level | Requests per month | Data sent | Architecture | Monthly cost | Cost per million requests |
|---|---|---|---|---|---|
| Low | 10,000 | 0.5 GiB | 1 x e2-micro, static IP, Caddy TLS | **$3.88** | $388.00 |
| Medium | 1,000,000 | 47.7 GiB | 1 x e2-micro, static IP, Caddy TLS | **$9.76** | $9.76 |
| High | 30,000,000 | 1,430.5 GiB | 2 x e2-small behind a global HTTPS load balancer | **$226.16** | $7.54 |

#### Low: 10,000 requests per month (class demo and testing: a few hundred requests a day)

| Item | Quantity | Unit price | Cost | Note |
|---|---|---|---|---|
| Compute Engine e2-micro (1 VM, 730 h) | 730 h | $0.0084 per hour | $0.00 | covered by the free tier |
| Standard persistent disk, 10 GB | 10 GB-month | $0.04 per GB-month | $0.00 | free tier covers 30 GB |
| Static external IPv4 in use | 730 h | $0.005 per hour | $3.65 | not in the free tier |
| Internet egress (Premium Tier, to North America) | 0.5 GiB | tiered | $0.00 | first 1 GiB free |
| Cloud DNS managed zone | 1 zone | $0.2 per zone-month | $0.20 | no free tier |
| Cloud DNS queries | 1,000 | $0.4 per million | $0.00 |  |
| Cloud Storage, Standard | 0.01 GiB | $0.02 per GiB-month | $0.00 | free tier covers 5 GB |
| Cloud Storage Class A operations (list) | 10,000 | $0.005 per 1,000 | $0.03 | free tier covers 5,000 |
| Cloud Storage Class B operations (read) | 12,000 | $0.0004 per 1,000 | $0.00 | free tier covers 50,000 |
| **Total** | | | **$3.88** | Let's Encrypt certificate via Caddy: $0 |

#### Medium: 1,000,000 requests per month (small public site: about 33,000 requests a day, 0.4 per second on average)

| Item | Quantity | Unit price | Cost | Note |
|---|---|---|---|---|
| Compute Engine e2-micro (1 VM, 730 h) | 730 h | $0.0084 per hour | $0.00 | covered by the free tier |
| Standard persistent disk, 10 GB | 10 GB-month | $0.04 per GB-month | $0.00 | free tier covers 30 GB |
| Static external IPv4 in use | 730 h | $0.005 per hour | $3.65 | not in the free tier |
| Internet egress (Premium Tier, to North America) | 47.7 GiB | tiered | $5.60 | first 1 GiB free |
| Cloud DNS managed zone | 1 zone | $0.2 per zone-month | $0.20 | no free tier |
| Cloud DNS queries | 100,000 | $0.4 per million | $0.04 |  |
| Cloud Storage, Standard | 0.01 GiB | $0.02 per GiB-month | $0.00 | free tier covers 5 GB |
| Cloud Storage Class A operations (list) | 43,800 | $0.005 per 1,000 | $0.19 | free tier covers 5,000 |
| Cloud Storage Class B operations (read) | 243,800 | $0.0004 per 1,000 | $0.08 | free tier covers 50,000 |
| **Total** | | | **$9.76** | Let's Encrypt certificate via Caddy: $0 |

#### High: 30,000,000 requests per month (busy site: about 1 million requests a day, 11.6 per second on average, peaks around 5x that)

| Item | Quantity | Unit price | Cost | Note |
|---|---|---|---|---|
| Compute Engine e2-small (2 VMs, 730 h each) | 1,460 h | $0.0168 per hour | $24.53 | free tier only covers e2-micro |
| Standard persistent disk, 2 x 10 GB | 20 GB-month | $0.04 per GB-month | $0.00 | free tier covers 30 GB |
| Load balancer forwarding rule | 730 h | $0.025 per hour | $18.25 | its IP address is free |
| Load balancer data processed (in + out) | 1,459 GiB | $0.008 per GiB | $11.67 |  |
| Internet egress (Premium Tier, to North America) | 1,431 GiB | tiered | $167.48 | first 1 GiB free |
| Cloud DNS managed zone | 1 zone | $0.2 per zone-month | $0.20 | no free tier |
| Cloud DNS queries | 3,000,000 | $0.4 per million | $1.20 |  |
| Cloud Storage, Standard | 0.01 GiB | $0.02 per GiB-month | $0.00 | free tier covers 5 GB |
| Cloud Storage Class A operations (list) | 87,600 | $0.005 per 1,000 | $0.41 | free tier covers 5,000 |
| Cloud Storage Class B operations (read) | 6,087,600 | $0.0004 per 1,000 | $2.42 | free tier covers 50,000 |
| **Total** | | | **$226.16** | Google-managed certificate on the load balancer: $0 |
