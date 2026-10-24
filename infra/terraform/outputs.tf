output "resource_group_name" {
  description = "Resource group holding everything."
  value       = azurerm_resource_group.main.name
}

output "acr_name" {
  description = "Container Registry name (az acr login --name <this>)."
  value       = azurerm_container_registry.main.name
}

output "acr_login_server" {
  description = "Registry host the images are pushed to."
  value       = azurerm_container_registry.main.login_server
}

output "frontend_url" {
  description = "Public URL of the admin panel / API gateway (nginx)."
  value       = local.frontend_url
}

output "backend_app_name" {
  description = "Backend Container App name (used by the deploy workflow)."
  value       = local.backend_name
}

output "frontend_app_name" {
  description = "Frontend Container App name (used by the deploy workflow)."
  value       = local.frontend_name
}

output "migrations_job_name" {
  description = "Migrations Container Apps Job name (az containerapp job start)."
  value       = local.migrations_name
}

output "container_app_environment_name" {
  description = "Container Apps Environment name."
  value       = azurerm_container_app_environment.main.name
}

output "key_vault_name" {
  description = "Key Vault holding the app secrets."
  value       = azurerm_key_vault.main.name
}

output "postgres_fqdn" {
  description = "PostgreSQL Flexible Server host name."
  value       = azurerm_postgresql_flexible_server.main.fqdn
}

output "managed_identity_client_id" {
  description = "Client ID of the apps' user-assigned identity."
  value       = azurerm_user_assigned_identity.apps.client_id
}

output "application_insights_connection_string" {
  description = "Application Insights connection string."
  value       = azurerm_application_insights.main.connection_string
  sensitive   = true
}

output "set_anthropic_key_command" {
  description = "Command to store the real Anthropic key (paste the key when prompted by your shell; never commit it)."
  value       = "az keyvault secret set --vault-name ${azurerm_key_vault.main.name} --name anthropic-api-key --value <ANTHROPIC_API_KEY>"
}
