locals {
  budget_start = formatdate("YYYY-MM-01'T'00:00:00'Z'", timestamp())
}

# Monthly budget on the resource group. Alerts only: Azure budgets never stop
# or delete anything by themselves.
resource "azurerm_consumption_budget_resource_group" "monthly" {
  count = length(var.budget_contact_emails) > 0 ? 1 : 0

  name              = "budget-${local.name}"
  resource_group_id = azurerm_resource_group.main.id
  amount            = var.budget_amount
  time_grain        = "Monthly"

  time_period {
    start_date = local.budget_start
  }

  notification {
    enabled        = true
    threshold      = 50
    threshold_type = "Actual"
    operator       = "GreaterThan"
    contact_emails = var.budget_contact_emails
  }

  notification {
    enabled        = true
    threshold      = 80
    threshold_type = "Actual"
    operator       = "GreaterThan"
    contact_emails = var.budget_contact_emails
  }

  notification {
    enabled        = true
    threshold      = 100
    threshold_type = "Forecasted"
    operator       = "GreaterThan"
    contact_emails = var.budget_contact_emails
  }

  lifecycle {
    # start_date is derived from timestamp(); keep the original month.
    ignore_changes = [time_period]
  }
}
