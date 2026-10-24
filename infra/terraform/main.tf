data "azurerm_client_config" "current" {}

resource "random_string" "suffix" {
  length  = 5
  upper   = false
  special = false
  numeric = true
}

locals {
  name   = "${var.project}-${var.environment}"
  suffix = random_string.suffix.result

  # Names that must be globally unique (or alphanumeric only) get the suffix.
  acr_name         = "${var.project}${var.environment}${local.suffix}"
  key_vault_name   = "${var.project}-${var.environment}-${local.suffix}"
  postgres_name    = "${local.name}-pg-${local.suffix}"
  backend_name     = "${local.name}-backend"
  frontend_name    = "${local.name}-frontend"
  redis_name       = "${local.name}-redis"
  migrations_name  = "${local.name}-migrate"
  postgres_db_name = "agentops"

  tags = merge(
    {
      project     = var.project
      environment = var.environment
      managed_by  = "terraform"
    },
    var.tags,
  )

  backend_image  = "${azurerm_container_registry.main.login_server}/agentops-backend:${var.image_tag}"
  frontend_image = "${azurerm_container_registry.main.login_server}/agentops-frontend:${var.image_tag}"

  # The frontend's public URL is derivable without referencing the frontend
  # app itself (that would be a cycle: backend CORS -> frontend -> backend).
  frontend_url = "https://${local.frontend_name}.${azurerm_container_app_environment.main.default_domain}"
}

resource "azurerm_resource_group" "main" {
  name     = "rg-${local.name}"
  location = var.location
  tags     = local.tags
}
