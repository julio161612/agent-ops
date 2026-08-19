# Agent Ops — Backend

API en FastAPI (Python 3.12, async) que implementa toda la plataforma:
multi-tenancy y autenticación, el motor de agentes de IA que ejecuta agentes
configurables por tenant contra la API de Anthropic, el orquestador de
routing que decide automáticamente qué agente atiende cada mensaje, los
guardrails + límites por tenant que validan cada mensaje antes y después de
llamar al agente, la cola de escalado a humano que recoge las conversaciones
que ningún agente pudo resolver, el framework de evaluación (ver
[`eval/README.md`](eval/README.md)) que mide con un dataset dorado y un
LLM-as-judge si el sistema completo funciona bien de verdad, observabilidad
(trazas y métricas), roles y configuración low-code, integraciones externas
(API pública, widget embebible, Slack), y facturación/planes de suscripción.
Consulta el [README raíz](../README.md) para la visión de producto completa,
el diagrama de arquitectura y cómo se relaciona con el
[frontend](../frontend/README.md).

## Stack

- **FastAPI** + **Uvicorn**
- **SQLAlchemy 2.0 (async)** + **asyncpg** sobre **PostgreSQL**
- **Alembic** para migraciones
- **Redis** (rate limiting por sliding window)
- **JWT** (access + refresh) con **passlib/bcrypt** para contraseñas
- **anthropic** (SDK oficial) para ejecutar agentes de verdad
- **pytest** + **httpx** para tests
- **ruff** + **black** para calidad de código

## Arrancar en local con Docker (recomendado)

Desde la raíz del monorepo:

```bash
docker compose up --build
```

Esto levanta PostgreSQL, Redis, el backend y el frontend (ver
[README raíz](../README.md)), aplica las migraciones de Alembic
automáticamente y expone la API en `http://localhost:8000` (docs interactivas en
`http://localhost:8000/docs`). Si solo quieres el backend con hot-reload para
desarrollar sobre él, usa `docker compose up -d postgres redis` y sigue con la
sección de abajo.

## Arrancar sin Docker

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # ajusta si tu Postgres/Redis local usan otra config
alembic upgrade head
uvicorn app.main:app --reload
```

Necesitas un PostgreSQL y un Redis accesibles con las credenciales de `.env`
(puedes levantar solo esas dos dependencias con `docker compose up postgres redis`).

Para que el motor de agentes funcione de verdad (no solo el CRUD), añade tu
`ANTHROPIC_API_KEY` en `.env` — consíguela en
[console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys).
Sin ella, `/agents` funciona con normalidad pero cualquier llamada a
`POST /conversations/{id}/messages` fallará al intentar autenticarse contra la
API de Anthropic.

## Motor de agentes: prueba manual con una llamada real

Con el backend arriba y `ANTHROPIC_API_KEY` configurada, el flujo completo es:
registrarte → obtener un token → crear un agente → mandarle un mensaje.

```bash
# 1. Registro (crea tenant + usuario admin) y guarda el access_token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"company_name":"Acme Corp","email":"admin@acme.com","password":"supersecret123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 2. Crea un agente de soporte
AGENT_ID=$(curl -s -X POST http://localhost:8000/api/v1/agents \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{
        "name": "Agente de Soporte",
        "agent_type": "soporte",
        "system_prompt": "Eres un agente de soporte de Acme Corp, responde breve y en español.",
        "model": "claude-sonnet-4-6",
        "parameters": {"temperature": 0.7, "max_tokens": 300}
      }' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# 3. Manda un mensaje — conversation_id lo genera el cliente (UUID nuevo = conversación nueva)
CONVERSATION_ID=$(python3 -c "import uuid; print(uuid.uuid4())")
curl -s -X POST "http://localhost:8000/api/v1/conversations/$CONVERSATION_ID/messages" \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d "{\"content\": \"Hola, ¿cuál es el horario de atención?\", \"agent_id\": \"$AGENT_ID\"}"

# 4. Sigue la conversación (mismo conversation_id, ya no hace falta agent_id)
curl -s -X POST "http://localhost:8000/api/v1/conversations/$CONVERSATION_ID/messages" \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"content": "¿Y los fines de semana?"}'

# 5. Recupera el historial completo
curl -s "http://localhost:8000/api/v1/conversations/$CONVERSATION_ID/messages" \
  -H "Authorization: Bearer $TOKEN"
```

La respuesta de `POST /conversations/{id}/messages` incluye el mensaje del
usuario y la respuesta del asistente, con metadata real de la llamada
(`model`, `input_tokens`, `output_tokens`, `latency_ms`, `stop_reason`):

```json
{
  "conversation_id": "...",
  "user_message": { "role": "user", "content": "Hola, ...", "metadata": {}, ... },
  "assistant_message": {
    "role": "assistant",
    "content": "¡Hola! Nuestro horario es...",
    "metadata": {
      "model": "claude-sonnet-4-6",
      "input_tokens": 34,
      "output_tokens": 22,
      "latency_ms": 812,
      "stop_reason": "end_turn"
    }
  }
}
```

Con equivalente en **httpie**, el paso 3 sería:

```bash
http POST localhost:8000/api/v1/conversations/$CONVERSATION_ID/messages \
  "Authorization:Bearer $TOKEN" content="Hola" agent_id="$AGENT_ID"
```

## Orquestador de routing: mensajes sin `agent_id`

Desde la Fase 3, `agent_id` en `POST /conversations/{id}/messages` es **opcional**.
Si se omite y la conversación todavía no tiene agente asignado, `RoutingService`
decide automáticamente en dos niveles:

1. **Reglas** (`routing_rules`, sin llamar a ningún LLM — rápido y gratis):
   - `keyword`: matchea si el mensaje contiene alguna de las palabras/frases de
     `condition.keywords` (subcadena, sin distinguir mayúsculas).
   - `category`: matchea sin mirar el contenido del mensaje — actúa como agente
     por defecto para `condition.agent_type`, mientras el agente destino siga
     activo y siga teniendo ese `agent_type`. Útil como regla de prioridad baja
     ("si nada más específico matcheó, manda esto al agente general").
   - Si varias reglas matchean, gana la de mayor `priority` (empate → la más antigua).
2. **Router por LLM** (fallback, solo si ninguna regla matcheó): Claude recibe la
   lista de agentes activos del tenant (nombre, `agent_type`, descripción) y el
   mensaje, y elige uno mediante una *tool call* forzada (JSON estricto por
   diseño, no texto libre a parsear). Si la `confidence` devuelta es menor que
   `ROUTING_CONFIDENCE_THRESHOLD` (por defecto `0.5`), o el JSON viene
   incompleto/inválido, o no hay agentes activos en el tenant, el resultado es
   "sin agente asignado" — la conversación queda en estado `unassigned` (lista
   para escalarse a un humano en la Fase 5) y el endpoint responde **200** igualmente,
   con `assistant_message: null` y el detalle en `routing`.

Cada decisión de routing (regla o LLM, agente elegido, confianza, razonamiento)
se persiste en `routing_decisions` para observabilidad futura, y se devuelve en
el campo `routing` de la respuesta — solo en el turno en el que realmente se
ejecutó el routing (los turnos siguientes de una conversación ya asignada no
vuelven a rutear).

### Crear una regla de routing

```bash
curl -s -X POST http://localhost:8000/api/v1/routing-rules \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d "{
        \"agent_id\": \"$AGENT_ID\",
        \"rule_type\": \"keyword\",
        \"condition\": {\"keywords\": [\"horario\", \"apertura\"]},
        \"priority\": 10
      }"
