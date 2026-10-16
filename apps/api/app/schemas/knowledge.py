from datetime import date
from pydantic import BaseModel, Field, field_validator


class KnowledgeDocumentIn(BaseModel):
    source_system: str = Field(min_length=2, max_length=50)
    source_id: str = Field(min_length=2, max_length=250)
    document_type: str = Field(min_length=2, max_length=60)
    title: str = Field(min_length=2, max_length=250)
    content: str = Field(min_length=1, max_length=250_000)
    customer_code: str | None = Field(default=None, max_length=50)
    jurisdiction: str | None = Field(default=None, max_length=30)
    effective_from: date | None = None
    effective_to: date | None = None

    @field_validator("source_system", "document_type")
    @classmethod
    def upper_tokens(cls, value: str) -> str:
        return value.strip().upper().replace(" ", "_")

    @field_validator("content")
    @classmethod
    def non_binary_text(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("Knowledge content must be text, not binary data.")
        return value.strip()


class KnowledgeQuery(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    customer_code: str | None = Field(default=None, max_length=50)
    document_type: str | None = Field(default=None, max_length=60)
    jurisdiction: str | None = Field(default=None, max_length=30)
    effective_on: date | None = None
    top_k: int = Field(default=5, ge=1, le=10)
