# GKE Autopilot for the Temporal server and the flow/ingestion workers (temporal.md: workers
# long-poll the task queue, so they scale on queue backlog with KEDA, not on HTTP).
# Private nodes; the control plane is public but restricted to authorized networks.

variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "name" {
  type = string
}

variable "network" {
  type = string
}

variable "subnetwork" {
  type = string
}

variable "pods_range_name" {
  type = string
}

variable "services_range_name" {
  type = string
}

variable "master_cidr" {
  type    = string
  default = "172.16.0.0/28"
}

variable "authorized_networks" {
  type        = map(string)
  default     = {}
  description = "name -> CIDR allowed to reach the control plane (operators, CI runners)."
}

variable "release_channel" {
  type    = string
  default = "REGULAR"
}

variable "deletion_protection" {
  type    = bool
  default = true
}

resource "google_container_cluster" "this" {
  project             = var.project_id
  name                = var.name
  location            = var.region
  enable_autopilot    = true
  network             = var.network
  subnetwork          = var.subnetwork
  deletion_protection = var.deletion_protection

  ip_allocation_policy {
    cluster_secondary_range_name  = var.pods_range_name
    services_secondary_range_name = var.services_range_name
  }

  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = var.master_cidr
  }

  dynamic "master_authorized_networks_config" {
    for_each = length(var.authorized_networks) > 0 ? [1] : []
    content {
      dynamic "cidr_blocks" {
        for_each = var.authorized_networks
        content {
          display_name = cidr_blocks.key
          cidr_block   = cidr_blocks.value
        }
      }
    }
  }

  release_channel {
    channel = var.release_channel
  }

  # Autopilot enables Workload Identity; pods map to Google SAs via the binding below.
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  secret_manager_config {
    enabled = true
  }

  resource_labels = {
    app = "igs-os"
  }
}

output "name" {
  value = google_container_cluster.this.name
}

output "endpoint" {
  value     = google_container_cluster.this.endpoint
  sensitive = true
}

output "workload_pool" {
  value = "${var.project_id}.svc.id.goog"
}
