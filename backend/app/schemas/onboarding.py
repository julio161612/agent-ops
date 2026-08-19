from pydantic import BaseModel


class OnboardingItemRead(BaseModel):
    key: str
    label: str
    done: bool
    detail: str


class OnboardingStatusRead(BaseModel):
    items: list[OnboardingItemRead]
    completed_count: int
    total_count: int
    is_complete: bool
