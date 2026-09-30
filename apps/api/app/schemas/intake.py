from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    Field,
    model_validator,
)

from app.schemas.c2c import (
    ManualOrderValidationResponse,
)


class ExtractedOrderLine(BaseModel):
    line_number: int = Field(ge=1)

    product_term: str = Field(
        min_length=1,
        max_length=250,
    )

    quantity: float = Field(gt=0)

    uom: str = Field(
        default="EA",
        max_length=20,
    )

    requested_unit_price: float | None = Field(
        default=None,
        ge=0,
    )


class ExtractedOrderDraft(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def quarantine_noncanonical_ai_confidence(cls, value):
        """Recover a common small-model *format* error, never trust its certainty.

        The AI contract requires 0..1, but local LLMs occasionally emit 100
        for 100%. We can still use other schema-valid fields for source
        verification, provided the malformed confidence triggers human review.
        Other invalid values remain validation failures (fail closed).
        """
        if not isinstance(value, dict):
            return value
        original = value.get("overall_confidence")
        percentage_marked = (
            isinstance(original, str) and original.strip().endswith("%")
        )
        candidate = original.strip()[:-1].strip() if percentage_marked else original
        if isinstance(candidate, bool):
            raise ValueError("AI confidence must be a number, not a boolean.")
        try:
            # Don't accept arbitrary numeric strings as a signal that a
            # percentage scale was used: "100" is unambiguous, "0.9" is not.
            number = float(candidate)
        except (TypeError, ValueError, OverflowError):
            return value
        if (percentage_marked and 0 <= number <= 100) or (1 < number <= 100):
            flags = value.get("risk_flags", [])
            if flags is None:
                flags = []
            if not isinstance(flags, list):
                return value  # Preserve invalid risk_flags for Pydantic rejection.
            fixed = dict(value)
            fixed["overall_confidence"] = number / 100
            fixed["risk_flags"] = list(dict.fromkeys([
                *flags,
                "REVIEW_REQUIRED_NONCANONICAL_AI_CONFIDENCE",
            ]))
            return fixed
        return value

    document_type: Literal[
        "PURCHASE_ORDER",
        "RFQ",
        "OTHER",
    ]

    po_number: str | None = None

    customer_hint: str | None = None

    customer_domain: str | None = None

    currency: str = "GBP"

    delivery_location: str | None = None

    delivery_warehouse_code: (
        Literal["MAN", "LON", "RTM"]
        | None
    ) = None

    requested_delivery_date: (
        date | None
    ) = None

    lines: list[ExtractedOrderLine] = Field(
        default_factory=list,
    )

    overall_confidence: float = Field(
        ge=0,
        le=1,
    )

    evidence: list[str] = Field(
        default_factory=list,
    )

    missing_fields: list[str] = Field(
        default_factory=list,
    )

    risk_flags: list[str] = Field(
        default_factory=list,
    )


class IntakeUploadResponse(BaseModel):
    artifact_id: UUID

    object_key: str

    provider: str

    model: str

    prompt_version: str

    extraction: ExtractedOrderDraft

    transaction: ManualOrderValidationResponse