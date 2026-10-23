# Monthly budget with e-mail alerts at 50/90/100% (actual) and 100% (forecast).

variable "project_id" {
  type = string
}

variable "project_number" {
  type = string
}

variable "billing_account" {
  type = string
}

variable "amount_usd" {
  type = number
}

variable "alert_email" {
  type = string
}

variable "display_name" {
  type = string
}

resource "google_monitoring_notification_channel" "email" {
  project      = var.project_id
  display_name = "${var.display_name} budget"
  type         = "email"
  labels = {
    email_address = var.alert_email
  }
}

resource "google_billing_budget" "this" {
  billing_account = var.billing_account
  display_name    = var.display_name

  budget_filter {
    projects = ["projects/${var.project_number}"]
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.amount_usd)
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }

  threshold_rules {
    threshold_percent = 0.9
  }

  threshold_rules {
    threshold_percent = 1.0
  }

  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "FORECASTED_SPEND"
  }

  all_updates_rule {
    monitoring_notification_channels = [google_monitoring_notification_channel.email.id]
    disable_default_iam_recipients   = false
  }
}
