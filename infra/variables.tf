variable "project_id" {
  description = "Google Cloud project ID (not the project name)."
  type        = string
}

variable "domain" {
  description = "Domain you own, without a trailing dot, e.g. example.me. Cloud DNS becomes its name server."
  type        = string

  validation {
    condition     = can(regex("^([a-z0-9-]+\\.)+[a-z]{2,}$", var.domain))
    error_message = "Use a lower-case domain such as example.me, without https:// and without a trailing dot."
  }
}

variable "acme_email" {
  description = "Email for Let's Encrypt expiry notices (optional, can be empty)."
  type        = string
  default     = ""
}

variable "region" {
  description = "Region. us-central1, us-east1 and us-west1 are the free-tier regions for e2-micro."
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "Zone inside the region."
  type        = string
  default     = "us-central1-a"
}

variable "machine_type" {
  description = "VM size. e2-micro is covered by the free tier (one instance per month)."
  type        = string
  default     = "e2-micro"
}

variable "app_version" {
  description = "Label shown by /api/info. Change it to make the VM pick up a new release on its next boot."
  type        = string
  default     = "1.0.0"
}
