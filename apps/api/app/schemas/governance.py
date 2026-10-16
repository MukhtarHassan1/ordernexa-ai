from decimal import Decimal
from pydantic import BaseModel, Field


class AutonomyPolicyUpdate(BaseModel):
    level: int = Field(ge=0, le=4)
    enabled: bool = False
    max_value: Decimal | None = Field(default=None, ge=0)
    allowed_risks: list[str] = Field(default_factory=list, max_length=3)
    notes: str | None = Field(default=None, max_length=1000)


class AskOpsRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
