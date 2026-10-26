output "url" {
  description = "Live endpoint (works once DNS is delegated and the certificate is issued)."
  value       = "https://${var.domain}"
}

output "static_ip" {
  value = google_compute_address.web.address
}

output "name_servers" {
  description = "Enter these as custom name servers at your domain registrar."
  value       = google_dns_managed_zone.main.name_servers
}

output "bucket" {
  value = google_storage_bucket.content.name
}

output "vm_service_account" {
  value = google_service_account.web_vm.email
}

output "ssh_command" {
  value = "gcloud compute ssh ${google_compute_instance.web.name} --zone ${var.zone} --tunnel-through-iap"
}
