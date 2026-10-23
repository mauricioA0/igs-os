variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "repository_id" {
  type    = string
  default = "igs"
}

resource "google_artifact_registry_repository" "docker" {
  project       = var.project_id
  location      = var.region
  repository_id = var.repository_id
  format        = "DOCKER"
  description   = "IGS OS images: core API, worker, models."

  docker_config {
    immutable_tags = true
  }

  # Keep the 15 most recent images per package; drop untagged layers after a week.
  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 15
    }
  }

  cleanup_policies {
    id     = "delete-untagged"
    action = "DELETE"
    condition {
      tag_state  = "UNTAGGED"
      older_than = "604800s"
    }
  }
}

output "repository" {
  value = google_artifact_registry_repository.docker.name
}

# e.g. us-central1-docker.pkg.dev/mv-cloud-509914/igs
output "image_prefix" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.docker.repository_id}"
}
