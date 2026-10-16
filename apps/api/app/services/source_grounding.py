"""Deterministic source grounding for business-order intake.

The AI output is always a proposal. This module independently anchors critical
fields to source text and structured tables when the source can be parsed
reliably. It is intentionally fail-closed: ambiguity remains a human-review
state, while parser limitations must not create false conflicts for ordinary
business documents.

Supported grounding shapes include:
- labelled key/value text (same-line or next-line values),
- common PO/RFQ header variants,
- ship-to / bill-to / buyer blocks,
- native PDF tables discovered by PyMuPDF,
- spreadsheet / CSV tables supplied by document_intelligence,
- canonical labelled line-item blocks used by fixtures and APIs.

No parser result is an ERP execution permit. Downstream deterministic customer,
product, pricing, inventory, credit and policy validation remains authoritative.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from app.schemas.intake import ExtractedOrderDraft, ExtractedOrderLine


# ---------------------------------------------------------------------------
# Source-field vocabulary
# ---------------------------------------------------------------------------

_FIELD_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "po_number": (
        re.compile(r"(?:^|\s{2,})(?:PO|P\.O\.|Purchase\s+Order)\s*(?:Number|No\.?|#)\s*:?\s*(.*)$", re.I),
        re.compile(r"(?:^|\s{2,})Order\s+(?:Number|No\.?|#)\s*:?\s*(.*)$", re.I),
    ),
    "customer_hint": (
        re.compile(r"(?:^|\s{2,})(?:Customer(?!\s+Ref)(?:\s+Name)?|Buyer(?!\s+Contact)(?:\s+Name)?|Purchaser|Bill\s+To|Sold\s+To)\s*:?\s*(.*)$", re.I),
    ),
    "delivery_location": (
        re.compile(r"(?:^|\s{2,})(?:Deliver\s+To|Delivery\s+Location|Ship\s+To)\s*:?\s*(.*)$", re.I),
    ),
    "requested_delivery_date": (
        re.compile(r"(?:^|\s{2,})(?:Requested\s+Delivery(?:\s+Date)?|Required\s+Delivery(?:\s+Date)?|"
                   r"Delivery\s+Date|Required\s+By|Need\s+By|Requested\s+Ship\s+Date)\s*:?\s*(.*)$", re.I),
    ),
    "currency": (
        re.compile(r"(?:^|\s{2,})(?:Currency|Order\s+Currency)\s*:?\s*(.*)$", re.I),
    ),
}

_BLOCK_LABELS = {
    "ship to": "delivery_location",
    "deliver to": "delivery_location",
    "delivery location": "delivery_location",
    "bill to": "customer_hint",
    "sold to": "customer_hint",
    "buyer": "customer_hint",
    "customer": "customer_hint",
    "purchaser": "customer_hint",
}

_LINE_START = re.compile(r"^\s*Line\s+(\d+)\s*:?\s*$", re.I)
_LINE_PATTERNS: dict[str, re.Pattern[str]] = {
    "product_term": re.compile(r"^\s*(?:Product|Item|Part|SKU|Customer\s+Ref)\s*:?\s*(.+?)\s*$", re.I),
    "quantity": re.compile(r"^\s*(?:Quantity|Qty)\s*:?\s*([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]{1,12})?\s*$", re.I),
    "requested_unit_price": re.compile(
        r"^\s*(?:Requested\s+Unit\s+Price|Unit\s+Price|Price)\s*:?\s*"
        r"(?:(?:GBP|EUR|USD)\s*)?(?:[£€$]\s*)?([0-9][0-9,]*(?:\.[0-9]{1,4})?)\s*$", re.I
    ),
}

_DATE_FORMATS = (
    "%d %B %Y", "%d %b %Y", "%Y-%m-%d", "%d-%m-%Y",
    "%B %d %Y", "%b %d %Y",
)
_WAREHOUSES = {"manchester": "MAN", "london": "LON", "rotterdam": "RTM"}
_REQUIRED = ("po_number", "customer_hint", "currency", "delivery_location")

_SUSPICIOUS_INSTRUCTIONS = re.compile(
    r"\b(?:ignore\s+(?:all|previous|the)\s+(?:instructions|rules)|"
    r"mark\s+(?:this\s+)?(?:po|order)\s+automatically\s+approved|"
    r"reveal\s+(?:system|developer)\s+(?:prompt|instructions)|"
    r"send\s+(?:financial|secret|bank)\s+records|"
    r"bypass\s+(?:approval|policy|security)|"
    r"override\s+(?:system|policy|pricing|credit))\b", re.I
)

_TABLE_HEADER_ALIASES: dict[str, set[str]] = {
    "line_number": {"line", "line no", "line number", "item no", "item number", "#"},
    "product_term": {
        "product", "product ref", "product code", "customer ref", "customer reference",
        "sku", "item", "item code", "part", "part no", "part number", "material", "material code",
    },
    "description": {"description", "item description", "product description", "details"},
    "quantity": {"qty", "quantity", "order qty", "ordered qty", "quantity ordered"},
    "uom": {"uom", "unit", "unit of measure", "units"},
    "requested_unit_price": {"unit price", "price", "requested unit price", "unit cost", "rate"},
    "line_total": {"line total", "total", "amount", "extended price", "ext price"},
}
_TOTAL_WORDS = {"subtotal", "total", "vat", "tax", "freight", "shipping", "grand total"}

_TABLE_FIELD_LABELS = {
    "po number": "po_number", "po no": "po_number", "po #": "po_number",
    "purchase order number": "po_number", "purchase order no": "po_number",
    "customer": "customer_hint", "customer name": "customer_hint",
    "buyer": "customer_hint", "buyer name": "customer_hint",
    "bill to": "customer_hint", "sold to": "customer_hint",
    "ship to": "delivery_location", "deliver to": "delivery_location",
    "delivery location": "delivery_location",
    "requested delivery": "requested_delivery_date",
    "requested delivery date": "requested_delivery_date",
    "required delivery": "requested_delivery_date",
    "required delivery date": "requested_delivery_date",
    "delivery date": "requested_delivery_date", "required by": "requested_delivery_date",
    "need by": "requested_delivery_date",
    "currency": "currency", "order currency": "currency",
}
_CURRENCY_SYMBOLS = {"£": "GBP", "€": "EUR", "$": "USD"}


@dataclass(frozen=True)
class SourceValue:
    value: object
    evidence: tuple[str, ...]


@dataclass
class SourceAnchors:
    fields: dict[str, SourceValue] = field(default_factory=dict)
    ambiguous: set[str] = field(default_factory=set)
    lines: list[ExtractedOrderLine] | None = None
    line_evidence: list[str] = field(default_factory=list)
    document_type: str | None = None
    warnings: list[str] = field(default_factory=list)


def _norm(value: object) -> str:
    return " ".join(str(value).split()).casefold()


def _tokens(value: object) -> set[str]:
    return {item for item in re.findall(r"[a-z0-9]+", str(value).casefold()) if len(item) > 1}


def _evidence(index: int, content: str) -> str:
    return f"SOURCE_TEXT line {index}: {content.strip()[:250]}"


def _table_evidence(source: str, row_number: int, row: list[str]) -> str:
    text = " | ".join(cell.strip() for cell in row if str(cell).strip())
    return f"SOURCE_TABLE {source} row {row_number}: {text[:350]}"


def _parse_date(value: str) -> date | None:
    value = value.strip().rstrip(".,")
    # Slash-only dates are locale-sensitive. Do not guess them.
    if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{2,4}", value):
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _parse_decimal(value: object) -> Decimal | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = re.sub(r"\b(?:GBP|EUR|USD)\b", "", text, flags=re.I)
    text = text.replace("£", "").replace("€", "").replace("$", "")
    text = text.replace(",", "").strip()
    # Allow accounting negatives but reject them later as invalid order values.
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _clean_header(value: object) -> str:
    return re.sub(r"[^a-z0-9#]+", " ", str(value or "").casefold()).strip()


def _canonical_header(value: object) -> str | None:
    cleaned = _clean_header(value)
    for canonical, aliases in _TABLE_HEADER_ALIASES.items():
        if cleaned in aliases:
            return canonical
    return None


def _rows_from_table(table: Any) -> tuple[str, list[list[str]]]:
    source = str(getattr(table, "source", None) or (table.get("source") if isinstance(table, dict) else None) or "table")
    rows_obj = getattr(table, "rows", None)
    if rows_obj is None and isinstance(table, dict):
        rows_obj = table.get("rows")
    rows: list[list[str]] = []
    for row in rows_obj or []:
        rows.append(["" if cell is None else str(cell).strip() for cell in row])
    return source, rows


def _detect_document_type(lines: list[str]) -> str | None:
    sample = "\n".join(lines[:30]).upper()
    if re.search(r"\bPURCHASE\s+ORDER\b", sample) or re.search(r"\bCUSTOMER\s+PO\b", sample):
        return "PURCHASE_ORDER"
    if re.search(r"\bREQUEST\s+FOR\s+QUOTATION\b", sample) or re.search(r"(?:^|\W)RFQ(?:\W|$)", sample):
        return "RFQ"
    return None


def _is_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    key = _clean_header(stripped)
    if key in _BLOCK_LABELS:
        return True
    if any(pattern.match(stripped) for patterns in _FIELD_PATTERNS.values() for pattern in patterns):
        return True
    if _LINE_START.match(stripped):
        return True
    if stripped.upper() in {
        "PURCHASE ORDER", "CUSTOMER PURCHASE ORDER", "REQUEST FOR QUOTATION", "RFQ",
        "SUPPLIER & DELIVERY DETAILS", "ORDER LINES", "PURCHASE INSTRUCTIONS",
        "COMMERCIAL TERMS", "BUYER CONTACT", "AUTHORIZED BY", "PURCHASE ORDER STATUS",
    }:
        return True
    # Short multi-word all-uppercase section heading. Single-token values such
    # as GBP, EA or SKU codes are data, not headings.
    return (len(stripped) <= 80 and stripped == stripped.upper()
            and any(c.isalpha() for c in stripped) and len(stripped.split()) >= 2)


def _collect_block(lines: list[str], start: int, *, max_lines: int = 5) -> tuple[str, tuple[str, ...]]:
    values: list[str] = []
    proof: list[str] = [_evidence(start + 1, lines[start])]
    for idx in range(start + 1, min(len(lines), start + 1 + max_lines)):
        raw = lines[idx].strip()
        if not raw:
            if values:
                break
            continue
        if values and _is_heading(raw):
            break
        if not values and _is_heading(raw):
            break
        values.append(raw)
        proof.append(_evidence(idx + 1, lines[idx]))
    return " ".join(values).strip(), tuple(proof)


def _infer_issuer(lines: list[str]) -> SourceValue | None:
    """Infer the purchaser from a prominent company heading immediately around PO title.

    This is used only as a customer *hint*, never as authoritative customer identity.
    """
    po_idx = next((i for i, line in enumerate(lines[:20]) if re.search(r"\bPURCHASE\s+ORDER\b", line, re.I)), None)
    if po_idx is None:
        return None
    # Common letterhead layout: "BUYER COMPANY        PURCHASE ORDER" on one line.
    same_line = re.split(r"\bPURCHASE\s+ORDER\b", lines[po_idx], maxsplit=1, flags=re.I)[0].strip()
    if (same_line and 3 <= len(same_line) <= 100 and re.search(r"[A-Za-z]", same_line)
            and not re.fullmatch(r"[A-Z]{1,3}\d+=?", same_line, re.I)):
        return SourceValue(same_line, (_evidence(po_idx + 1, lines[po_idx]),))
    candidates: list[tuple[int, str]] = []
    for idx in range(max(0, po_idx - 3), min(len(lines), po_idx + 2)):
        text = lines[idx].strip()
        if not text or idx == po_idx:
            continue
        if text.startswith("---") and text.endswith("---"):
            continue
        if re.match(r"^[A-Z]{1,3}\d+=", text, re.I):
            continue
        if re.search(r"\b(?:PURCHASE\s+ORDER|PO\s+(?:NUMBER|NO))\b", text, re.I):
            continue
        # Company-like heading: letters, moderate length, not an address/metadata row.
        if 3 <= len(text) <= 100 and re.search(r"[A-Za-z]", text) and not re.search(
            r"\b(?:ROAD|STREET|AVENUE|VAT|COMPANY\s+NO|PHONE|EMAIL|DATE|CURRENCY)\b", text, re.I
        ):
            candidates.append((idx, text))
    if not candidates:
        return None
    idx, text = candidates[0]
    return SourceValue(text, (_evidence(idx + 1, lines[idx]),))


def _parse_structured_tables(tables: Iterable[Any] | None, result: SourceAnchors) -> tuple[list[ExtractedOrderLine] | None, list[str]]:
    """Parse common order-line tables without depending on one vendor's layout."""
    if not tables:
        return None, []
    best: tuple[int, list[ExtractedOrderLine], list[str]] | None = None
    currencies: set[str] = set()

    for table in tables:
        source, rows = _rows_from_table(table)
        if not rows:
            continue
        # Find a header row anywhere in the first 12 non-empty rows. Real spreadsheets
        # often have title/address rows before the actual order table.
        for header_index, header_row in enumerate(rows[:12]):
            mapping: dict[str, int] = {}
            for col, cell in enumerate(header_row):
                canonical = _canonical_header(cell)
                if canonical and canonical not in mapping:
                    mapping[canonical] = col
            if "quantity" not in mapping or not ({"product_term", "description"} & mapping.keys()):
                continue

            parsed: list[ExtractedOrderLine] = []
            evidence: list[str] = []
            seen_numbers: set[int] = set()
            auto_number = 1
            for row_index in range(header_index + 1, len(rows)):
                row = rows[row_index]
                if not any(cell.strip() for cell in row):
                    if parsed:
                        break
                    continue
                first_text = _clean_header(next((cell for cell in row if cell.strip()), ""))
                if any(first_text.startswith(word) for word in _TOTAL_WORDS):
                    break

                def cell_for(name: str) -> str:
                    col = mapping.get(name)
                    return row[col].strip() if col is not None and col < len(row) else ""

                product = cell_for("product_term") or cell_for("description")
                qty_raw = cell_for("quantity")
                if not product and not qty_raw:
                    if parsed:
                        continue
                    continue
                qty = _parse_decimal(qty_raw)
                if not product or qty is None or qty <= 0:
                    # A malformed row inside an otherwise recognized order table is
                    # significant: do not silently skip it.
                    result.warnings.append("REVIEW_REQUIRED_UNPARSEABLE_TABLE_LINE")
                    parsed = []
                    break

                line_raw = cell_for("line_number")
                try:
                    line_no = int(Decimal(line_raw)) if line_raw else auto_number
                except (InvalidOperation, ValueError):
                    result.warnings.append("REVIEW_REQUIRED_UNPARSEABLE_LINE_NUMBER")
                    parsed = []
                    break
                if line_no <= 0 or line_no in seen_numbers:
                    result.warnings.append("REVIEW_REQUIRED_DUPLICATE_LINE_NUMBER")
                    parsed = []
                    break
                seen_numbers.add(line_no)
                auto_number = max(auto_number + 1, line_no + 1)

                uom = cell_for("uom").upper()
                if not uom:
                    # Quantity strings sometimes embed UOM: "40 EA".
                    m = re.fullmatch(r"\s*[0-9]+(?:\.[0-9]+)?\s+([A-Za-z]{1,12})\s*", qty_raw)
                    uom = (m.group(1) if m else "EA").upper()

                price_raw = cell_for("requested_unit_price")
                price_dec = _parse_decimal(price_raw) if price_raw else None
                if price_dec is not None and price_dec < 0:
                    result.warnings.append(f"REVIEW_REQUIRED_UNPARSEABLE_LINE_{line_no}")
                    parsed = []
                    break
                for symbol, code in _CURRENCY_SYMBOLS.items():
                    if symbol in price_raw:
                        currencies.add(code)
                explicit = {code for code in ("GBP", "EUR", "USD") if re.search(rf"\b{code}\b", price_raw, re.I)}
                currencies.update(explicit)

                parsed.append(ExtractedOrderLine(
                    line_number=line_no,
                    product_term=product,
                    quantity=float(qty),
                    uom=uom,
                    requested_unit_price=float(price_dec) if price_dec is not None else None,
                ))
                evidence.append(_table_evidence(source, row_index + 1, row))

            if parsed:
                score = len(parsed) * 10 + len(mapping)
                if best is None or score > best[0]:
                    best = (score, parsed, evidence)
                break

    if len(currencies) == 1 and "currency" not in result.fields:
        result.fields["currency"] = SourceValue(next(iter(currencies)), tuple())
    elif len(currencies) > 1:
        result.warnings.append("REVIEW_REQUIRED_AMBIGUOUS_CURRENCY")
    if best:
        return best[1], best[2]
    return None, []