```

### Probar el flujo completo sin especificar `agent_id`

```bash
# Matchea la regla de keyword de arriba -> routing.method == "rule"
curl -s -X POST "http://localhost:8000/api/v1/conversations/$(python3 -c 'import uuid;print(uuid.uuid4())')/messages" \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"content": "¿Cuál es vuestro horario?"}'

# No matchea ninguna regla -> cae al router por LLM, que elige entre los
# agentes activos del tenant por su nombre/descripción/agent_type
curl -s -X POST "http://localhost:8000/api/v1/conversations/$(python3 -c 'import uuid;print(uuid.uuid4())')/messages" \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"content": "Se me ha caducado la leche que compré, ¿qué hago?"}'
```

La respuesta trae siempre `conversation_status` (`open` si se asignó agente,
`unassigned` si no) y, cuando el routing corrió en ese turno, el campo `routing`:

```json
{
  "conversation_id": "...",
  "conversation_status": "open",
  "user_message": { "...": "..." },
  "assistant_message": { "...": "..." },
  "routing": {
    "method": "rule",
    "agent_id": "...",
    "matched_rule_id": "...",
    "confidence": null,
    "reasoning": null
  }
}
```

## Guardrails: validar mensajes antes y después del agente

Desde la Fase 4, cada mensaje pasa por un pipeline completo antes de llegar al
usuario:

```
rate limit + coste mensual  →  guardrails INPUT  →  routing  →  agente  →  registro de coste  →  guardrails OUTPUT  →  respuesta
```

### Políticas de guardrail (`guardrail_policies`)

Cada política tiene un `guardrail_type` (`input` o `output`), un `rule_type`, y
una `config` cuya forma depende del `rule_type`:

| `rule_type`           | `config`                                              | Qué hace |
|------------------------|--------------------------------------------------------|----------|
| `blocklist_keywords`   | `{"keywords": ["palabra1", "palabra2"]}`               | Busca coincidencia simple (subcadena, sin mayúsculas) |
| `pii_detection`        | `{"patterns": ["email", "credit_card", "phone", "spanish_dni"]}` (opcional; si se omite, comprueba las 4) | Regex básicas — detección, no un escáner de PII de nivel producción |
| `max_length`           | `{"max_characters": 2000}`                             | Límite de caracteres (no tokens — ver nota más abajo) |
| `custom_llm_check`     | `{"instruction": "no debe prometer reembolsos...", "model": "claude-haiku-4-5-20251001"}` (`model` opcional) | Claude evalúa la instrucción en lenguaje natural vía *tool use* forzado |

`agent_id` es opcional: si se omite, la política aplica a **todos** los agentes
del tenant; si se especifica, solo a ese agente. `action_on_violation` es
`"block"` (detiene la ejecución) o `"flag"` (se registra pero continúa).

```bash
# Bloquea cualquier mensaje de entrada que contenga estas palabras
curl -s -X POST http://localhost:8000/api/v1/guardrail-policies \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{
        "guardrail_type": "input",
        "rule_type": "blocklist_keywords",
        "config": {"keywords": ["idiota", "estúpido"]},
        "action_on_violation": "block"
      }'

# Detecta (sin bloquear) posible PII en la entrada — útil para auditar sin frenar el chat
curl -s -X POST http://localhost:8000/api/v1/guardrail-policies \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"guardrail_type": "input", "rule_type": "pii_detection", "config": {}, "action_on_violation": "flag"}'

# Un agente no puede prometer reembolsos — evaluado por Claude en la salida
curl -s -X POST http://localhost:8000/api/v1/guardrail-policies \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d "{
        \"agent_id\": \"$AGENT_ID\",
        \"guardrail_type\": \"output\",
        \"rule_type\": \"custom_llm_check\",
        \"config\": {\"instruction\": \"No debe prometer reembolsos que la empresa no puede garantizar\"},
        \"action_on_violation\": \"block\"
      }"
```

### Qué pasa cuando algo se bloquea

- **Bloqueo en INPUT**: el agente nunca se ejecuta (ni el routing corre). La
  respuesta sigue siendo **200**, con `assistant_message` sustituido por un
  texto genérico (`message.metadata.guardrail_blocked: true`) y el detalle en
  `guardrail_violations`.
- **Bloqueo en OUTPUT**: la respuesta real del agente **nunca llega al
  usuario** — ni en la respuesta del endpoint ni en el historial (`GET
  .../messages`) — se sustituye por un mensaje genérico, y
  `conversation_status` pasa a `"escalated"` (el estado que dejamos preparado
  en fases anteriores para el handoff a humano de la Fase 5).
- **`custom_llm_check` que falla o no responde en JSON válido**: se trata como
  *fail-open* — nunca bloquea por una comprobación inconclusa (evita que una
  caída de este chequeo secundario tumbe todo el tráfico), pero **sí** queda
  registrada como violación con `action_taken: "flag"` para que quede auditada.
- Cada violación (bloqueada o solo marcada) se guarda en `guardrail_violations`,
  consultable vía `GET /guardrail-violations?conversation_id=...`. El campo
  `detail` de una violación de `pii_detection` **nunca** contiene el dato
  detectado en sí (solo qué tipo de patrón saltó) — evita duplicar PII en el
  propio log de auditoría.

Nota de diseño: los guardrails de INPUT se ejecutan **antes** del routing, tal
y como se pidió. Esto significa que en el primer mensaje de una conversación
nueva que todavía no tiene agente asignado, solo aplican las políticas
tenant-wide (`agent_id: null`) — las políticas específicas de un agente no
pueden evaluarse hasta que se sepa qué agente la atenderá.

## Límites por tenant: rate limiting y coste mensual

Cada tenant tiene una fila en `tenant_limits` (creada automáticamente al
registrarse) con `messages_per_minute_limit` (por defecto 60) y
`monthly_cost_limit_usd` (por defecto sin límite). Se consultan/editan vía:

> Desde la Fase 10, estos valores son un **tope propio dentro de lo que el
> plan de suscripción del tenant permite** — nunca por encima. El límite que
> realmente se aplica es el más estricto de los dos (`min(tenant_limits,
> plan)`), calculado al vuelo en cada petición. Ver la sección
> "Facturación y planes de suscripción" más abajo para el modelo completo.

```bash
curl -s http://localhost:8000/api/v1/tenant-limits -H "Authorization: Bearer $TOKEN"

