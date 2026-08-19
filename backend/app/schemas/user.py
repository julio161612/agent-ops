import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    email: EmailStr
    role: UserRole
    is_active: bool
    created_at: datetime


class UserInvite(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = Field(description="No default on purpose — the inviting admin must pick one.")


class UserRoleUpdate(BaseModel):
    role: UserRole