def _source_field_candidates_from_tables(
    tables: Iterable[Any] | None,
    candidates: dict[str, list[SourceValue]],
) -> None:
    """Recover key/value blocks and metadata cells from structured tables."""
    for table in tables or []:
        source, rows = _rows_from_table(table)
        for row_no, row in enumerate(rows, start=1):
            ev = (_table_evidence(source, row_no, row),)

            # Common spreadsheet form: ["PO Number", "PO-123", "Currency", "GBP"].
            for idx, cell in enumerate(row):
                label = _clean_header(cell)
                target = _TABLE_FIELD_LABELS.get(label)
                if not target or idx + 1 >= len(row):
                    continue
                raw_value = row[idx + 1].strip()
                if not raw_value:
                    continue
                parsed: object = raw_value
                if target == "requested_delivery_date":
                    parsed = _parse_date(raw_value)
                    if parsed is None:
                        continue
                elif target == "currency":
                    m = re.search(r"\b([A-Z]{3})\b", raw_value.upper())
                    if not m:
                        continue
                    parsed = m.group(1)
                elif target == "po_number":
                    token = raw_value.split()[0].strip().rstrip(",;")
                    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./#-]*", token):
                        continue
                    parsed = token
                candidates[target].append(SourceValue(parsed, ev))

            # PDF block table cells often preserve embedded newlines.
            for cell in row:
                parts = [part.strip() for part in str(cell).splitlines() if part.strip()]
                if not parts:
                    continue
                label = _clean_header(parts[0])
                target = _BLOCK_LABELS.get(label)
                if target and len(parts) > 1:
                    value = " ".join(parts[1:])
                    if target == "delivery_location":
                        candidates[target].append(SourceValue(value, ev))
                        first = parts[1]
                        if (not re.search(r"\d", first) and "," not in first
                                and not any(city in _norm(first) for city in _WAREHOUSES)):
                            candidates["customer_hint"].append(SourceValue(first, ev))
                    elif target == "customer_hint":
                        candidates[target].append(SourceValue(parts[1], ev))


