import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.routing_rule import RoutingRuleType


def validate_condition(rule_type: RoutingRuleType, condition: dict[str, Any]) -> None:
    """Shape-check ``condition`` against ``rule_type``. Raises ValueError if invalid.

    Shared between the Create schema (validated on the initial payload) and
    routing_rule_service.update_routing_rule (validated after merging a PATCH
    payload onto the existing row, since a partial update might change only
    one of the two fields).
    """
    if rule_type == RoutingRuleType.KEYWORD:
        keywords = condition.get("keywords")
        if (
            not isinstance(keywords, list)
            or not keywords
            or not all(isinstance(k, str) and k.strip() for k in keywords)
        ):
            raise ValueError(
                "keyword rules require condition = {'keywords': [<non-empty strings>, ...]}"
            )
    elif rule_type == RoutingRuleType.CATEGORY:
        agent_type = condition.get("agent_type")
        if not isinstance(agent_type, str) or not agent_type.strip():
            raise ValueError(
                "category rules require condition = {'agent_type': '<non-empty string>'}"
            )


class RoutingRuleCreate(BaseModel):
    agent_id: uuid.UUID
    rule_type: RoutingRuleType
    condition: dict[str, Any]
    priority: int = 0
    is_active: bool = True

    @model_validator(mode="after")
    def _check_condition(self) -> "RoutingRuleCreate":
        validate_condition(self.rule_type, self.condition)
        return self


class RoutingRuleUpdate(BaseModel):
    agent_id: uuid.UUID | None = None
    rule_type: RoutingRuleType | None = None
    condition: dict[str, Any] | None = None
    priority: int | None = None
    is_active: bool | None = None


class RoutingRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    agent_id: uuid.UUID
    rule_type: RoutingRuleType
    condition: dict[str, Any]
    priority: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class RoutingValidateRequest(BaseModel):
    content: str = Field(min_length=1, description="Example inbound message to test routing for.")


class RoutingRuleMatchPreview(BaseModel):
    rule_id: uuid.UUID
    rule_type: RoutingRuleType
    priority: int
    agent_id: uuid.UUID
    agent_name: str
    would_win: bool = Field(
        description="True only for the highest-priority match — routing always stops at the "
        "first match, so the others are shown for debugging ('why didn't rule X apply') but "
        "would never actually fire while this one exists."
    )


class RoutingValidateResponse(BaseModel):
    content: str
    matched_rules: list[RoutingRuleMatchPreview]
    resulting_agent_id: uuid.UUID | None
    resulting_agent_name: str | None
    would_use_llm_router: bool = Field(
        description="True when no rule matched — real routing would fall through to the LLM "
        "router at that point, but this endpoint never calls it (no real execution, no cost)."
    )
