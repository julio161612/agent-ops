resource "azurerm_container_app_environment" "main" {
  name                       = "cae-${local.name}"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  tags                       = local.tags
}

# --- Redis (internal container) ----------------------------------------------
# Only holds rate-limiting counters, which are cheap to lose, so it has no
# persistence. Reachable inside the environment as redis://<app name>:6379.

resource "azurerm_container_app" "redis" {
  name                         = local.redis_name
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"
  tags                         = local.tags

  ingress {
    external_enabled = false
    target_port      = 6379
    exposed_port     = 6379
    transport        = "tcp"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    # Redis is single-instance by design here: more replicas would each keep
    # their own counters and break the rate limiter.
    min_replicas = 1
    max_replicas = 1

    container {
      name   = "redis"
      image  = var.redis_image
      cpu    = var.redis_cpu
      memory = var.redis_memory
    }
  }
}

# --- Backend -----------------------------------------------------------------

resource "azurerm_container_app" "backend" {
  count = var.deploy_apps ? 1 : 0

  name                         = local.backend_name
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"
  tags                         = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.apps.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.apps.id
  }

  secret {
    name                = "database-url"
    key_vault_secret_id = azurerm_key_vault_secret.database_url.versionless_id
    identity            = azurerm_user_assigned_identity.apps.id
  }

  secret {
    name                = "jwt-secret-key"
    key_vault_secret_id = azurerm_key_vault_secret.jwt_secret_key.versionless_id
    identity            = azurerm_user_assigned_identity.apps.id
  }

  secret {
    name                = "anthropic-api-key"
    key_vault_secret_id = azurerm_key_vault_secret.anthropic_api_key.versionless_id
    identity            = azurerm_user_assigned_identity.apps.id
  }

  # Only the frontend (nginx) talks to the backend, over the environment's
  # internal network. allow_insecure_connections lets nginx use plain
  # http://<app name> instead of the internal HTTPS FQDN.
  ingress {
    external_enabled           = false
    target_port                = 8000
    transport                  = "auto"
    allow_insecure_connections = true

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = var.backend_min_replicas
    max_replicas = var.backend_max_replicas

    container {
      name   = "backend"
      image  = local.backend_image
      cpu    = var.backend_cpu
      memory = var.backend_memory

      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }
      # Migrations run in the dedicated job, never on app start.
      env {
        name  = "RUN_MIGRATIONS_ON_START"
        value = "false"
      }
      env {
        name  = "REDIS_URL"
        value = "redis://${azurerm_container_app.redis.name}:6379/0"
      }
      # JSON array, see backend/app/core/config.py. Add custom domains here.
      env {
        name  = "BACKEND_CORS_ORIGINS"
        value = jsonencode([local.frontend_url])
      }
      env {
        name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = azurerm_application_insights.main.connection_string
      }
      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }
      env {
        name        = "JWT_SECRET_KEY"
        secret_name = "jwt-secret-key"
      }
      env {
        name        = "ANTHROPIC_API_KEY"
        secret_name = "anthropic-api-key"
      }

      startup_probe {
        transport               = "HTTP"
        port                    = 8000
        path                    = "/health"
        interval_seconds        = 5
        failure_count_threshold = 24
      }

      liveness_probe {
        transport               = "HTTP"
        port                    = 8000
        path                    = "/health"
        interval_seconds        = 15
        failure_count_threshold = 5
      }
    }
  }

  depends_on = [
    azurerm_role_assignment.apps_key_vault,
    azurerm_role_assignment.apps_acr_pull,
  ]

  lifecycle {
    # The deploy workflow rolls new images out with `az containerapp update`.
    ignore_changes = [template[0].container[0].image]
  }
}

# --- Frontend (nginx + React build) ------------------------------------------

resource "azurerm_container_app" "frontend" {
  count = var.deploy_apps ? 1 : 0

  name                         = local.frontend_name
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"
  tags                         = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.apps.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.apps.id
  }

  ingress {
    external_enabled = true
    target_port      = 80
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = var.frontend_min_replicas
    max_replicas = var.frontend_max_replicas

    container {
      name   = "frontend"
      image  = local.frontend_image
      cpu    = var.frontend_cpu
      memory = var.frontend_memory

      # Rendered into nginx's config at start (frontend/nginx.conf.template).
      env {
        name  = "BACKEND_URL"
        value = "http://${local.backend_name}"
      }

      liveness_probe {
        transport = "HTTP"
        port      = 80
        path      = "/"
      }
    }
  }

  depends_on = [
    azurerm_role_assignment.apps_acr_pull,
    azurerm_container_app.backend,
  ]

  lifecycle {
    ignore_changes = [template[0].container[0].image]
  }
}

# --- Migrations job ----------------------------------------------------------
# Same image as the backend, started on demand (manual trigger) by the deploy
# workflow before the apps are updated: `az containerapp job start`.

resource "azurerm_container_app_job" "migrations" {
  count = var.deploy_apps ? 1 : 0

  name                         = local.migrations_name
  resource_group_name          = azurerm_resource_group.main.name
  location                     = azurerm_resource_group.main.location
  container_app_environment_id = azurerm_container_app_environment.main.id
  replica_timeout_in_seconds   = var.migration_job_timeout_seconds
  replica_retry_limit          = 1
  tags                         = local.tags

  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.apps.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.apps.id
  }

  secret {
    name                = "database-url"
    key_vault_secret_id = azurerm_key_vault_secret.database_url.versionless_id
    identity            = azurerm_user_assigned_identity.apps.id
  }

  template {
    container {
      name    = "migrate"
      image   = local.backend_image
      cpu     = 0.25
      memory  = "0.5Gi"
      command = ["alembic"]
      args    = ["upgrade", "head"]

      env {
        name  = "RUN_MIGRATIONS_ON_START"
        value = "false"
      }
      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }
    }
  }

  depends_on = [
    azurerm_role_assignment.apps_key_vault,
    azurerm_role_assignment.apps_acr_pull,
  ]

  lifecycle {
    ignore_changes = [template[0].container[0].image]
  }
}
