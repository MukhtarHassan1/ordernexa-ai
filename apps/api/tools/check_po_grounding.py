"""Read-only PO-88192 safety check. No MinIO/DB/Odoo writes.

Run in API container:
    python tools/check_po_grounding.py --offline
    python tools/check_po_grounding.py --live

A source-corrected draft can pass 10/10 while the underlying model is wrong.
Only a raw-vs-grounded comparison tells us what inference learned, and
corrected/conflicting fields *must* go to human review.
"""

import argparse
import json
import asyncio
import time
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.intake import ExtractedOrderDraft
from app.services.document_intelligence import extract_document, extract_order_draft
from app.services.source_grounding import ground_draft_against_source

SAMPLE = Path('/sample-data/purchase-orders/po-88192-upload.txt')
if not SAMPLE.exists():
    SAMPLE = Path(__file__).resolve().parents[3] / 'sample-data/purchase-orders/po-88192-upload.txt'


def checks(d):
    by_line = {item.line_number: item for item in d.lines}
    return {
        'Document type': d.document_type == 'PURCHASE_ORDER',
        'PO number': d.po_number == 'PO-88192',
        'Customer': d.customer_hint == 'Northstar Engineering Ltd',
        'Currency': d.currency == 'GBP',
        'Delivery date': d.requested_delivery_date == date(2026, 9, 30),
        'Warehouse': d.delivery_warehouse_code == 'MAN',
        'Number of lines': len(d.lines) == 2,
        'First product/quantity/price': 1 in by_line and
            by_line[1].product_term == 'XTR-42' and
            by_line[1].quantity == 40 and
            by_line[1].requested_unit_price == 260,
        'Second product/quantity/price': 2 in by_line and
            by_line[2].product_term == 'BRK-90' and
            by_line[2].quantity == 15 and
            by_line[2].requested_unit_price == 165,
        'Source evidence': bool(d.evidence),
    }


def report(raw, grounded, grounding, original_confidence=None):
    print('\nRAW MODEL RESULT (not corrected)', flush=True)
    raw_checks = checks(raw)
    for name, ok in raw_checks.items():
        print(f'  {name}: {"PASS" if ok else "FAIL"}')
    print(f'Raw checks: {sum(raw_checks.values())}/{len(raw_checks)}', flush=True)

    print('\nSOURCE-GROUNDED PIPELINE RESULT', flush=True)
    final_checks = checks(grounded)
    for name, ok in final_checks.items():
        print(f'  {name}: {"PASS" if ok else "FAIL"}')
    print(f'Grounded checks: {sum(final_checks.values())}/{len(final_checks)}')
    print('Corrected fields:', grounding.get('corrected_fields', []))
    print('Source-verified fields:', grounding.get('verified_fields', []))
    print('Risk flags:', grounded.risk_flags)
    print('Requires human review:', grounding['requires_human_review'])
    print('Model-reported confidence (untrusted, original):', repr(original_confidence))
    print('Schema-normalized confidence (also untrusted):', raw.overall_confidence)
    print('Grounded confidence after flags:', grounded.overall_confidence)
    if grounding['requires_human_review']:
        print('DECISION: HUMAN REVIEW REQUIRED. No order/ERP write authorized.')
    elif all(final_checks.values()):
        print('DECISION: SOURCE-GROUNDED SAMPLE PASSES. Broader evaluation still required.')
    else:
        print('DECISION: DO NOT AUTO-PROCESS. Investigate failed fields.')
    return all(final_checks.values())


async def main(live: bool) -> int:
    doc = extract_document(filename=SAMPLE.name, data=SAMPLE.read_bytes())
    if not live:
        raw = ExtractedOrderDraft.model_validate({
            'document_type':'PURCHASE_ORDER',
            'po_number':None,
            'customer_hint':'Northstar',
            'currency':'GBP',
            'delivery_location':'Manchester, United Kingdom',
            'delivery_warehouse_code':'MAN',
            'requested_delivery_date':'3099-09-20',
            'lines':[
                {'line_number':1, 'product_term':'XTR-42', 'quantity':40,
                 'uom':'EA','requested_unit_price':260},
                {'line_number':2, 'product_term':'BRK-90', 'quantity':15,
                 'uom':'EA','requested_unit_price':165},
            ], 'overall_confidence':1.0,
        })
        grounded, grounding = ground_draft_against_source(raw, doc.text)
        original_confidence = raw.overall_confidence
        print('OFFLINE REGRESSION (deliberately wrong model output; NO Ollama request)')
    else:
        print('LIVE MODEL TEST (NO DB, MINIO, OR ERP WRITES)', flush=True)
        start = time.monotonic()
        result = await extract_order_draft(doc)
        original_confidence = json.loads(result.raw_content).get('overall_confidence')
        raw = ExtractedOrderDraft.model_validate_json(result.raw_content)
        grounded = result.data
        grounding = result.usage.get('source_grounding', {})
        print('Model:', result.model)
        print('Inference seconds:', round(time.monotonic()-start, 2), flush=True)
    ok = report(raw, grounded, grounding, original_confidence)
    return 0 if ok else 1


if __name__ == '__main__':
    args = argparse.ArgumentParser()
    group = args.add_mutually_exclusive_group(required=True)
    group.add_argument('--offline', action='store_true')
    group.add_argument('--live', action='store_true')
    parsed = args.parse_args()
    raise SystemExit(asyncio.run(main(parsed.live)))
