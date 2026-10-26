# APIs the project needs. They stay enabled if the infrastructure is destroyed,
# so other work in the project is not affected.
resource "google_project_service" "apis" {
  for_each = toset([
    "compute.googleapis.com",
    "dns.googleapis.com",
    "storage.googleapis.com",
    "iam.googleapis.com",
    "iap.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

# A custom VPC instead of the "default" network: the default network comes
# with broad firewall rules. Here only the rules below exist, and everything
# else coming in from outside is blocked by the implied deny-all ingress rule.
resource "google_compute_network" "web" {
  name                    = "web-vpc"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.apis]
}

resource "google_compute_subnetwork" "web" {
  name                     = "web-subnet"
  region                   = var.region
  network                  = google_compute_network.web.id
  ip_cidr_range            = "10.10.0.0/24"
  private_ip_google_access = true
}

# HTTP and HTTPS from anywhere. Port 80 is needed for the Let's Encrypt
# HTTP-01 check and for redirecting visitors to HTTPS.
resource "google_compute_firewall" "allow_web" {
  name          = "allow-http-https"
  network       = google_compute_network.web.id
  direction     = "INGRESS"
  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["web"]

  allow {
    protocol = "tcp"
    ports    = ["80", "443"]
  }
}

# SSH only from Google's Identity-Aware Proxy range, not from the internet.
# Connect with:  gcloud compute ssh web-1 --zone ZONE --tunnel-through-iap
resource "google_compute_firewall" "allow_ssh_iap" {
  name          = "allow-ssh-from-iap"
  network       = google_compute_network.web.id
  direction     = "INGRESS"
  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["web"]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}

# Static external IP, so the DNS records never have to change.
resource "google_compute_address" "web" {
  name         = "web-ip"
  region       = var.region
  address_type = "EXTERNAL"
  network_tier = "PREMIUM"
  depends_on   = [google_project_service.apis]
}
