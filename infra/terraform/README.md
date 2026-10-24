# Terraform — Agent Ops en Azure

Define toda la infraestructura de Azure del proyecto. **Todavía no se ha
aplicado nunca**: solo se ha validado en local (`terraform fmt` y
`terraform validate`, que no contactan con Azure). Ver
[`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md) para el diagrama, el coste
estimado y las decisiones de diseño.

## Recursos

| Archivo | Recurso | Para qué |
|---|---|---|
| `main.tf` | Resource group `rg-<project>-<env>` | Contiene todo; el presupuesto se aplica sobre él. Sufijo aleatorio para los nombres globalmente únicos. |
| `registry_monitoring.tf` | Container Registry (Basic) | Guarda las imágenes `agentops-backend` y `agentops-frontend`. Sin usuario admin: se descarga con la identidad gestionada. |
| `registry_monitoring.tf` | Log Analytics + Application Insights | Los logs de los contenedores van al workspace; App Insights (basado en workspace) queda listo para trazas. |
| `postgres.tf` | PostgreSQL Flexible Server (Burstable B1ms, v16) + base `agentops` | Base de datos de la aplicación. Contraseña generada por Terraform. Regla de firewall "Azure services". |
| `identity_keyvault.tf` | Key Vault (RBAC) | Guarda `jwt-secret-key`, `database-url` y `anthropic-api-key`. |
| `identity_keyvault.tf` | Managed Identity + roles | `Key Vault Secrets User` y `AcrPull` para las apps y el job; `Key Vault Secrets Officer` para quien ejecuta Terraform. |
| `container_apps.tf` | Container Apps Environment | Red y entorno de ejecución compartido; envía logs a Log Analytics. |
| `container_apps.tf` | Container App `redis` | Redis 7 interno (ingress TCP interno, 1 réplica fija). Solo contadores de rate limiting. |
| `container_apps.tf` | Container App `backend` | FastAPI. Ingress interno; secretos desde Key Vault; `RUN_MIGRATIONS_ON_START=false`. |
| `container_apps.tf` | Container App `frontend` | nginx + React. Único punto de entrada público (HTTPS); hace proxy al backend con `BACKEND_URL`. |
| `container_apps.tf` | Container Apps Job `migrate` | Ejecuta `alembic upgrade head` bajo demanda (disparo manual). |
| `budget.tf` | Presupuesto mensual del resource group | Avisos al 50 % y 80 % reales y al 100 % previsto. Solo avisa, no apaga nada. Solo se crea si hay emails en `budget_contact_emails`. |

## Variables principales

Ver `variables.tf` (todas tienen descripción) y `terraform.tfvars.example`.
Las obligatorias son solo `subscription_id`. Tamaños y réplicas se ajustan con
`postgres_sku_name`, `backend_cpu`, `backend_memory`, `backend_min_replicas`,
`frontend_*`, `redis_*`, etc.

## Outputs

`terraform output` devuelve lo que necesita el workflow de despliegue
(`resource_group_name`, `acr_name`, `backend_app_name`, `frontend_app_name`,
`migrations_job_name`), la URL pública (`frontend_url`) y el comando para
guardar la clave de Anthropic (`set_anthropic_key_command`).

## Primer despliegue (cuando exista la cuenta de Azure)

Hay un huevo y la gallina: las Container Apps necesitan imágenes que aún no
existen en el registro vacío. Por eso `deploy_apps`:

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars    # rellena subscription_id, etc.
az login                                        # (tú, cuando tengas cuenta)
terraform init
terraform plan  -var deploy_apps=false
terraform apply -var deploy_apps=false          # RG, ACR, PG, Key Vault, Redis, entorno...

# Guarda la clave real (no pasa por el estado de Terraform):
az keyvault secret set --vault-name <key_vault_name> --name anthropic-api-key --value <clave>

# Sube las primeras imágenes (o ejecuta el workflow "Deploy to Azure" a medias):
az acr login --name <acr_name>
docker build -t <acr_login_server>/agentops-backend:latest  ./backend
docker build -t <acr_login_server>/agentops-frontend:latest ./frontend
docker push <acr_login_server>/agentops-backend:latest
docker push <acr_login_server>/agentops-frontend:latest

terraform apply                                 # crea backend, frontend y job
# Primera migración: az containerapp job start -n <migrations_job_name> -g <rg>
```

A partir de ahí, los despliegues los hace el workflow
`.github/workflows/deploy-azure.yml`. Terraform ignora el campo `image` de las
apps y del job para no revertir lo que despliega el workflow.

## Estado remoto

Por defecto el estado es local (`terraform.tfstate`, ignorado por git). El
estado contiene secretos (contraseña de Postgres, `JWT_SECRET_KEY`), así que
antes de compartir el entorno muévelo a un Storage Account con un bloque
`backend "azurerm"` en `versions.tf`.

## Limitaciones conocidas (no verificadas contra Azure)

- Nunca se ha hecho `plan` ni `apply`. `validate` comprueba la sintaxis y los
  tipos, no que Azure acepte cada combinación (nombres, cuotas, regiones, SKU).
- La cadena de conexión usa `?ssl=require` para asyncpg; hay que confirmarlo en
  el primer despliegue con el job de migraciones.
- PostgreSQL es accesible por red pública (con TLS, contraseña aleatoria y la
  regla "Azure services"). Para endurecerlo: VNet en el entorno + subred
  delegada + Private DNS (más complejo y algo más caro).
- Redis sin persistencia ni contraseña: es interno al entorno y solo guarda
  contadores. No uses este Redis para nada que no puedas perder.
- `APPLICATIONINSIGHTS_CONNECTION_STRING` se inyecta, pero la aplicación aún no
  usa el SDK de Application Insights.
