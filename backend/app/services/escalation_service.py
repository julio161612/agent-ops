import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    EscalationCaseAlreadyClaimedError,
    EscalationCaseInvalidStateError,
    EscalationCaseNotFoundError,
    EscalationCaseNotOwnedError,
)
from app.models.conversation import Conversation, ConversationStatus
from app.models.escalation_case import EscalationCase, EscalationReason, EscalationStatus
from app.models.message import Message, MessageRole
from app.services.notification_service import notify_escalation

_OPEN_STATUSES = (EscalationStatus.PENDING, EscalationStatus.IN_PROGRESS)


async def get_open_case_for_conversation(
    db: AsyncSession, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
) -> EscalationCase | None:
    result = await db.execute(
        select(EscalationCase).where(
            EscalationCase.tenant_id == tenant_id,
            EscalationCase.conversation_id == conversation_id,
            EscalationCase.status.in_(_OPEN_STATUSES),
        )
    )
    return result.scalar_one_or_none()


async def create_if_not_exists(
    db: AsyncSession, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID, reason: EscalationReason
) -> EscalationCase | None:
    """Open a PENDING case for this conversation, unless one is already open.

    Returns None (and does nothing else) if an open case already exists —
    callers should not assume a case was created. Notifies only when one
    actually gets created.
    """
    existing = await get_open_case_for_conversation(
        db, tenant_id=tenant_id, conversation_id=conversation_id
    )
    if existing is not None:
        return None

    case = EscalationCase(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        reason=reason,
        status=EscalationStatus.PENDING,
    )
    db.add(case)
    await db.flush()
    await notify_escalation(db, case)
    return case


async def list_cases(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    status: EscalationStatus | None = None,
    reason: EscalationReason | None = None,
) -> list[EscalationCase]:
    stmt = select(EscalationCase).where(EscalationCase.tenant_id == tenant_id)
    if status is not None:
        stmt = stmt.where(EscalationCase.status == status)
    if reason is not None:
        stmt = stmt.where(EscalationCase.reason == reason)
    stmt = stmt.order_by(EscalationCase.created_at)

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_case(db: AsyncSession, *, tenant_id: uuid.UUID, case_id: uuid.UUID) -> EscalationCase:
    result = await db.execute(
        select(EscalationCase).where(
            EscalationCase.id == case_id, EscalationCase.tenant_id == tenant_id
        )
    )
    case = result.scalar_one_or_none()
    if case is None:
        raise EscalationCaseNotFoundError(str(case_id))
    return case


async def claim_case(
    db: AsyncSession, *, tenant_id: uuid.UUID, case_id: uuid.UUID, user_id: uuid.UUID
) -> EscalationCase:
    """Assign a PENDING case to ``user_id``, atomically.

    Uses a single UPDATE ... WHERE status = 'pending' statement rather than a
    SELECT-then-UPDATE, so that under two concurrent claim attempts exactly
    one succeeds — Postgres serializes the two UPDATEs at the row level, and
    whichever commits first is the only one that actually matches the WHERE
    clause. This is the property the "race condition" test exercises.
    """
    result = await db.execute(
        update(EscalationCase)
        .where(
            EscalationCase.id == case_id,
            EscalationCase.tenant_id == tenant_id,
            EscalationCase.status == EscalationStatus.PENDING,
        )
        .values(
            status=EscalationStatus.IN_PROGRESS, assigned_to=user_id, assigned_at=datetime.now(UTC)
        )
    )
    await db.commit()

    if result.rowcount == 0:
        case = await get_case(
            db, tenant_id=tenant_id, case_id=case_id
        )  # raises if missing entirely
        raise EscalationCaseAlreadyClaimedError(
            f"Case {case_id} is not pending (current status: {case.status.value})"
        )
    return await get_case(db, tenant_id=tenant_id, case_id=case_id)


async def release_case(
    db: AsyncSession, *, tenant_id: uuid.UUID, case_id: uuid.UUID
) -> EscalationCase:
    case = await get_case(db, tenant_id=tenant_id, case_id=case_id)
    if case.status != EscalationStatus.IN_PROGRESS:
        raise EscalationCaseInvalidStateError(
            f"Case {case_id} is not in progress (current status: {case.status.value})"
        )
    case.status = EscalationStatus.PENDING
    case.assigned_to = None
    case.assigned_at = None
    await db.commit()
    await db.refresh(case)
    return case


async def respond_to_case(
    db: AsyncSession, *, tenant_id: uuid.UUID, case_id: uuid.UUID, user_id: uuid.UUID, content: str
) -> tuple[EscalationCase, Message]:
    case = await get_case(db, tenant_id=tenant_id, case_id=case_id)
    if case.status != EscalationStatus.IN_PROGRESS:
        raise EscalationCaseInvalidStateError(
            f"Case {case_id} must be claimed (in_progress) before responding "
            f"(current status: {case.status.value})"
        )
    if case.assigned_to != user_id:
        raise EscalationCaseNotOwnedError(f"Case {case_id} is claimed by a different user")

    message = Message(
        tenant_id=tenant_id,
        conversation_id=case.conversation_id,
        role=MessageRole.ASSISTANT,
        content=content,
        message_metadata={"author": "human", "responded_by_user_id": str(user_id)},
    )
    db.add(message)
    await db.commit()
    await db.refresh(case)
    await db.refresh(message)
    return case, message


async def resolve_case(
    db: AsyncSession, *, tenant_id: uuid.UUID, case_id: uuid.UUID, notes: str | None
) -> EscalationCase:
    case = await get_case(db, tenant_id=tenant_id, case_id=case_id)
    if case.status == EscalationStatus.RESOLVED:
        raise EscalationCaseInvalidStateError(f"Case {case_id} is already resolved")

    case.status = EscalationStatus.RESOLVED
    case.resolved_at = datetime.now(UTC)
    case.resolution_notes = notes

    # The human handled it — the conversation is no longer stuck, regardless of
    # whether it got here via failed routing (UNASSIGNED) or a blocked
    # guardrail output (ESCALATED). Doesn't touch agent_id: a conversation that
    # was never routed to an agent stays that way until the next message
    # re-triggers routing (or the human's reply above stands as the answer).
    conversation = await db.get(Conversation, case.conversation_id)
    if conversation is not None:
        conversation.status = ConversationStatus.OPEN

    await db.commit()
    await db.refresh(case)
    return case