curl -s -X PATCH http://localhost:8000/api/v1/tenant-limits \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"messages_per_minute_limit": 30, "monthly_cost_limit_usd": 50.0}'
```

- **Rate limiting**: *sliding window log* en Redis (un `ZSET` por tenant con
  las marcas de tiempo de los últimos 60s). Se eligió sobre una ventana fija
  (que permite hasta 2x el límite en una ráfaga a caballo entre dos ventanas)
  y sobre un token bucket (mejor cuando quieres permitir ráfagas controladas
  con recarga continua — no es el caso de un simple "N mensajes por minuto";
  además su lógica de recarga continua es más difícil de testear con
  precisión que un conteo exacto por ventana). Al superarse, `POST
  /conversations/{id}/messages` responde **429**.
- **Coste mensual**: cada llamada real a Anthropic (ejecución del agente, el
  router por LLM, y `custom_llm_check`) calcula su coste real en USD a partir
  de `input_tokens`/`output_tokens` y el precio del modelo usado
  (`app/core/pricing.py`), y lo acumula en `tenant_limits.current_month_cost_usd`
  — en base de datos, no en Redis, para que el gasto acumulado sobreviva a un
  reinicio de Redis (perderlo silenciosamente dejaría a un tenant gastar de
  más sin que nadie se entere). El contador se resetea solo al detectar que
  ha cambiado el mes (sin cron). Si ya se superó el límite, cualquier mensaje
  nuevo responde **429** antes de tocar la base de datos de conversación
  siquiera.

## Escalado a humano

Cuando una conversación queda `unassigned` (el routing de la Fase 3 no
encontró un agente con suficiente confianza) o `escalated` (un guardrail de
salida bloqueó la respuesta del agente, Fase 4), el pipeline crea
automáticamente un `EscalationCase` en estado `pending` — como mucho uno
abierto por conversación a la vez, aunque la misma conversación siga
generando eventos de escalado en mensajes sucesivos. Cada caso creado dispara
`notify_escalation()` (`app/services/notification_service.py`), de momento un
log estructurado — el punto de extensión para Slack/email/PagerDuty más
adelante, sin tocar el resto del pipeline cuando llegue esa integración real.

### Flujo: cola → claim → respond → resolve

```bash
# 1. Ver la cola de casos pendientes
curl -s "http://localhost:8000/api/v1/escalations?status=pending" \
  -H "Authorization: Bearer $TOKEN"

# 2. Tomar un caso (falla con 409 si otro compañero ya lo tomó)
CASE_ID="..."  # de la respuesta anterior
curl -s -X POST "http://localhost:8000/api/v1/escalations/$CASE_ID/claim" \
  -H "Authorization: Bearer $TOKEN"

# 3. Responder — se guarda como Message (role=assistant) en la conversación,
#    con metadata.author="human" para diferenciarlo de una respuesta del agente
curl -s -X POST "http://localhost:8000/api/v1/escalations/$CASE_ID/respond" \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"content": "Hola, soy Marta del equipo de soporte, ¡encantada de ayudarte!"}'

# 4. Resolver, con notas opcionales — reabre la conversación (vuelve a "open")
curl -s -X POST "http://localhost:8000/api/v1/escalations/$CASE_ID/resolve" \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"notes": "Resuelto manualmente, no había agente de esa categoría."}'

# Liberar un caso tomado por error, sin resolverlo
curl -s -X POST "http://localhost:8000/api/v1/escalations/$CASE_ID/release" \
  -H "Authorization: Bearer $TOKEN"
```

### Decisiones de este flujo

- **`claim` es atómico a nivel de base de datos**: usa un único `UPDATE ...
  WHERE status = 'pending'` en vez de "leer y luego escribir". Bajo dos
  intentos de tomar el mismo caso a la vez, Postgres serializa ambos UPDATE a
  nivel de fila — solo el primero en confirmar realmente cambia la fila, el
  segundo no matchea el `WHERE` y recibe **409**. Es la forma correcta de
  evitar que dos personas trabajen el mismo caso, no una comprobación a nivel
  de aplicación (que sí tendría una ventana de carrera real).
- **Solo quien tomó el caso puede responder** (`403` en caso contrario) —
  `release` sí lo puede hacer cualquier usuario del tenant, pensado para
  cuando alguien lo tomó por error y otro compañero necesita liberarlo.
- **`resolve` reabre la conversación** (pasa a `open`) independientemente de si
  llegó por routing sin agente o por un guardrail bloqueado — no toca
  `agent_id`, así que si la conversación nunca tuvo agente asignado, el
  siguiente mensaje volverá a intentar el routing normalmente.
- **`MANUAL` como motivo de escalado** ya está en el enum (`EscalationReason`)
  pero sin ningún disparador todavía — queda preparado para cuando un agente
  pueda pedir ayuda explícitamente en una fase futura.

## Observabilidad: trazas y métricas

Cada llamada a `POST /conversations/{id}/messages` genera exactamente una fila
en `interaction_traces` — la traza unificada de ese turno, con el resultado
final, el coste real, los tokens y la latencia desglosada por etapa
(`rate_limit_check`, `input_guardrails`, `routing`, `agent_execution`,
`output_guardrails`, en milisegundos, siempre las 5 claves presentes aunque
alguna etapa no se haya ejecutado — vale 0). `SendMessageResponse` ahora
incluye `trace_id` para poder ir directo al detalle.

### `GET /traces` — listado con filtros

```bash
curl -s "http://localhost:8000/api/v1/traces?outcome=completed&limit=20" \
  -H "Authorization: Bearer $TOKEN"
```

Filtros disponibles (todos opcionales, combinables): `conversation_id`,
`outcome` (`completed` / `blocked` / `escalated` / `unassigned`), `date_from`,
`date_to` (ISO 8601), y paginación con `limit` (máx. 200, por defecto 50) y
`offset`. La respuesta es `{"items": [...], "total": N, "limit": ..., "offset": ...}`.

### `GET /traces/{id}` — detalle completo

```bash
curl -s "http://localhost:8000/api/v1/traces/$TRACE_ID" \
  -H "Authorization: Bearer $TOKEN"
