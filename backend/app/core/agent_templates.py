"""Catalog of predefined agent templates for the low-code onboarding flow (Phase 8).

Static, in-memory, not tenant-scoped — this is the same list for every tenant,
the starting point a non-technical admin picks from instead of writing a
system_prompt and guardrail policy from scratch. Each template pairs a
system_prompt with the one guardrail policy that best matches that use case's
most likely failure mode (over-promising, leaking PII, unsafe instructions,
etc) — a sane default, not the only guardrail a real deployment would ever
want.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RecommendedGuardrail:
    guardrail_type: str  # "input" | "output"
    rule_type: str
    config: dict[str, Any]
    action_on_violation: str  # "block" | "flag"
    rationale: str


@dataclass(frozen=True)
class AgentTemplate:
    id: str
    name: str
    description: str
    agent_type: str
    system_prompt: str
    suggested_model: str
    suggested_parameters: dict[str, Any]
    recommended_guardrail: RecommendedGuardrail


_DEFAULT_PARAMETERS: dict[str, Any] = {"temperature": 0.4, "max_tokens": 400}

AGENT_TEMPLATES: dict[str, AgentTemplate] = {
    "customer_support": AgentTemplate(
        id="customer_support",
        name="Soporte al cliente general",
        description=(
            "Atiende dudas, incidencias y quejas de clientes ya existentes: estado de "
            "pedidos, problemas con el servicio, dudas de cuenta. Deriva a un humano lo "
            "que no pueda resolver."
        ),
        agent_type="support",
        system_prompt=(
            "Eres el agente de soporte al cliente. Responde siempre en el idioma del "
            "usuario, de forma breve, profesional y empática. Reconoce el problema del "
            "cliente antes de proponer una solución. Pide los datos concretos que "
            "necesites (número de pedido, de cuenta, fecha) para poder ayudar. Si el "
            "problema requiere acceso a sistemas internos, un reembolso, o una decisión "
            "que no puedes tomar, dilo con claridad y explica que un miembro del equipo "
            "lo revisará. Nunca inventes información sobre pedidos, plazos o políticas "
            "que no conoces."
        ),
        suggested_model="claude-sonnet-4-6",
        suggested_parameters=dict(_DEFAULT_PARAMETERS),
        recommended_guardrail=RecommendedGuardrail(
            guardrail_type="output",
            rule_type="custom_llm_check",
            config={
                "instruction": (
                    "No debe prometer reembolsos, descuentos ni compensaciones que la "
                    "empresa no ha autorizado explícitamente"
                )
            },
            action_on_violation="block",
            rationale=(
                "El riesgo más común de un bot de soporte es que 'resuelva' un caso "
                "prometiendo algo que la empresa luego tiene que cumplir."
            ),
        ),
    ),
    "lead_qualification": AgentTemplate(
        id="lead_qualification",
        name="Cualificación de leads",
        description=(
            "Primer contacto con un prospecto: entiende su necesidad, tamaño de empresa "
            "y presupuesto orientativo, y prepara el traspaso a un comercial humano."
        ),
        agent_type="sales",
        system_prompt=(
            "Eres el agente de cualificación comercial. Tu objetivo NO es cerrar una "
            "venta, es entender si el prospecto encaja con lo que ofrecemos y recoger la "
            "información que un comercial necesitará: qué problema quiere resolver, "
            "tamaño aproximado de su empresa, plazos, y si ya evalúa otras alternativas. "
            "Sé cercano pero directo, sin sonar a cuestionario. En cuanto tengas lo "
            "esencial, explica que un comercial le contactará. No cierres acuerdos ni "
            "confirmes condiciones comerciales."
        ),
        suggested_model="claude-sonnet-4-6",
        suggested_parameters=dict(_DEFAULT_PARAMETERS),
        recommended_guardrail=RecommendedGuardrail(
            guardrail_type="output",
            rule_type="custom_llm_check",
            config={
                "instruction": (
                    "No debe compartir precios exactos, descuentos, ni cerrar o "
                    "confirmar una venta sin intervención de un comercial humano"
                )
            },
            action_on_violation="block",
            rationale=(
                "Un agente de cualificación que empieza a negociar precio o cerrar "
                "condiciones se sale de su función y puede comprometer a la empresa."
            ),
        ),
    ),
    "product_faq": AgentTemplate(
        id="product_faq",
        name="FAQ de producto",
        description=(
            "Responde preguntas frecuentes sobre el producto: funcionalidades, "
            "requisitos, cómo hacer algo. No gestiona cuentas ni incidencias."
        ),
        agent_type="faq",
        system_prompt=(
            "Eres el agente de preguntas frecuentes sobre el producto. Responde de forma "
            "breve, concreta y basada solo en lo que sabes del producto — si la "
            "pregunta trata sobre la cuenta específica de un usuario, un pedido o una "
            "incidencia, indica que eso lo gestiona el equipo de soporte y no lo "
            "atiendes tú. No necesitas datos personales del usuario para responder "
            "preguntas generales; si el usuario los comparte igualmente, no los "
            "utilices ni los repitas en tu respuesta."
        ),
        suggested_model="claude-sonnet-4-6",
        suggested_parameters={"temperature": 0.2, "max_tokens": 300},
        recommended_guardrail=RecommendedGuardrail(
            guardrail_type="input",
            rule_type="pii_detection",
            config={},
            action_on_violation="flag",
            rationale=(
                "Un FAQ público no debería necesitar datos personales — si aparecen, "
                "es señal de que el usuario en realidad tiene un caso de soporte, no "
                "una duda general (se marca para revisión, no se bloquea, porque no es "
                "un fallo del usuario)."
            ),
        ),
    ),
    "backoffice_ops": AgentTemplate(
        id="backoffice_ops",
        name="Backoffice / operaciones",
        description=(
            "Uso interno: ayuda al equipo a consultar procedimientos, plantillas y "
            "checklists operativos. No es de cara al cliente final."
        ),
        agent_type="backoffice",
        system_prompt=(
            "Eres el asistente interno de operaciones. Tu audiencia es el propio equipo, "
            "no clientes externos. Ayuda a encontrar procedimientos, redactar respuestas "
            "internas, y aplicar checklists operativos. Responde de forma directa y "
            "concisa, como a un compañero de equipo. Si te piden algo que implica "
            "cambiar datos reales en un sistema en producción, recuerda que solo puedes "
            "asesorar sobre el procedimiento — la ejecución la hace una persona."
        ),
        suggested_model="claude-sonnet-4-6",
        suggested_parameters=dict(_DEFAULT_PARAMETERS),
        recommended_guardrail=RecommendedGuardrail(
            guardrail_type="input",
            rule_type="pii_detection",
            config={},
            action_on_violation="flag",
            rationale=(
                "El equipo interno maneja PII de clientes legítimamente — no se "
                "bloquea, pero queda marcado en el registro de auditoría por si hace "
                "falta revisar cómo se está usando."
            ),
        ),
    ),
    "technical_triage": AgentTemplate(
        id="technical_triage",
        name="Triaje técnico",
        description=(
            "Primer nivel de soporte técnico: diagnostica el problema, sugiere pasos "
            "básicos de resolución, y clasifica la severidad antes de escalar."
        ),
        agent_type="technical",
        system_prompt=(
            "Eres el agente de triaje técnico. Ayuda a diagnosticar problemas técnicos "
            "haciendo preguntas concretas (versión, pasos para reproducir, mensaje de "
            "error exacto) y sugiere únicamente pasos de resolución seguros y "
            "reversibles (reiniciar, limpiar caché, revisar configuración). Nunca "
            "sugieras acciones destructivas o irreversibles (borrar datos, resetear de "
            "fábrica, modificar la base de datos) sin advertir explícitamente el riesgo "
            "y recomendar que lo haga o lo confirme una persona del equipo técnico. "
            "Clasifica la severidad (baja/media/alta/crítica) para quien lo revise "
            "después."
        ),
        suggested_model="claude-sonnet-4-6",
        suggested_parameters={"temperature": 0.3, "max_tokens": 500},
        recommended_guardrail=RecommendedGuardrail(
            guardrail_type="output",
            rule_type="custom_llm_check",
            config={
                "instruction": (
                    "No debe dar instrucciones que impliquen borrado de datos, reseteo "
                    "de fábrica, o cambios irreversibles en sistemas sin advertir "
                    "claramente el riesgo y recomendar confirmación humana"
                )
            },
            action_on_violation="block",
            rationale=(
                "El riesgo específico del triaje técnico es sugerir un 'arreglo' que "
                "en realidad causa pérdida de datos o downtime."
            ),
        ),
    ),
}


def list_templates() -> list[AgentTemplate]:
    return list(AGENT_TEMPLATES.values())


def get_template(template_id: str) -> AgentTemplate | None:
    return AGENT_TEMPLATES.get(template_id)
