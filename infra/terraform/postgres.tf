resource "random_password" "postgres_admin" {
  length  = 32
  special = false # keeps the password safe to embed in a connection URL
}

resource "azurerm_postgresql_flexible_server" "main" {
  name                = local.postgres_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  version             = var.postgres_version

  administrator_login    = "agentops"
  administrator_password = random_password.postgres_admin.result

  sku_name   = var.postgres_sku_name
  storage_mb = var.postgres_storage_mb

  backup_retention_days         = var.postgres_backup_retention_days
  geo_redundant_backup_enabled  = false
  public_network_access_enabled = true # see README: network trade-off

  tags = local.tags

  lifecycle {
    # Azure picks the availability zone; do not fight it on later plans.
    ignore_changes = [zone]
  }
}

resource "azurerm_postgresql_flexible_server_database" "main" {
  name      = local.postgres_db_name
  server_id = azurerm_postgresql_flexible_server.main.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

# 0.0.0.0 - 0.0.0.0 is Azure's special "allow Azure services" rule. It lets the
# Container Apps (whose outbound IPs are not fixed in a non-VNet environment)
# reach the server. TLS and the generated password still apply.
resource "azurerm_postgresql_flexible_server_firewall_rule" "azure_services" {
  name             = "allow-azure-services"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}
