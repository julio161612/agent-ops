import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConversationNotFoundError
from app.models.conversation import Conversation
from app.models.message import Message


async def get_conversation(
    db: AsyncSession, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
) -> Conversation:
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.tenant_id == tenant_id
        )
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise ConversationNotFoundError(str(conversation_id))
    return conversation


async def list_messages(
    db: AsyncSession, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
) -> list[Message]:
    await get_conversation(db, tenant_id=tenant_id, conversation_id=conversation_id)
    result = await db.execute(
        select(Message)
        .where(Message.tenant_id == tenant_id, Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return list(result.scalars().all())