```

Además de los campos planos de la traza, incluye:
- `guardrail_violations`: todas las violaciones (bloqueo o solo aviso) de ese
  turno, tanto de entrada como de salida.
- `routing_decision`: el objeto completo de `RoutingDecision` si esa traza
  pasó por routing (`null` si la conversación ya tenía agente asignado).
- `escalation_case`: el caso de escalado asociado, si el resultado fue
  `escalated` o `unassigned`.

### `GET /metrics/summary` — métricas agregadas

```bash
# Por defecto, últimos 7 días
curl -s "http://localhost:8000/api/v1/metrics/summary" \
  -H "Authorization: Bearer $TOKEN"

# Rango explícito
curl -s "http://localhost:8000/api/v1/metrics/summary?date_from=2026-08-01T00:00:00Z&date_to=2026-08-16T00:00:00Z" \
  -H "Authorization: Bearer $TOKEN"
```

Campos de la respuesta:
- `total_interactions`, y el desglose `completed` / `blocked` / `escalated` /
  `unassigned`.
- `auto_resolution_rate`: fracción de interacciones que terminaron en
  `completed` sin intervención humana. `escalation_rate`: fracción que
  terminó en `escalated` (bloqueada por un guardrail de salida — no incluye
  `unassigned`, que es un fallo de routing, no un escalado por contenido).
- `total_cost_usd`: coste real sumado de todas las interacciones del rango
  (incluye la llamada del agente, la del router LLM cuando se usó, y
  cualquier `custom_llm_check` de guardrails — no solo el mensaje final).
- `latency_ms_avg` / `latency_ms_p95`: latencia total del turno completo
  (todas las etapas sumadas), media y percentil 95, calculadas en Postgres con
  `percentile_cont`.
- `agent_usage`: lista de `{agent_id, agent_name, interaction_count,
  cost_usd}` por agente, ordenada de más a menos usado. Un `agent_id: null`
  agrupa las interacciones que nunca llegaron a tener agente asignado (p. ej.
  bloqueadas por un guardrail de entrada, antes de que corra el routing).
- `guardrail_violations_by_type`: conteo de violaciones en el rango,
  agrupadas por `violation_type` (independientemente de si bloquearon o solo
  avisaron).

### `GET /metrics/timeseries` — la misma información por bucket temporal

```bash
curl -s "http://localhost:8000/api/v1/metrics/timeseries?granularity=day" \
  -H "Authorization: Bearer $TOKEN"
```

Mismo rango de fechas configurable que `/summary` (por defecto 7 días).
`granularity` es `day` (por defecto) u `hour`. Cada bucket trae
`bucket_start`, el desglose por resultado, `total_cost_usd` y
`latency_ms_avg` — pensado para alimentar directamente un gráfico de líneas o
barras apiladas por resultado.

### Decisiones técnicas

- **Tabla real (`interaction_traces`), no una vista sobre las tablas
  existentes.** Dos de los campos pedidos — la latencia desglosada por etapa,
  y un coste total verdadero por turno que cubra routing + guardrails +
  ejecución — no existen en ninguna tabla anterior (`Message`,
  `RoutingDecision`, `GuardrailViolation`, `EscalationCase`); una vista solo
  puede reorganizar datos que ya existen, no puede materializar una medición
  que nadie tomó. Como `AgentExecutionService` ya tenía que instrumentarse
  para capturar esos tiempos, escribir el resultado en una fila por turno es
  la consecuencia natural, no un coste de diseño extra. La ganancia grande
  está en la lectura: los agregados de `/metrics` (sumar coste, media/p95 de
  latencia, contar por resultado, agrupar por agente) corren como un único
  escaneo indexado sobre una tabla plana, en vez de un `JOIN` sobre varias
  tablas con relación uno-a-muchos (una traza puede tener varias violaciones
  de guardrail — sumar/promediar tras ese `JOIN` sin desduplicar habría
  contado de más). Esa ventaja crece exactamente cuando más importa: a medida
  que aumenta el volumen.
- **Sin caché de Redis para `/metrics/summary`.** Las consultas de agregación
  usan directamente el índice compuesto `(tenant_id, created_at)` — un único
  escaneo acotado por rango de fechas, no un full scan. El test de
  rendimiento (`tests/test_metrics.py`) inserta 500 filas sintéticas para un
  tenant y confirma que `/metrics/summary` responde en menos de 2 segundos
  (en la práctica, muy por debajo). A esta escala, añadir caché solo suma
  complejidad de invalidación (¿cuándo expira tras escribir una traza nueva?)
  sin una ganancia medible. Si el volumen por tenant creciera a millones de
  filas sería el primer punto a revisar, junto con particionar
  `interaction_traces` por fecha.
- **`cost_usd` es el gasto real del turno completo**, no solo el de la
  respuesta final: se calcula como la diferencia de
  `tenant_limits.current_month_cost_usd` entre el inicio y el final del
  `send_message`, así que incluye la llamada del router LLM (Fase 3) y
  cualquier `custom_llm_check` de guardrails (Fase 4) además de la ejecución
  del agente. `input_tokens`/`output_tokens`, en cambio, son solo los de la
  llamada principal del agente (ya estaban en `message_metadata` desde la
  Fase 2) — son el número que de verdad le importa a un admin mirando una
  traza individual; el desglose de tokens de sub-llamadas de routing/guardrail
  no se expone por separado (su coste sí cuenta en `cost_usd`).
- **Los guardrails apuntan de vuelta a su traza** (`guardrail_violations.trace_id`,
  nullable, `SET NULL` al borrar la traza) — se rellena al escribir la traza
  del turno, así el detalle de una traza no necesita reconstruir qué
  violaciones fueron suyas a través de `message_id`.
- **Desviación deliberada del enunciado literal**: en vez de un único
  `message_id`, el modelo tiene `user_message_id` y `assistant_message_id`
  (este último `nullable`, porque una traza `unassigned` nunca llega a crear
  una respuesta real). Un solo campo habría obligado a elegir cuál de los dos
  mensajes del turno representa, perdiendo información sin necesidad.

## Roles, permisos y configuración guiada (Fase 8)

### Roles

Cada usuario tiene un `role` (`viewer` / `operator` / `admin`), jerárquico —
cada nivel puede hacer todo lo que puede el nivel anterior:

| Rol | Puede |
|---|---|
| `viewer` | Leer todo lo de su tenant: agentes, reglas de routing, guardrails, escalados, trazas, métricas, catálogo de plantillas, estado de onboarding. Nunca escribe ni gasta dinero. |
| `operator` | Todo lo de `viewer`, más: crear/editar/borrar agentes, reglas de routing y guardrails; crear agentes desde plantilla; usar el modo de prueba; enviar mensajes reales (`POST /conversations/{id}/messages`); trabajar la cola de escalados (`claim`/`respond`/`resolve`/`release`); ejecutar `POST /routing-rules/validate`. |
| `admin` | Todo lo de `operator`, más: gestionar usuarios del tenant (invitar, cambiar rol, desactivar) y modificar `tenant-limits` (rate limit y tope de coste mensual); ejecutar `POST /eval/run`. |

La regla general: **cualquier acción con coste real o que cambie la
configuración del tenant requiere `operator`; lo que además puede
comprometer el presupuesto, la seguridad de la cuenta o el acceso de otros
usuarios requiere `admin`.** `tenant-limits` en concreto es de solo lectura
para `operator` (puede consultarlo) pero de escritura solo para `admin`,
porque cambiar el tope de coste mensual es una decisión de negocio, no de
configuración de producto.

La dependencia reutilizable vive en `app/api/deps.py::require_role(min_role)`
— se usa como `dependencies=[Depends(require_role(UserRole.OPERATOR))]` en el
decorador de la ruta (cuando el handler no necesita el objeto `User`), o como
`current_user: User = Depends(require_role(UserRole.OPERATOR))` cuando sí lo
necesita (p. ej. para saber quién reclamó un caso de escalado). Un usuario
desactivado (`is_active=False`) no puede autenticarse ni con login nuevo ni
con un token ya emitido — `get_current_user` lo rechaza con 401 en cada
petición.

### Gestión de usuarios (solo `admin`)

```bash
# Invitar (crear directamente, sin flujo de email todavía)
curl -s -X POST "http://localhost:8000/api/v1/users" \
  -H "Content-Type: application/json" -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"email": "ana@acme.example.com", "password": "unaClaveSegura123", "role": "operator"}'

