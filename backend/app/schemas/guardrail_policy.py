import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.guardrail_policy import GuardrailAction, GuardrailRuleType, GuardrailType

_VALID_PII_PATTERNS = {"email", "credit_card", "phone", "spanish_dni"}


def validate_config(rule_type: GuardrailRuleType, config: dict[str, Any]) -> None:
    """Shape-check ``config`` against ``rule_type``. Raises ValueError if invalid.

    Shared between the Create schema and guardrail_policy_service.update_policy,
    which re-validates after merging a PATCH payload onto the existing row.
    """
    if rule_type == GuardrailRuleType.BLOCKLIST_KEYWORDS:
        keywords = config.get("keywords")
        if (
            not isinstance(keywords, list)
            or not keywords
            or not all(isinstance(k, str) and k.strip() for k in keywords)
        ):
            raise ValueError(
                "blocklist_keywords rules require config = {'keywords': [<non-empty strings>, ...]}"
            )
    elif rule_type == GuardrailRuleType.PII_DETECTION:
        patterns = config.get("patterns")
        if patterns is not None and (
            not isinstance(patterns, list)
            or not patterns
            or not all(p in _VALID_PII_PATTERNS for p in patterns)
        ):
            raise ValueError(
                "pii_detection config.patterns, if given, must be a non-empty list from "
                f"{sorted(_VALID_PII_PATTERNS)} (omit it entirely to check all of them)"
            )
    elif rule_type == GuardrailRuleType.MAX_LENGTH:
        max_characters = config.get("max_characters")
        if (
            not isinstance(max_characters, int)
            or isinstance(max_characters, bool)
            or max_characters <= 0
        ):
            raise ValueError("max_length rules require config = {'max_characters': <positive int>}")
    elif rule_type == GuardrailRuleType.CUSTOM_LLM_CHECK:
        instruction = config.get("instruction")
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValueError(
                "custom_llm_check rules require config = {'instruction': '<non-empty string>'} "
                "(optionally also 'model' to override the default guardrail model)"
            )


class GuardrailPolicyCreate(BaseModel):
    agent_id: uuid.UUID | None = None
    guardrail_type: GuardrailType
    rule_type: GuardrailRuleType
    config: dict[str, Any]
    action_on_violation: GuardrailAction = GuardrailAction.BLOCK
    is_active: bool = True

    @model_validator(mode="after")
    def _check_config(self) -> "GuardrailPolicyCreate":
        validate_config(self.rule_type, self.config)
        return self


class GuardrailPolicyUpdate(BaseModel):
    agent_id: uuid.UUID | None = None
    guardrail_type: GuardrailType | None = None
    rule_type: GuardrailRuleType | None = None
    config: dict[str, Any] | None = None
    action_on_violation: GuardrailAction | None = None
    is_active: bool | None = None


class GuardrailPolicyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    agent_id: uuid.UUID | None
    guardrail_type: GuardrailType
    rule_type: GuardrailRuleType
    config: dict[str, Any]
    action_on_violation: GuardrailAction
    is_active: bool
    created_at: datetime
    updated_at: datetime
