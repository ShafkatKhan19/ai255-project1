resource "google_compute_instance" "web" {
  name                      = "web-1"
  machine_type              = var.machine_type
  zone                      = var.zone
  tags                      = ["web"] # the firewall rules apply to this tag
  allow_stopping_for_update = true

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 10            # GB; the free tier covers 30 GB of standard disk
      type  = "pd-standard" # the disk type covered by the free tier
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.web.id
    access_config {
      nat_ip       = google_compute_address.web.address
      network_tier = "PREMIUM"
    }
  }

  # The VM acts as the web-vm service account. The cloud-platform scope is
  # Google's recommended setting: what the VM may actually do is limited by
  # the IAM roles of the service account (only objectViewer on one bucket).
  service_account {
    email  = google_service_account.web_vm.email
    scopes = ["cloud-platform"]
  }

  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  metadata = {
    enable-oslogin = "TRUE" # SSH access is controlled by IAM, no SSH keys in metadata
    app-md5        = google_storage_bucket_object.app.md5hash
    startup-script = templatefile("${path.module}/startup.sh.tftpl", {
      bucket      = google_storage_bucket.content.name
      domain      = var.domain
      acme_email  = var.acme_email
      app_version = var.app_version
    })
  }

  # The VM must be able to read the bucket before its startup script runs.
  depends_on = [
    google_storage_bucket_iam_member.vm_reads_bucket,
    google_storage_bucket_object.app,
    google_storage_bucket_object.content,
    google_compute_firewall.allow_web,
  ]
}
