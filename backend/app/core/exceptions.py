class AppError(Exception):
    """Base class for domain errors that routers translate into HTTP responses."""


class EmailAlreadyRegisteredError(AppError):
    pass


class InvalidCredentialsError(AppError):
    pass


class InvalidTokenError(AppError):
    pass


class AgentNotFoundError(AppError):
    pass


class ConversationNotFoundError(AppError):
    pass


class RoutingRuleNotFoundError(AppError):
    pass


class InvalidRoutingRuleConditionError(AppError):
    """Raised when a routing rule's condition doesn't match the shape its rule_type expects."""


class AgentExecutionError(AppError):
    """Base class for failures of the underlying Anthropic API call."""


class AgentRateLimitedError(AgentExecutionError):
    pass


class AgentTimeoutError(AgentExecutionError):
    pass


class AgentUpstreamError(AgentExecutionError):
    """Any other non-retryable failure from the Anthropic API (auth, bad request, 5xx)."""


class GuardrailPolicyNotFoundError(AppError):
    pass


class InvalidGuardrailConfigError(AppError):
    """Raised when a guardrail policy's config doesn't match the shape its rule_type expects."""


class TenantRateLimitExceededError(AppError):
    pass


class TenantCostLimitExceededError(AppError):
    pass


class EscalationCaseNotFoundError(AppError):
    pass


class EscalationCaseAlreadyClaimedError(AppError):
    """Raised when claiming a case that isn't PENDING (already claimed, or resolved)."""


class EscalationCaseNotOwnedError(AppError):
    """Raised when a user tries to respond to a case claimed by someone else."""


class EscalationCaseInvalidStateError(AppError):
    """Raised for any other state transition that isn't valid from the case's current status."""


class InteractionTraceNotFoundError(AppError):
    pass


class UserNotFoundError(AppError):
    pass


class CannotModifySelfError(AppError):
    """Raised when a user tries to deactivate their own account via /users."""


class LastActiveAdminError(AppError):
    """Raised when an action would leave a tenant with zero active admins."""


class AgentTemplateNotFoundError(AppError):
    pass


class ApiKeyNotFoundError(AppError):
    pass


class InvalidApiKeyError(AppError):
    """Raised when the X-API-Key header is missing, malformed, unknown, or revoked."""


class ApiKeyForbiddenError(AppError):
    """Raised when a valid API key doesn't have the scope for the action it just tried."""


class PlanNotFoundError(AppError):
    pass


class PlanNotActiveError(AppError):
    """Raised when trying to subscribe a tenant to a retired (is_active=False) plan."""


class TenantLimitsExceedPlanError(AppError):
    """Raised when an admin's requested tenant_limits values exceed their plan's ceiling."""


class TenantMessageQuotaExceededError(AppError):
    """Raised when a tenant is over its plan's included monthly messages and overage is off."""


class PlanAgentLimitExceededError(AppError):
    """Raised when creating an agent would exceed the plan's included_active_agents."""


class PlanUserLimitExceededError(AppError):
    """Raised when inviting a user would exceed the plan's included_users."""


class InvoiceNotFoundError(AppError):
    pass


class InvoiceAlreadyExistsError(AppError):
    """Raised when generating an invoice for a tenant+period that already has one."""
