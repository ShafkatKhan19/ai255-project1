# AI 255 Project 1: First Cloud Deployment (Google Cloud)

A web service on a Compute Engine VM, with its content in a private Cloud Storage bucket, a domain in Cloud DNS, HTTPS through Caddy and Let's Encrypt, and a service account that can only read that one bucket. Everything is created with Terraform.

```
app/            web service (server.py, Python standard library only) and its tests
content/        files uploaded to the bucket: site/index.html and public/*
infra/          Terraform: network, firewall, static IP, bucket, IAM, VM, DNS, startup script
scripts/        verify.py (checks the live site), build_report.py, and tests
cost/           cost_model.py, prices.json (with sources), cost_estimate.md
docs/           architecture diagram, report template, REPORT.md
evidence/       created by verify.py and the IAM check
```

## Deploy it (Windows, PowerShell)

Plan about an hour, most of it waiting for DNS. Do step 1 first, because a new domain can take time to work.

### 1. Get a domain

You need a domain whose name servers you can change. Two options:

* **Free:** the GitHub Student Developer Pack (education.github.com/pack) has included a free one-year `.me` domain from Namecheap. Check that the offer is still listed for you, then register the domain.
* **Paid:** buy the cheapest domain at any registrar (Namecheap, Porkbun, Cloudflare, Google Cloud Domains, …). Many first-year prices are a few dollars.

Do not change the name servers yet. Terraform tells you what to enter in step 6.

### 2. Install the tools

```powershell
winget install Google.CloudSDK
winget install Hashicorp.Terraform
winget install Python.Python.3.12
```
Close and reopen PowerShell, then check: `gcloud --version`, `terraform -version`, `python --version`.

### 3. Create the project and log in

Pick a project ID that is unique, for example `ai255-p1-shafkat` (lower case, digits and hyphens).

```powershell
gcloud auth login
gcloud projects create ai255-p1-shafkat --name "AI255 Project 1"
gcloud config set project ai255-p1-shafkat
gcloud billing accounts list
gcloud billing projects link ai255-p1-shafkat --billing-account YOUR-BILLING-ACCOUNT-ID
gcloud auth application-default login
gcloud auth application-default set-quota-project ai255-p1-shafkat
```
Use a personal Google account (not your university one): projects inside a school organization can have policies that block external IPs or new VMs. Billing must be linked even on the free tier. Set a budget alert now: Billing, then Budgets and alerts, then create a budget of $10 with email alerts.

### 4. Configure

```powershell
cd ai255-first-cloud-deployment\infra
Copy-Item terraform.tfvars.example terraform.tfvars
notepad terraform.tfvars
```
Fill in `project_id`, `domain` (for example `shafkat.me`, no `https://`) and `acme_email`.

### 5. Create everything

```powershell
terraform init
terraform validate
terraform plan -out tfplan
terraform apply tfplan
```
`plan` should list 22 resources to add (5 APIs, network, subnet, 2 firewall rules, IP, bucket, 3 content objects, release object, service account, IAM binding, VM, DNS zone, 3 DNS records). If `apply` fails with "API has not been used in project" or "not enabled", wait one minute and run `terraform apply` again: newly enabled APIs take a moment.

### 6. Point the domain to Cloud DNS

```powershell
terraform output name_servers
```
At your registrar, set the domain's name servers to these four values (custom DNS; enter them without the trailing dot). On Namecheap: Domain List, Manage, Nameservers, Custom DNS.

### 7. Wait for DNS and the certificate

```powershell
nslookup -type=NS shafkat.me 8.8.8.8
nslookup shafkat.me 8.8.8.8
```
When the second command returns your `static_ip` (`terraform output static_ip`), open `https://shafkat.me`. Caddy keeps retrying the certificate on its own, usually within a few minutes after DNS works. To see what the VM is doing:

```powershell
gcloud compute ssh web-1 --zone us-central1-a --tunnel-through-iap --command "sudo journalctl -u google-startup-scripts -n 40 --no-pager"
gcloud compute ssh web-1 --zone us-central1-a --tunnel-through-iap --command "sudo journalctl -u caddy -n 40 --no-pager"
```

### 8. Collect evidence and build the report

Run these from the repository root (`cd ..`):

```powershell
python scripts\verify.py --from-terraform infra
gcloud compute ssh web-1 --zone us-central1-a --tunnel-through-iap --command iam-check | Out-File -Encoding utf8 evidence\iam-check.txt
python cost\cost_model.py
python scripts\build_report.py
```
`verify.py` should print `13/13 checks passed`. `iam-check` should show READ 200 and 403 for everything else. `docs/REPORT.md` is then complete. Also take screenshots for your presentation: the padlock and certificate in the browser, the VM, the bucket's Permissions tab, the Cloud DNS zone, and the IAM page.

### 9. Updating and removing

* After changing `app/server.py` or `content/`: `terraform apply`, then `gcloud compute instances reset web-1 --zone us-central1-a` (the VM downloads the new release at boot).
* After grading: `terraform destroy` in `infra/` removes everything. Until then it costs about $0.13 per day, mostly the static IP.

## Tests

```powershell
pip install pytest
python -m pytest -q app scripts cost
```

## Troubleshooting

| Problem | Cause and fix |
|---|---|
| `gcloud projects create` says the ID is in use | Project IDs are global. Add digits, for example `ai255-p1-shafkat-26`, and use that ID everywhere. |
| `apply` fails with "service account ... does not exist" or a 403 right after creating it | New service accounts and APIs take a few seconds to become visible. Run `terraform apply` again; it continues where it stopped. |
| Bucket name already exists | Bucket names are global. Change `project_id` or edit the name in `infra/storage.tf`. |
| Browser shows a certificate warning | DNS was not ready when Caddy started. Wait, then `gcloud compute ssh web-1 --zone us-central1-a --tunnel-through-iap --command "sudo systemctl restart caddy"`. |
| `/api/files` returns 502 | The VM cannot read the bucket. Run `iam-check` (step 8) and check the IAM binding in `infra/iam.tf`. |
| SSH through IAP fails | Your account needs the IAP-secured Tunnel User role (project owners have it), and the firewall rule `allow-ssh-from-iap` must exist. |
| "Constraint ... violated" or "organization policy" errors | The project is inside an organization with restrictive policies. Create the project with a personal Google account instead. |
| Startup script failed | Check its log (step 7). It is safe to run again: `gcloud compute instances reset web-1 --zone us-central1-a`. |
