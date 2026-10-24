from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, loaded from environment variables / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General
    PROJECT_NAME: str = "Agent Ops"
    ENVIRONMENT: str = "local"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://agentops:agentops@localhost:5432/agentops"
    DATABASE_URL_TEST: str = "postgresql+asyncpg://agentops:agentops@localhost:5432/agentops_test"
    DB_ECHO: bool = False

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_URL_TEST: str = "redis://localhost:6379/1"

    # Auth / JWT
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    # Only what the admin panel and the widget actually use (see widget.js and
    # api/deps.py) — not "*".
    CORS_ALLOW_METHODS: list[str] = ["GET", "POST", "PATCH", "DELETE", "OPTIONS"]
    CORS_ALLOW_HEADERS: list[str] = ["Authorization", "Content-Type", "X-API-Key"]

    # Anthropic — used by AgentExecutionService to run agents for real.
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_DEFAULT_MODEL: str = "claude-sonnet-4-6"
    ANTHROPIC_TIMEOUT_SECONDS: float = 60.0

    # Routing — RoutingService falls back to "no agent assigned" below this confidence.
    ROUTING_CONFIDENCE_THRESHOLD: float = 0.5

    # Guardrails — cheap/fast model used for custom_llm_check policies by default.
    GUARDRAIL_LLM_MODEL: str = "claude-haiku-4-5-20251001"

    # Tenant limits — applied to new tenants at registration (see TenantLimits).
    DEFAULT_MESSAGES_PER_MINUTE_LIMIT: int = 60
    DEFAULT_MONTHLY_COST_LIMIT_USD: float | None = None  # None = unlimited

    # Public API (Phase 9) — per-API-key limit, on top of (not instead of) the
    # tenant-wide messages_per_minute_limit send_message already enforces.
    # Stricter by default: this traffic comes straight from end-customer
    # browsers/backends the tenant doesn't fully control, unlike internal
    # JWT-authenticated traffic from the tenant's own staff.
    PUBLIC_API_RATE_LIMIT_PER_MINUTE: int = 20

    # Slack webhook call timeout (Phase 9 escalation notifications).
    SLACK_WEBHOOK_TIMEOUT_SECONDS: float = 10.0


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance, so .env is parsed only once per process."""
    return Settings()


settings = get_settings()
