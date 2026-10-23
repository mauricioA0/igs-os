# One Cloud Run (v2) service. Images are rolled by the deploy pipeline, so Terraform ignores
# image changes after creation and only owns configuration.

variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "name" {
  type = string
}

variable "image" {
  type        = string
  description = "Initial image; later rollouts come from CD."
}

variable "service_account" {
  type = string
}

variable "public" {
  type        = bool
  default     = false
  description = "allUsers may invoke (the API serves the public demo and Vercel)."
}

variable "internal_only" {
  type        = bool
  default     = false
  description = "Ingress from the VPC only (e.g. the models service)."
}

variable "invokers" {
  type    = list(string)
  default = []
}

variable "cpu" {
  type    = string
  default = "1"
}

variable "memory" {
  type    = string
  default = "512Mi"
}

variable "gpu" {
  type        = bool
  default     = false
  description = "Attach one NVIDIA L4 (needs >= 4 CPU / 16Gi)."
}

variable "min_instances" {
  type    = number
  default = 0
}

variable "max_instances" {
  type    = number
  default = 10
}

variable "concurrency" {
  type    = number
  default = 80
}

variable "port" {
  type    = number
  default = 8080
}

variable "timeout" {
  type    = string
  default = "300s"
}

variable "health_path" {
  type    = string
  default = "/healthz"
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
  type    = string
  default = null
}

variable "subnetwork" {
  type    = string
  default = null
}

variable "deletion_protection" {
  type    = bool
  default = false
}

resource "google_cloud_run_v2_service" "this" {
  project             = var.project_id
  name                = var.name
  location            = var.region
  ingress             = var.internal_only ? "INGRESS_TRAFFIC_INTERNAL_ONLY" : "INGRESS_TRAFFIC_ALL"
  deletion_protection = var.deletion_protection

  template {
    service_account                  = var.service_account
    timeout                          = var.timeout
    max_instance_request_concurrency = var.concurrency
    gpu_zonal_redundancy_disabled    = var.gpu ? true : null

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    dynamic "node_selector" {
      for_each = var.gpu ? [1] : []
      content {
        accelerator = "nvidia-l4"
      }
    }

    dynamic "vpc_access" {
      for_each = var.network == null ? [] : [1]
      content {
        # ALL_TRAFFIC: calls to the internal-ingress models service must leave through the VPC
        # (Private Google Access); internet egress (OpenAI) goes out via Cloud NAT.
        egress = "ALL_TRAFFIC"
        network_interfaces {
          network    = var.network
          subnetwork = var.subnetwork
        }
      }
    }

    containers {
      image = var.image

      ports {
        container_port = var.port
      }

      resources {
        limits = merge(
          { cpu = var.cpu, memory = var.memory },
          var.gpu ? { "nvidia.com/gpu" = "1" } : {},
        )
        cpu_idle          = var.min_instances == 0
        startup_cpu_boost = true
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

      startup_probe {
        initial_delay_seconds = 0
        period_seconds        = 5
        # Loading BGE-M3 + the reranker on CPU takes ~2–3 min; allow 5 min.
        failure_threshold = 60
        timeout_seconds   = 3
        http_get {
          path = var.health_path
        }
      }

      liveness_probe {
        period_seconds  = 30
        timeout_seconds = 5
        http_get {
          path = var.health_path
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version,
    ]
  }
}

resource "google_cloud_run_v2_service_iam_member" "public" {
  count    = var.public ? 1 : 0
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.this.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "invoker" {
  for_each = toset(var.invokers)
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.this.name
  role     = "roles/run.invoker"
  member   = each.value
}

output "uri" {
  value = google_cloud_run_v2_service.this.uri
}

output "name" {
  value = google_cloud_run_v2_service.this.name
}
