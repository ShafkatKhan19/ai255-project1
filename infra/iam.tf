# A dedicated identity for the VM instead of the Compute Engine default
# service account (which gets the broad Editor role in many projects).
resource "google_service_account" "web_vm" {
  account_id   = "web-vm"
  display_name = "Web VM (AI 255 Project 1)"
  description  = "Runs the web service. Can only read objects in the content bucket."
  depends_on   = [google_project_service.apis]
}

# Least privilege: read-only access, granted on this one bucket only (not on
# the project), so the VM cannot write or delete objects, cannot see other
# buckets, and has no other Google Cloud permissions.
resource "google_storage_bucket_iam_member" "vm_reads_bucket" {
  bucket = google_storage_bucket.content.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.web_vm.email}"
}
