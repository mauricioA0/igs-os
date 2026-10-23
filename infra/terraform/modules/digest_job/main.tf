# Morning ops digest: Cloud Scheduler → Cloud Run job (`python -m igs_core.digest_job`).
#
# Weekdays at 07:30 Buenos Aires the scheduler calls the Run Admin API `jobs/<name>:run` with
# its own service account (which may only invoke this job). The job runs as the core service
# account (it already reads the database URL and the OpenAI key), builds the digest per tenant,
# writes a `digest.generated` outbox event and, when a relay webhook is configured, posts the
# HTML/text email to it. Images roll from CD like every other job; Terraform owns config.

variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "name" {
  type        = string
  description = "Job name, e.g. igs-demo-digest."
}

variable "image" {
  type        = string
  description = "The ops image (scripts/deploy/ops.Dockerfile); later rollouts come from CD."
}

variable "service_account" {
  type        = string
  description = "Runs the job (needs the database URL + OpenAI secrets): the core SA."
}

variable "schedule" {
  type    = string
  default = "30 7 * * 1-5"
}

variable "time_zone" {
  type    = string
  default = "America/Argentina/Buenos_Aires"
}

variable "tenants" {
  type        = list(string)
  default     = []
  description = "Tenant slugs; empty = every tenant."
}

variable "env" {
  type    = map(string)
  default = {}
}

variable "secret_env" {
  type        = map(string)
  default     = {}
  description = "ENV_NAME -> Secret Manager secret id (latest version)."
}

variable "network" {
  type = string
}

variable "subnetwork" {
  type = string
}

variable "paused" {
  type    = bool
  default = false
}

resource "google_project_service" "scheduler" {
  project            = var.project_id
  service            = "cloudscheduler.googleapis.com"
  disable_on_destroy = false
}

resource "google_cloud_run_v2_job" "digest" {
  project             = var.project_id
  name                = var.name
  location            = var.region
  deletion_protection = false

  template {
    task_count = 1

    template {
      service_account = var.service_account
      max_retries     = 1
      timeout         = "600s"

      vpc_access {
        egress = "ALL_TRAFFIC"
        network_interfaces {
          network    = var.network
          subnetwork = var.subnetwork
        }
      }

      containers {
        image   = var.image
        command = ["python", "-m", "igs_core.digest_job"]
        args    = flatten([for t in var.tenants : ["--tenant", t]])

        resources {
          limits = {
            cpu    = "1"
            memory = "512Mi"
          }
        }

        dynamic "env" {
          for_each = var.env
          content {
            name  = env.key
            value = env.value
          }
        }

        dynamic "env" {
          for_each = var.secret_env
          content {
            name = env.key
            value_source {
              secret_key_ref {
                secret  = env.value
                version = "latest"
              }
            }
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].template[0].containers[0].image,
      client,
      client_version,
    ]
  }
}

# The scheduler's identity can run this one job and nothing else.
resource "google_service_account" "scheduler" {
  project      = var.project_id
  account_id   = substr("${var.name}-sched", 0, 30)
  display_name = "Cloud Scheduler → ${var.name}"
}

resource "google_cloud_run_v2_job_iam_member" "scheduler_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.digest.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}

resource "google_cloud_scheduler_job" "digest" {
  project     = var.project_id
  region      = var.region
  name        = var.name
  description = "Morning ops digest (weekdays)."
  schedule    = var.schedule
  time_zone   = var.time_zone
  paused      = var.paused

  attempt_deadline = "60s"
  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.digest.name}:run"

    oauth_token {
      service_account_email = google_service_account.scheduler.email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }

  depends_on = [google_project_service.scheduler, google_cloud_run_v2_job_iam_member.scheduler_invoker]
}

output "job_name" {
  value = google_cloud_run_v2_job.digest.name
}

output "scheduler_job" {
  value = google_cloud_scheduler_job.digest.id
}