def inspect_source_text(text: str, *, tables: Iterable[Any] | None = None) -> SourceAnchors:
    """Identify source-backed order facts from native text and structured tables."""
    lines = text.splitlines()
    result = SourceAnchors()
    candidates: dict[str, list[SourceValue]] = {name: [] for name in _FIELD_PATTERNS}

    if _SUSPICIOUS_INSTRUCTIONS.search(text):
        result.warnings.append("REVIEW_REQUIRED_SUSPICIOUS_DOCUMENT_INSTRUCTIONS")
    result.document_type = _detect_document_type(lines)

    # Explicit labels, same-line or next-line.
    for i, raw in enumerate(lines):
        for name, patterns in _FIELD_PATTERNS.items():
            match = next((p.search(raw) for p in patterns if p.search(raw)), None)
            if match is None:
                continue
            value = match.group(1).strip()
            proof = [_evidence(i + 1, raw)]
            if not value:
                # When a label is discovered in the right-hand column of flattened
                # PDF text (for example "Supplier     Ship To"), following lines
                # are interleaved and cannot be safely treated as one block. Native
                # table extraction handles that shape instead.
                if raw[:match.start()].strip():
                    continue
                block, block_proof = _collect_block(lines, i, max_lines=5 if name == "delivery_location" else 2)
                value = block
                proof = list(block_proof)
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
                # Tolerate "GBP - Pound Sterling" while remaining explicit.
                code = re.search(r"\b([A-Z]{3})\b", value.upper())
                if code is None:
                    result.warnings.append("REVIEW_REQUIRED_UNPARSEABLE_CURRENCY")
                    continue
                parsed = code.group(1)
            elif name == "po_number":
                token = value.split()[0].strip().rstrip(",;")
                if len(token) > 80 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./#-]*", token):
                    result.warnings.append("REVIEW_REQUIRED_UNPARSEABLE_PO_NUMBER")
                    continue
                parsed = token
            candidates[name].append(SourceValue(parsed, tuple(proof)))

    # Explicit block labels without colons, e.g. "Ship To" on one line.
    for i, raw in enumerate(lines):
        key = _clean_header(raw)
        target = _BLOCK_LABELS.get(key)
        if not target:
            continue
        block, proof = _collect_block(lines, i, max_lines=5)
        if not block:
            continue
        if target == "delivery_location":
            candidates[target].append(SourceValue(block, proof))
            # First line of a ship-to block is often the buyer/customer organization.
            first = next((ln.strip() for ln in block.split("  ") if ln.strip()), None)
            # _collect_block joins with single spaces, so recover first source line from proof by using text.
            first_line = ""
            for idx in range(i + 1, min(len(lines), i + 6)):
                if lines[idx].strip():
                    first_line = lines[idx].strip()
                    break
            if (first_line and not re.search(r"\d", first_line)
                    and "," not in first_line
                    and not any(city in _norm(first_line) for city in _WAREHOUSES)):
                candidates["customer_hint"].append(SourceValue(first_line, proof[:2]))
        elif target == "customer_hint":
            first_line = ""
            for idx in range(i + 1, min(len(lines), i + 4)):
                if lines[idx].strip():
                    first_line = lines[idx].strip()
                    break
            candidates[target].append(SourceValue(first_line or block, proof))

    _source_field_candidates_from_tables(tables, candidates)

    # If the PO has no explicit Buyer/Customer field, a prominent issuer heading
    # is a useful source-backed customer hint. It is still only a hint; CRM/ERP
    # resolution remains authoritative later.
    if result.document_type == "PURCHASE_ORDER":
        issuer = _infer_issuer(lines)
        if issuer:
            candidates["customer_hint"].append(issuer)

    # Resolve candidates conservatively. For customer/location, allow multiple
    # candidates when one is clearly a more specific rendering of the same entity.
    for name, values in candidates.items():
        if not values:
            continue
        unique: list[SourceValue] = []
        for item in values:
            if not any(_field_equal(name, item.value, prior.value) for prior in unique):
                unique.append(item)
        if len(unique) > 1:
            result.ambiguous.add(name)
            result.warnings.append(f"REVIEW_REQUIRED_AMBIGUOUS_{name.upper()}")
        else:
            # Prefer the most detailed value for location; shortest company-like
            # value for customer hints to avoid storing full addresses as names.
            if name == "delivery_location":
                chosen = max(values, key=lambda v: len(str(v.value)))
            elif name == "customer_hint":
                chosen = min(values, key=lambda v: len(str(v.value)))
            else:
                chosen = values[0]
            result.fields[name] = chosen

    # Structured tables are the preferred independent anchor for line items.
    table_lines, table_evidence = _parse_structured_tables(tables, result)
    if table_lines is not None:
        result.lines = table_lines
        result.line_evidence = table_evidence

    # Fallback: canonical labelled line blocks for text/email payloads.
    if result.lines is None:
        starts = [(i, int(m.group(1))) for i, raw in enumerate(lines) if (m := _LINE_START.match(raw))]
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
                line_groups: dict[str, list[tuple[re.Match[str], int]]] = {key: [] for key in _LINE_PATTERNS}
                for row in range(start + 1, end):
                    for key, pattern in _LINE_PATTERNS.items():
                        if match := pattern.match(lines[row]):
                            line_groups[key].append((match, row))
                if (any(len(group) > 1 for group in line_groups.values())
                        or not line_groups["product_term"] or not line_groups["quantity"]):
                    result.warnings.append(f"REVIEW_REQUIRED_AMBIGUOUS_LINE_{number}")
                    break
                try:
                    product_match, product_row = line_groups["product_term"][0]
                    qty_match, qty_row = line_groups["quantity"][0]
                    quantity = Decimal(qty_match.group(1))
                    if quantity <= 0:
                        raise ValueError("nonpositive quantity")
                    price: float | None = None
                    if line_groups["requested_unit_price"]:
                        price_match, price_row = line_groups["requested_unit_price"][0]
                        price_decimal = Decimal(price_match.group(1).replace(",", ""))
                        if price_decimal < 0:
                            raise ValueError("negative price")
                        price = float(price_decimal)
                        price_text = lines[price_row].upper()
                        explicit = {code for code in ("GBP", "EUR", "USD") if re.search(rf"\b{code}\b", price_text)}
                        explicit.update(code for symbol, code in _CURRENCY_SYMBOLS.items() if symbol in price_text)
                        document_currency = result.fields.get("currency")
                        if len(explicit) > 1 or (document_currency and explicit and str(document_currency.value).upper() not in explicit):
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
                except (InvalidOperation, ValueError):
                    result.warnings.append(f"REVIEW_REQUIRED_UNPARSEABLE_LINE_{number}")
                    break
            else:
                result.lines = parsed_lines
                result.line_evidence = all_evidence

    # Infer currency from explicit source symbols if no currency label existed.
    if "currency" not in result.fields and result.lines:
        symbols = {code for symbol, code in _CURRENCY_SYMBOLS.items() if symbol in text}
        if len(symbols) == 1:
            result.fields["currency"] = SourceValue(next(iter(symbols)), tuple())

    delivery = result.fields.get("delivery_location")
    if delivery:
        mentioned = {code for name, code in _WAREHOUSES.items() if name in _norm(delivery.value)}
        if len(mentioned) == 1:
            result.fields["delivery_warehouse_code"] = SourceValue(next(iter(mentioned)), delivery.evidence)
        elif len(mentioned) > 1:
            result.warnings.append("REVIEW_REQUIRED_AMBIGUOUS_WAREHOUSE")
    return result


