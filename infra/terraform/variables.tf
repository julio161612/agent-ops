variable "subscription_id" {
  description = "Azure subscription ID. TODO: fill in once the Azure account exists."
  type        = string
}

variable "project" {
  description = "Short project name, used as a prefix for every resource."
  type        = string
  default     = "agentops"

  validation {
    condition     = can(regex("^[a-z0-9]{3,12}$", var.project))
    error_message = "project must be 3-12 lowercase letters/digits (it is part of globally unique names)."
  }
}

variable "environment" {
  description = "Environment name (dev, staging, prod)."
  type        = string
  default     = "dev"

  validation {
    condition     = can(regex("^[a-z0-9]{2,8}$", var.environment))
    error_message = "environment must be 2-8 lowercase letters/digits."
  }
}

variable "location" {
  description = "Azure region for every resource."
  type        = string
  default     = "westeurope"
}

variable "tags" {
  description = "Extra tags added to every resource."
  type        = map(string)
  default     = {}
}

# --- Container Registry ------------------------------------------------------

variable "acr_sku" {
  description = "Container Registry SKU (Basic, Standard, Premium)."
  type        = string
  default     = "Basic"
}

# --- Observability -----------------------------------------------------------

variable "log_retention_days" {
  description = "Log Analytics retention in days."
  type        = number
  default     = 30
}

# --- PostgreSQL --------------------------------------------------------------

variable "postgres_sku_name" {
  description = "PostgreSQL Flexible Server SKU. B_Standard_B1ms = Burstable, 1 vCPU, 2 GiB."
  type        = string
  default     = "B_Standard_B1ms"
}

variable "postgres_storage_mb" {
  description = "PostgreSQL storage in MB (32768 = 32 GiB, the minimum)."
  type        = number
  default     = 32768
}

variable "postgres_version" {
  description = "PostgreSQL major version (the local docker-compose uses 16)."
  type        = string
  default     = "16"
}

variable "postgres_backup_retention_days" {
  description = "Automated backup retention (7-35 days)."
  type        = number
  default     = 7
}

# --- Container Apps ----------------------------------------------------------

variable "deploy_apps" {
  description = "Create the Container Apps and the migrations job. Set to false on the very first apply: the images do not exist in the still-empty registry yet (see README, First deployment)."
  type        = bool
  default     = true
}

variable "image_tag" {
  description = "Image tag the apps are created with. The deploy workflow later moves them to the commit SHA; Terraform ignores that drift."
  type        = string
  default     = "latest"
}

variable "backend_cpu" {
  description = "vCPU for the backend container."
  type        = number
  default     = 0.5
}

variable "backend_memory" {
  description = "Memory for the backend container (must pair with the CPU, e.g. 0.5 vCPU -> 1Gi)."
  type        = string
  default     = "1Gi"
}

variable "backend_min_replicas" {
  description = "Minimum backend replicas. 1 avoids cold starts; 0 saves money but the first request after idle is slow."
  type        = number
  default     = 1
}

variable "backend_max_replicas" {
  description = "Maximum backend replicas."
  type        = number
  default     = 3
}

variable "frontend_cpu" {
  description = "vCPU for the frontend (nginx) container."
  type        = number
  default     = 0.25
}

variable "frontend_memory" {
  description = "Memory for the frontend container."
  type        = string
  default     = "0.5Gi"
}

variable "frontend_min_replicas" {
  description = "Minimum frontend replicas."
  type        = number
  default     = 1
}

variable "frontend_max_replicas" {
  description = "Maximum frontend replicas."
  type        = number
  default     = 2
}

variable "redis_image" {
  description = "Image for the internal Redis container app."
  type        = string
  default     = "docker.io/library/redis:7-alpine"
}

variable "redis_cpu" {
  description = "vCPU for Redis."
  type        = number
  default     = 0.25
}

variable "redis_memory" {
  description = "Memory for Redis."
  type        = string
  default     = "0.5Gi"
}

variable "migration_job_timeout_seconds" {
  description = "Max run time of the migrations job."
  type        = number
  default     = 600
}

# --- Secrets -----------------------------------------------------------------

variable "anthropic_api_key" {
  description = "Anthropic API key. Optional: leave null to create a placeholder secret and set the real value later with az keyvault secret set (Terraform then ignores the value). Sensitive, but it still lands in Terraform state if set here."
  type        = string
  default     = null
  sensitive   = true
}

variable "key_vault_purge_protection" {
  description = "Enable Key Vault purge protection (recommended for prod; the vault name stays reserved for 90 days after deletion)."
  type        = bool
  default     = false
}

# --- Budget ------------------------------------------------------------------

variable "budget_amount" {
  description = "Monthly budget for the resource group, in the subscription's billing currency."
  type        = number
  default     = 80
}

variable "budget_contact_emails" {
  description = "Who gets budget alerts. TODO: fill in; the budget is not created while this list is empty."
  type        = list(string)
  default     = []
}