# Listar usuarios del tenant
curl -s "http://localhost:8000/api/v1/users" -H "Authorization: Bearer $ADMIN_TOKEN"

# Cambiar de rol
curl -s -X PATCH "http://localhost:8000/api/v1/users/$USER_ID" \
  -H "Content-Type: application/json" -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"role": "viewer"}'

# Desactivar (nunca a ti mismo, y nunca al último admin activo del tenant — ambos devuelven error)
curl -s -X POST "http://localhost:8000/api/v1/users/$USER_ID/deactivate" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

### Catálogo de plantillas de agente

```bash
curl -s "http://localhost:8000/api/v1/agent-templates" -H "Authorization: Bearer $TOKEN"
```

5 plantillas listas para usar (`app/core/agent_templates.py`), cada una con
`system_prompt`, `agent_type` sugerido y una `recommended_guardrail` (con su
`rationale`, el riesgo concreto que mitiga):

- **`customer_support`** — Soporte al cliente general. Guardrail: bloquea si
  la respuesta promete reembolsos/descuentos no autorizados.
- **`lead_qualification`** — Cualificación de leads. Guardrail: bloquea si
  comparte precios exactos o cierra una venta sin un comercial humano.
- **`product_faq`** — FAQ de producto. Guardrail: marca (no bloquea) si el
  usuario comparte PII en una pregunta que debería ser genérica.
- **`backoffice_ops`** — Uso interno del equipo. Guardrail: marca PII para
  auditoría (el equipo interno sí la maneja legítimamente).
- **`technical_triage`** — Triaje técnico de primer nivel. Guardrail:
  bloquea instrucciones que impliquen borrado de datos o cambios
  irreversibles sin advertencia clara.

```bash
# Crear un agente a partir de una plantilla — sobrescribiendo el nombre,
# y aplicando (por defecto) su guardrail recomendado como una política
# nueva, ya vinculada a este agente
curl -s -X POST "http://localhost:8000/api/v1/agents/from-template/customer_support" \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"name": "Soporte Acme"}'
```

La respuesta trae `agent` y `guardrail_policy` (o `null` si se envía
`"apply_recommended_guardrail": false`). Todo lo demás sigue siendo un
`Agent`/`GuardrailPolicy` normal, editable después por los endpoints ya
existentes.

### Modo de prueba: validar antes de publicar

```bash
curl -s -X POST "http://localhost:8000/api/v1/agents/$AGENT_ID/test" \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"content": "Hola, ¿cuánto tarda un reembolso?"}'
```

Manda un mensaje suelto directamente a ese agente (sin routing, de por sí ya
elegido) y corre sus guardrails de entrada/salida de verdad — para que
"¿responde bien mi agente?" incluya también "¿lo bloquea algún guardrail que
configuré?". **No** crea `Conversation`, `Message`, `GuardrailViolation` ni
`InteractionTrace`: no aparece en el historial de conversaciones ni en
`/traces` ni en `/metrics/summary`. Sí es una llamada real a Anthropic, así
que sí tiene coste real (visible en `cost_usd` en la respuesta, y sí suma al
`tenant_limits.current_month_cost_usd` real — ocultarlo daría una factura
que no cuadra) y sí respeta el rate limit y el tope de coste mensual del
tenant, para que el modo de prueba no sea una forma de saltárselos.

```bash
curl -s -X POST "http://localhost:8000/api/v1/routing-rules/validate" \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"content": "tengo un problema con mi factura"}'
```

Comprueba qué regla(s) de routing matchean un mensaje de ejemplo — muestra
**todas** las que matchean (no solo la que gana), marcando cuál es
`would_win` (la de mayor prioridad, que es la única que el routing real
llegaría a usar) — útil para depurar "¿por qué esta regla no se está
aplicando, si otra con más prioridad también matchea?". Si ninguna regla
matchea, `would_use_llm_router: true` — nunca llama de verdad al router LLM
(costaría dinero y no sería determinista), solo informa de que ese sería el
siguiente paso.

### Onboarding guiado

```bash
curl -s "http://localhost:8000/api/v1/onboarding/status" -H "Authorization: Bearer $TOKEN"
```

Checklist derivada en vivo del estado real del tenant (sin tabla propia que
mantener sincronizada) — pensada para que un futuro frontend guíe a un
cliente nuevo paso a paso:

- `active_agent` — al menos un agente activo.
- `routing` — al menos una regla de routing activa, **o** al menos un
  agente activo (el router LLM ya puede actuar sin reglas explícitas,
  aunque de forma menos predecible).
