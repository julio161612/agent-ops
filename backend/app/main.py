from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.agent_templates import router as agent_templates_router
from app.api.routers.agents import router as agents_router
from app.api.routers.api_keys import router as api_keys_router
from app.api.routers.auth import router as auth_router
from app.api.routers.billing import router as billing_router
from app.api.routers.conversations import router as conversations_router
from app.api.routers.escalations import router as escalations_router
from app.api.routers.eval import router as eval_router
from app.api.routers.guardrail_policies import router as guardrail_policies_router
from app.api.routers.guardrail_violations import router as guardrail_violations_router
from app.api.routers.integrations import router as integrations_router
from app.api.routers.metrics import router as metrics_router
from app.api.routers.onboarding import router as onboarding_router
from app.api.routers.plans import router as plans_router
from app.api.routers.public import router as public_router
from app.api.routers.routing_rules import router as routing_rules_router
from app.api.routers.subscription import router as subscription_router
from app.api.routers.tenant_limits import router as tenant_limits_router
from app.api.routers.traces import router as traces_router
from app.api.routers.users import router as users_router
from app.api.routers.widget import router as widget_router
from app.core.config import settings

app = FastAPI(title=settings.PROJECT_NAME, openapi_url=f"{settings.API_V1_PREFIX}/openapi.json")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
app.include_router(agents_router, prefix=settings.API_V1_PREFIX)
app.include_router(agent_templates_router, prefix=settings.API_V1_PREFIX)
app.include_router(conversations_router, prefix=settings.API_V1_PREFIX)
app.include_router(routing_rules_router, prefix=settings.API_V1_PREFIX)
app.include_router(guardrail_policies_router, prefix=settings.API_V1_PREFIX)
app.include_router(guardrail_violations_router, prefix=settings.API_V1_PREFIX)
app.include_router(tenant_limits_router, prefix=settings.API_V1_PREFIX)
app.include_router(escalations_router, prefix=settings.API_V1_PREFIX)
app.include_router(eval_router, prefix=settings.API_V1_PREFIX)
app.include_router(traces_router, prefix=settings.API_V1_PREFIX)
app.include_router(metrics_router, prefix=settings.API_V1_PREFIX)
app.include_router(users_router, prefix=settings.API_V1_PREFIX)
app.include_router(onboarding_router, prefix=settings.API_V1_PREFIX)
app.include_router(api_keys_router, prefix=settings.API_V1_PREFIX)
app.include_router(public_router)  # /public/v1/* — deliberately NOT under API_V1_PREFIX
app.include_router(widget_router)  # /widget.js — also not under API_V1_PREFIX
app.include_router(integrations_router, prefix=settings.API_V1_PREFIX)
app.include_router(plans_router, prefix=settings.API_V1_PREFIX)
app.include_router(subscription_router, prefix=settings.API_V1_PREFIX)
app.include_router(billing_router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
