terraform {
  required_version = ">= 1.0.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.3.0"
    }
  }
}

resource "google_storage_bucket" "logs_data_bucket" {
  name                        = "${var.dev_project_id}-logs-data"
  location                    = var.region
  project                     = var.dev_project_id
  uniform_bucket_level_access = true

  lifecycle {
    prevent_destroy = true
    ignore_changes  = all
  }

  # Use this block to create the bucket only if it doesn't exist
  count = length(data.google_storage_bucket.existing_bucket) > 0 ? 0 : 1
}


data "google_storage_bucket" "existing_bucket" {
  name = "${var.dev_project_id}-logs-data"
}