- `guardrails` — al menos una política de guardrail activa.
- `tenant_limits` — un tope de coste mensual configurado explícitamente (no
  basta con que exista la fila, que se crea sola con valores por defecto
  desde la Fase 4 — este ítem pide una decisión consciente sobre el gasto
  máximo).
- `team` — más de un usuario activo en el tenant.

## Integraciones externas (Fase 9)

Hasta la Fase 8, todo lo que habla con el sistema necesita un JWT de usuario
del tenant. Esta fase añade una vía distinta pensada para que un CLIENTE
FINAL (no un empleado del tenant) hable con los agentes: API Keys propias,
una API pública sin JWT, un widget de chat embebible, y notificaciones reales
a Slack cuando algo se escala.

### API Keys — dos tipos, con prefijos que no se pueden confundir

```bash
# Key de servidor: puede enviar mensajes Y leer el historial de una sesión.
# Pensada para el propio backend del tenant.
curl -s -X POST "http://localhost:8000/api/v1/api-keys" \
  -H "Content-Type: application/json" -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"name": "Integración backend", "key_type": "server"}'
# -> { "api_key": "ao_sk_...", "key_prefix": "ao_sk_XXXXXXXX", ... }

# Key de widget: SOLO puede enviar mensajes (aunque se pida can_send_messages,
# se ignora para este tipo) — pensada para vivir en el HTML público de una web.
curl -s -X POST "http://localhost:8000/api/v1/api-keys" \
  -H "Content-Type: application/json" -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"name": "Widget del sitio web", "key_type": "widget"}'
# -> { "api_key": "ao_pk_...", ... }

# Listar (nunca devuelve la key completa, solo el prefijo)
curl -s "http://localhost:8000/api/v1/api-keys" -H "Authorization: Bearer $ADMIN_TOKEN"

# Revocar — deja de funcionar en la siguiente petición, no hay periodo de gracia
curl -s -X DELETE "http://localhost:8000/api/v1/api-keys/$KEY_ID" -H "Authorization: Bearer $ADMIN_TOKEN"
```

`ao_sk_...` (server) y `ao_pk_...` (widget) son deliberadamente distintos —
mismo espíritu que `sk_`/`pk_` de Stripe — para que nadie pegue por error una
key de servidor en el HTML público de un cliente. La key completa solo se
devuelve en la respuesta de `POST /api-keys`; en base de datos solo se guarda
su hash SHA-256 (determinista, no bcrypt — la key ya tiene 256 bits de
entropía propia, así que no hay riesgo de fuerza bruta, y un hash
determinista es lo que permite un `WHERE key_hash = ?` indexado; bcrypt con
salt aleatorio no lo permitiría). No existe ningún endpoint ni consulta que
recupere una key ya creada en claro.

### API pública para clientes finales (`/public/v1`, sin JWT)

Nótese que esta API vive fuera de `/api/v1` — es literalmente
`/public/v1/...`, con su propia autenticación por cabecera `X-API-Key`.

```bash
# Enviar un mensaje — pasa por el pipeline completo (routing, guardrails,
# coste, escalado), igual que /api/v1/conversations/{id}/messages
curl -s -X POST "http://localhost:8000/public/v1/messages" \
  -H "Content-Type: application/json" -H "X-API-Key: $SERVER_OR_WIDGET_KEY" \
  -d '{"content": "Necesito ayuda con mi factura", "external_user_id": "cliente-42"}'
# -> { "session_id": "...", "reply": "...", "status": "open" }

# Continuar la misma sesión: reutiliza el session_id devuelto arriba
curl -s -X POST "http://localhost:8000/public/v1/messages" \
  -H "Content-Type: application/json" -H "X-API-Key: $SERVER_OR_WIDGET_KEY" \
  -d '{"content": "¿Cuánto tardará?", "external_user_id": "cliente-42", "session_id": "'"$SESSION_ID"'"}'

# Historial de una sesión — SOLO con key de servidor (ver más abajo)
curl -s "http://localhost:8000/public/v1/messages/$SESSION_ID" -H "X-API-Key: $SERVER_KEY"
```

- `external_user_id` es un identificador que el propio cliente elige (su id
  de usuario, un email, un id de visitante) — Agent Ops no lo valida contra
  nada, solo lo guarda en la conversación para que el cliente pueda filtrar
  después.
- `reply` es `null` únicamente cuando no hay agente asignado todavía
  (`status: "unassigned"`) — cualquier otro desenlace, incluido un bloqueo
  por guardrail, sigue devolviendo una respuesta (el texto genérico que ya
  generan los guardrails desde la Fase 4).
- `GET /public/v1/messages/{session_id}` está reservado a keys `server` — una
  key `widget` recibe `403` aunque intente leer una sesión que ella misma
  creó. Es una restricción impuesta en el servidor (`require_server_key`),
  no solo una convención: una key de widget, por diseño, vive en HTML
  público y solo puede hacer la única cosa que necesita hacer.
- **Rate limiting propio y más estricto**: además del límite interno por
  tenant (`messages_per_minute_limit`), cada API Key tiene su propio límite
  (`PUBLIC_API_RATE_LIMIT_PER_MINUTE`, 20/min por defecto) — así una sola key
  con tráfico descontrolado no puede agotar el presupuesto de mensajes de
  todo el tenant.
- **Aislamiento**: una key solo ve conversaciones de su propio tenant —
  `GET /public/v1/messages/{id}` con el `session_id` de otro tenant devuelve
  `404`, nunca una fuga de qué tenant es dueño de ese id.

### Widget de chat embebible

`GET /widget.js` sirve un script standalone (vanilla JS, sin build step,
~200 líneas) que cualquier web puede pegar tal cual:

```html
<script src="http://localhost:8000/widget.js"
        data-api-key="ao_pk_TU_CLAVE_DE_WIDGET"
        data-api-url="http://localhost:8000"></script>
```

`data-api-key` **debe** ser una key `widget` (`ao_pk_...`) — nunca una de
servidor, porque termina en el código fuente público de la página. El widget:

- pinta una burbuja flotante y un panel de chat (sin diseño elaborado
  todavía — eso es la Fase 11 — pero funcional de verdad);
- guarda `session_id`, un `external_user_id` generado una vez, y el
  historial de la conversación en `localStorage`, para sobrevivir a recargas
  de página;
- habla directamente con `POST /public/v1/messages` vía `fetch`.

`backend/widget-demo.html` es una página de ejemplo (representa la web de un
cliente del tenant) para probarlo contra un backend real — lee la key de
`?key=ao_pk_...` en la URL para no tener que editar el archivo en cada
prueba.

### Slack: notificaciones reales de escalado

