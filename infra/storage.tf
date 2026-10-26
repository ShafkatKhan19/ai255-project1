# Private bucket for the app release and the files the web service serves.
# Nothing in it is public: visitors only reach it through the VM.
resource "google_storage_bucket" "content" {
  name                        = "${var.project_id}-web-content"
  location                    = upper(var.region) # single region, same as the VM: no transfer cost between them
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true       # IAM only, no per-object ACLs
  public_access_prevention    = "enforced" # the bucket can never be made public by mistake
  force_destroy               = true       # lets "terraform destroy" remove it with its objects

  versioning {
    enabled = true # an overwritten or deleted object can be restored
  }

  depends_on = [google_project_service.apis]
}

locals {
  content_dir = "${path.module}/../content"
  mime_types = {
    html = "text/html; charset=utf-8"
    txt  = "text/plain; charset=utf-8"
    json = "application/json"
    png  = "image/png"
    svg  = "image/svg+xml"
    css  = "text/css"
    js   = "application/javascript"
  }
}

# Every file under content/ (site/index.html, public/*) becomes an object.
resource "google_storage_bucket_object" "content" {
  for_each = fileset(local.content_dir, "**")

  bucket         = google_storage_bucket.content.name
  name           = each.value
  source         = "${local.content_dir}/${each.value}"
  source_md5hash = filemd5("${local.content_dir}/${each.value}")
  content_type   = lookup(local.mime_types, lower(regex("[^.]+$", each.value)), "application/octet-stream")
}

# The application release: one Python file, downloaded by the VM at boot.
resource "google_storage_bucket_object" "app" {
  bucket         = google_storage_bucket.content.name
  name           = "release/server.py"
  source         = "${path.module}/../app/server.py"
  source_md5hash = filemd5("${path.module}/../app/server.py")
  content_type   = "text/x-python"
}
