"""Conservative source anchoring for text-based purchase orders.

LLM output is a *proposal*. Explicitly labelled fields and line blocks in native
text are taken from the original source. Conflicts are corrected for display,
flagged for human review, and must never authorize automatic transactions.

This deliberately does not pretend to parse arbitrary invoice tables, scanned
pages, emails with quoted orders, or ambiguous date conventions. Unsupported or
ambiguous material must be reviewed; the model is not a source of authority.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.schemas.intake import ExtractedOrderDraft, ExtractedOrderLine


_FIELD_PATTERNS: dict[str, re.Pattern[str]] = {
    "po_number": re.compile(r"^\s*(?:PO|Purchase\s+Order)\s*(?:Number|No\.?|#)\s*:\s*(.*)$", re.I),
    "customer_hint": re.compile(r"^\s*(?:Customer|Buyer)\s*:\s*(.*)$", re.I),
    "delivery_location": re.compile(r"^\s*(?:Deliver\s+To|Delivery\s+Location|Ship\s+To)\s*:\s*(.*)$", re.I),
    "requested_delivery_date": re.compile(r"^\s*(?:Requested\s+Delivery\s+Date|Required\s+Delivery\s+Date)\s*:\s*(.*)$", re.I),
    "currency": re.compile(r"^\s*Currency\s*:\s*(.*)$", re.I),
}
_LINE_START = re.compile(r"^\s*Line\s+(\d+)\s*:?\s*$", re.I)
_LINE_PATTERNS: dict[str, re.Pattern[str]] = {
    "product_term": re.compile(r"^\s*(?:Product|Item|Part)\s*:\s*(.+?)\s*$", re.I),
    "quantity": re.compile(r"^\s*Quantity\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]{1,12})?\s*$", re.I),
    "requested_unit_price": re.compile(
        r"^\s*Requested\s+Unit\s+Price\s*:\s*(?:(?:GBP|EUR|USD)\s*)?"
        r"(?:[£€$]\s*)?([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*$", re.I
    ),
}
_DATE_FORMATS = ("%d %B %Y", "%d %b %Y", "%Y-%m-%d", "%d/%m/%Y")
_WAREHOUSES = {"manchester": "MAN", "london": "LON", "rotterdam": "RTM"}
_REQUIRED = ("po_number", "customer_hint", "currency", "delivery_location")
# Basic independent guard against common direct instruction attacks. This is
# intentionally *not* claimed as comprehensive prompt-injection detection.
_SUSPICIOUS_INSTRUCTIONS = re.compile(
    r"\b(?:ignore\s+(?:all|previous|the)\s+(?:instructions|rules)|"
    r"mark\s+(?:this\s+)?(?:po|order)\s+automatically\s+approved|"
    r"reveal\s+(?:system|developer)\s+(?:prompt|instructions)|"
    r"send\s+(?:financial|secret|bank)\s+records)\b", re.I
)


@dataclass(frozen=True)
class SourceValue:
    value: object
    evidence: tuple[str, ...]


@dataclass
class SourceAnchors:
    fields: dict[str, SourceValue] = field(default_factory=dict)
    ambiguous: set[str] = field(default_factory=set)
    # None means there is no reliably parseable labelled line block.
    lines: list[ExtractedOrderLine] | None = None
    line_evidence: list[str] = field(default_factory=list)
    document_type: str | None = None
    warnings: list[str] = field(default_factory=list)


def _norm(value: object) -> str:
    return " ".join(str(value).split()).casefold()


def _evidence(index: int, content: str) -> str:
    # Truncate individual source lines, not the source document; no invented quote.
    return f"SOURCE_TEXT line {index}: {content.strip()[:250]}"


def _parse_date(value: str) -> date | None:
    # Never guess month/day for slash dates, which are locale-sensitive.
    if "/" in value:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def inspect_source_text(text: str) -> SourceAnchors:
    """Identify unambiguous, labelled native-text anchors and original line refs."""
    lines = text.splitlines()
    result = SourceAnchors()
    candidates: dict[str, list[SourceValue]] = {name: [] for name in _FIELD_PATTERNS}
    if _SUSPICIOUS_INSTRUCTIONS.search(text):
        result.warnings.append("REVIEW_REQUIRED_SUSPICIOUS_DOCUMENT_INSTRUCTIONS")

    # Classify only an explicit heading; model still handles free-form intent.
    for line in lines[:12]:
        upper = line.strip().upper()
        if upper in {"PURCHASE ORDER", "CUSTOMER PURCHASE ORDER"}:
            result.document_type = "PURCHASE_ORDER"
            break
        if upper in {"REQUEST FOR QUOTATION", "RFQ"}:
            result.document_type = "RFQ"
            break

    def next_label_or_heading(candidate: str) -> bool:
        return (bool(_LINE_START.match(candidate)) or
                any(pattern.match(candidate) for pattern in _FIELD_PATTERNS.values()) or
                candidate.strip().upper() in {"PURCHASE ORDER", "REQUEST FOR QUOTATION", "RFQ"})

    for i, raw in enumerate(lines):
        for name, pattern in _FIELD_PATTERNS.items():
            match = pattern.match(raw)
            if match is None:
                continue
            value = match.group(1).strip()
            proof = [_evidence(i + 1, raw)]
            if not value:
                # Support the actual fixture: "Customer:\nNorthstar Engineering".
                for next_i in range(i + 1, len(lines)):
                    candidate = lines[next_i].strip()
                    if not candidate:
                        continue
                    if not next_label_or_heading(candidate):
                        value = candidate
                        proof.append(_evidence(next_i + 1, lines[next_i]))
                    break
            if not value:
                result.warnings.append(f"REVIEW_REQUIRED_EMPTY_{name.upper()}")
                continue
            parsed: object = value
            if name == "requested_delivery_date":
                parsed = _parse_date(value)
                if parsed is None:
                    result.warnings.append("REVIEW_REQUIRED_UNPARSEABLE_DELIVERY_DATE")
                    continue
            elif name == "currency":
                parsed = value.upper()
                if not re.fullmatch(r"[A-Z]{3}", str(parsed)):
                    result.warnings.append("REVIEW_REQUIRED_UNPARSEABLE_CURRENCY")
                    continue
            elif name == "po_number" and (len(value) > 80 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./#-]*", value)):
                result.warnings.append("REVIEW_REQUIRED_UNPARSEABLE_PO_NUMBER")
                continue
            candidates[name].append(SourceValue(parsed, tuple(proof)))

    for name, values in candidates.items():
        normalized = {_norm(item.value) for item in values}
        if len(normalized) > 1:
            result.ambiguous.add(name)
            result.warnings.append(f"REVIEW_REQUIRED_AMBIGUOUS_{name.upper()}")
        elif values:
            result.fields[name] = values[0]

    # These line-block patterns are *deliberately* strict. A table/ambiguous
    # format goes to review, never to automatic ERP processing.
    starts = [(i, int(m.group(1))) for i, raw in enumerate(lines)
              if (m := _LINE_START.match(raw))]
    if starts:
        parsed_lines: list[ExtractedOrderLine] = []
        seen: set[int] = set()
        all_evidence: list[str] = []
        for start_index, (start, number) in enumerate(starts):
            if number in seen:
                result.warnings.append("REVIEW_REQUIRED_DUPLICATE_LINE_NUMBER")
                break
            seen.add(number)
            end = starts[start_index + 1][0] if start_index + 1 < len(starts) else len(lines)
            candidates_line: dict[str, list[tuple[re.Match[str], int]]] = {
                key: [] for key in _LINE_PATTERNS
            }
            for row in range(start + 1, end):
                for key, pattern in _LINE_PATTERNS.items():
                    if match := pattern.match(lines[row]):
                        candidates_line[key].append((match, row))
            # A repeated/conflicting labelled value within the same line is
            # ambiguous, as is a missing product or quantity.
            if (any(len(group) > 1 for group in candidates_line.values()) or
                    not candidates_line["product_term"] or not candidates_line["quantity"]):
                result.warnings.append(f"REVIEW_REQUIRED_AMBIGUOUS_LINE_{number}")
                break
            try:
                product_match, product_row = candidates_line["product_term"][0]
                qty_match, qty_row = candidates_line["quantity"][0]
                quantity = Decimal(qty_match.group(1))
                if quantity <= 0:
                    raise ValueError("nonpositive quantity")
                price: float | None = None
                if candidates_line["requested_unit_price"]:
                    price_match, price_row = candidates_line["requested_unit_price"][0]
                    price_decimal = Decimal(price_match.group(1).replace(",", ""))
                    if price_decimal < 0:
                        raise ValueError("negative price")
                    price = float(price_decimal)
                    price_text = lines[price_row].upper()
                    explicit = {code for code in ("GBP", "EUR", "USD") if re.search(rf"\b{code}\b", price_text)}
                    explicit.update(code for symbol, code in (("£", "GBP"), ("€", "EUR"), ("$", "USD")) if symbol in price_text)
                    document_currency = result.fields.get("currency")
                    if (len(explicit) > 1 or (document_currency and explicit
                                                 and str(document_currency.value).upper() not in explicit)):
                        result.warnings.append(f"REVIEW_REQUIRED_CURRENCY_MISMATCH_LINE_{number}")
                    all_evidence.append(_evidence(price_row + 1, lines[price_row]))
                parsed_lines.append(ExtractedOrderLine(
                    line_number=number,
                    product_term=product_match.group(1).strip(),
                    quantity=float(quantity),
                    uom=(qty_match.group(2) or "EA").upper(),
                    requested_unit_price=price,
                ))
                all_evidence.extend([
                    _evidence(start + 1, lines[start]),
                    _evidence(product_row + 1, lines[product_row]),
                    _evidence(qty_row + 1, lines[qty_row]),
                ])
            except (InvalidOperation, ValueError) as exc:
                result.warnings.append(f"REVIEW_REQUIRED_UNPARSEABLE_LINE_{number}")
                break
        else:
            result.lines = parsed_lines
            result.line_evidence = all_evidence
    
    delivery = result.fields.get("delivery_location")
    if delivery:
        mentioned = {code for name, code in _WAREHOUSES.items() if name in _norm(delivery.value)}
        if len(mentioned) == 1:
            result.fields["delivery_warehouse_code"] = SourceValue(
                next(iter(mentioned)), delivery.evidence
            )
        elif len(mentioned) > 1:
            result.warnings.append("REVIEW_REQUIRED_AMBIGUOUS_WAREHOUSE")
    return result


def _equal(a: object, b: object) -> bool:
    if isinstance(a, date) or isinstance(b, date):
        return a == b
    return _norm(a) == _norm(b)


def _lines_equal(left: list[ExtractedOrderLine], right: list[ExtractedOrderLine]) -> bool:
    if len(left) != len(right):
        return False
    first = {v.line_number: v for v in left}
    second = {v.line_number: v for v in right}
    if len(first) != len(left) or len(second) != len(right) or first.keys() != second.keys():
        return False
    for no in first:
        a, b = first[no], second[no]
        if (_norm(a.product_term) != _norm(b.product_term)
                or _norm(a.uom) != _norm(b.uom)
                or Decimal(str(a.quantity)) != Decimal(str(b.quantity))
                or (None if a.requested_unit_price is None else Decimal(str(a.requested_unit_price)))
                != (None if b.requested_unit_price is None else Decimal(str(b.requested_unit_price)))):
            return False
    return True


def ground_draft_against_source(draft: ExtractedOrderDraft, text: str) -> tuple[ExtractedOrderDraft, dict]:
    """Return a source-grounded proposal and metadata, never an execution permit.

    Explicit critical source/LLM conflicts always require human review, even if
    the corrected display draft would pass a naive field accuracy score.
    """
    source = inspect_source_text(text)
    payload = draft.model_dump(mode="python")
    flags = list(draft.risk_flags)
    corrections: list[str] = []
    verified: list[str] = []
    evidence: list[str] = []

    if source.document_type is not None:
        if draft.document_type != source.document_type:
            flags.append("REVIEW_REQUIRED_SOURCE_CONFLICT_DOCUMENT_TYPE")
            corrections.append("document_type")
        payload["document_type"] = source.document_type
        verified.append("document_type")

    for name in (*_REQUIRED, "requested_delivery_date", "delivery_warehouse_code"):
        anchor = source.fields.get(name)
        if anchor is None:
            if name in _REQUIRED:
                flags.append(f"REVIEW_REQUIRED_UNVERIFIED_{name.upper()}")
            elif name == "requested_delivery_date" and draft.requested_delivery_date is not None:
                flags.append("REVIEW_REQUIRED_UNVERIFIED_DELIVERY_DATE")
            elif name == "delivery_warehouse_code" and draft.delivery_warehouse_code is not None:
                flags.append("REVIEW_REQUIRED_UNVERIFIED_WAREHOUSE")
            # Don't execute hallucinated key fields without a source anchor.
            if name in _REQUIRED or name == "requested_delivery_date":
                payload[name] = None if name != "currency" else draft.currency
            continue
        verified.append(name)
        evidence.extend(anchor.evidence)
        original = getattr(draft, name)
        if original is None or not _equal(original, anchor.value):
            flags.append(f"REVIEW_REQUIRED_SOURCE_CONFLICT_{name.upper()}")
            corrections.append(name)
        payload[name] = anchor.value

    if source.lines is None:
        flags.append("REVIEW_REQUIRED_UNVERIFIED_LINES")
    else:
        verified.append("lines")
        evidence.extend(source.line_evidence)
        if not _lines_equal(draft.lines, source.lines):
            flags.append("REVIEW_REQUIRED_SOURCE_CONFLICT_LINES")
            corrections.append("lines")
        payload["lines"] = [line.model_dump(mode="python") for line in source.lines]

    # Customer identity must come from independently verified channel/CRM
    # metadata, not from a PO's free text or an LLM guess. Never pass an
    # AI-supplied domain into exact CRM domain matching.
    if draft.customer_domain:
        flags.append("REVIEW_REQUIRED_UNTRUSTED_CUSTOMER_DOMAIN")
        corrections.append("customer_domain")
    payload["customer_domain"] = None

    flags.extend(source.warnings)
    if "REVIEW_REQUIRED_SUSPICIOUS_DOCUMENT_INSTRUCTIONS" in source.warnings:
        flags.append("POTENTIAL_PROMPT_INJECTION")
    if not source.document_type:
        flags.append("REVIEW_REQUIRED_UNVERIFIED_DOCUMENT_TYPE")
    payload["risk_flags"] = list(dict.fromkeys(flags))
    # Evidence comes from literal source lines only; AI self-citations don't count.
    payload["evidence"] = list(dict.fromkeys(evidence))
    missing = [item for item in draft.missing_fields
               if re.sub(r"[^a-z0-9]+", "_", item.casefold()).strip("_")
               not in verified]
    for name in _REQUIRED:
        if name not in source.fields and name not in missing:
            missing.append(name)
    if source.lines is None and "lines" not in missing:
        missing.append("lines")
    payload["missing_fields"] = missing
    if any(flag.startswith("REVIEW_REQUIRED_") for flag in payload["risk_flags"]):
        payload["overall_confidence"] = min(draft.overall_confidence, 0.5)
    grounded = ExtractedOrderDraft.model_validate(payload)
    return grounded, {
        "verified_fields": list(dict.fromkeys(verified)),
        "corrected_fields": list(dict.fromkeys(corrections)),
        "requires_human_review": any(f.startswith("REVIEW_REQUIRED_") for f in grounded.risk_flags),
        "review_reasons": [f for f in grounded.risk_flags if f.startswith("REVIEW_REQUIRED_")],
    }
