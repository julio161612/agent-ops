resource "azurerm_user_assigned_identity" "apps" {
  name                = "id-${local.name}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = local.tags
}

resource "azurerm_key_vault" "main" {
  name                = local.key_vault_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"

  rbac_authorization_enabled = true
  purge_protection_enabled   = var.key_vault_purge_protection
  soft_delete_retention_days = 7

  tags = local.tags
}

# The identity the apps and the job run as: read secrets, pull images.
resource "azurerm_role_assignment" "apps_key_vault" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.apps.principal_id
}

resource "azurerm_role_assignment" "apps_acr_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.apps.principal_id
}

# Whoever runs terraform apply must be able to write the secrets below.
resource "azurerm_role_assignment" "deployer_key_vault" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "random_password" "jwt_secret" {
  length  = 64
  special = false
}

resource "azurerm_key_vault_secret" "jwt_secret_key" {
  name         = "jwt-secret-key"
  value        = random_password.jwt_secret.result
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.deployer_key_vault]
}

resource "azurerm_key_vault_secret" "database_url" {
  name = "database-url"
  # asyncpg takes ssl=require; Azure PostgreSQL enforces TLS.
  value = format(
    "postgresql+asyncpg://%s:%s@%s:5432/%s?ssl=require",
    azurerm_postgresql_flexible_server.main.administrator_login,
    random_password.postgres_admin.result,
    azurerm_postgresql_flexible_server.main.fqdn,
    azurerm_postgresql_flexible_server_database.main.name,
  )
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.deployer_key_vault]
}

resource "azurerm_key_vault_secret" "anthropic_api_key" {
  name         = "anthropic-api-key"
  value        = coalesce(var.anthropic_api_key, "REPLACE-ME-with-az-keyvault-secret-set")
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.deployer_key_vault]

  lifecycle {
    # The real key is normally set out-of-band so it never enters Terraform state.
    ignore_changes = [value]
  }
}