def _field_equal(name: str, a: object, b: object) -> bool:
    if isinstance(a, date) or isinstance(b, date):
        return a == b
    left, right = _norm(a), _norm(b)
    if left == right:
        return True
    if name == "customer_hint":
        # "Northstar Engineering Ltd" vs "Northstar Engineering Ltd - Central Stores".
        return (len(left) >= 5 and left in right) or (len(right) >= 5 and right in left)
    if name == "delivery_location":
        lt, rt = _tokens(a), _tokens(b)
        # A concise model location can match a full ship-to address when all of
        # its meaningful tokens are present in the source address.
        return bool(lt and rt) and (lt <= rt or rt <= lt)
    return False


def _equal(a: object, b: object) -> bool:
    return _field_equal("", a, b)


def _lines_equal(left: list[ExtractedOrderLine], right: list[ExtractedOrderLine]) -> bool:
    if len(left) != len(right):
        return False
    first = {v.line_number: v for v in left}
    second = {v.line_number: v for v in right}
    if len(first) != len(left) or len(second) != len(right) or first.keys() != second.keys():
        return False
    for no in first:
        a, b = first[no], second[no]
        product_equal = _norm(a.product_term) == _norm(b.product_term)
        if not product_equal:
            la, lb = _norm(a.product_term), _norm(b.product_term)
            product_equal = (len(la) >= 3 and la in lb) or (len(lb) >= 3 and lb in la)
        if (not product_equal
                or _norm(a.uom) != _norm(b.uom)
                or Decimal(str(a.quantity)) != Decimal(str(b.quantity))
                or (None if a.requested_unit_price is None else Decimal(str(a.requested_unit_price)))
                != (None if b.requested_unit_price is None else Decimal(str(b.requested_unit_price)))):
            return False
    return True


