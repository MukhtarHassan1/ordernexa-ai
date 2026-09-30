"""Conservative native-text preview; requires explicit human verification.

Shares the source anchor parser with the AI grounder so multi-line labels do
not produce conflicting candidate values. No ERP action or AI decision here.
"""
from pathlib import Path

from app.schemas.c2c import ManualOrderInput, ManualOrderLineInput
from app.services.document_intelligence import extract_document
from app.services.source_grounding import inspect_source_text


class PreviewNotPossible(ValueError):
    pass


def preview_purchase_order(*, filename: str, data: bytes) -> dict:
    content = extract_document(filename=filename, data=data)
    if not content.text.strip():
        raise PreviewNotPossible(
            "No native text is available. Scanned images require AI or human transcription."
        )
    source = inspect_source_text(content.text)
    if source.warnings or source.ambiguous:
        raise PreviewNotPossible(
            "Source contains ambiguous or unparseable labelled values: "
            + ", ".join(source.warnings or sorted(source.ambiguous))
            + ". Use explicit manual entry after reading the original."
        )
    required = ("po_number", "customer_hint", "currency", "delivery_warehouse_code")
    missing = [key for key in required if key not in source.fields]
    if missing or source.lines is None or not source.lines:
        raise PreviewNotPossible(
            "Cannot reliably preview critical source fields: "
            + ", ".join(missing + (["lines"] if not source.lines else []))
            + ". Enter and verify manually."
        )
    candidate = ManualOrderInput(
        po_number=str(source.fields["po_number"].value),
        customer_hint=str(source.fields["customer_hint"].value),
        currency=str(source.fields["currency"].value),
        delivery_warehouse_code=str(source.fields["delivery_warehouse_code"].value),
        requested_delivery_date=(
            source.fields["requested_delivery_date"].value
            if "requested_delivery_date" in source.fields else None
        ),
        lines=[ManualOrderLineInput(
            line_number=item.line_number,
            product_term=item.product_term,
            quantity=str(item.quantity),
            uom=item.uom,
            requested_unit_price=(
                str(item.requested_unit_price)
                if item.requested_unit_price is not None else None
            ),
        ) for item in source.lines],
    )
    return {
        "method": "DETERMINISTIC_PREVIEW_NOT_AI",
        "source": Path(filename).name,
        "requires_human_confirmation": True,
        "warnings": [
            "Verify every field against the saved original before confirmation.",
            "Source parsing is format-limited; no business data, price, credit or stock has been validated.",
            "Requested unit prices are not executable contract prices.",
        ],
        "source_evidence": list(dict.fromkeys(
            proof for value in source.fields.values() for proof in value.evidence
        )) + source.line_evidence,
        "candidate": candidate.model_dump(mode="json"),
        "extraction_method": content.extraction_method,
    }
