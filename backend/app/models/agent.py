from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import SoftDeleteMixin, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.conversation import Conversation

DEFAULT_AGENT_PARAMETERS: dict[str, Any] = {"temperature": 1.0, "max_tokens": 1024}


class Agent(UUIDPrimaryKeyMixin, TenantScopedMixin, SoftDeleteMixin, TimestampMixin, Base):
    """A tenant-configured AI agent (e.g. support, backoffice, lead qualification)."""

    __tablename__ = "agents"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_type: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict(DEFAULT_AGENT_PARAMETERS)
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    conversations: Mapped[list[Conversation]] = relationship(back_populates="agent")