def ground_draft_against_source(
    draft: ExtractedOrderDraft,
    text: str,
    *,
    tables: Iterable[Any] | None = None,
) -> tuple[ExtractedOrderDraft, dict]:
    """Return a source-grounded proposal and review metadata.

    A deterministic source correction is not automatically a failure. If the
    original document clearly establishes a field, we correct the AI proposal,
    record that correction, and continue. Human review is reserved for fields
    that remain unverified/ambiguous, suspicious content, or unsafe conflicts.
    """
    source = inspect_source_text(text, tables=tables)
    payload = draft.model_dump(mode="python")
    flags = list(draft.risk_flags)
    corrections: list[str] = []
    verified: list[str] = []
    evidence: list[str] = []
    blocking: list[str] = []

    if source.document_type is not None:
        if draft.document_type != source.document_type:
            corrections.append("document_type")
            flags.append("SOURCE_CORRECTED_DOCUMENT_TYPE")
        payload["document_type"] = source.document_type
        verified.append("document_type")

    for name in (*_REQUIRED, "requested_delivery_date", "delivery_warehouse_code"):
        anchor = source.fields.get(name)
        if anchor is None:
            if name in _REQUIRED:
                reason = f"REVIEW_REQUIRED_UNVERIFIED_{name.upper()}"
                flags.append(reason); blocking.append(reason)
            elif name == "requested_delivery_date" and draft.requested_delivery_date is not None:
                reason = "REVIEW_REQUIRED_UNVERIFIED_DELIVERY_DATE"
                flags.append(reason); blocking.append(reason)
            elif name == "delivery_warehouse_code" and draft.delivery_warehouse_code is not None:
                reason = "REVIEW_REQUIRED_UNVERIFIED_WAREHOUSE"
                flags.append(reason); blocking.append(reason)
            if name in _REQUIRED or name == "requested_delivery_date":
                payload[name] = None if name != "currency" else draft.currency
            continue

        verified.append(name)
        evidence.extend(anchor.evidence)
        original = getattr(draft, name)
        if original is None or not _field_equal(name, original, anchor.value):
            # The source is authoritative for extraction facts. Correct the model
            # rather than forcing review solely because a small model mis-copied a
            # field. The correction remains auditable.
            corrections.append(name)
            flags.append(f"SOURCE_CORRECTED_{name.upper()}")
        elif _norm(original) != _norm(anchor.value):
            # Semantically equivalent but less precise model wording, e.g. a city
            # instead of the full source ship-to address. Preserve the richer source.
            corrections.append(name)
            flags.append(f"SOURCE_NORMALIZED_{name.upper()}")
        payload[name] = anchor.value

    if source.lines is None:
        reason = "REVIEW_REQUIRED_UNVERIFIED_LINES"
        flags.append(reason); blocking.append(reason)
    else:
        verified.append("lines")
        evidence.extend(source.line_evidence)
        if not _lines_equal(draft.lines, source.lines):
            corrections.append("lines")
            flags.append("SOURCE_CORRECTED_LINES")
        payload["lines"] = [line.model_dump(mode="python") for line in source.lines]

    # File content cannot establish a trusted CRM domain identity. Discard it,
    # but do not block an otherwise fully source-grounded order because this
    # optional AI field is never used as authority.
    if draft.customer_domain:
        flags.append("SECURITY_IGNORED_UNTRUSTED_CUSTOMER_DOMAIN")
        corrections.append("customer_domain")
    payload["customer_domain"] = None

    for warning in source.warnings:
        flags.append(warning)
        if warning.startswith("REVIEW_REQUIRED_"):
            blocking.append(warning)
    if "REVIEW_REQUIRED_SUSPICIOUS_DOCUMENT_INSTRUCTIONS" in source.warnings:
        flags.append("POTENTIAL_PROMPT_INJECTION")
    if not source.document_type:
        reason = "REVIEW_REQUIRED_UNVERIFIED_DOCUMENT_TYPE"
        flags.append(reason); blocking.append(reason)

    payload["risk_flags"] = list(dict.fromkeys(flags))
    payload["evidence"] = list(dict.fromkeys(evidence))

    missing = [
        item for item in draft.missing_fields
        if re.sub(r"[^a-z0-9]+", "_", item.casefold()).strip("_") not in verified
    ]
    for name in _REQUIRED:
        if name not in source.fields and name not in missing:
            missing.append(name)
    if source.lines is None and "lines" not in missing:
        missing.append("lines")
    payload["missing_fields"] = missing

    # Source verification, not model self-confidence, is what allows the draft
    # to proceed. Keep confidence conservative when blocking uncertainty remains.
    if blocking:
        payload["overall_confidence"] = min(draft.overall_confidence, 0.5)
    elif all(name in verified for name in (*_REQUIRED, "lines")):
        payload["overall_confidence"] = max(draft.overall_confidence, 0.90)

    grounded = ExtractedOrderDraft.model_validate(payload)
    review_reasons = list(dict.fromkeys(blocking))
    return grounded, {
        "verified_fields": list(dict.fromkeys(verified)),
        "corrected_fields": list(dict.fromkeys(corrections)),
        "requires_human_review": bool(review_reasons),
        "review_reasons": review_reasons,
        "source_warning_count": len(source.warnings),
        "source_table_grounding": source.lines is not None and bool(source.line_evidence),
    }
