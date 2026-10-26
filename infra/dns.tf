# Public zone for the domain. After "terraform apply", set the domain's name
# servers at the registrar to the four values in the name_servers output.
resource "google_dns_managed_zone" "main" {
  name        = "web-zone"
  dns_name    = "${var.domain}."
  description = "Public zone for AI 255 Project 1"
  visibility  = "public"
  depends_on  = [google_project_service.apis]
}

resource "google_dns_record_set" "apex" {
  managed_zone = google_dns_managed_zone.main.name
  name         = google_dns_managed_zone.main.dns_name
  type         = "A"
  ttl          = 300
  rrdatas      = [google_compute_address.web.address]
}

resource "google_dns_record_set" "www" {
  managed_zone = google_dns_managed_zone.main.name
  name         = "www.${google_dns_managed_zone.main.dns_name}"
  type         = "A"
  ttl          = 300
  rrdatas      = [google_compute_address.web.address]
}

# CAA: only Let's Encrypt may issue certificates for this domain.
resource "google_dns_record_set" "caa" {
  managed_zone = google_dns_managed_zone.main.name
  name         = google_dns_managed_zone.main.dns_name
  type         = "CAA"
  ttl          = 3600
  rrdatas      = ["0 issue \"letsencrypt.org\""]
}