```bash
# Configurar el webhook (una URL de "Incoming Webhook" de Slack)
curl -s -X POST "http://localhost:8000/api/v1/integrations/slack" \
  -H "Content-Type: application/json" -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"webhook_url": "https://hooks.slack.com/services/T000/B000/XXXX"}'

# Ver si está configurado (nunca devuelve la URL completa, es un secreto)
curl -s "http://localhost:8000/api/v1/integrations/slack" -H "Authorization: Bearer $ADMIN_TOKEN"
# -> {"configured": true, "masked_webhook_url": "https://hooks.slack.com/***XXXX"}

# Mandar un mensaje de prueba real al canal
curl -s -X POST "http://localhost:8000/api/v1/integrations/slack/test" -H "Authorization: Bearer $ADMIN_TOKEN"
```

A partir de aquí, cada vez que se abre un `EscalationCase` (Fase 5) —
routing sin agente confiable, o un guardrail de salida bloqueado — se manda
un mensaje real al canal configurado, con el motivo del caso y un enlace
(`https://app.agentops.dev/escalations/{id}`, todavía ficticio, apuntando al
frontend que llegará en la Fase 11). El envío es best-effort: un webhook mal
configurado o caído se registra en el log estructurado (igual que antes de
esta fase) pero nunca hace fallar el flujo de escalado que lo disparó. La
URL del webhook recibe el mismo trato que una API Key: se guarda tal cual
(es lo que Slack exige para poder llamarla), pero nunca se devuelve completa
en ninguna respuesta — solo un `masked_webhook_url` con el host y los
últimos caracteres.

## Facturación y planes de suscripción (Fase 10)

El coste real por interacción que ya se calculaba desde la Fase 4 (y se
desglosaba por agente/tenant en la Fase 7) se convierte aquí en un modelo de
negocio SaaS: un catálogo global de planes, límites que dependen del plan de
cada tenant, y facturación mensual simulada — sin cobro real de dinero, eso
queda fuera de alcance.

### Catálogo de planes (`plans`)

Tabla global, no específica de un tenant — el mismo catálogo se ofrece a
todos. Sembrada por la migración `9e921bb08c50` con 4 planes:

| Plan | Precio/mes | Mensajes incluidos | Agentes activos | Usuarios | Coste IA incluido | Msgs/min | Overage / 1000 msgs |
|---|---|---|---|---|---|---|---|
| Free | $0 | 100 | 1 | 1 | $5.00 | 10 | — (no se vende overage) |
| Starter | $29 | 1,000 | 3 | 3 | $15.00 | 30 | $8.00 |
| Growth | $99 | 5,000 | 10 | 10 | $75.00 | 60 | $6.00 |
| Enterprise | $499 | ilimitado | ilimitado | ilimitado | ilimitado | 300 | — (sin techo al que aplicar overage) |

Precios pensados como una escalera defendible frente al mercado actual de
herramientas comparables (Intercom Fin, Chatbase, Ada rondan
gratis/$0 → ~$30-40 → ~$100-150 → a medida/altos cientos para tiers
equivalentes), no números arbitrarios. `is_active=false` retira un plan de
nuevas altas sin borrarlo — las suscripciones y facturas históricas que ya lo
referencian siguen intactas.

```bash
curl -s http://localhost:8000/api/v1/plans -H "Authorization: Bearer $TOKEN"
```

### Suscripción del tenant (`tenant_subscriptions`)

Cada tenant tiene una fila en una tabla separada (no columnas sueltas en
`tenants`) con su plan actual, fecha de inicio, estado
(`active`/`canceled`/`past_due`) y si tiene activado el modo overage. Se
modela como tabla aparte por el mismo patrón que `tenant_limits` o
`tenant_integrations`: es un dato de ciclo de vida de la suscripción, no de
identidad del tenant, y así puede tener su propia migración/evolución sin
tocar el modelo `Tenant`. Todo tenant nuevo se suscribe automáticamente al
plan Free al registrarse.

```bash
# Ver la suscripción actual
curl -s http://localhost:8000/api/v1/subscription -H "Authorization: Bearer $ADMIN_TOKEN"

# Cambiar de plan (solo admin) — opcionalmente activar/desactivar overage
curl -s -X POST http://localhost:8000/api/v1/subscription/change-plan \
  -H "Content-Type: application/json" -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"plan_id": "<uuid-del-plan-starter>", "overage_enabled": true}'
```

**Sin prorrateo, a propósito**: el cambio de plan es efectivo *inmediatamente*
para todo lo que se hace cumplir (límites de mensajes, agentes, usuarios,
coste, tasa) — la siguiente petición ya ve el plan nuevo. Pero la factura del
mes en curso, cuando se genera, cobra el plan que esté vigente *en ese
momento de generación*, no una mezcla ponderada por días entre el plan viejo
y el nuevo. Es una simplificación deliberada: prorratear exige rastrear
"vigente desde X hasta Y" por tramos dentro de un mismo periodo, con su propia
complejidad de bordes (cambios múltiples en el mismo mes, cambios el mismo
día que se genera la factura...) que no aporta nada al objetivo de esta fase
— demostrar el modelo de negocio de punta a punta con números que cuadran.

### Límites propios del tenant vs límites del plan

`tenant_limits` (Fase 4) sigue existiendo y siendo editable por un admin, pero
desde esta fase es un **tope propio dentro de lo que el plan permite**, nunca
por encima. Lo que realmente se aplica en cada petición es el más estricto de
los dos, calculado al vuelo (no se reescribe `tenant_limits` cuando cambia el
plan):

```
límite_efectivo = min(tenant_limits.valor_propio, plan.techo)
```

Igual pasa con `messages_per_minute_limit` y `monthly_cost_limit_usd`: un
`PATCH /tenant-limits` que pida un valor por encima del techo de su plan
responde **422** nombrando el plan y su límite. Calcularlo al vuelo (en vez
de migrar los valores guardados cada vez que cambia el plan) significa que
una bajada de plan surte efecto de inmediato sin ningún paso extra, y que los
valores propios de un admin nunca se pierden si vuelve a subir de plan.

### Qué pasa al superar el nº de mensajes incluidos

Configurable por tenant vía `overage_enabled` (parte de la suscripción):

- **`overage_enabled=false` (por defecto)**: el mensaje que superaría la
  cuota se bloquea con **429** y un mensaje claro pidiendo subir de plan o
  activar overage. No se descuenta del contador.
- **`overage_enabled=true`**: el mensaje se procesa con normalidad, pero
  queda registrado como consumo excedente — se refleja en
  `GET /billing/current-usage` y, al final del mes, en la factura como
  `overage_messages` / `overage_cost_usd` (precio por cada 1000 mensajes
  extra, según el plan).

