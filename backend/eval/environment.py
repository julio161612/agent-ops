"""The fixed tenant configuration the golden dataset's expectations are written against.

Every case in eval/data/golden_dataset.yaml assumes exactly this setup exists:
three agents (billing, shipping, support), keyword routing rules that only
cover billing and shipping (support is reachable only through the LLM router
or an explicit agent_id — that asymmetry is what makes the "routing_llm" and
"routing_none" dataset categories meaningful), and a fixed set of guardrail
policies. If you change anything here, update the dataset's `expected` values
to match, or the accuracy metrics will just be measuring drift between the two
files instead of real system behavior.
"""

from dataclasses import dataclass, field

from httpx import AsyncClient

AGENT_DEFINITIONS: dict[str, dict] = {
    "billing": {
        "name": "Billing Agent",
        "agent_type": "billing",
        "description": "Resuelve dudas sobre facturas, cobros y pagos.",
        "system_prompt": (
            "Eres el agente de facturación de Acme. Responde de forma breve, profesional y en "
            "español. Pide los datos que necesites (número de factura, importe, fecha) para "
            "poder ayudar. Nunca prometas un reembolso sin revisión previa del caso."
        ),
        "model": "claude-sonnet-4-6",
        "parameters": {"temperature": 0.3, "max_tokens": 200},
    },
    "shipping": {
        "name": "Shipping Agent",
        "agent_type": "shipping",
        "description": "Gestiona el estado de envíos, cambios y devoluciones de pedidos.",
        "system_prompt": (
            "Eres el agente de envíos y devoluciones de Acme. Responde de forma breve y "
            "profesional en español. Pide el número de pedido o de seguimiento cuando lo "
            "necesites para investigar un caso."
        ),
        "model": "claude-sonnet-4-6",
        "parameters": {"temperature": 0.3, "max_tokens": 200},
    },
    "support": {
        "name": "General Support Agent",
        "agent_type": "support",
        "description": (
            "Preguntas generales sobre la cuenta o el producto que no encajan en facturación "
            "ni envíos (acceso a la cuenta, configuración, uso general)."
        ),
        "system_prompt": (
            "Eres el agente de soporte general de Acme. Responde de forma breve y profesional "
            "en español a preguntas generales sobre la cuenta o el producto."
        ),
        "model": "claude-sonnet-4-6",
        "parameters": {"temperature": 0.3, "max_tokens": 200},
    },
}

# (target agent, rule config) — deliberately no rule targets "support": that's
# what forces the "routing_llm" dataset cases to actually exercise the LLM router.
ROUTING_RULE_DEFINITIONS: list[tuple[str, dict]] = [
    ("billing", {"keywords": ["factura", "pago", "cobro"]}),
    ("shipping", {"keywords": ["paquete", "envío", "envio", "devolución", "devolucion"]}),
]

GUARDRAIL_POLICY_DEFINITIONS: list[dict] = [
    {
        "agent_id": None,  # tenant-wide
        "guardrail_type": "input",
        "rule_type": "blocklist_keywords",
        "config": {"keywords": ["idiota", "estúpido"]},
        "action_on_violation": "block",
    },
    {
        "agent_id": None,
        "guardrail_type": "input",
        "rule_type": "pii_detection",
        "config": {},
        "action_on_violation": "flag",
    },
    {
        "agent_id": None,
        "guardrail_type": "input",
        "rule_type": "max_length",
        "config": {"max_characters": 500},
        "action_on_violation": "block",
    },
    {
        "agent_id": "billing",  # resolved to a real agent_id at setup time
        "guardrail_type": "output",
        "rule_type": "custom_llm_check",
        "config": {"instruction": "No debe prometer reembolsos que la empresa no puede garantizar"},
        "action_on_violation": "block",
    },
]


@dataclass
class EnvironmentInfo:
    """What create_environment() actually created, keyed by logical name."""

    agent_ids: dict[str, str] = field(default_factory=dict)
    routing_rule_ids: list[str] = field(default_factory=list)
    guardrail_policy_ids: list[str] = field(default_factory=list)


async def create_environment(client: AsyncClient, headers: dict[str, str]) -> EnvironmentInfo:
    """Create the canonical agents/rules/policies in the tenant behind ``client``+``headers``.

    Idempotent-ish only in the sense that it always creates fresh rows — call
    this once per eval tenant (the runner registers a brand new tenant per
    run specifically so this never needs to worry about pre-existing state).
    """
    info = EnvironmentInfo()

    for logical_name, definition in AGENT_DEFINITIONS.items():
        response = await client.post("/api/v1/agents", json=definition, headers=headers)
        response.raise_for_status()
        info.agent_ids[logical_name] = response.json()["id"]

    for logical_name, condition in ROUTING_RULE_DEFINITIONS:
        payload = {
            "agent_id": info.agent_ids[logical_name],
            "rule_type": "keyword",
            "condition": condition,
            "priority": 10,
        }
        response = await client.post("/api/v1/routing-rules", json=payload, headers=headers)
        response.raise_for_status()
        info.routing_rule_ids.append(response.json()["id"])

    for definition in GUARDRAIL_POLICY_DEFINITIONS:
        payload = dict(definition)
        if payload["agent_id"] is not None:
            payload["agent_id"] = info.agent_ids[payload["agent_id"]]
        response = await client.post("/api/v1/guardrail-policies", json=payload, headers=headers)
        response.raise_for_status()
        info.guardrail_policy_ids.append(response.json()["id"])

    return info
