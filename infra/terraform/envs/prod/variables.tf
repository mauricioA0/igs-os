variable "project_id" {
  type    = string
  default = "mv-cloud-509914"
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "billing_account" {
  type = string
}

variable "alert_email" {
  type = string
}

variable "web_origins" {
  type    = list(string)
  default = []
}

variable "gke_authorized_networks" {
  type    = map(string)
  default = {}
}
