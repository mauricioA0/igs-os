# Cloud SQL for PostgreSQL on private IP only, IAM database authentication on.
# Demo: one shared zonal db-g1-small hosts `igs`, `temporal` and `temporal_visibility`.
# Prod: called twice (app + Temporal), regional HA, PITR.

variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "name" {
  type = string
}

variable "network_id" {
  type = string
}

variable "private_services_connection" {
  type        = string
  description = "Only used to order creation after the VPC peering exists."
}

variable "tier" {
  type = string
}

variable "edition" {
  type    = string
  default = "ENTERPRISE"
}

variable "high_availability" {
  type    = bool
  default = false
}

variable "disk_size_gb" {
  type    = number
  default = 20
}

variable "databases" {
  type = list(string)
}

variable "iam_service_accounts" {
  type        = list(string)
  description = "Service account emails that log in with IAM auth (no passwords)."
  default     = []
}

variable "builtin_users" {
  type        = map(string)
  description = "user -> password (Temporal's SQL plugin needs a password user)."
  default     = {}
  sensitive   = true
}

variable "point_in_time_recovery" {
  type    = bool
  default = false
}

variable "deletion_protection" {
  type    = bool
  default = true
}

variable "max_connections" {
  type    = number
  default = 100
}

resource "google_sql_database_instance" "this" {
  project             = var.project_id
  name                = var.name
  region              = var.region
  database_version    = "POSTGRES_17"
  deletion_protection = var.deletion_protection

  settings {
    tier                        = var.tier
    edition                     = var.edition
    availability_type           = var.high_availability ? "REGIONAL" : "ZONAL"
    disk_type                   = "PD_SSD"
    disk_size                   = var.disk_size_gb
    disk_autoresize             = true
    deletion_protection_enabled = var.deletion_protection

    ip_configuration {
      ipv4_enabled                                  = false
      private_network                               = var.network_id
      enable_private_path_for_google_cloud_services = true
      ssl_mode                                      = "ENCRYPTED_ONLY"
    }

    backup_configuration {
      enabled                        = true
      start_time                     = "06:00" # 03:00 Buenos Aires
      point_in_time_recovery_enabled = var.point_in_time_recovery
      backup_retention_settings {
        retained_backups = var.point_in_time_recovery ? 14 : 7
      }
    }

    maintenance_window {
      day          = 7
      hour         = 7
      update_track = "stable"
    }

    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on"
    }

    database_flags {
      name  = "max_connections"
      value = tostring(var.max_connections)
    }

    insights_config {
      query_insights_enabled  = true
      record_application_tags = true
      record_client_address   = false
    }

    user_labels = {
      app = "igs-os"
    }
  }

  lifecycle {
    precondition {
      condition     = var.private_services_connection != ""
      error_message = "Cloud SQL needs the private services connection (network module)."
    }
  }
}

resource "google_sql_database" "this" {
  for_each = toset(var.databases)
  project  = var.project_id
  instance = google_sql_database_instance.this.name
  name     = each.value
}

# IAM database users: Postgres user name is the SA email without ".gserviceaccount.com".
resource "google_sql_user" "iam" {
  for_each = toset(var.iam_service_accounts)
  project  = var.project_id
  instance = google_sql_database_instance.this.name
  name     = trimsuffix(each.value, ".gserviceaccount.com")
  type     = "CLOUD_IAM_SERVICE_ACCOUNT"
}

resource "google_sql_user" "builtin" {
  for_each = nonsensitive(toset(keys(var.builtin_users)))
  project  = var.project_id
  instance = google_sql_database_instance.this.name
  name     = each.value
  password = var.builtin_users[each.value]
  type     = "BUILT_IN"
}

output "connection_name" {
  value = google_sql_database_instance.this.connection_name
}

output "private_ip" {
  value = google_sql_database_instance.this.private_ip_address
}

output "instance_name" {
  value = google_sql_database_instance.this.name
}