Los agentes activos y los usuarios del tenant siguen la misma lógica de techo
por plan, pero sin modo overage — no tiene sentido "facturar por agente
extra" de la misma forma que por mensaje extra, así que crear un agente o
invitar un usuario que superaría el límite del plan simplemente responde
**422** (a menos que el plan sea Enterprise, con límites `null` = sin techo).
Un agente creado inactivo y luego activado pasa por el mismo chequeo que
crear uno nuevo activo — no hay atajo para esquivar el límite creando de más
en inactivo.

### Uso en tiempo real: `GET /billing/current-usage`

```bash
curl -s http://localhost:8000/api/v1/billing/current-usage -H "Authorization: Bearer $TOKEN"
```

```json
{
  "plan": { "name": "Starter", "slug": "starter", "included_messages_per_month": 1000, "...": "..." },
  "period_year": 2026, "period_month": 8,
  "messages_used": 1042,
  "included_messages": 1000,
  "overage_messages": 42,
  "overage_cost_usd": "0.336000",
  "ai_cost_usd": "3.812400",
  "included_ai_cost_usd": "15.000000",
  "overage_enabled": true
}
```

Lee directamente de `interaction_traces` (no de los contadores de
`tenant_limits`, que solo reflejan el mes en curso) filtrando por el mes
actual — la misma fuente de verdad que usa la generación de facturas, así los
números que ve un tenant a mitad de mes coinciden con lo que dirá su factura
cuando se cierre el periodo.

### Facturas (`invoices`)

```bash
curl -s http://localhost:8000/api/v1/billing/invoices -H "Authorization: Bearer $TOKEN"
curl -s http://localhost:8000/api/v1/billing/invoices/<id> -H "Authorization: Bearer $TOKEN"
```

Cada factura es un cálculo real a partir de `interaction_traces` del periodo
(no datos inventados): cuenta mensajes reales, suma el coste real de IA, y
aplica la aritmética de overage del plan vigente en el momento de generarla.
`plan_name_snapshot` congela el nombre del plan tal como estaba al generar la
factura — si el plan se renombra después, las facturas viejas no cambian
retroactivamente de nombre. La combinación `(tenant_id, period_year,
period_month)` es única: generar dos veces la misma factura del mismo tenant
para el mismo mes es un no-op, no crea un duplicado.

### Generación mensual

No hay un cron real (fuera de alcance), pero sí el script que un cron
llamaría el día 1 de cada mes:

```bash
cd backend && source .venv/bin/activate
python -m scripts.generate_invoices                    # mes anterior, para todos los tenants
python -m scripts.generate_invoices --year 2026 --month 7   # periodo explícito
```

Itera todos los tenants directamente contra la base de datos (no vía HTTP,
a diferencia de `eval/runner.py`) porque necesita recorrerlos todos sin
depender de ningún JWT/API key concreto, y usa el mismo
`billing_service.generate_invoice` — idempotente y auto-verificable — que los
endpoints usan indirectamente, así que ejecutarlo dos veces para el mismo
periodo es seguro.

## Evaluación (dataset dorado + LLM-as-judge)

Además de los tests, hay un framework de evaluación completo en
[`eval/`](eval/README.md) que mide el sistema de punta a punta contra un
dataset de 30 casos reales (precisión de routing, aciertos/fallos de
guardrails, latencia, coste real, y calidad de respuesta vía un juez basado
en Claude):

```bash
docker compose up -d postgres redis
cd backend && source .venv/bin/activate
python -m eval.runner
```

Genera un informe en `eval/reports/` (JSON + Markdown) contra un tenant
desechable creado solo para esa ejecución. También hay un subconjunto rápido
y gratuito (mockeado, sin API real) que corre como parte de `pytest`
(`tests/test_eval_regression.py`), y un endpoint `POST /eval/run` (solo
admin) que evalúa los guardrails y agentes ya configurados del propio tenant
que llama. Todos los detalles, incluida la justificación de qué corre en cada
sitio y por qué, están en [`eval/README.md`](eval/README.md).

## Tests

Los tests usan una base de datos Postgres de test separada (`agentops_test`,
configurable vía `DATABASE_URL_TEST` en `.env`), cuyo esquema se recrea
automáticamente antes de cada test. Esa base de datos se crea sola la primera vez
que arranca el contenedor de Postgres (ver `infra/postgres/init-test-db.sh`).

```bash
docker compose up -d postgres redis
pytest
```

Los tests que ejercitan el pipeline de mensajes (`test_conversations.py`,
`test_routing.py`, `test_guardrails.py`, `test_tenant_limits.py`,
`test_escalations.py`, `test_eval_regression.py`, `test_eval_endpoint.py`,
`test_agent_test_mode.py`, `test_agent_templates.py`, `test_public_api.py`,
`test_slack_integration.py`, `test_billing.py`) **no llaman a la API
real de Anthropic**: sustituyen el
cliente
(`app.core.anthropic_client.get_anthropic_client`) por un doble de prueba vía
`app.dependency_overrides` (ver `tests/helpers.py` y el fixture
`fake_anthropic_client` en `tests/conftest.py`), así no consumen créditos ni
dependen de red en cada ejecución. `test_routing.py` y `test_guardrails.py`
simulan las respuestas de *tool use* del router y de `custom_llm_check`
fabricadas a mano (confianza alta, confianza baja, sin bloque `tool_use`,
`agent_id` inventado, `violates: true/false`) para probar que cada caso se
degrada con gracia en vez de reventar. El rate limiter sí usa un Redis real
(vía `docker compose up -d postgres redis`), pero aislado en su propia base
(`REDIS_URL_TEST`, índice 1 por defecto) que se vacía antes y después de cada
test — no tiene sentido fakear un `ZSET` cuando Redis real está a un
`docker compose up` de distancia y es la pieza cuya semántica exacta queremos
probar. Por la misma razón, el test de la condición de carrera en `claim`
(`test_escalations.py`) lanza dos peticiones de verdad en paralelo
(`asyncio.gather`) contra el Postgres real de test, en vez de simular el
resultado — es la única forma honesta de probar que el `UPDATE ... WHERE`
atómico realmente serializa las dos escrituras. Todo lo demás — persistencia
de mensajes, historial, matching de reglas por prioridad, creación de
conversación, aislamiento por tenant — se ejecuta de verdad contra la base de
datos de test. No hace falta `ANTHROPIC_API_KEY` para correr `pytest`. Para
probar la llamada real, sigue la sección "Motor de agentes" más arriba.

## Calidad de código

```bash
ruff check .
black --check .
```
